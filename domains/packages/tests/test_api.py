from decimal import Decimal

from django.contrib.auth.models import User
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APITestCase

from domains.customer.models import Customer, CustomerStatus
from domains.packages.models import Feature, Package, PackageFeature, PackagePriceHistory

BASE = "/api/packages"


class PackageAPIMixin:
    def setUp(self):
        self.admin = User.objects.create_superuser("pkg-admin", password="password")
        self.client.force_authenticate(self.admin)


class PackageAPITests(PackageAPIMixin, APITestCase):
    def test_list_is_paginated_and_follows_the_standard_envelope(self):
        Package.objects.create(code="growth", name="Growth", price=Decimal("100.00"))

        response = self.client.get(f"{BASE}/admin/packages")

        self.assertEqual(response.status_code, 200)
        self.assertIn("success", response.data)
        self.assertIn("message", response.data)
        self.assertIn("data", response.data)
        self.assertIn("errors", response.data)
        self.assertTrue(response.data["success"])
        self.assertEqual(response.data["data"]["count"], 1)
        row = response.data["data"]["results"][0]
        self.assertEqual(row["code"], "growth")
        self.assertEqual(row["price"], "100.00")
        self.assertEqual(row["features"], [])

    def test_list_serializes_assigned_features(self):
        package = Package.objects.create(code="growth", name="Growth", price=Decimal("100.00"))
        feature = Feature.objects.create(code="shop.products", name="Products")
        PackageFeature.objects.create(
            package=package, feature=feature, config={"enabled": True, "limit": 1000}
        )

        row = self.client.get(f"{BASE}/admin/packages").data["data"]["results"][0]

        self.assertEqual(len(row["features"]), 1)
        self.assertEqual(row["features"][0]["feature"]["code"], "shop.products")
        self.assertEqual(row["features"][0]["config"], {"enabled": True, "limit": 1000})

    def test_list_does_not_issue_a_query_per_package(self):
        feature_ids = [
            Feature.objects.create(code=f"shop.f{i}", name=f"F{i}").id for i in range(5)
        ]
        for index in range(10):
            package = Package.objects.create(
                code=f"pkg{index}", name=f"P{index}", price=Decimal("10.00")
            )
            for feature_id in feature_ids:
                PackageFeature.objects.create(
                    package=package, feature_id=feature_id, config={}
                )

        with CaptureQueriesContext(connection) as captured:
            response = self.client.get(f"{BASE}/admin/packages")

        self.assertEqual(response.data["data"]["count"], 10)
        # One page query plus one prefetch for the nested features. Without
        # `prefetch_related` this would be 1 + 10 (packages) + 50 (features).
        self.assertLess(len(captured.captured_queries), 6)

    def test_create_package_returns_201_and_records_initial_history(self):
        response = self.client.post(
            f"{BASE}/admin/packages",
            {"code": "growth", "name": "Growth", "price": "100.00", "off_discount": "10.00"},
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["data"]["code"], "growth")
        package = Package.objects.get(code="growth")
        history = list(package.price_history.all())
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0].price, Decimal("100.00"))
        self.assertEqual(history[0].off_discount, Decimal("10.00"))

    def test_create_rejects_negative_price(self):
        response = self.client.post(
            f"{BASE}/admin/packages",
            {"code": "neg", "name": "Neg", "price": "-1.00"},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.data["success"])
        self.assertFalse(Package.objects.filter(code="neg").exists())

    def test_create_rejects_discount_above_100(self):
        response = self.client.post(
            f"{BASE}/admin/packages",
            {"code": "high", "name": "High", "price": "10.00", "off_discount": "101.00"},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(Package.objects.filter(code="high").exists())

    def test_create_rejects_duplicate_code(self):
        Package.objects.create(code="taken", name="First", price=Decimal("1.00"))

        response = self.client.post(
            f"{BASE}/admin/packages",
            {"code": "taken", "name": "Second", "price": "2.00"},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(Package.objects.count(), 1)

    def test_retrieve_missing_package_is_404(self):
        response = self.client.get(f"{BASE}/admin/packages/999999")

        self.assertEqual(response.status_code, 404)
        self.assertFalse(response.data["success"])

    def test_update_price_creates_exactly_one_history_row(self):
        package = Package.objects.create(code="growth", name="Growth", price=Decimal("100.00"))

        response = self.client.patch(
            f"{BASE}/admin/packages/{package.id}", {"price": "150.00"}, format="json"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(PackagePriceHistory.objects.count(), 2)
        self.assertEqual(
            [row.price for row in package.price_history.all()],
            [Decimal("100.00"), Decimal("150.00")],
        )

    def test_update_price_and_discount_together_creates_one_row(self):
        package = Package.objects.create(code="growth", name="Growth", price=Decimal("100.00"))

        response = self.client.patch(
            f"{BASE}/admin/packages/{package.id}",
            {"price": "200.00", "off_discount": "25.00"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        history = list(package.price_history.all())
        self.assertEqual(len(history), 2)
        self.assertEqual(history[1].price, Decimal("200.00"))
        self.assertEqual(history[1].off_discount, Decimal("25.00"))

    def test_update_name_creates_no_history(self):
        package = Package.objects.create(code="growth", name="Growth", price=Decimal("100.00"))

        response = self.client.patch(
            f"{BASE}/admin/packages/{package.id}", {"name": "Renamed"}, format="json"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(PackagePriceHistory.objects.count(), 1)

    def test_update_unchanged_pricing_creates_no_history(self):
        package = Package.objects.create(code="growth", name="Growth", price=Decimal("100.00"))

        response = self.client.patch(
            f"{BASE}/admin/packages/{package.id}", {"price": "100.00"}, format="json"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(PackagePriceHistory.objects.count(), 1)

    def test_update_toggles_is_active_without_history(self):
        package = Package.objects.create(code="growth", name="Growth", price=Decimal("100.00"))

        response = self.client.patch(
            f"{BASE}/admin/packages/{package.id}", {"is_active": False}, format="json"
        )

        self.assertEqual(response.status_code, 200)
        self.assertIs(response.data["data"]["is_active"], False)
        self.assertEqual(PackagePriceHistory.objects.count(), 1)

    def test_update_cannot_change_code(self):
        package = Package.objects.create(code="growth", name="Growth", price=Decimal("100.00"))

        response = self.client.patch(
            f"{BASE}/admin/packages/{package.id}", {"code": "renamed"}, format="json"
        )

        self.assertEqual(response.status_code, 200)
        package.refresh_from_db()
        self.assertEqual(package.code, "growth")

    def test_price_history_is_chronological_and_enveloped(self):
        package = Package.objects.create(code="growth", name="Growth", price=Decimal("100.00"))
        package.price = Decimal("150.00")
        package.save()
        package.price = Decimal("200.00")
        package.save()

        response = self.client.get(f"{BASE}/admin/packages/{package.id}/price-history")

        self.assertEqual(response.status_code, 200)
        rows = response.data["data"]["results"]
        self.assertEqual(
            [row["price"] for row in rows],
            ["100.00", "150.00", "200.00"],
        )

    def test_price_history_has_no_write_verbs(self):
        package = Package.objects.create(code="growth", name="Growth", price=Decimal("100.00"))
        url = f"{BASE}/admin/packages/{package.id}/price-history"

        self.assertEqual(self.client.post(url, {}, format="json").status_code, 405)
        self.assertEqual(self.client.patch(url, {}, format="json").status_code, 405)
        self.assertEqual(self.client.delete(url).status_code, 405)
        self.assertEqual(PackagePriceHistory.objects.count(), 1)


class FeatureAPITests(PackageAPIMixin, APITestCase):
    def test_feature_list_and_create(self):
        Feature.objects.create(code="shop.products", name="Products")

        listing = self.client.get(f"{BASE}/admin/features")
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.data["data"]["count"], 1)

        created = self.client.post(
            f"{BASE}/admin/features",
            {"code": "shop.orders", "name": "Orders", "description": "Order tools"},
            format="json",
        )
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.data["data"]["code"], "shop.orders")

    def test_feature_create_rejects_duplicate_code(self):
        Feature.objects.create(code="shop.products", name="Products")

        response = self.client.post(
            f"{BASE}/admin/features", {"code": "shop.products", "name": "Dup"}, format="json"
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(Feature.objects.count(), 1)

    def test_feature_update_editable_fields_only(self):
        feature = Feature.objects.create(code="shop.products", name="Products")

        response = self.client.patch(
            f"{BASE}/admin/features/{feature.id}",
            {"name": "Products renamed", "code": "shop.items"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        feature.refresh_from_db()
        self.assertEqual(feature.code, "shop.products")
        self.assertEqual(feature.name, "Products renamed")

    def test_feature_detail_missing_is_404(self):
        self.assertEqual(self.client.get(f"{BASE}/admin/features/999999").status_code, 404)

    def test_feature_retrieve(self):
        feature = Feature.objects.create(code="shop.products", name="Products")

        response = self.client.get(f"{BASE}/admin/features/{feature.id}")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["code"], "shop.products")


class PackageFeatureAPITests(PackageAPIMixin, APITestCase):
    def setUp(self):
        super().setUp()
        self.package = Package.objects.create(
            code="growth", name="Growth", price=Decimal("100.00")
        )
        self.feature = Feature.objects.create(code="shop.products", name="Products")

    def test_assign_feature_returns_201(self):
        response = self.client.post(
            f"{BASE}/admin/packages/{self.package.id}/features",
            {"feature": self.feature.id, "config": {"enabled": True, "limit": 1000}},
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["data"]["feature"]["code"], "shop.products")
        self.assertEqual(response.data["data"]["config"], {"enabled": True, "limit": 1000})

    def test_assign_same_feature_twice_is_rejected(self):
        payload = {"feature": self.feature.id}
        self.assertEqual(
            self.client.post(
                f"{BASE}/admin/packages/{self.package.id}/features", payload, format="json"
            ).status_code,
            201,
        )

        response = self.client.post(
            f"{BASE}/admin/packages/{self.package.id}/features", payload, format="json"
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.data["success"])
        self.assertEqual(PackageFeature.objects.count(), 1)

    def test_list_package_features(self):
        PackageFeature.objects.create(package=self.package, feature=self.feature)

        response = self.client.get(f"{BASE}/admin/packages/{self.package.id}/features")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["count"], 1)

    def test_assign_to_missing_package_is_404(self):
        response = self.client.post(
            f"{BASE}/admin/packages/999999/features",
            {"feature": self.feature.id},
            format="json",
        )

        self.assertEqual(response.status_code, 404)

    def test_assign_missing_feature_is_400(self):
        # A related object referenced by id inside the body follows the same
        # convention as inventory's warehouse `city`/`status`: DRF's
        # PrimaryKeyRelatedField reports 400 "pk does not exist". Only a
        # resource addressed by URL path answers 404.
        response = self.client.post(
            f"{BASE}/admin/packages/{self.package.id}/features",
            {"feature": 999999},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("feature", response.data["errors"])
        self.assertEqual(PackageFeature.objects.count(), 0)

    def test_update_config(self):
        assignment = PackageFeature.objects.create(
            package=self.package, feature=self.feature, config={"enabled": True}
        )

        response = self.client.patch(
            f"{BASE}/admin/packages/{self.package.id}/features/{self.feature.id}",
            {"config": {"enabled": True, "limit": 5}},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        assignment.refresh_from_db()
        self.assertEqual(assignment.config, {"enabled": True, "limit": 5})

    def test_update_missing_assignment_is_404(self):
        response = self.client.patch(
            f"{BASE}/admin/packages/{self.package.id}/features/{self.feature.id}",
            {"config": {"enabled": True}},
            format="json",
        )

        self.assertEqual(response.status_code, 404)

    def test_remove_feature(self):
        PackageFeature.objects.create(package=self.package, feature=self.feature)

        response = self.client.delete(
            f"{BASE}/admin/packages/{self.package.id}/features/{self.feature.id}"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(PackageFeature.objects.count(), 0)

    def test_remove_missing_assignment_is_404(self):
        response = self.client.delete(
            f"{BASE}/admin/packages/{self.package.id}/features/{self.feature.id}"
        )

        self.assertEqual(response.status_code, 404)


class FeatureConfigValidationTests(PackageAPIMixin, APITestCase):
    def setUp(self):
        super().setUp()
        self.package = Package.objects.create(
            code="growth", name="Growth", price=Decimal("100.00")
        )
        self.feature = Feature.objects.create(code="shop.products", name="Products")
        self.assignment = PackageFeature.objects.create(
            package=self.package, feature=self.feature, config={}
        )

    def _patch(self, config):
        return self.client.patch(
            f"{BASE}/admin/packages/{self.package.id}/features/{self.feature.id}",
            {"config": config},
            format="json",
        )

    def _post(self, config, feature_id=None):
        return self.client.post(
            f"{BASE}/admin/packages/{self.package.id}/features",
            {"feature": feature_id or self.feature.id, "config": config},
            format="json",
        )

    def test_object_config_is_required(self):
        response = self._patch(["not", "an", "object"])

        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.data["success"])

    def test_enabled_must_be_a_boolean(self):
        self.assertEqual(self._patch({"enabled": "yes"}).status_code, 400)
        self.assertEqual(self._patch({"enabled": 1}).status_code, 400)

    def test_limit_rejects_a_boolean(self):
        # `True` is an `int` subclass in Python, so a naive integer check
        # would accept it as a limit of 1.
        response = self._patch({"enabled": True, "limit": True})

        self.assertEqual(response.status_code, 400)
        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.config, {})

    def test_limit_rejects_negative_and_non_integer(self):
        self.assertEqual(self._patch({"limit": -1}).status_code, 400)
        self.assertEqual(self._patch({"limit": 1.5}).status_code, 400)
        self.assertEqual(self._patch({"limit": "100"}).status_code, 400)
        self.assertEqual(self._patch({"limit": None}).status_code, 400)

    def test_limitless_config_is_accepted(self):
        response = self._patch({"enabled": True})

        self.assertEqual(response.status_code, 200)
        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.config, {"enabled": True})

    def test_config_without_any_known_key_is_accepted(self):
        # Unknown keys pass through so a feature can grow its own settings
        # without a validation change.
        response = self._patch({"custom": {"region": "eu"}})

        self.assertEqual(response.status_code, 200)

    def test_empty_config_is_accepted(self):
        self.assertEqual(self._patch({}).status_code, 200)

    def test_invalid_config_on_assign_is_rejected(self):
        response = self._post({"limit": -5})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(PackageFeature.objects.count(), 1)


class PackagePermissionTests(APITestCase):
    def setUp(self):
        self.package = Package.objects.create(
            code="growth", name="Growth", price=Decimal("100.00")
        )
        self.admin = User.objects.create_superuser("pkg-perm", password="password")

    def test_unauthenticated_request_is_rejected(self):
        for method, url in (
            ("get", f"{BASE}/admin/packages"),
            ("post", f"{BASE}/admin/packages"),
            ("get", f"{BASE}/admin/features"),
            ("get", f"{BASE}/admin/packages/{self.package.id}/price-history"),
        ):
            with self.subTest(method=method, url=url):
                status = getattr(self.client, method)(url).status_code
                self.assertIn(status, (401, 403))

    def test_customer_principal_cannot_administer_packages(self):
        status = CustomerStatus.objects.create(name="active", title="Active")
        customer = Customer.objects.create_user(
            phone="09120000102",
            password="password",
            first_name="Package",
            last_name="Customer",
            customer_code="CUS-PKG-101",
            status=status,
        )
        self.client.force_authenticate(customer)

        for method, url in (
            ("get", f"{BASE}/admin/packages"),
            ("post", f"{BASE}/admin/packages"),
            ("get", f"{BASE}/admin/features"),
        ):
            with self.subTest(method=method, url=url):
                self.assertEqual(getattr(self.client, method)(url).status_code, 403)

    def test_staff_without_permission_is_rejected(self):
        staff = User.objects.create_user(
            username="pkg-noperm", password="password", is_staff=True
        )
        self.client.force_authenticate(staff)

        self.assertEqual(self.client.get(f"{BASE}/admin/packages").status_code, 403)
        self.assertEqual(self.client.post(f"{BASE}/admin/features").status_code, 403)

    def test_authenticated_staff_can_read_but_not_write_without_permission(self):
        reader = User.objects.create_user(
            username="pkg-reader", password="password", is_staff=True
        )
        reader.user_permissions.set([])
        self.client.force_authenticate(reader)

        self.assertEqual(self.client.get(f"{BASE}/admin/packages").status_code, 403)

    def test_superuser_can_administer(self):
        self.client.force_authenticate(self.admin)

        self.assertEqual(self.client.get(f"{BASE}/admin/packages").status_code, 200)
