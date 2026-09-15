from datetime import time
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase, TransactionTestCase
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from domains.business.api.serializers import BusinessWorkingDaySerializer
from domains.business.models import BusinessCategory, BusinessPhone, BusinessProfile, BusinessSocialLink, BusinessWorkingDay
from domains.catalog.models import Category, CategoryStatus
from domains.files.models import File, FileStatus
from domains.files.services import FileService


PROFILE = {"business_name": "Uz Shop", "display_name": "Uz", "legal_name": "Uz LLC", "email": "hello@example.com"}


class BusinessModelTests(TransactionTestCase):
    reset_sequences = True

    def test_profile_is_a_database_enforced_singleton(self):
        BusinessProfile.objects.create(**PROFILE)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                BusinessProfile.objects.create(**PROFILE)
        self.assertEqual(BusinessProfile.objects.count(), 1)

    def test_keys_are_immutable_outside_the_api(self):
        phone = BusinessPhone.objects.create(key="support", title="Support", number="123")
        phone.key = "sales"
        with self.assertRaises(ValidationError):
            phone.save()


class WorkingDayValidationTests(TestCase):
    def test_open_day_requires_an_ordered_interval(self):
        serializer = BusinessWorkingDaySerializer(data={"weekday": 0, "is_open": True, "opens_at": "17:00", "closes_at": "09:00"})
        self.assertFalse(serializer.is_valid())

    def test_second_interval_cannot_overlap(self):
        serializer = BusinessWorkingDaySerializer(data={"weekday": 0, "is_open": True, "opens_at": "09:00", "closes_at": "13:00", "second_opens_at": "12:00", "second_closes_at": "17:00"})
        self.assertFalse(serializer.is_valid())

    def test_valid_split_day(self):
        serializer = BusinessWorkingDaySerializer(data={"weekday": 0, "is_open": True, "opens_at": "09:00", "closes_at": "13:00", "second_opens_at": "14:00", "second_closes_at": "17:00"})
        self.assertTrue(serializer.is_valid(), serializer.errors)


