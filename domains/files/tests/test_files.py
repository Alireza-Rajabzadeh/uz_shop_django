import hashlib

from django.contrib.auth import get_user_model
from django.core.files.storage import InMemoryStorage, storages
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from rest_framework.test import APITestCase

from domains.files.models import File, FileStatus
from domains.files.services import FileService
from domains.payments.models import PaymentChannel


IN_MEMORY_STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
    "secondary": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
    },
}

FAILING_STORAGES = {
    **IN_MEMORY_STORAGES,
    "default": {"BACKEND": "domains.files.tests.test_files.FailingStorage"},
}


class FailingStorage(InMemoryStorage):
    def _save(self, name, content):
        super()._save(name, content)
        raise OSError("storage unavailable")


@override_settings(
    STORAGES=IN_MEMORY_STORAGES,
    FILE_STORAGE_ALIASES=["default", "secondary"],
)
class FileServiceTests(TestCase):
    def setUp(self):
        self.service = FileService()

    def upload(self, content=b"file contents", name="photo.JPG", content_type="image/jpeg"):
        return self.service.upload(
            SimpleUploadedFile(name, content, content_type=content_type),
            metadata={"alt": "Example"},
        )

    def test_upload_hashes_classifies_and_stores_under_file_uuid(self):
        file = self.upload()

        self.assertEqual(file.status.name, "available")
        self.assertEqual(file.file_type, "image")
        self.assertEqual(file.extension, "jpg")
        self.assertEqual(file.size, len(b"file contents"))
        self.assertEqual(file.checksum, hashlib.sha256(b"file contents").hexdigest())
        self.assertEqual(file.object_key, f"files/{file.id}.jpg")
        self.assertTrue(self.service.exists(file))
        self.assertTrue(self.service.url(file))

    def test_verify_marks_corrupt_object_failed_then_valid_object_available(self):
        file = self.upload()
        storage = storages["default"]
        storage.delete(file.object_key)
        storage.save(file.object_key, SimpleUploadedFile("bad", b"wrong"))

        self.service.verify(file)
        self.assertEqual(file.status.name, "failed")

        storage.delete(file.object_key)
        storage.save(file.object_key, SimpleUploadedFile("good", b"file contents"))
        self.service.verify(file)
        self.assertEqual(file.status.name, "available")

    def test_delete_removes_object_and_retains_deleted_record(self):
        file = self.upload()

        self.service.delete(file)

        file.refresh_from_db()
        self.assertEqual(file.status.name, "deleted")
        self.assertIsNotNone(file.deleted_at)
        self.assertFalse(storages["default"].exists(file.object_key))

    def test_orphans_returns_only_unreferenced_available_files_without_catalog_dependency(self):
        available = self.upload(name="available.txt", content_type="text/plain")
        failed = self.upload(name="failed.txt", content_type="text/plain")
        failed.status = FileStatus.objects.get(name="failed")
        failed.save(update_fields=["status"])

        self.assertEqual(list(self.service.orphans()), [available])

    def test_payment_channel_logo_is_not_an_orphan(self):
        logo = self.upload()
        PaymentChannel.objects.create(
            code="file-test-channel",
            name="File test channel",
            logo_file=logo,
        )

        self.assertNotIn(logo, self.service.orphans())

    def test_delete_detaches_payment_channel_logo(self):
        logo = self.upload()
        channel = PaymentChannel.objects.create(
            code="deleted-logo-channel",
            name="Deleted logo channel",
            logo_file=logo,
        )

        self.service.delete(logo)

        channel.refresh_from_db()
        self.assertIsNone(channel.logo_file)

    def test_migrate_to_alias_copies_verifies_switches_and_removes_source(self):
        file = self.upload()
        old_key = file.object_key

        self.service.migrate_to_alias(file, "secondary")

        self.assertEqual(file.storage_alias, "secondary")
        self.assertTrue(storages["secondary"].exists(file.object_key))
        self.assertFalse(storages["default"].exists(old_key))


