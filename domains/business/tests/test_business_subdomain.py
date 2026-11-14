from datetime import timedelta
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.test import TestCase, TransactionTestCase
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from rest_framework.test import APITestCase

from core.management.seeders.configs.business_subdomain_statuses import BusinessSubdomainStatusSeeder
from domains.business.enums import BusinessStatusEnum, BusinessSubdomainEnum, business_subdomain_enum
from domains.business.models import (
    BusinessProfile,
    BusinessStatus,
    BusinessSubdomain,
    BusinessSubdomainStatus,
    RESERVED_SUBDOMAINS,
    validate_subdomain_format,
)
from domains.business.services.business_service import BusinessService
from domains.business.services.business_subdomain_service import BusinessSubdomainService
from domains.vendor.models import Vendor, VendorStatus


class SubdomainEnumAndSeederTests(TestCase):
    def test_enum_values_and_aliases(self):
        self.assertEqual(BusinessSubdomainEnum.ACTIVE.value, 1)
        self.assertEqual(BusinessSubdomainEnum.REDIRECT.value, 2)
        self.assertEqual(BusinessSubdomainEnum.RESERVED.value, 3)
        self.assertIs(business_subdomain_enum, BusinessSubdomainEnum)

    def test_seeder_populates_statuses_and_is_idempotent(self):
        seeder = BusinessSubdomainStatusSeeder()
        seeder.run()
        count_first = BusinessSubdomainStatus.objects.count()
        self.assertEqual(count_first, 3)

        active = BusinessSubdomainStatus.objects.get(id=BusinessSubdomainEnum.ACTIVE.value)
        self.assertEqual(active.code, "active")
        self.assertEqual(active.name, "Active")
        self.assertEqual(active.title, "فعال")

        redirect = BusinessSubdomainStatus.objects.get(id=BusinessSubdomainEnum.REDIRECT.value)
        self.assertEqual(redirect.code, "redirect")

        reserved = BusinessSubdomainStatus.objects.get(id=BusinessSubdomainEnum.RESERVED.value)
        self.assertEqual(reserved.code, "reserved")

        # Second run must be idempotent
        seeder.run()
        count_second = BusinessSubdomainStatus.objects.count()
        self.assertEqual(count_second, 3)

    def test_status_protected_fk(self):
        active = BusinessSubdomainStatus.objects.get(id=BusinessSubdomainEnum.ACTIVE.value)
        biz = BusinessProfile.objects.create(business_name="protect-test", display_name="Protect Test")
        sub = BusinessSubdomain.objects.create(business=biz, subdomain="protect-test-sub", status=active)

        with self.assertRaises(ProtectedError):
            active.delete()


class SubdomainValidationTests(TestCase):
    def test_valid_subdomains(self):
        valid_samples = [
            "abc",
            "delta",
            "shop-123",
            "my-great-shop",
            "a1-b2-c3",
            "x" * 30,
        ]
        for s in valid_samples:
            self.assertEqual(validate_subdomain_format(s), s.lower())

    def test_invalid_length(self):
        with self.assertRaises(DjangoValidationError):
            validate_subdomain_format("ab")  # Too short (< 3)
        with self.assertRaises(DjangoValidationError):
            validate_subdomain_format("a" * 31)  # Too long (> 30)

    def test_invalid_characters_and_hyphens(self):
        invalid_samples = [
            "shop name",  # Space
            "shop_name",  # Underscore
            "-shop",      # Leading hyphen
            "shop-",      # Trailing hyphen
            "shop@name",  # Special character
            "فروشگاه",    # Non-ASCII
        ]
        for s in invalid_samples:
            with self.assertRaises(DjangoValidationError, msg=f"Should fail for {s}"):
                validate_subdomain_format(s)

    def test_reserved_subdomains(self):
        active = BusinessSubdomainStatus.objects.get(id=BusinessSubdomainEnum.ACTIVE.value)
        biz = BusinessProfile.objects.create(business_name="reserved-test", display_name="Reserved Test")

        for reserved in ["www", "api", "admin", "vendor", "client", "dashboard", "support", "help", "static", "cdn", "mail"]:
            self.assertIn(reserved, RESERVED_SUBDOMAINS)
            sub = BusinessSubdomain(business=biz, subdomain=reserved, status=active)
            with self.assertRaises(DjangoValidationError):
                sub.clean()


class SubdomainConstraintsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.active_status = BusinessSubdomainStatus.objects.get(id=BusinessSubdomainEnum.ACTIVE.value)
        cls.redirect_status = BusinessSubdomainStatus.objects.get(id=BusinessSubdomainEnum.REDIRECT.value)
        cls.biz1 = BusinessProfile.objects.create(business_name="biz1", display_name="Biz 1")
        cls.biz2 = BusinessProfile.objects.create(business_name="biz2", display_name="Biz 2")

    def test_subdomain_global_uniqueness(self):
        BusinessSubdomain.objects.create(
            business=self.biz1, subdomain="unique-shop", status=self.active_status
        )
        # Attempting to reuse "unique-shop" for another business must raise validation or integrity error
        with self.assertRaises((DjangoValidationError, IntegrityError)):
            with transaction.atomic():
                BusinessSubdomain.objects.create(
                    business=self.biz2, subdomain="unique-shop", status=self.active_status
                )

    def test_historical_subdomain_remains_globally_unique(self):
        BusinessSubdomain.objects.create(
            business=self.biz1, subdomain="old-shop", status=self.redirect_status
        )
        # Another business cannot take a historical REDIRECT subdomain
        with self.assertRaises((DjangoValidationError, IntegrityError)):
            with transaction.atomic():
                BusinessSubdomain.objects.create(
                    business=self.biz2, subdomain="old-shop", status=self.active_status
                )

    def test_one_active_subdomain_per_business_db_constraint(self):
        BusinessSubdomain.objects.create(
            business=self.biz1, subdomain="active-one", status=self.active_status
        )
        # Attempting to add a second ACTIVE subdomain for the same business must violate partial unique constraint
        with self.assertRaises((DjangoValidationError, IntegrityError)):
            with transaction.atomic():
                BusinessSubdomain.objects.create(
                    business=self.biz1, subdomain="active-two", status=self.active_status
                )


