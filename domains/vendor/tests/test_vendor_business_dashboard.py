"""The two blocks the vendor dashboard asks its own endpoint for.

The dashboard is the page a seller lands on, and it answers with their profile,
their working days, their ongoing orders and open return requests, and the
configuration a customer sees. Four things have to hold: every group only ever
covers the caller's business, "ongoing" means exactly what the order list
already means by it, a seller whose package withholds orders gets a dashboard
rather than a 402, and a setting nobody configured comes back empty rather than
missing so the panel can say "not set" instead of hiding the section.
"""

from decimal import Decimal

from core.management.seeders.configs.business_service_modes import BusinessServiceModeSeeder
from core.management.seeders.configs.packages import PackagesSeeder
from core.management.seeders.configs.shipment import ShipmentSeeder
from domains.business.models import (
    BusinessCategory,
    BusinessCharge,
    BusinessProfileServiceMode,
    BusinessServiceMode,
    BusinessShipment,
)
from domains.catalog.models import Category, CategoryStatus
from domains.marketplace.models import MarketplaceReturnRequest
from domains.order.flow import BaseOrderService
from domains.packages.models import Package, PackageFeature
from domains.packages.permissions import RequiresShopOrders
from domains.shipment.models import ShipmentMethod, ShipmentPricingMethod
from domains.vendor.models import Vendor, VendorStatus
from domains.vendor.views.business import VendorBusinessDashboardView

from .test_vendor_orders import VendorOrderApiFixture

DASHBOARD = "/api/vendor/business/dashboard"
SETTINGS_KEYS = ["categories", "charges", "service_modes", "shipments"]


class DashboardRequestMixin:
    """One dashboard call, shared by the two test classes beside it."""

    def dashboard(self):
        response = self.client.get(DASHBOARD)
        self.assertEqual(response.status_code, 200)
        return response.data["data"]