@override_settings(STORAGES=FAILING_STORAGES, FILE_STORAGE_ALIASES=["default"])
class FailedUploadTests(TestCase):
    def test_upload_failure_keeps_failed_database_record_and_cleans_partial_object(self):
        with self.assertRaises(FileService.Error) as caught:
            FileService().upload(SimpleUploadedFile("broken.txt", b"content"))

        file = caught.exception.file
        file.refresh_from_db()
        self.assertEqual(file.status.name, "failed")
        self.assertFalse(storages["default"].exists(file.object_key))


@override_settings(STORAGES=IN_MEMORY_STORAGES, FILE_STORAGE_ALIASES=["default"])
class FileAPITests(APITestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            username="file-admin", password="password"
        )
        self.client.force_authenticate(self.user)

    def test_upload_list_detail_metadata_verify_and_delete_lifecycle(self):
        upload = self.client.post(
            "/api/files/",
            {
                "file": SimpleUploadedFile("manual.pdf", b"pdf data", content_type="application/pdf"),
                "metadata": '{"title":"Manual"}',
            },
            format="multipart",
        )
        self.assertEqual(upload.status_code, 201)
        file_id = upload.data["data"]["id"]
        self.assertEqual(upload.data["data"]["file_type"], "document")
        self.assertIsNotNone(upload.data["data"]["url"])

        listing = self.client.get("/api/files/", {"search": "manual", "page_size": 1})
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.data["data"]["count"], 1)

        detail = self.client.get(f"/api/files/{file_id}")
        self.assertEqual(detail.status_code, 200)

        patch = self.client.patch(
            f"/api/files/{file_id}", {"metadata": {"title": "Updated"}}, format="json"
        )
        self.assertEqual(patch.status_code, 200)
        self.assertEqual(patch.data["data"]["metadata"], {"title": "Updated"})

        verify = self.client.post(f"/api/files/{file_id}/verify", {}, format="json")
        self.assertEqual(verify.status_code, 200)
        self.assertEqual(verify.data["data"]["status"]["name"], "available")

        deleted = self.client.delete(f"/api/files/{file_id}")
        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(deleted.data["data"]["status"]["name"], "deleted")
        self.assertTrue(File.objects.filter(pk=file_id).exists())

    def test_status_orphan_endpoints_and_query_validation(self):
        service = FileService()
        orphan = service.upload(SimpleUploadedFile("orphan.txt", b"orphan", content_type="text/plain"))

        statuses = self.client.get("/api/files/statuses")
        self.assertEqual(statuses.status_code, 200)
        self.assertEqual(
            {status["name"] for status in statuses.data["data"]},
            {"pending", "available", "failed", "deleted"},
        )

        orphans = self.client.get("/api/files/orphans")
        self.assertEqual(orphans.status_code, 200)
        self.assertEqual(orphans.data["data"]["results"][0]["id"], str(orphan.id))

        filtered_orphans = self.client.get(
            "/api/files/orphans", {"search": "missing"}
        )
        self.assertEqual(filtered_orphans.status_code, 200)
        self.assertEqual(filtered_orphans.data["data"]["count"], 0)

        invalid = self.client.get("/api/files/", {"page_size": 101})
        self.assertEqual(invalid.status_code, 400)

    def test_patch_rejects_non_metadata_fields(self):
        file = FileService().upload(SimpleUploadedFile("note.txt", b"note"))

        response = self.client.patch(
            f"/api/files/{file.id}",
            {"metadata": {}, "original_name": "renamed.txt"},
            format="json",
        )

        self.assertEqual(response.status_code, 400)

    def test_upload_rejects_storage_alias_outside_managed_allowlist(self):
        response = self.client.post(
            "/api/files/",
            {
                "file": SimpleUploadedFile("unsafe.txt", b"unsafe"),
                "storage_alias": "staticfiles",
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(File.objects.count(), 0)

    @override_settings(FILE_MAX_UPLOAD_SIZE=3)
    def test_upload_rejects_file_over_size_limit(self):
        response = self.client.post(
            "/api/files/",
            {"file": SimpleUploadedFile("large.txt", b"four")},
            format="multipart",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(File.objects.count(), 0)
