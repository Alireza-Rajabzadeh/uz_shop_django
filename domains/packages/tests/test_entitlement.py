"""Entitlement: what a seller's package makes available, and what happens
when they reach for something it does not include.

Three layers answer the same question here: the splash payload
(``/api/packages/me``), the area gates on products and orders, and the
count rule past the baseline warehouse. Two properties matter throughout.
A denial is 402 with the standard envelope — never 403, which the panels
read as a dead session and would log the seller out. And an environment
with no provisioned tier denies nothing: only an existing tier can say no.
"""

from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from core.management.seeders.marketplace_order import MarketplaceOrderSeeder
from core.management.seeders.packages import PackagesSeeder
from domains.business.enums.BusinessStatusEnum import BusinessStatusEnum
from domains.business.models import BusinessProfile
from domains.inventory.models import Warehouse, WarehouseStatus
from domains.location.models import City, Country, State
from domains.packages.models import Package, PackageFeature
from domains.vendor.models import Vendor, VendorStatus

ME = "/api/packages/me"
CATALOG = "/api/packages/catalog"
PRODUCTS = "/api/vendor/products"
ORDERS = "/api/vendor/orders"
WAREHOUSES = "/api/vendor/warehouses"
LANDING_PAGES = "/api/business-content/vendor/landing-pages"

FREE_FEATURES = {"shop.products", "shop.orders"}
PRO_FEATURES = FREE_FEATURES | {
    "shop.coupons",
    "shop.custom_domain",
    "shop.advanced_analytics",
    "shop.multiple_warehouses",
    "shop.api",
    "content.landingpage",
}


class EntitlementFixture(APITestCase):
    """A seller with a business, on the seeded tiers."""

    def setUp(self):
        PackagesSeeder().run()
        self.business = self.make_seller("VEN-ENT-001", "+9990001001")
        self.as_vendor(self.business.vendor)

        country = Country.objects.create(name="Ent Country", code="EC", phone_code="+1")
        state = State.objects.create(name="Ent State", country=country)
        self.city = City.objects.create(name="Ent City", state=state)
        self.warehouse_status = WarehouseStatus.objects.create(name="available-ent")

    # ───────────────────────── fixtures ─────────────────────────

    def make_seller(self, vendor_code, phone):
        status, _ = VendorStatus.objects.get_or_create(
            name="active", defaults={"title": "Active"}
        )
        vendor = Vendor.objects.create(
            phone=phone,
            first_name="Seller",
            last_name=vendor_code,
            national_id="0000001099",
            vendor_code=vendor_code,
            status=status,
        )
        return BusinessProfile.objects.create(
            vendor=vendor,
            business_name=f"Shop {vendor_code}",
            display_name=f"Shop {vendor_code}",
            # Fixture businesses are trading: the lifecycle gate stays open.
            status_id=BusinessStatusEnum.ACTIVE.value,
        )

    def as_vendor(self, vendor):
        refresh = RefreshToken.for_user(vendor)
        refresh["user_type"] = "vendor"
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")

    def as_anonymous(self):
        self.client.credentials()

    def put_on_package(self, code):
        self.business.package = Package.objects.get(code=code)
        self.business.save()

    def make_warehouse(self):
        return Warehouse.objects.create(
            name="Existing Warehouse",
            business=self.business,
            city=self.city,
            address="Somewhere",
            lat="0",
            lng="0",
            status=self.warehouse_status,
        )

    def warehouse_payload(self, name="Second Warehouse"):
        return {
            "name": name,
            "city": self.city.id,
            "address": "Somewhere else",
            "lat": "1.000000",
            "lng": "1.000000",
            "phone_numbers": ["09120000001"],
            "status": self.warehouse_status.id,
        }

    def assert_denied(self, response):
        """A tier denial: 402, the standard envelope, and no data."""
        self.assertEqual(response.status_code, 402)
        self.assertFalse(response.data["success"])
        self.assertIsNone(response.data["data"])
        self.assertTrue(response.data["message"])