class VendorBusinessDashboardSummaryTests(DashboardRequestMixin, VendorOrderApiFixture):
    def setUp(self):
        super().setUp()
        self.summary = self.dashboard()["summary"]

    # ───────────────────────── fixtures ─────────────────────────

    def make_return(self, order, *, status="requested"):
        return MarketplaceReturnRequest.objects.create(
            order=order,
            customer=self.customer,
            status=status,
            reason="Broken on arrival",
            refund_destination_type="card",
            refund_destination_value="6037991234567890",
        )

    def on_default_tier(self):
        """Put the caller's business on `free`, whose grants the tests edit."""
        PackagesSeeder().run()
        self.business.package = Package.objects.get(code="free")
        self.business.save()
        return PackageFeature.objects.get(
            package__code="free", feature__code="shop.orders"
        )

    # ───────────────────────── the shape ─────────────────────────

    def test_the_summary_carries_both_groups(self):
        self.assertEqual(sorted(self.summary), ["ongoing_orders", "ongoing_returns"])
        for group in self.summary.values():
            self.assertEqual(sorted(group), ["count", "results"])

    def test_the_order_row_carries_what_a_summary_line_renders(self):
        row = self.summary["ongoing_orders"]["results"][0]

        self.assertEqual(row["id"], self.order.id)
        self.assertEqual(row["status"]["name"], "payment_pending")
        self.assertTrue(row["status"]["fa_name"])
        self.assertEqual(row["total_amount"], "100.00")
        self.assertIsNotNone(row["created_at"])
        self.assertEqual(row["customer"], {"name": "Vendor Orders"})

    # ───────────────────────── only the caller's book ─────────────────────────

    def test_another_seller_orders_are_absent(self):
        self.assertEqual(self.summary["ongoing_orders"]["count"], 1)
        self.assertEqual(
            [row["id"] for row in self.summary["ongoing_orders"]["results"]],
            [self.order.id],
        )

    def test_a_return_on_another_seller_order_is_absent(self):
        self.make_return(self.other_order)

        returns = self.dashboard()["summary"]["ongoing_returns"]

        self.assertEqual(returns["count"], 0)
        self.assertEqual(returns["results"], [])

    def test_a_return_names_the_order_it_decides_on(self):
        request = self.make_return(self.order)

        row = self.dashboard()["summary"]["ongoing_returns"]["results"][0]

        # A return has no page of its own; `order_id` is the only link target.
        self.assertEqual(
            {key: row[key] for key in ("id", "order_id", "status")},
            {"id": request.id, "order_id": self.order.id, "status": "requested"},
        )

    # ───────────────────────── counts against the page ─────────────────────────

    def test_the_count_is_the_total_and_the_rows_are_the_newest_page(self):
        # The card lists five of them; the map beside it groups the whole
        # page, so the payload carries a page rather than the display slice.
        created = [self.make_order(self.business, status="paid") for _ in range(25)]

        orders = self.dashboard()["summary"]["ongoing_orders"]

        self.assertEqual(orders["count"], 26)  # twenty-five here plus the fixture's own
        self.assertEqual(
            [row["id"] for row in orders["results"]],
            [order.id for order in created][-20:][::-1],
        )

    def test_the_summary_rows_are_locatable(self):
        """The dashboard map groups the very rows the card lists.

        The province is a projection of a column this read already loads, so
        it arrives with no second request and no street address attached.
        """
        self.order.address_info = {
            "state_id": 7,
            "state_name": "Tehran",
            "state_fa_title": "تهران",
            "city_id": 44,
            "city_name": "Tehran",
            "city_fa_title": "تهران",
            "receiver_phone": "09120000801",
        }
        self.order.save(update_fields=["address_info"])

        row = self.dashboard()["summary"]["ongoing_orders"]["results"][0]

        self.assertEqual(row["id"], self.order.id)
        self.assertEqual(row["location"]["state_id"], 7)
        self.assertNotIn("receiver_phone", row["location"])
        self.assertNotIn("address_info", row)

    # ───────────────────────── the status vocabulary ─────────────────────────

    def test_terminal_and_failed_orders_are_not_ongoing(self):
        for name in ("delivered", "cancelled", "payment_expired", "returned"):
            self.make_order(self.business, status=name)

        self.assertEqual(self.dashboard()["summary"]["ongoing_orders"]["count"], 1)

    def test_every_status_the_order_list_calls_ongoing_is_counted(self):
        for name in BaseOrderService.IN_PROGRESS_STATUSES:
            self.make_order(self.business, status=name)

        # plus the fixture's own `payment_pending` order
        self.assertEqual(
            self.dashboard()["summary"]["ongoing_orders"]["count"],
            len(BaseOrderService.IN_PROGRESS_STATUSES) + 1,
        )

    def test_only_open_returns_are_ongoing(self):
        for status in ("requested", "approved", "received"):
            self.make_return(self.order, status=status)
        for status in ("rejected", "completed", "cancelled"):
            self.make_return(self.order, status=status)

        returns = self.dashboard()["summary"]["ongoing_returns"]

        self.assertEqual(returns["count"], 3)
        self.assertEqual(
            sorted(row["status"] for row in returns["results"]),
            ["approved", "received", "requested"],
        )

    # ───────────────────────── degrading, not failing ─────────────────────────

    def test_a_seller_without_a_business_gets_a_dashboard_and_no_summary(self):
        homeless = Vendor.objects.create(
            phone="+9990000089",
            first_name="No",
            last_name="Business",
            national_id="0000000089",
            vendor_code="VEN-VOR-009",
            status=VendorStatus.objects.get(name="active"),
        )
        self.as_vendor(homeless)

        data = self.dashboard()

        self.assertIsNone(data["profile"])
        self.assertIsNone(data["summary"])
        for key in SETTINGS_KEYS:
            self.assertEqual(data[key], [])

    def test_a_package_without_orders_hides_the_summary_rather_than_the_page(self):
        grant = self.on_default_tier()
        grant.config = {"enabled": False}
        grant.save()

        data = self.dashboard()

        self.assertIsNone(data["summary"])
        self.assertIsNotNone(data["profile"])

    def test_an_unprovisioned_package_table_fails_open_like_every_other_route(self):
        # No PackagesSeeder here: with no tier to enforce, nothing is denied.
        self.assertIsNotNone(self.summary)

    def test_the_page_stays_readable_so_the_gate_is_not_on_the_view(self):
        self.assertNotIn(
            RequiresShopOrders, VendorBusinessDashboardView.permission_classes
        )


