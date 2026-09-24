from decimal import Decimal

from rest_framework.test import APITestCase

from domains.business.models import BusinessCategory, BusinessProfile
from domains.catalog.models import (
    Category,
    CategoryStatus,
    Product,
    ProductStatus,
    ProductVariants,
)
from domains.inventory.models import (
    InventorySupply,
    Warehouse,
    WarehouseStatus,
)
from domains.location.models import City, Country, State
from domains.vendor.enums.VendorStatusEnum import VendorStatusEnum
from domains.vendor.models import Vendor, VendorStatus


class VendorSupplyOwnershipAPITests(APITestCase):
    def setUp(self):
        self.vendor_status, _ = VendorStatus.objects.get_or_create(
            id=VendorStatusEnum.ACTIVE.value,
            defaults={"name": "active", "title": "Active"},
        )
        self.vendor = Vendor.objects.create_user(
            phone="09121112233",
            password="pass1234",
            first_name="Supply",
            last_name="Vendor",
            national_id="1234567890",
            status=self.vendor_status,
        )
        self.other_vendor = Vendor.objects.create_user(
            phone="09129998877",
            password="pass1234",
            first_name="Other",
            last_name="Vendor",
            national_id="9876543210",
            status=self.vendor_status,
        )
        self.business = BusinessProfile.objects.create(
            id=101,
            vendor=self.vendor,
            business_name="Supply Vendor Business",
            display_name="Supply Vendor",
        )
        self.other_business = BusinessProfile.objects.create(
            id=102,
            vendor=self.other_vendor,
            business_name="Other Vendor Business",
            display_name="Other Vendor",
        )

        self.category_status = CategoryStatus.objects.create(name="active")
        self.category = Category.objects.create(
            name="Shared Vendor Category",
            status=self.category_status,
        )
        BusinessCategory.objects.create(
            business=self.business,
            category=self.category,
        )
        BusinessCategory.objects.create(
            business=self.other_business,
            category=self.category,
        )

        self.product_status = ProductStatus.objects.create(name="active")
        self.product = Product.objects.create(
            name="Shared Vendor Product",
            status=self.product_status,
        )
        self.product.categories.add(self.category)
        self.variant = ProductVariants.objects.create(
            product=self.product,
            sku="SHARED-SUPPLY-SKU",
            combination_key="shared-supply-sku",
        )

        country = Country.objects.create(
            name="Supply Country",
            code="SC",
            phone_code="+1",
        )
        state = State.objects.create(
            name="Supply State",
            country=country,
        )
        city = City.objects.create(name="Supply City", state=state)
        self.warehouse_status = WarehouseStatus.objects.create(name="available")
        self.warehouse = Warehouse.objects.create(
            code="WH-VENDOR-A",
            name="Vendor A Warehouse",
            business=self.business,
            city=city,
            address="Vendor A address",
            lat="0",
            lng="0",
            status=self.warehouse_status,
        )
        self.other_warehouse = Warehouse.objects.create(
            code="WH-VENDOR-B",
            name="Vendor B Warehouse",
            business=self.other_business,
            city=city,
            address="Vendor B address",
            lat="0",
            lng="0",
            status=self.warehouse_status,
        )
        self.global_warehouse = Warehouse.objects.create(
            code="WH-GLOBAL-SUPPLY",
            name="Global Warehouse",
            city=city,
            address="Global address",
            lat="0",
            lng="0",
            status=self.warehouse_status,
        )
        self.client.force_authenticate(self.vendor)

    def _payload(self, warehouse=None, **overrides):
        payload = {
            "warehouse_id": (warehouse or self.warehouse).id,
            "quantity": 5,
            "unit_buy_price": "100.00",
            "supplied_at": "2026-01-01T00:00:00Z",
            "reference_number": "REF-1",
            "invoice_number": "INV-1",
            "notes": "Initial supply",
            "costs": [
                {"type": "shipment", "amount": "10.00", "description": "Freight"}
            ],
        }
        payload.update(overrides)
        return payload

    def _make_supply(self, *, business=None, warehouse=None):
        return InventorySupply.objects.create(
            business=business,
            variant=self.variant,
            warehouse=warehouse or self.warehouse,
            quantity=5,
            unit_buy_price="100.00",
            supplied_at="2026-01-01T00:00:00Z",
        )

    def test_variant_list_returns_only_current_business_supplies(self):
        own = self._make_supply(business=self.business)
        self._make_supply(business=self.other_business, warehouse=self.other_warehouse)
        self._make_supply(warehouse=self.global_warehouse)

        response = self.client.get(
            f"/api/vendor/variants/{self.variant.id}/supplies"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [row["id"] for row in response.data["data"]],
            [own.id],
        )

    def test_create_persists_authenticated_business_atomically(self):
        response = self.client.post(
            f"/api/vendor/variants/{self.variant.id}/supplies",
            self._payload(),
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        supply = InventorySupply.objects.get(id=response.data["data"]["id"])
        self.assertEqual(supply.business, self.business)
        self.assertEqual(supply.warehouse, self.warehouse)
        self.assertEqual(supply.costs.get().amount, Decimal("10.00"))

    def test_create_rejects_other_business_and_global_warehouses(self):
        for warehouse in (self.other_warehouse, self.global_warehouse):
            with self.subTest(warehouse=warehouse.code):
                response = self.client.post(
                    f"/api/vendor/variants/{self.variant.id}/supplies",
                    self._payload(warehouse=warehouse),
                    format="json",
                )
                self.assertEqual(response.status_code, 400)
                self.assertIn("warehouse", response.data["errors"])
        self.assertFalse(InventorySupply.objects.exists())

    def test_create_rejects_client_supplied_business(self):
        response = self.client.post(
            f"/api/vendor/variants/{self.variant.id}/supplies",
            self._payload(business_id=self.other_business.id),
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(InventorySupply.objects.exists())

    def test_invalid_cost_rolls_back_supply_creation(self):
        response = self.client.post(
            f"/api/vendor/variants/{self.variant.id}/supplies",
            self._payload(costs=[{"type": "unsupported", "amount": "10.00"}]),
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(InventorySupply.objects.exists())

    def test_other_and_unassigned_supplies_are_not_accessible(self):
        supplies = [
            self._make_supply(
                business=self.other_business,
                warehouse=self.other_warehouse,
            ),
            self._make_supply(warehouse=self.global_warehouse),
        ]
        for supply in supplies:
            with self.subTest(supply=supply.id):
                detail_url = f"/api/vendor/supplies/{supply.id}"
                self.assertEqual(self.client.get(detail_url).status_code, 404)
                self.assertEqual(
                    self.client.patch(
                        detail_url,
                        {"notes": "Unauthorized update"},
                        format="json",
                    ).status_code,
                    404,
                )
                self.assertEqual(self.client.delete(detail_url).status_code, 404)
                self.assertEqual(
                    self.client.post(
                        f"{detail_url}/receive",
                        {},
                        format="json",
                    ).status_code,
                    404,
                )
        self.assertEqual(InventorySupply.objects.count(), len(supplies))

    def test_owned_supply_cannot_move_to_another_business_warehouse(self):
        supply = self._make_supply(business=self.business)

        response = self.client.patch(
            f"/api/vendor/supplies/{supply.id}",
            {"warehouse_id": self.other_warehouse.id},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        supply.refresh_from_db()
        self.assertEqual(supply.warehouse, self.warehouse)

    def test_supply_overview_returns_only_current_business(self):
        own = self._make_supply(business=self.business)
        self._make_supply(business=self.other_business, warehouse=self.other_warehouse)
        self._make_supply(warehouse=self.global_warehouse)

        response = self.client.get("/api/vendor/supplies/overview")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [row["id"] for row in response.data["data"]],
            [own.id],
        )

    def test_variant_outside_business_categories_is_not_found(self):
        other_category = Category.objects.create(
            name="Other Category",
            status=self.category_status,
        )
        other_product = Product.objects.create(
            name="Other Product",
            status=self.product_status,
        )
        other_product.categories.add(other_category)
        other_variant = ProductVariants.objects.create(
            product=other_product,
            sku="OTHER-SUPPLY-SKU",
            combination_key="other-supply-sku",
        )

        response = self.client.get(
            f"/api/vendor/variants/{other_variant.id}/supplies"
        )

        self.assertEqual(response.status_code, 404)
