from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from domains.business.models import BusinessProfile
from domains.catalog.models import (
    Category,
    CategoryStatus,
    Product,
    ProductStatus,
    ProductVariants,
    VariantAttribute,
    VariantOption,
)
from domains.inventory.models import (
    InventoryAttributeDefinition,
    InventoryUnitAttribute,
    Warehouse,
    WarehouseStatus,
)
from domains.location.models import City, Country, State


class SerializedUnitAttributeTests(APITestCase):
    """Serialized units carry attributes beyond their serial number.

    A snapshot row may submit ``attributes: [{code, value}]``. Codes resolve
    through ``InventoryAttributeService``, so a definition the vocabulary does
    not have must be inserted first via ``POST inventory/attribute-definitions``
    instead of being created implicitly by a stock write.
    """

    def setUp(self):
        self.user = User.objects.create_superuser(
            username="unit-attribute-admin", password="password"
        )
        self.client.force_authenticate(self.user)

        country = Country.objects.create(name="UA Country", code="UC", phone_code="+1")
        state = State.objects.create(name="UA State", country=country)
        city = City.objects.create(name="UA City", state=state)
        self.warehouse_status = WarehouseStatus.objects.create(name="available-for-attributes")
        self.warehouse = Warehouse.objects.create(
            code="WH-ATTR",
            name="Attribute Warehouse",
            city=city,
            address="Test address",
            lat="0",
            lng="0",
            is_default=True,
            status=self.warehouse_status,
        )
        category_status = CategoryStatus.objects.create(name="attributes-active")
        product_status = ProductStatus.objects.create(name="attributes-pending")
        category = Category.objects.create(name="Attribute Category", status=category_status)
        self.product = Product.objects.create(name="Attribute Product", status=product_status)
        self.product.categories.add(category)
        self.attribute = VariantAttribute.objects.create(name="Attribute Color")
        self.option_a = VariantOption.objects.create(
            attribute=self.attribute, name="Black", sku_code="ATRBLK"
        )

        self.imei = InventoryAttributeDefinition.objects.create(
            business=None,
            name="IMEI",
            fa_title="شماره IMEI",
            code="imei",
            type="text",
        )
        self.warranty = InventoryAttributeDefinition.objects.create(
            business=None,
            name="Warranty (months)",
            fa_title="گارانتی (ماه)",
            code="warranty_months",
            type="integer",
        )

    def create_serialized_variant(self, *, serial_number="SN-001"):
        response = self.client.post(
            f"/api/catalog/products/{self.product.id}/variants",
            {
                "selections": [
                    {
                        "attribute_id": self.attribute.id,
                        "option_id": self.option_a.id,
                    }
                ],
                "serial_items": [{"serial_number": serial_number, "on_sale": True}],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        variant = ProductVariants.objects.get()
        detail = self.get_detail(variant.id)
        return variant.id, detail["serial_items"][0]["id"]

    def get_detail(self, variant_id):
        response = self.client.get(f"/api/inventory/variants/{variant_id}")
        self.assertEqual(response.status_code, 200, response.data)
        return response.data["data"]

    def patch_snapshot(self, variant_id, serial_items):
        return self.client.patch(
            f"/api/inventory/variants/{variant_id}",
            {"serial_items": serial_items},
            format="json",
        )

    def test_attributes_are_persisted_and_returned(self):
        variant_id, unit_id = self.create_serialized_variant()

        response = self.patch_snapshot(variant_id, [{
            "id": unit_id,
            "serial_number": "SN-001",
            "on_sale": True,
            "attributes": [
                {"code": "imei", "value": "123456789012345"},
                {"code": "warranty_months", "value": "24"},
            ],
        }])

        self.assertEqual(response.status_code, 200, response.data)
        item = response.data["data"]["serial_items"][0]
        by_code = {row["code"]: row for row in item["attributes"]}
        self.assertEqual(set(by_code), {"imei", "warranty_months"})
        self.assertEqual(by_code["imei"]["value"], "123456789012345")
        self.assertEqual(by_code["warranty_months"]["value"], "24")
        self.assertEqual(by_code["imei"]["fa_title"], "شماره IMEI")
        self.assertEqual(by_code["warranty_months"]["type"], "integer")

        # The serial number is its own field, never a member of the list.
        self.assertNotIn("serial_number", by_code)
        self.assertEqual(
            InventoryUnitAttribute.objects.filter(
                inventory_unit_id=unit_id
            ).count(),
            3,
        )

    def test_detail_returns_persisted_attributes(self):
        variant_id, unit_id = self.create_serialized_variant()
        self.patch_snapshot(variant_id, [{
            "id": unit_id,
            "serial_number": "SN-001",
            "on_sale": True,
            "attributes": [{"code": "imei", "value": "999"}],
        }])

        item = self.get_detail(variant_id)["serial_items"][0]

        self.assertEqual(
            [(row["code"], row["value"]) for row in item["attributes"]],
            [("imei", "999")],
        )

    def test_blank_value_clears_the_attribute(self):
        variant_id, unit_id = self.create_serialized_variant()
        self.patch_snapshot(variant_id, [{
            "id": unit_id,
            "serial_number": "SN-001",
            "on_sale": True,
            "attributes": [{"code": "imei", "value": "999"}],
        }])

        response = self.patch_snapshot(variant_id, [{
            "id": unit_id,
            "serial_number": "SN-001",
            "on_sale": True,
            "attributes": [{"code": "imei", "value": ""}],
        }])

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(
            response.data["data"]["serial_items"][0]["attributes"], []
        )
        self.assertFalse(
            InventoryUnitAttribute.objects.filter(
                inventory_unit_id=unit_id,
                attribute_definition=self.imei,
            ).exists()
        )

    def test_new_row_accepts_attributes(self):
        variant_id, first_unit_id = self.create_serialized_variant()

        response = self.patch_snapshot(variant_id, [
            {
                "id": first_unit_id,
                "serial_number": "SN-001",
                "on_sale": True,
            },
            {
                "serial_number": "SN-002",
                "on_sale": False,
                "attributes": [{"code": "imei", "value": "42"}],
            },
        ])

        self.assertEqual(response.status_code, 200, response.data)
        created = next(
            item for item in response.data["data"]["serial_items"]
            if item["serial_number"] == "SN-002"
        )
        self.assertTrue(created["id"])
        self.assertEqual(
            [(row["code"], row["value"]) for row in created["attributes"]],
            [("imei", "42")],
        )
        self.assertEqual(
            created["on_sale"], False
        )

    def test_unknown_code_is_rejected_and_creates_nothing(self):
        variant_id, unit_id = self.create_serialized_variant()
        before = InventoryUnitAttribute.objects.count()

        response = self.patch_snapshot(variant_id, [{
            "id": unit_id,
            "serial_number": "SN-001",
            "on_sale": True,
            "attributes": [{"code": "box_serial", "value": "A-1"}],
        }])

        self.assertEqual(response.status_code, 400)
        self.assertIn("box_serial", str(response.data["errors"]))
        self.assertEqual(InventoryUnitAttribute.objects.count(), before)

    def test_value_must_match_the_definition_type(self):
        variant_id, unit_id = self.create_serialized_variant()

        response = self.patch_snapshot(variant_id, [{
            "id": unit_id,
            "serial_number": "SN-001",
            "on_sale": True,
            "attributes": [{"code": "warranty_months", "value": "two years"}],
        }])

        self.assertEqual(response.status_code, 400)
        self.assertIn("warranty_months", str(response.data["errors"]))

    def test_serial_number_cannot_be_submitted_as_an_attribute(self):
        variant_id, unit_id = self.create_serialized_variant()

        response = self.patch_snapshot(variant_id, [{
            "id": unit_id,
            "serial_number": "SN-001",
            "on_sale": True,
            "attributes": [{"code": "serial_number", "value": "SN-001"}],
        }])

        self.assertEqual(response.status_code, 400)
        self.assertIn("attributes", str(response.data["errors"]))

    def test_attribute_edits_are_refused_on_a_reserved_row(self):
        variant_id, unit_id = self.create_serialized_variant()
        self.patch_snapshot(variant_id, [{
            "id": unit_id,
            "serial_number": "SN-001",
            "on_sale": False,
        }])

        response = self.patch_snapshot(variant_id, [{
            "id": unit_id,
            "serial_number": "SN-001",
            "on_sale": False,
            "attributes": [{"code": "imei", "value": "1"}],
        }])

        self.assertEqual(response.status_code, 400)
        # The message is translated, so assert on the field and the effect.
        self.assertIn("serial_items", str(response.data["errors"]))
        self.assertFalse(
            InventoryUnitAttribute.objects.filter(
                inventory_unit_id=unit_id,
                attribute_definition=self.imei,
            ).exists()
        )

    def test_business_owned_definition_resolves_without_a_caller_business(self):
        """The admin snapshot passes no business, so resolution falls back to
        the inventory row's own business for business-owned definitions."""
        InventoryAttributeDefinition.objects.create(
            business=BusinessProfile.objects.get(id=1),
            name="Batch Number",
            fa_title="شماره سری تولید",
            code="batch_number",
            type="text",
        )
        variant_id, unit_id = self.create_serialized_variant()

        response = self.patch_snapshot(variant_id, [{
            "id": unit_id,
            "serial_number": "SN-001",
            "on_sale": True,
            "attributes": [{"code": "batch_number", "value": "B-7"}],
        }])

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(
            [
                row["value"]
                for row in response.data["data"]["serial_items"][0]["attributes"]
            ],
            ["B-7"],
        )

    def test_unrelated_attributes_survive_a_serial_rewrite(self):
        variant_id, unit_id = self.create_serialized_variant()
        self.patch_snapshot(variant_id, [{
            "id": unit_id,
            "serial_number": "SN-001",
            "on_sale": True,
            "attributes": [{"code": "imei", "value": "5"}],
        }])

        response = self.patch_snapshot(variant_id, [{
            "id": unit_id,
            "serial_number": "SN-001-RENAMED",
            "on_sale": True,
            "attributes": [{"code": "imei", "value": "5"}],
        }])

        self.assertEqual(response.status_code, 200, response.data)
        item = response.data["data"]["serial_items"][0]
        self.assertEqual(item["serial_number"], "SN-001-RENAMED")
        self.assertEqual(
            [(row["code"], row["value"]) for row in item["attributes"]],
            [("imei", "5")],
        )

    def test_duplicate_code_in_one_row_is_rejected(self):
        variant_id, unit_id = self.create_serialized_variant()

        response = self.patch_snapshot(variant_id, [{
            "id": unit_id,
            "serial_number": "SN-001",
            "on_sale": True,
            "attributes": [
                {"code": "imei", "value": "1"},
                {"code": "IMEI", "value": "2"},
            ],
        }])

        self.assertEqual(response.status_code, 400)
        self.assertIn("imei", str(response.data["errors"]))
