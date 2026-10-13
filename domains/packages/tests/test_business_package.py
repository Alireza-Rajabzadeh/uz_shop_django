import importlib
from decimal import Decimal

from django.apps import apps as global_apps
from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import ProtectedError
from django.test import TestCase
from rest_framework.test import APITestCase

from core.management.seeders.packages import PackagesSeeder
from domains.business.api.serializers import (
    BusinessProfileSerializer,
    PublicBusinessProfileSerializer,
)
from domains.business.models import BusinessProfile
from domains.packages.data.packages import PACKAGE_SEED
from domains.packages.models import DEFAULT_PACKAGE_CODE, Package

PROFILE = {"business_name": "UzShop", "display_name": "UzShop"}

BUSINESS_ADMIN = "/api/business/admin/profile"

# Loaded by module name because migration filenames start with a digit.
backfill_default_package = importlib.import_module(
    "domains.business.migrations.0010_businessprofile_package"
).backfill_default_package


def make_profile(**kwargs):
    return BusinessProfile.objects.create(**{**PROFILE, **kwargs})


class BusinessPackageDefaultTests(TestCase):
    def test_new_business_without_a_package_gets_the_default(self):
        PackagesSeeder().run()

        business = make_profile()

        self.assertEqual(business.package.code, DEFAULT_PACKAGE_CODE)
        self.assertEqual(business.package_code, DEFAULT_PACKAGE_CODE)

    def test_new_business_keeps_an_explicit_package(self):
        PackagesSeeder().run()
        plus = Package.objects.get(code="plus")

        business = make_profile(package=plus)

        self.assertEqual(business.package, plus)
        self.assertEqual(business.package_code, "plus")

    def test_default_is_applied_on_create_only(self):
        PackagesSeeder().run()
        plus = Package.objects.get(code="plus")
        business = make_profile(package=plus)

        # An update that leaves the column alone must not reassign the tier.
        business.display_name = "Renamed"
        business.save()

        self.assertEqual(business.package, plus)

    def test_explicit_null_is_left_null_and_falls_back_in_code(self):
        PackagesSeeder().run()
        business = make_profile(package=None)

        BusinessProfile.objects.filter(pk=business.pk).update(package=None)
        business.refresh_from_db()

        self.assertIsNone(business.package_id)
        self.assertEqual(business.package_code, DEFAULT_PACKAGE_CODE)

    def test_unseeded_environment_creates_a_profile_without_failing(self):
        # No packages exist here. The default lookup must tolerate that,
        # because many call sites build a profile without seeding first.
        self.assertEqual(Package.objects.count(), 0)

        business = make_profile()

        self.assertIsNone(business.package_id)
        self.assertEqual(business.package_code, DEFAULT_PACKAGE_CODE)

    def test_package_code_is_the_tier_string_not_the_id(self):
        PackagesSeeder().run()
        business = make_profile()

        self.assertIsInstance(business.package_code, str)
        self.assertEqual(business.package_code, DEFAULT_PACKAGE_CODE)


class BusinessPackageDeletionTests(TestCase):
    def test_deleting_a_referenced_package_is_protected(self):
        PackagesSeeder().run()
        free = Package.objects.get(code=DEFAULT_PACKAGE_CODE)
        make_profile()  # lands on the default tier
        # Clear the price history so the only thing guarding the tier here
        # is the business relation under test.
        free.price_history.all().delete()

        with self.assertRaises(ProtectedError):
            with transaction.atomic():
                free.delete()

        free.refresh_from_db()
        self.assertTrue(BusinessProfile.objects.filter(package=free).exists())

    def test_a_tier_with_no_business_on_it_can_be_deleted(self):
        PackagesSeeder().run()
        pro = Package.objects.get(code="pro")
        pro.price_history.all().delete()

        with transaction.atomic():
            pro.delete()

        self.assertFalse(Package.objects.filter(code="pro").exists())

    def test_price_history_alone_also_blocks_deletion(self):
        # Worth stating plainly: because history is written on every create
        # and is PROTECT, no seeded tier is deletable in practice.
        PackagesSeeder().run()
        pro = Package.objects.get(code="pro")

        with self.assertRaises(ProtectedError):
            with transaction.atomic():
                pro.delete()

    def test_deleting_the_business_is_not_blocked_by_the_relation(self):
        PackagesSeeder().run()
        business = make_profile()

        business.delete()

        # `inventory.0022` seeds a BusinessProfile into every test database,
        # so assert on this row rather than on a global count.
        self.assertFalse(BusinessProfile.objects.filter(pk=business.pk).exists())
        # The tier survives the business that was on it.
        self.assertTrue(Package.objects.filter(code=DEFAULT_PACKAGE_CODE).exists())