class SubdomainChangeRulesTests(TestCase):
    def setUp(self):
        self.active_status = BusinessSubdomainStatus.objects.get(id=BusinessSubdomainEnum.ACTIVE.value)
        self.redirect_status = BusinessSubdomainStatus.objects.get(id=BusinessSubdomainEnum.REDIRECT.value)

    def test_first_change_fails_before_30_days(self):
        biz = BusinessProfile.objects.create(
            business_name="young-store",
            display_name="Young Store",
        )
        # Young store registered now
        eligibility = BusinessSubdomainService.check_eligibility(biz)
        self.assertFalse(eligibility["can_change"])
        self.assertTrue(eligibility["is_first_change"])
        self.assertGreater(eligibility["days_remaining"], 0)
        self.assertIn("30 days", eligibility["message"])

        # Attempting change without eligibility raises ValidationError
        with self.assertRaises(ValidationError):
            BusinessSubdomainService.change_subdomain(biz, "new-young-store", confirmed=True)

    def test_first_change_succeeds_after_30_days(self):
        biz = BusinessProfile.objects.create(
            business_name="mature-store",
            display_name="Mature Store",
        )
        # Backdate registration to 31 days ago
        BusinessProfile.objects.filter(id=biz.id).update(
            created_at=timezone.now() - timedelta(days=31)
        )
        biz.refresh_from_db()

        # Provision initial active subdomain
        BusinessSubdomain.objects.create(business=biz, subdomain="mature-store", status=self.active_status)

        eligibility = BusinessSubdomainService.check_eligibility(biz)
        self.assertTrue(eligibility["can_change"])
        self.assertTrue(eligibility["is_first_change"])
        self.assertEqual(eligibility["days_remaining"], 0)

        # Successful change
        new_active = BusinessSubdomainService.change_subdomain(
            biz, "brand-new-mature", confirmed=True
        )
        self.assertEqual(new_active.subdomain, "brand-new-mature")
        self.assertEqual(new_active.status_id, BusinessSubdomainEnum.ACTIVE.value)

        # Old active record became REDIRECT
        old_record = BusinessSubdomain.objects.get(subdomain="mature-store")
        self.assertEqual(old_record.status_id, BusinessSubdomainEnum.REDIRECT.value)
        self.assertEqual(old_record.business_id, biz.id)

    def test_subsequent_change_fails_before_90_days(self):
        biz = BusinessProfile.objects.create(
            business_name="twice-store",
            display_name="Twice Store",
        )
        # 100 days old business
        BusinessProfile.objects.filter(id=biz.id).update(
            created_at=timezone.now() - timedelta(days=100)
        )
        biz.refresh_from_db()

        # Has a historical redirect (so first change already occurred 10 days ago)
        BusinessSubdomain.objects.create(
            business=biz,
            subdomain="first-twice-store",
            status=self.redirect_status,
        )
        # Manually set updated_at on the redirect to 10 days ago
        BusinessSubdomain.objects.filter(subdomain="first-twice-store").update(
            updated_at=timezone.now() - timedelta(days=10)
        )

        BusinessSubdomain.objects.create(
            business=biz,
            subdomain="current-twice-store",
            status=self.active_status,
        )

        eligibility = BusinessSubdomainService.check_eligibility(biz)
        self.assertFalse(eligibility["can_change"])
        self.assertFalse(eligibility["is_first_change"])
        self.assertGreater(eligibility["days_remaining"], 0)
        self.assertIn("90 days", eligibility["message"])

    def test_subsequent_change_succeeds_after_90_days(self):
        biz = BusinessProfile.objects.create(
            business_name="patient-store",
            display_name="Patient Store",
        )
        BusinessProfile.objects.filter(id=biz.id).update(
            created_at=timezone.now() - timedelta(days=200)
        )
        biz.refresh_from_db()

        # First change occurred 95 days ago
        redirect = BusinessSubdomain.objects.create(
            business=biz,
            subdomain="first-patient-store",
            status=self.redirect_status,
        )
        BusinessSubdomain.objects.filter(id=redirect.id).update(
            updated_at=timezone.now() - timedelta(days=95)
        )

        BusinessSubdomain.objects.create(
            business=biz,
            subdomain="current-patient-store",
            status=self.active_status,
        )

        eligibility = BusinessSubdomainService.check_eligibility(biz)
        self.assertTrue(eligibility["can_change"])
        self.assertFalse(eligibility["is_first_change"])

        new_sub = BusinessSubdomainService.change_subdomain(biz, "third-patient-store", confirmed=True)
        self.assertEqual(new_sub.subdomain, "third-patient-store")
        self.assertEqual(new_sub.status_id, BusinessSubdomainEnum.ACTIVE.value)

        # Now both previous subdomains are REDIRECT
        self.assertEqual(
            BusinessSubdomain.objects.filter(business=biz, status_id=BusinessSubdomainEnum.REDIRECT.value).count(),
            2,
        )

    def test_confirmation_required_for_change(self):
        biz = BusinessProfile.objects.create(
            business_name="confirm-store",
            display_name="Confirm Store",
        )
        BusinessProfile.objects.filter(id=biz.id).update(
            created_at=timezone.now() - timedelta(days=50)
        )
        biz.refresh_from_db()

        BusinessSubdomain.objects.create(business=biz, subdomain="confirm-store", status=self.active_status)

        with self.assertRaises(ValidationError) as ctx:
            BusinessSubdomainService.change_subdomain(biz, "new-confirm-store", confirmed=False)
        self.assertIn("confirmed", ctx.exception.detail)


class SubdomainTenantResolutionIntegrationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.active_biz_status = BusinessStatus.objects.get(id=BusinessStatusEnum.ACTIVE.value)
        cls.active_sub_status = BusinessSubdomainStatus.objects.get(id=BusinessSubdomainEnum.ACTIVE.value)
        cls.redirect_sub_status = BusinessSubdomainStatus.objects.get(id=BusinessSubdomainEnum.REDIRECT.value)

        cls.biz = BusinessProfile.objects.create(
            business_name="delta-corp",
            display_name="Delta Corp",
            status=cls.active_biz_status,
        )
        # Historical subdomain
        BusinessSubdomain.objects.create(
            business=cls.biz,
            subdomain="old-delta",
            status=cls.redirect_sub_status,
        )
        # Current active subdomain
        BusinessSubdomain.objects.create(
            business=cls.biz,
            subdomain="delta-official",
            status=cls.active_sub_status,
        )

    def test_active_subdomain_resolves_business(self):
        resolved = BusinessService.get_active_by_slug("delta-official")
        self.assertIsNotNone(resolved)
        self.assertEqual(resolved.id, self.biz.id)

    def test_historical_redirect_subdomain_resolves_business(self):
        # A request to the historical subdomain should resolve the same business
        resolved = BusinessService.get_active_by_slug("old-delta")
        self.assertIsNotNone(resolved)
        self.assertEqual(resolved.id, self.biz.id)

    def test_reserved_subdomain_returns_none(self):
        resolved = BusinessService.get_active_by_slug("admin")
        self.assertIsNone(resolved)

        resolved_api = BusinessService.get_active_by_slug("api")
        self.assertIsNone(resolved_api)

    def test_unknown_subdomain_returns_none(self):
        resolved = BusinessService.get_active_by_slug("completely-unknown-store")
        self.assertIsNone(resolved)