class PackageMeTests(EntitlementFixture):
    def test_anonymous_is_rejected(self):
        self.as_anonymous()

        response = self.client.get(ME)

        self.assertIn(response.status_code, (401, 403))

    def test_the_default_tier_reports_its_own_grants(self):
        response = self.client.get(ME)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["package"], "free")
        self.assertEqual(set(response.data["data"]["features"]), FREE_FEATURES)

    def test_the_top_tier_reports_the_full_surface(self):
        self.put_on_package("pro")

        response = self.client.get(ME)

        self.assertEqual(response.data["data"]["package"], "pro")
        self.assertEqual(set(response.data["data"]["features"]), PRO_FEATURES)

    def test_a_disabled_grant_is_not_reported_as_available(self):
        grant = PackageFeature.objects.get(
            package__code="free", feature__code="shop.orders"
        )
        grant.config = {"enabled": False}
        grant.save()

        response = self.client.get(ME)

        self.assertEqual(set(response.data["data"]["features"]), {"shop.products"})

    def test_an_inactive_tier_reports_no_features(self):
        self.put_on_package("plus")
        plus = Package.objects.get(code="plus")
        plus.is_active = False
        plus.save()

        response = self.client.get(ME)

        self.assertEqual(response.data["data"]["package"], "plus")
        self.assertEqual(response.data["data"]["features"], [])

    def test_a_null_package_reads_as_the_default_tier(self):
        # The stored relation is empty; the endpoint must still answer with
        # the default tier rather than with nothing.
        BusinessProfile.objects.filter(pk=self.business.pk).update(package=None)

        response = self.client.get(ME)

        self.assertEqual(response.data["data"]["package"], "free")
        self.assertEqual(set(response.data["data"]["features"]), FREE_FEATURES)

    def test_a_vendor_without_a_profile_gets_the_default_tier(self):
        status, _ = VendorStatus.objects.get_or_create(
            name="active", defaults={"title": "Active"}
        )
        vendor = Vendor.objects.create(
            phone="+9990001002",
            first_name="No",
            last_name="Profile",
            national_id="0000001098",
            vendor_code="VEN-ENT-002",
            status=status,
        )
        self.as_vendor(vendor)

        response = self.client.get(ME)

        # The splash must not dead-end an account that has not created its
        # shop yet, so this answers instead of 404ing.
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["package"], "free")
        self.assertEqual(set(response.data["data"]["features"]), FREE_FEATURES)


class AreaGateTests(EntitlementFixture):
    def put_on_a_package_without_features(self):
        bare = Package.objects.create(
            code="bare", name="Bare", price="0.00", off_discount="0.00"
        )
        self.business.package = bare
        self.business.save()

    def test_products_are_denied_without_the_feature(self):
        self.put_on_a_package_without_features()

        response = self.client.get(PRODUCTS)

        self.assert_denied(response)

    def test_products_are_readable_on_the_default_tier(self):
        response = self.client.get(PRODUCTS)

        self.assertEqual(response.status_code, 200)

    def test_orders_are_denied_without_the_feature(self):
        self.put_on_a_package_without_features()

        response = self.client.get(ORDERS)

        self.assert_denied(response)

    def test_orders_are_readable_on_the_default_tier(self):
        MarketplaceOrderSeeder().run()

        response = self.client.get(ORDERS)

        self.assertEqual(response.status_code, 200)

    def test_a_vendor_without_a_profile_is_not_denied(self):
        # No profile means no tier to apply; the view keeps whatever
        # behaviour it already had for that state.
        status, _ = VendorStatus.objects.get_or_create(
            name="active", defaults={"title": "Active"}
        )
        vendor = Vendor.objects.create(
            phone="+9990001003",
            first_name="No",
            last_name="Profile",
            national_id="0000001097",
            vendor_code="VEN-ENT-003",
            status=status,
        )
        self.as_vendor(vendor)

        self.assertNotEqual(self.client.get(PRODUCTS).status_code, 402)
        self.assertNotEqual(self.client.get(ORDERS).status_code, 402)

    def test_the_denial_is_402_so_the_panel_keeps_the_session(self):
        self.put_on_a_package_without_features()

        response = self.client.get(PRODUCTS)

        # Explicitly not 403: the panels invalidate the session on 401/403.
        self.assertNotEqual(response.status_code, 403)
        self.assert_denied(response)


class WarehouseCapacityTests(EntitlementFixture):
    def test_the_first_warehouse_needs_no_feature(self):
        # A bare package grants nothing, yet the baseline location stands.
        bare = Package.objects.create(
            code="bare-wh", name="Bare WH", price="0.00", off_discount="0.00"
        )
        self.business.package = bare
        self.business.save()

        response = self.client.post(WAREHOUSES, self.warehouse_payload(), format="json")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Warehouse.objects.filter(business=self.business).count(), 1)

    def test_a_second_warehouse_is_denied_without_the_feature(self):
        self.make_warehouse()

        response = self.client.post(WAREHOUSES, self.warehouse_payload(), format="json")

        self.assert_denied(response)
        self.assertEqual(Warehouse.objects.filter(business=self.business).count(), 1)

    def test_the_feature_allows_more_warehouses_up_to_the_limit(self):
        self.put_on_package("pro")
        self.make_warehouse()

        response = self.client.post(WAREHOUSES, self.warehouse_payload(), format="json")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Warehouse.objects.filter(business=self.business).count(), 2)

    def test_the_limit_stops_warehouse_creation(self):
        self.put_on_package("pro")
        grant = PackageFeature.objects.get(
            package__code="pro", feature__code="shop.multiple_warehouses"
        )
        grant.config = {"enabled": True, "limit": 1}
        grant.save()
        self.make_warehouse()

        response = self.client.post(WAREHOUSES, self.warehouse_payload(), format="json")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(Warehouse.objects.filter(business=self.business).count(), 1)


