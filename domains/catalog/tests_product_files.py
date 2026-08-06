from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from rest_framework.test import APITestCase

from domains.catalog.models import (
    Category,
    CategoryStatus,
    Product,
    ProductFile,
    ProductStatus,
)
from domains.catalog.services import ProductFileService
from domains.files.services import FileService


TEST_STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.InMemoryStorage",
        "OPTIONS": {"base_url": "/test-media/"},
    },
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}


@override_settings(STORAGES=TEST_STORAGES, FILE_STORAGE_ALIASES=["default"])
class ProductFileTests(APITestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            username="file-admin",
            email="file-admin@example.com",
            password="test-pass",
        )
        self.client.force_authenticate(self.user)
        category_status, _ = CategoryStatus.objects.get_or_create(name="active")
        self.category = Category.objects.create(
            name="File test category", status=category_status
        )
        product_status = ProductStatus.objects.get(name="pending")
        self.product = Product.objects.create(
            name="File test product",
            status=product_status,
        )
        self.product.categories.add(self.category)
        self.other_product = Product.objects.create(
            name="Other file test product",
            status=product_status,
        )
        self.other_product.categories.add(self.category)
        self.file_service = FileService()
        self.relation_service = ProductFileService()

    def upload(self, name="photo.jpg", content=b"image-data"):
        return self.file_service.upload(
            SimpleUploadedFile(name, content, content_type="image/jpeg"),
            created_by=self.user,
        )

    def test_file_can_be_shared_but_not_duplicated_per_product(self):
        file = self.upload()
        first = self.relation_service.attach(
            self.product, file, role="gallery", position=0, is_primary=False,
            alt_text="",
        )
        second = self.relation_service.attach(
            self.other_product, file, role="thumbnail", position=0,
            is_primary=True, alt_text="Shared",
        )

        self.assertNotEqual(first.product_id, second.product_id)
        with self.assertRaises(ProductFileService.ValidationError):
            self.relation_service.attach(
                self.product, file, role="gallery", position=1,
                is_primary=False, alt_text="",
            )

    def test_setting_primary_replaces_existing_primary(self):
        first = self.relation_service.attach(
            self.product, self.upload("one.jpg", b"one"), role="gallery",
            position=1, is_primary=True, alt_text="One",
        )
        second = self.relation_service.attach(
            self.product, self.upload("two.jpg", b"two"), role="thumbnail",
            position=0, is_primary=True, alt_text="Two",
        )

        first.refresh_from_db()
        self.assertFalse(first.is_primary)
        self.assertTrue(second.is_primary)

    def test_nested_api_and_product_detail_return_runtime_urls_in_order(self):
        first = self.upload("first.jpg", b"first")
        second = self.upload("second.jpg", b"second")
        collection = f"/api/catalog/products/{self.product.id}/files"

        response = self.client.post(
            collection,
            {
                "file": str(first.id), "role": "gallery", "position": 2,
                "is_primary": False, "alt_text": "First",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        response = self.client.post(
            collection,
            {
                "file": str(second.id), "role": "thumbnail", "position": 1,
                "is_primary": True, "alt_text": "Second",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)

        response = self.client.get(f"/api/catalog/products/{self.product.id}")
        self.assertEqual(response.status_code, 200)
        pictures = response.data["data"]["pictures"]
        self.assertEqual([item["file"] for item in pictures], [second.id, first.id])
        self.assertEqual(
            pictures[0]["url"], f"/test-media/{second.object_key}"
        )

        listing = self.client.get("/api/catalog/products")
        self.assertEqual(listing.status_code, 200)
        listed_product = next(
            item for item in listing.data["data"]["results"]
            if item["id"] == self.product.id
        )
        self.assertEqual(
            listed_product["thumbnail_url"],
            f"/test-media/{second.object_key}",
        )

    def test_unavailable_file_cannot_be_attached(self):
        file = self.upload()
        file.status = self.file_service._status(FileService.STATUS_FAILED)
        file.save(update_fields=["status", "updated_at"])

        response = self.client.post(
            f"/api/catalog/products/{self.product.id}/files",
            {"file": str(file.id), "role": "gallery"},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(ProductFile.objects.count(), 0)

    def test_role_must_match_file_type(self):
        file = self.file_service.upload(
            SimpleUploadedFile("clip.mp4", b"video", content_type="video/mp4"),
            created_by=self.user,
        )

        response = self.client.post(
            f"/api/catalog/products/{self.product.id}/files",
            {"file": str(file.id), "role": "gallery"},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(ProductFile.objects.count(), 0)

    def test_reorder_endpoint_updates_every_position_atomically(self):
        first = self.relation_service.attach(
            self.product, self.upload("first.jpg", b"first"), role="gallery",
            position=0, is_primary=False, alt_text="",
        )
        second = self.relation_service.attach(
            self.product, self.upload("second.jpg", b"second"), role="gallery",
            position=1, is_primary=False, alt_text="",
        )

        response = self.client.patch(
            f"/api/catalog/products/{self.product.id}/files/reorder",
            {"files": [second.id, first.id]},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [item["id"] for item in response.data["data"]],
            [second.id, first.id],
        )
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual((second.position, first.position), (0, 1))

    def test_orphans_and_file_deletion_follow_relation_lifecycle(self):
        attached = self.upload("attached.jpg", b"attached")
        orphan = self.upload("orphan.jpg", b"orphan")
        self.relation_service.attach(
            self.product, attached, role="gallery", position=0,
            is_primary=False, alt_text="",
        )

        self.assertEqual(list(self.file_service.orphans()), [orphan])
        self.file_service.delete(attached)
        attached.refresh_from_db()

        self.assertEqual(attached.status.name, FileService.STATUS_DELETED)
        self.assertFalse(ProductFile.objects.filter(file=attached).exists())
        self.assertFalse(self.file_service.exists(attached))