class VendorSubdomainAPITests(APITestCase):
    def setUp(self):
        vendor_status, _ = VendorStatus.objects.get_or_create(name="active", defaults={"title": "Active"})
        self.vendor = Vendor.objects.create(
            phone="+989129990001",
            first_name="Vendor",
            last_name="One",
            national_id="9990000001",
            status=vendor_status,
        )
        self.other_vendor = Vendor.objects.create(
            phone="+989129990002",
            first_name="Vendor",
            last_name="Two",
            national_id="9990000002",
            status=vendor_status,
        )
        self.active_biz_status = BusinessStatus.objects.get(id=BusinessStatusEnum.ACTIVE.value)
        self.active_sub_status = BusinessSubdomainStatus.objects.get(id=BusinessSubdomainEnum.ACTIVE.value)

        self.business = BusinessProfile.objects.create(
            vendor=self.vendor,
            business_name="my-vendor-store",
            display_name="My Vendor Store",
            status=self.active_biz_status,
        )
        # Age 40 days
        BusinessProfile.objects.filter(id=self.business.id).update(
            created_at=timezone.now() - timedelta(days=40)
        )
        self.business.refresh_from_db()

        self.subdomain = BusinessSubdomain.objects.create(
            business=self.business,
            subdomain="my-vendor-store",
            status=self.active_sub_status,
        )

        self.client.force_authenticate(user=self.vendor)

    def test_unauthenticated_cannot_access_vendor_subdomain_api(self):
        self.client.force_authenticate(user=None)
        response = self.client.get("/api/vendor/business/subdomain")
        self.assertEqual(response.status_code, 401)

    def test_get_subdomain_overview(self):
        response = self.client.get("/api/vendor/business/subdomain")
        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertEqual(data["current_subdomain"], "my-vendor-store")
        self.assertEqual(data["status"], "active")
        self.assertTrue(data["eligibility"]["can_change"])

    def test_check_subdomain_availability_api(self):
        # 1. Check available name
        resp1 = self.client.get("/api/vendor/business/subdomain/check?subdomain=fresh-unique-name")
        self.assertEqual(resp1.status_code, 200)
        self.assertTrue(resp1.json()["data"]["available"])

        # 2. Check reserved name
        resp2 = self.client.get("/api/vendor/business/subdomain/check?subdomain=admin")
        self.assertEqual(resp2.status_code, 200)
        self.assertFalse(resp2.json()["data"]["available"])
        self.assertIn("reserved", resp2.json()["data"]["reason"])

        # 3. Check taken name
        resp3 = self.client.get("/api/vendor/business/subdomain/check?subdomain=my-vendor-store")
        self.assertEqual(resp3.status_code, 200)
        self.assertFalse(resp3.json()["data"]["available"])

    def test_change_subdomain_api_success(self):
        response = self.client.post(
            "/api/vendor/business/subdomain",
            data={"subdomain": "brand-new-slug", "confirmed": True},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertEqual(data["subdomain"], "brand-new-slug")
        self.assertEqual(data["status"], "active")

        # Verify history API contains both
        history_resp = self.client.get("/api/vendor/business/subdomain/history")
        self.assertEqual(history_resp.status_code, 200)
        history_data = history_resp.json()["data"]
        self.assertEqual(len(history_data), 2)
        subdomains = [item["subdomain"] for item in history_data]
        self.assertIn("brand-new-slug", subdomains)
        self.assertIn("my-vendor-store", subdomains)

    def test_user_cannot_modify_other_business_subdomain(self):
        # Authenticate as other_vendor who does not own self.business
        self.client.force_authenticate(user=self.other_vendor)
        # other_vendor has no business profile
        response = self.client.post(
            "/api/vendor/business/subdomain",
            data={"subdomain": "hijack-slug", "confirmed": True},
            format="json",
        )
        self.assertEqual(response.status_code, 404)


class ConcurrentSubdomainChangeTests(TransactionTestCase):
    def setUp(self):
        super().setUp()
        from domains.business.data.business_statuses import BUSINESS_STATUS_SEED
        for row in BUSINESS_STATUS_SEED:
            BusinessStatus.objects.get_or_create(
                id=row["id"],
                defaults={"code": row["code"], "name": row["name"], "title": row["title"]},
            )
        from domains.business.data.business_subdomain_statuses import BUSINESS_SUBDOMAIN_STATUS_SEED
        for row in BUSINESS_SUBDOMAIN_STATUS_SEED:
            BusinessSubdomainStatus.objects.get_or_create(
                id=row["id"],
                defaults={"code": row["code"], "name": row["name"], "title": row["title"]},
            )

    def test_concurrent_same_business_changes(self):
        import concurrent.futures
        from django.db import connection

        biz = BusinessProfile.objects.create(business_name="concurrent-biz", display_name="Concurrent Biz")
        BusinessProfile.objects.filter(id=biz.id).update(created_at=timezone.now() - timedelta(days=60))
        biz.refresh_from_db()
        active_status = BusinessSubdomainStatus.objects.get(id=BusinessSubdomainEnum.ACTIVE.value)
        BusinessSubdomain.objects.create(business=biz, subdomain="concurrent-biz", status=active_status)

        results = []
        errors = []

        def attempt_change(new_slug):
            connection.close()
            try:
                sub = BusinessSubdomainService.change_subdomain(biz, new_slug, confirmed=True)
                results.append(sub.subdomain)
            except Exception as e:
                errors.append(e)
            finally:
                connection.close()

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            f1 = executor.submit(attempt_change, "concurrent-slug-1")
            f2 = executor.submit(attempt_change, "concurrent-slug-2")
            f1.result()
            f2.result()

        # Exactly one change must succeed; the other must fail
        self.assertEqual(len(results), 1)
        self.assertEqual(len(errors), 1)
        self.assertEqual(
            BusinessSubdomain.objects.filter(business=biz, status_id=BusinessSubdomainEnum.ACTIVE.value).count(),
            1,
        )