class UnprovisionedEnvironmentTests(APITestCase):
    """Migrated but never seeded: no entitlement data exists to enforce."""

    def setUp(self):
        status, _ = VendorStatus.objects.get_or_create(
            name="active", defaults={"title": "Active"}
        )
        vendor = Vendor.objects.create(
            phone="+9990001004",
            first_name="Seedless",
            last_name="Seller",
            national_id="0000001096",
            vendor_code="VEN-ENT-004",
            status=status,
        )
        self.business = BusinessProfile.objects.create(
            vendor=vendor,
            business_name="Seedless Shop",
            display_name="Seedless Shop",
            status_id=BusinessStatusEnum.ACTIVE.value,
        )
        refresh = RefreshToken.for_user(vendor)
        refresh["user_type"] = "vendor"
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")

        country = Country.objects.create(name="Seedless Country", code="SX", phone_code="+1")
        state = State.objects.create(name="Seedless State", country=country)
        self.city = City.objects.create(name="Seedless City", state=state)
        self.warehouse_status = WarehouseStatus.objects.create(name="available-seedless")

    def test_the_splash_reports_no_entitlement_data(self):
        response = self.client.get(ME)

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.data["data"]["package"])
        self.assertIsNone(response.data["data"]["features"])

    def test_nothing_is_denied(self):
        self.assertNotEqual(self.client.get(PRODUCTS).status_code, 402)
        self.assertNotEqual(self.client.get(ORDERS).status_code, 402)

    def test_warehouse_creation_is_not_denied_either(self):
        # Past the baseline there is still no tier to consult, so the count
        # rule must not invent a refusal.
        Warehouse.objects.create(
            name="First",
            business=self.business,
            city=self.city,
            address="Somewhere",
            lat="0",
            lng="0",
            status=self.warehouse_status,
        )

        response = self.client.post(
            WAREHOUSES,
            {
                "name": "Second",
                "city": self.city.id,
                "address": "Elsewhere",
                "lat": "1.000000",
                "lng": "1.000000",
                "phone_numbers": ["09120000002"],
                "status": self.warehouse_status.id,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Warehouse.objects.filter(business=self.business).count(), 2)


class CatalogTests(EntitlementFixture):
    """The feature/package map the panels cache to name upgrade targets."""

    def feature(self, code):
        return next(
            row for row in self.client.get(CATALOG).data["data"]["features"]
            if row["code"] == code
        )

    def test_anonymous_is_rejected(self):
        self.as_anonymous()

        self.assertIn(self.client.get(CATALOG).status_code, (401, 403))

    def test_packages_arrive_cheapest_first(self):
        response = self.client.get(CATALOG)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [row["code"] for row in response.data["data"]["packages"]],
            ["free", "plus", "pro"],
        )

    def test_a_feature_lists_the_packages_that_grant_it(self):
        self.assertEqual(
            self.feature("shop.products")["packages"], ["free", "plus", "pro"]
        )

    def test_a_gated_feature_points_at_its_upgrade_target(self):
        landing = self.feature("content.landingpage")

        # The free seller lacks it; the first (cheapest) package that has
        # it is what the panel's badge names.
        self.assertEqual(landing["packages"], ["pro"])

    def test_a_disabled_grant_is_not_an_upgrade_target(self):
        grant = PackageFeature.objects.get(
            package__code="pro", feature__code="shop.api"
        )
        grant.config = {"enabled": False}
        grant.save()

        self.assertEqual(self.feature("shop.api")["packages"], [])

    def test_an_inactive_tier_is_not_an_upgrade_target(self):
        plus = Package.objects.get(code="plus")
        plus.is_active = False
        plus.save()

        response = self.client.get(CATALOG)

        self.assertEqual(
            [row["code"] for row in response.data["data"]["packages"]],
            ["free", "pro"],
        )
        self.assertEqual(self.feature("shop.coupons")["packages"], ["pro"])


class LandingPageGateTests(EntitlementFixture):
    """`content.landingpage` enforced on the authoring routes."""

    def test_the_default_tier_is_denied(self):
        response = self.client.get(LANDING_PAGES)

        self.assert_denied(response)

    def test_the_top_tier_reads_the_list(self):
        self.put_on_package("pro")

        response = self.client.get(LANDING_PAGES)

        self.assertEqual(response.status_code, 200)

    def test_a_detail_write_is_denied_too(self):
        response = self.client.post(
            f"{LANDING_PAGES}/1/publish", {}, format="json"
        )

        self.assert_denied(response)

    def test_anonymous_is_rejected(self):
        self.as_anonymous()

        self.assertIn(self.client.get(LANDING_PAGES).status_code, (401, 403))