class VendorBusinessDashboardSettingsTests(DashboardRequestMixin, VendorOrderApiFixture):
    """The configuration the panel shows as business information.

    Each group reuses the query the storefront or checkout already answers
    with, so a seller never reads a number on their dashboard that a customer
    could not actually pick.
    """

    def setUp(self):
        super().setUp()
        ShipmentSeeder().run()
        BusinessServiceModeSeeder().run()
        self.fixed = ShipmentPricingMethod.objects.get(code="fixed")
        self.post = ShipmentMethod.objects.get(code="post")
        self.courier = ShipmentMethod.objects.get(code="courier")
        self.online = BusinessServiceMode.objects.get(code="online")
        self.in_person = BusinessServiceMode.objects.get(code="in_person")
        self.category_status, _ = CategoryStatus.objects.get_or_create(
            name="dashboard-active"
        )

    # ───────────────────────── fixtures ─────────────────────────

    def make_category(self, name):
        return Category.objects.create(
            name=name, fa_name=f"فا-{name}", status=self.category_status
        )

    def register(self, category, business=None):
        return BusinessCategory.objects.create(
            business=business or self.business, category=category
        )

    def make_shipment(self, method=None, business=None, **overrides):
        values = {
            "business": business or self.business,
            "shipment_method": method or self.post,
            "pricing_method": self.fixed,
            "cost": Decimal("50.00"),
        }
        values.update(overrides)
        return BusinessShipment.objects.create(**values)

    def make_charge(self, business=None, **overrides):
        values = {
            "business": business or self.business,
            "name": "Tax",
            "type": "tax",
            "calculation_type": "percentage",
            "amount": Decimal("10"),
        }
        values.update(overrides)
        return BusinessCharge.objects.create(**values)

    def enable_mode(self, mode, business=None, **overrides):
        values = {"business_profile": business or self.business, "service_mode": mode}
        values.update(overrides)
        return BusinessProfileServiceMode.objects.create(**values)

    # ───────────────────────── nothing configured ─────────────────────────

    def test_an_untouched_shop_answers_with_empty_groups_rather_than_absent_ones(self):
        data = self.dashboard()

        # `[]` is what lets the panel say "not set"; a missing key would let a
        # broken response look like an unconfigured shop.
        for key in SETTINGS_KEYS:
            self.assertEqual(data[key], [])

    # ───────────────────────── only the caller's shop ─────────────────────────

    def test_another_sellers_configuration_is_absent_from_every_group(self):
        category = self.register(self.make_category("Mine"))
        shipment = self.make_shipment()
        charge = self.make_charge()
        mode = self.enable_mode(self.online)
        self.register(self.make_category("Theirs"), business=self.other_business)
        self.make_shipment(business=self.other_business)
        self.make_charge(business=self.other_business, name="Their tax")
        self.enable_mode(self.in_person, business=self.other_business)

        data = self.dashboard()

        self.assertEqual([row["id"] for row in data["categories"]], [category.category_id])
        self.assertEqual([row["id"] for row in data["shipments"]], [shipment.id])
        self.assertEqual([row["id"] for row in data["charges"]], [charge.id])
        self.assertEqual([row["id"] for row in data["service_modes"]], [mode.id])

    # ───────────────────────── what counts as available ─────────────────────────

    def test_a_setting_the_seller_switched_off_is_absent(self):
        self.make_shipment(is_active=False)
        self.make_charge(is_active=False)
        self.enable_mode(self.online, is_active=False)

        data = self.dashboard()

        for key in ("shipments", "charges", "service_modes"):
            self.assertEqual(data[key], [])

    def test_a_method_retired_by_an_administrator_is_absent_too(self):
        self.make_shipment()
        self.enable_mode(self.online)
        self.post.is_active = False
        self.post.save()
        self.online.is_active = False
        self.online.save()

        data = self.dashboard()

        # The same rule the checkout list applies: a retired vocabulary row is
        # off the market, whatever the seller still has configured.
        self.assertEqual(data["shipments"], [])
        self.assertEqual(data["service_modes"], [])

    def test_a_retired_method_leaves_the_sellers_other_methods_alone(self):
        self.make_shipment(self.post)
        courier = self.make_shipment(self.courier)

        self.post.is_active = False
        self.post.save()

        self.assertEqual(
            [row["id"] for row in self.dashboard()["shipments"]], [courier.id]
        )

    # ───────────────────────── the rows themselves ─────────────────────────

    def test_a_shipment_carries_the_method_and_the_price_a_customer_pays(self):
        shipment = self.make_shipment(self.courier, is_default=True)

        row = self.dashboard()["shipments"][0]

        self.assertEqual(row["id"], shipment.id)
        self.assertEqual(row["shipment_method"]["code"], "courier")
        self.assertTrue(row["shipment_method"]["is_active"])
        self.assertEqual(row["pricing_method"]["code"], "fixed")
        self.assertEqual(Decimal(row["cost"]), Decimal("50.00"))
        self.assertTrue(row["is_default"])

    def test_a_charge_carries_how_it_is_calculated(self):
        packaging = self.make_charge(
            name="هزینه بسته‌بندی",
            type="extra",
            calculation_type="fixed",
            amount=Decimal("30000"),
        )
        tax = self.make_charge()

        rows = self.dashboard()["charges"]

        # Configuration order, so a seller reading tax then packaging sees the
        # list in the order they built it.
        self.assertEqual([row["id"] for row in rows], [packaging.id, tax.id])
        self.assertEqual(
            [(row["type"], row["calculation_type"]) for row in rows],
            [("extra", "fixed"), ("tax", "percentage")],
        )
        self.assertEqual(Decimal(rows[0]["amount"]), Decimal("30000"))
        self.assertEqual(Decimal(rows[1]["amount"]), Decimal("10"))

    def test_a_service_mode_is_named_by_its_stable_code(self):
        self.enable_mode(self.online)
        self.enable_mode(self.in_person)

        data = self.dashboard()

        self.assertEqual(
            [row["service_mode"]["code"] for row in data["service_modes"]],
            ["online", "in_person"],
        )

    def test_categories_arrive_ready_for_the_browse_shape(self):
        root = self.make_category("Electronics")
        self.register(root)
        self.register(self.make_category("Groceries"))
        Category.objects.create(
            name="Phones", parent=root, status=self.category_status
        )

        rows = self.dashboard()["categories"]

        # A registration is always a root, and the panel reuses the browse list
        # shape, so both flags have to be the real answer.
        self.assertEqual([row["name"] for row in rows], ["Electronics", "Groceries"])
        for row in rows:
            self.assertTrue(row["selected"])
        self.assertTrue(rows[0]["has_children"])
        self.assertFalse(rows[1]["has_children"])

    # ───────────────────────── degrading, not failing ─────────────────────────

    def test_the_settings_block_ignores_the_orders_gate(self):
        PackagesSeeder().run()
        self.business.package = Package.objects.get(code="free")
        self.business.save()
        grant = PackageFeature.objects.get(
            package__code="free", feature__code="shop.orders"
        )
        grant.config = {"enabled": False}
        grant.save()

        self.make_charge()

        data = self.dashboard()

        # Two independent blocks: withholding orders blanks the activity
        # summary, never the seller's own shop configuration.
        self.assertIsNone(data["summary"])
        self.assertEqual([row["name"] for row in data["charges"]], ["Tax"])