class BusinessAPITests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = get_user_model().objects.create_superuser(username="business-admin", email="admin@example.com", password="test")
        cls.profile = BusinessProfile.objects.create(**PROFILE)

    def authenticate(self):
        token = RefreshToken.for_user(self.admin)
        token["user_type"] = "admin"
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token.access_token}")

    @classmethod
    def make_file(cls, *, status="available", file_type="image"):
        file_status, _ = FileStatus.objects.get_or_create(name=status)
        return File.objects.create(
            status=file_status,
            object_key=f"business/{status}-{file_type}",
            original_name="social-logo.png",
            file_type=file_type,
            content_type="image/png" if file_type == "image" else "text/plain",
            extension="png",
            size=10,
            checksum=f"{status}-{file_type}",
        )

    @patch("domains.business.api.serializers.FileService.url", return_value="https://cdn.example.com/social.png")
    def test_admin_accepts_available_image_logo_and_returns_metadata(self, _url):
        self.authenticate()
        logo = self.make_file()
        response = self.client.post("/api/business/admin/social-links", {
            "key": "instagram", "title": "Instagram", "platform": "instagram",
            "url": "https://instagram.com/example", "logo_file_id": str(logo.id),
        }, format="json")

        self.assertEqual(response.status_code, 201)
        self.assertNotIn("logo_file_id", response.data["data"])
        self.assertEqual(response.data["data"]["logo_file"]["id"], str(logo.id))
        self.assertEqual(response.data["data"]["logo_file"]["url"], "https://cdn.example.com/social.png")

    def test_admin_rejects_nonavailable_and_nonimage_logo_files(self):
        self.authenticate()
        for logo in (self.make_file(status="failed"), self.make_file(file_type="document")):
            response = self.client.post("/api/business/admin/social-links", {
                "key": f"social-{logo.id}", "title": "Social", "platform": "web",
                "url": "https://example.com", "logo_file_id": str(logo.id),
            }, format="json")
            self.assertEqual(response.status_code, 400)
            self.assertIn("logo_file_id", response.data["errors"])

    @patch("domains.business.api.serializers.FileService.url", return_value="https://cdn.example.com/social.png")
    @patch("domains.business.api.views.CacheService")
    def test_public_social_logo_url_and_null_logo(self, cache_class, _url):
        cache_class.return_value.get_public.return_value = None
        logo = self.make_file()
        BusinessSocialLink.objects.create(
            key="with-logo", title="With logo", platform="web",
            url="https://example.com/with-logo", logo_file=logo,
        )
        BusinessSocialLink.objects.create(
            key="without-logo", title="Without logo", platform="web",
            url="https://example.com/without-logo",
        )

        response = self.client.get("/api/business/public")
        links = {item["key"]: item for item in response.data["data"]["social_links"]}
        self.assertEqual(links["with-logo"]["logo_url"], "https://cdn.example.com/social.png")
        self.assertIsNone(links["without-logo"]["logo_url"])
        self.assertNotIn("logo_file", links["with-logo"])
        self.assertNotIn("logo_file_id", links["with-logo"])

    @patch("domains.business.api.serializers.FileService.url", side_effect=FileService.Error("unavailable"))
    def test_public_logo_url_generation_fails_gracefully(self, _url):
        logo = self.make_file()
        link = BusinessSocialLink.objects.create(
            key="broken-logo", title="Broken logo", platform="web",
            url="https://example.com/broken", logo_file=logo,
        )
        from domains.business.api.serializers import PublicBusinessSocialLinkSerializer

        self.assertIsNone(PublicBusinessSocialLinkSerializer(link).data["logo_url"])

    def test_admin_crud_search_and_private_visibility(self):
        self.authenticate()
        created = self.client.post("/api/business/admin/phones", {"key": "private-support", "title": "Secret Support", "number": "555", "visibility": "private", "status": "inactive", "notes": "admin only"}, format="json")
        self.assertEqual(created.status_code, 201)
        response = self.client.get("/api/business/admin/phones", {"search": "Secret", "visibility": "private"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["count"], 1)
        self.assertEqual(response.data["data"]["results"][0]["notes"], "admin only")
        changed = self.client.patch(f"/api/business/admin/phones/{created.data['data']['id']}", {"key": "changed"}, format="json")
        self.assertEqual(changed.status_code, 400)
        deleted = self.client.delete(f"/api/business/admin/phones/{created.data['data']['id']}")
        self.assertEqual(deleted.status_code, 200)

    def test_admin_requires_authentication(self):
        self.assertEqual(self.client.get("/api/business/admin/phones").status_code, 401)

    @patch("domains.business.api.views.CacheService")
    def test_public_filters_private_inactive_and_notes(self, cache_class):
        cache_class.return_value.get_public.return_value = None
        BusinessPhone.objects.create(key="public", title="Public", number="1", notes="hidden")
        BusinessPhone.objects.create(key="private", title="Private", number="2", visibility="private")
        BusinessPhone.objects.create(key="inactive", title="Inactive", number="3", status="inactive")
        BusinessSocialLink.objects.create(key="social", title="Social", platform="web", url="https://example.com")
        BusinessSocialLink.objects.create(key="secret", title="Secret", platform="web", url="https://secret.example.com", visibility="private")
        BusinessWorkingDay.objects.create(weekday=0, is_open=True, opens_at=time(9), closes_at=time(17))
        response = self.client.get("/api/business/public")
        self.assertEqual(response.status_code, 200)
        data = response.data["data"]
        self.assertEqual([item["key"] for item in data["phones"]], ["public"])
        self.assertNotIn("notes", data["phones"][0])
        self.assertEqual([item["key"] for item in data["social_links"]], ["social"])
        cache_class.return_value.put_public.assert_called_once_with("business:data", data, ttl=3600)

    @patch("domains.business.api.views.BusinessService.public_data")
    @patch("domains.business.api.views.CacheService")
    def test_cache_hit_skips_database_payload(self, cache_class, public_data):
        cache_class.return_value.get_public.return_value = {"cached": True}
        response = self.client.get("/api/business/public")
        self.assertEqual(response.data["data"], {"cached": True})
        public_data.assert_not_called()

    @patch("domains.business.api.views.CacheService")
    def test_zero_ttl_disables_cache_write(self, cache_class):
        cache_class.return_value.get_public.return_value = None
        self.profile.cache_ttl = 0
        self.profile.save()
        self.client.get("/api/business/public")
        cache_class.return_value.put_public.assert_not_called()

    @patch("domains.business.api.views.CacheService")
    def test_cache_outage_fails_open(self, cache_class):
        cache_class.return_value.get_public.return_value = None
        cache_class.return_value.put_public.return_value = False
        response = self.client.get("/api/business/public")
        self.assertEqual(response.status_code, 200)


class BusinessInvalidationTests(TransactionTestCase):
    @patch("domains.business.signals.invalidate_business_cache")
    def test_save_and_delete_invalidate_after_commit(self, invalidate):
        with transaction.atomic():
            phone = BusinessPhone.objects.create(key="cache", title="Cache", number="1")
            self.assertFalse(invalidate.called)
        invalidate.assert_called_once_with()
        invalidate.reset_mock()
        phone.delete()
        invalidate.assert_called_once_with()


class BusinessCategoryModelTests(TransactionTestCase):
    reset_sequences = True

    def _get_or_create_business(self):
        business, _ = BusinessProfile.objects.get_or_create(
            id=1, defaults=PROFILE
        )
        return business

    def test_unique_constraint(self):
        business = self._get_or_create_business()
        cat_status, _ = CategoryStatus.objects.get_or_create(name="active")
        category = Category.objects.create(name="Phones", status=cat_status)
        BusinessCategory.objects.create(business=business, category=category)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                BusinessCategory.objects.create(business=business, category=category)

    def test_different_categories_for_same_business(self):
        business = self._get_or_create_business()
        cat_status, _ = CategoryStatus.objects.get_or_create(name="active")
        cat1 = Category.objects.create(name="Phones", status=cat_status)
        cat2 = Category.objects.create(name="Laptops", status=cat_status)
        BusinessCategory.objects.create(business=business, category=cat1)
        BusinessCategory.objects.create(business=business, category=cat2)
        self.assertEqual(BusinessCategory.objects.filter(business=business).count(), 2)

    def test_same_category_for_different_businesses(self):
        from django.db import connection
        from domains.vendor.models import Vendor, VendorStatus

        bp1 = self._get_or_create_business()
        status, _ = VendorStatus.objects.get_or_create(id=1, defaults={"name": "Active", "is_active": True})
        vendor2 = Vendor.objects.create(phone="+9999999999", national_id="9999999999", status=status)
        with connection.cursor() as cursor:
            cursor.execute("SELECT setval(pg_get_serial_sequence('business_profile', 'id'), (SELECT COALESCE(MAX(id),0) FROM business_profile)+1)")
        bp2 = BusinessProfile.objects.create(business_name="Biz2", display_name="Biz2", vendor=vendor2)
        cat_status, _ = CategoryStatus.objects.get_or_create(name="active")
        category = Category.objects.create(name="Phones", status=cat_status)
        BusinessCategory.objects.create(business=bp1, category=category)
        BusinessCategory.objects.create(business=bp2, category=category)
        self.assertEqual(BusinessCategory.objects.filter(category=category).count(), 2)


class BusinessCategoryAPITests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = get_user_model().objects.create_superuser(
            username="bizcat-admin", email="admin@example.com", password="test"
        )
        cls.profile, _ = BusinessProfile.objects.get_or_create(id=1, defaults=PROFILE)
        cls.cat_status, _ = CategoryStatus.objects.get_or_create(name="active")
        cls.cat1 = Category.objects.create(name="Phones", status=cls.cat_status)
        cls.cat2 = Category.objects.create(name="Laptops", status=cls.cat_status)
        cls.cat3 = Category.objects.create(name="Tablets", status=cls.cat_status)

    def authenticate(self):
        token = RefreshToken.for_user(self.admin)
        token["user_type"] = "admin"
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token.access_token}")

    def test_get_empty_categories(self):
        self.authenticate()
        response = self.client.get("/api/business/admin/categories")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"], [])

    def test_put_replaces_categories(self):
        self.authenticate()
        response = self.client.put(
            "/api/business/admin/categories",
            {"category_ids": [self.cat1.id, self.cat2.id]},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["data"]), 2)

    def test_put_removes_old_adds_new(self):
        self.authenticate()
        self.client.put(
            "/api/business/admin/categories",
            {"category_ids": [self.cat1.id]},
            format="json",
        )
        response = self.client.put(
            "/api/business/admin/categories",
            {"category_ids": [self.cat2.id, self.cat3.id]},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        ids = [item["category"] for item in response.data["data"]]
        self.assertEqual(sorted(ids), [self.cat2.id, self.cat3.id])

    def test_put_empty_list_clears_all(self):
        self.authenticate()
        self.client.put(
            "/api/business/admin/categories",
            {"category_ids": [self.cat1.id]},
            format="json",
        )
        response = self.client.put(
            "/api/business/admin/categories",
            {"category_ids": []},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"], [])

    def test_put_invalid_category_id(self):
        self.authenticate()
        response = self.client.put(
            "/api/business/admin/categories",
            {"category_ids": [9999]},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_put_no_business_profile(self):
        self.authenticate()
        BusinessProfile.objects.all().delete()
        response = self.client.put(
            "/api/business/admin/categories",
            {"category_ids": [self.cat1.id]},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_get_requires_authentication(self):
        response = self.client.get("/api/business/admin/categories")
        self.assertEqual(response.status_code, 401)

    def test_put_idempotent(self):
        self.authenticate()
        self.client.put(
            "/api/business/admin/categories",
            {"category_ids": [self.cat1.id, self.cat2.id]},
            format="json",
        )
        response = self.client.put(
            "/api/business/admin/categories",
            {"category_ids": [self.cat1.id, self.cat2.id]},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["data"]), 2)

    def test_put_rejects_child_category(self):
        self.authenticate()
        child = Category.objects.create(name="Smartphones", parent=self.cat1, status=self.cat_status)
        response = self.client.put(
            "/api/business/admin/categories",
            {"category_ids": [child.id]},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_put_rejects_mix_of_root_and_child(self):
        self.authenticate()
        child = Category.objects.create(name="Smartphones", parent=self.cat1, status=self.cat_status)
        response = self.client.put(
            "/api/business/admin/categories",
            {"category_ids": [self.cat1.id, child.id]},
            format="json",
        )
        self.assertEqual(response.status_code, 400)


class VendorCategoryBrowseTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        from domains.vendor.models import Vendor, VendorStatus

        cls.vendor_status, _ = VendorStatus.objects.get_or_create(id=1, defaults={"name": "Active", "is_active": True})
        cls.vendor = Vendor.objects.create(phone="+9876543210", national_id="1234567890", status=cls.vendor_status)
        cls.profile = BusinessProfile.objects.get_or_create(
            vendor=cls.vendor, defaults={"business_name": "Test Biz", "display_name": "Test Biz"}
        )[0]
        cls.cat_status, _ = CategoryStatus.objects.get_or_create(name="active")
        cls.root1 = Category.objects.create(name="Electronics", status=cls.cat_status)
        cls.root2 = Category.objects.create(name="Clothing", status=cls.cat_status)
        cls.child1 = Category.objects.create(name="Phones", parent=cls.root1, status=cls.cat_status)
        cls.child2 = Category.objects.create(name="Laptops", parent=cls.root1, status=cls.cat_status)
        cls.grandchild = Category.objects.create(name="Smartphones", parent=cls.child1, status=cls.cat_status)

    def _auth(self):
        from rest_framework_simplejwt.tokens import RefreshToken

        token = RefreshToken.for_user(self.vendor)
        token["user_type"] = "vendor"
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token.access_token}")

    def test_get_returns_root_categories(self):
        self._auth()
        response = self.client.get("/api/vendor/business/categories")
        self.assertEqual(response.status_code, 200)
        names = [c["name"] for c in response.data["data"]]
        self.assertIn("Electronics", names)
        self.assertIn("Clothing", names)
        self.assertNotIn("Phones", names)

    def test_get_root_categories_have_has_children(self):
        self._auth()
        response = self.client.get("/api/vendor/business/categories")
        data = {c["name"]: c for c in response.data["data"]}
        self.assertTrue(data["Electronics"]["has_children"])
        self.assertFalse(data["Clothing"]["has_children"])

    def test_get_with_parent_returns_children(self):
        self._auth()
        response = self.client.get(f"/api/vendor/business/categories?parent={self.root1.id}")
        self.assertEqual(response.status_code, 200)
        names = [c["name"] for c in response.data["data"]]
        self.assertIn("Phones", names)
        self.assertIn("Laptops", names)
        self.assertNotIn("Electronics", names)

    def test_get_with_parent_returns_grandchildren_flag(self):
        self._auth()
        response = self.client.get(f"/api/vendor/business/categories?parent={self.child1.id}")
        self.assertEqual(response.status_code, 200)
        data = response.data["data"]
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["name"], "Smartphones")
        self.assertFalse(data[0]["has_children"])

    def test_get_shows_selected_status(self):
        self._auth()
        BusinessCategory.objects.create(business=self.profile, category=self.root1)
        response = self.client.get("/api/vendor/business/categories")
        data = {c["id"]: c for c in response.data["data"]}
        self.assertTrue(data[self.root1.id]["selected"])
        self.assertFalse(data[self.root2.id]["selected"])

    def test_get_with_parent_shows_selected_status(self):
        self._auth()
        BusinessCategory.objects.create(business=self.profile, category=self.child1)
        response = self.client.get(f"/api/vendor/business/categories?parent={self.root1.id}")
        data = {c["id"]: c for c in response.data["data"]}
        self.assertTrue(data[self.child1.id]["selected"])
        self.assertFalse(data[self.child2.id]["selected"])

    def test_get_without_business_profile(self):
        from rest_framework_simplejwt.tokens import RefreshToken

        vendor2 = Vendor.objects.create(phone="+9876543211", national_id="1234567891", status=self.vendor_status)
        token = RefreshToken.for_user(vendor2)
        token["user_type"] = "vendor"
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token.access_token}")
        response = self.client.get("/api/vendor/business/categories")
        self.assertEqual(response.status_code, 200)
        for item in response.data["data"]:
            self.assertFalse(item["selected"])

    def test_get_invalid_parent_param(self):
        self._auth()
        response = self.client.get("/api/vendor/business/categories?parent=abc")
        self.assertEqual(response.status_code, 400)

    def test_get_requires_authentication(self):
        response = self.client.get("/api/vendor/business/categories")
        self.assertEqual(response.status_code, 401)

    def test_put_replaces_categories(self):
        self._auth()
        response = self.client.put(
            "/api/vendor/business/categories",
            {"category_ids": [self.child1.id, self.child2.id]},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["data"]), 2)