class BusinessPackageBackfillTests(TestCase):
    def test_backfill_assigns_the_default_to_null_rows(self):
        PackagesSeeder().run()
        business = make_profile()
        BusinessProfile.objects.filter(pk=business.pk).update(package=None)

        backfill_default_package(global_apps, None)

        business.refresh_from_db()
        self.assertEqual(business.package.code, DEFAULT_PACKAGE_CODE)

    def test_backfill_leaves_an_explicitly_assigned_tier_alone(self):
        PackagesSeeder().run()
        plus = Package.objects.get(code="plus")
        business = make_profile(package=plus)

        backfill_default_package(global_apps, None)

        business.refresh_from_db()
        self.assertEqual(business.package, plus)

    def test_backfill_is_a_noop_when_packages_are_not_seeded(self):
        business = make_profile()
        self.assertIsNone(business.package_id)

        backfill_default_package(global_apps, None)

        business.refresh_from_db()
        self.assertIsNone(business.package_id)


class BusinessPackageSerializerTests(TestCase):
    def setUp(self):
        PackagesSeeder().run()
        self.business = make_profile()

    def test_admin_serializer_exposes_the_package(self):
        data = BusinessProfileSerializer(self.business).data

        self.assertIn("package", data)
        self.assertEqual(data["package"], self.business.package_id)

    def test_public_serializer_hides_the_package(self):
        data = PublicBusinessProfileSerializer(self.business).data

        self.assertNotIn("package", data)
        self.assertNotIn("package_id", data)

    def test_package_code_property_is_not_serialized_by_any_field_all(self):
        # `package_code` is a property, not a model field, so `__all__` and
        # `exclude` must not pick it up and leak it to either audience.
        self.assertNotIn("package_code", BusinessProfileSerializer(self.business).data)
        self.assertNotIn(
            "package_code", PublicBusinessProfileSerializer(self.business).data
        )

    def test_default_package_code_matches_the_seeded_tiers(self):
        # The constant lives in models while the seed row lives in the pure
        # data module; this guards the two from drifting apart.
        self.assertIn(
            DEFAULT_PACKAGE_CODE, {record["code"] for record in PACKAGE_SEED}
        )
        self.assertTrue(
            Package.objects.filter(code=DEFAULT_PACKAGE_CODE).exists()
        )
        self.assertEqual(
            Package.objects.get(code=DEFAULT_PACKAGE_CODE).price, Decimal("0.00")
        )


class BusinessPackageAPITests(APITestCase):
    def setUp(self):
        PackagesSeeder().run()
        self.admin = User.objects.create_superuser("biz-pkg", password="password")
        self.client.force_authenticate(self.admin)
        # `inventory.0022` seeds a BusinessProfile into every test database,
        # so counts are asserted as deltas from this baseline.
        self.baseline = BusinessProfile.objects.count()

    def test_admin_create_without_a_package_lands_on_the_default(self):
        response = self.client.post(BUSINESS_ADMIN, PROFILE, format="json")

        self.assertEqual(response.status_code, 201)
        business = BusinessProfile.objects.get(pk=response.data["data"]["id"])
        self.assertEqual(business.package.code, DEFAULT_PACKAGE_CODE)

    def test_admin_create_with_an_explicit_package_keeps_it(self):
        plus = Package.objects.get(code="plus")

        response = self.client.post(
            BUSINESS_ADMIN, {**PROFILE, "package": plus.id}, format="json"
        )

        self.assertEqual(response.status_code, 201)
        business = BusinessProfile.objects.get(pk=response.data["data"]["id"])
        self.assertEqual(business.package, plus)

    def test_admin_create_with_an_unknown_package_is_rejected(self):
        response = self.client.post(
            BUSINESS_ADMIN, {**PROFILE, "package": 999999}, format="json"
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("package", response.data["errors"])
        self.assertEqual(BusinessProfile.objects.count(), self.baseline)

    def test_admin_patch_can_move_a_business_to_another_tier(self):
        business = make_profile()
        pro = Package.objects.get(code="pro")

        response = self.client.patch(
            f"{BUSINESS_ADMIN}/{business.id}", {"package": pro.id}, format="json"
        )

        self.assertEqual(response.status_code, 200)
        business.refresh_from_db()
        self.assertEqual(business.package, pro)

    def test_admin_patch_with_an_unknown_package_is_rejected(self):
        business = make_profile()

        response = self.client.patch(
            f"{BUSINESS_ADMIN}/{business.id}", {"package": 999999}, format="json"
        )

        self.assertEqual(response.status_code, 400)
        business.refresh_from_db()
        self.assertEqual(business.package.code, DEFAULT_PACKAGE_CODE)

    def test_admin_delete_of_a_business_still_works(self):
        business = make_profile()

        response = self.client.delete(f"{BUSINESS_ADMIN}/{business.id}")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(BusinessProfile.objects.count(), self.baseline)

    def test_admin_list_reports_the_tier_id_for_the_business_it_reads(self):
        business = make_profile()

        response = self.client.get(BUSINESS_ADMIN)

        self.assertEqual(response.status_code, 200)
        row = next(
            item for item in response.data["data"]["results"] if item["id"] == business.id
        )
        self.assertEqual(row["package"], business.package_id)
        self.assertNotIn("package_code", row)
