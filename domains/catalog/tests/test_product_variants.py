from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from domains.catalog.models import (
    Category,
    CategoryStatus,
    CategoryVariantAttribute,
    Product,
    ProductStatus,
    ProductVariantSelection,
    ProductVariants,
    VariantAttribute,
    VariantOption,
)
from domains.inventory.models import Warehouse, WarehouseStatus
from domains.location.models import City, Country, State


class ProductVariantWorkflowTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(username="variant-admin", password="password")
        self.client.force_authenticate(self.user)
        category_status = CategoryStatus.objects.create(name="variant-active")
        product_status = ProductStatus.objects.create(name="variant-pending")
        self.category = Category.objects.create(name="Variant Phones", status=category_status)
        self.product = Product.objects.create(name="Test Phone", status=product_status)
        self.product.categories.add(self.category)
        self.color = VariantAttribute.objects.create(name="Color")
        self.storage = VariantAttribute.objects.create(name="Storage")
        self.black = VariantOption.objects.create(attribute=self.color, name="Black", sku_code="BLK")
        self.white = VariantOption.objects.create(attribute=self.color, name="White", sku_code="WHT")
        self.gb128 = VariantOption.objects.create(attribute=self.storage, name="128 GB", sku_code="128GB")
        CategoryVariantAttribute.objects.create(category=self.category, attribute=self.color)
        country = Country.objects.create(name="Variant Country", code="VC", phone_code="+1")
        state = State.objects.create(name="Variant State", country=country)
        city = City.objects.create(name="Variant City", state=state)
        warehouse_status = WarehouseStatus.objects.create(name="variant-available")
        Warehouse.objects.create(
            code="WH-VARIANT",
            name="Variant Warehouse",
            city=city,
            address="Test",
            lat="0",
            lng="0",
            is_default=True,
            status=warehouse_status,
        )

    def variant_payload(self, options=None):
        options = options or [(self.color, self.black), (self.storage, self.gb128)]
        return {
            "inventory": {"quantity": 0, "sellable": 0},
            "selections": [
                {"attribute_id": attribute.id, "option_id": option.id}
                for attribute, option in options
            ],
        }

    def create_variant(self, options=None):
        return self.client.post(
            f"/api/catalog/products/{self.product.id}/variants",
            self.variant_payload(options),
            format="json",
        )

    def test_form_options_prioritize_category_attributes_without_restricting_others(self):
        response = self.client.get(f"/api/catalog/products/{self.product.id}/variant-form-options")

        self.assertEqual(response.status_code, 200)
        attributes = {item["id"]: item for item in response.data["data"]["attributes"]}
        self.assertTrue(attributes[self.color.id]["category_default"])
        self.assertFalse(attributes[self.storage.id]["category_default"])

    def test_category_variant_attribute_assignment_is_full_replacement(self):
        get_response = self.client.get(f"/api/catalog/categories/{self.category.id}/assign-variant-attributes")
        candidates = get_response.data["data"]["attributes"]
        self.assertEqual(candidates[0]["id"], self.color.id)
        self.assertTrue(candidates[0]["assigned"])

        post_response = self.client.post(
            f"/api/catalog/categories/{self.category.id}/assign-variant-attributes",
            {"attributes": [self.storage.id]},
            format="json",
        )
        self.assertEqual(post_response.status_code, 200)
        self.assertEqual(
            list(self.category.variant_attribute_assignments.values_list("attribute_id", flat=True)),
            [self.storage.id],
        )

    def test_create_variant_generates_exact_sku_and_accepts_unsuggested_attribute(self):
        response = self.create_variant()

        self.assertEqual(response.status_code, 201)
        variant = ProductVariants.objects.get(product=self.product)
        self.assertEqual(variant.sku, f"CG{self.category.id}-PD{self.product.id}-BLK-128GB")
        self.assertEqual(
            variant.combination_key,
            f"{self.color.id}:{self.black.id}|{self.storage.id}:{self.gb128.id}",
        )

    def test_update_replaces_selections_regenerates_sku_and_keeps_strategy(self):
        self.create_variant()
        variant = ProductVariants.objects.get(product=self.product)

        response = self.client.patch(
            f"/api/catalog/variants/{variant.id}",
            {"selections": [{"attribute_id": self.color.id, "option_id": self.white.id}]},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["sku"], f"CG{self.category.id}-PD{self.product.id}-WHT")
        variant.refresh_from_db()
        self.assertEqual(variant.sku, f"CG{self.category.id}-PD{self.product.id}-WHT")
        self.assertEqual(
            list(variant.selections.values_list("attribute_id", "option_id")),
            [(self.color.id, self.white.id)],
        )

    def test_rejects_duplicate_combination(self):
        self.assertEqual(self.create_variant().status_code, 201)
        response = self.create_variant()
        self.assertEqual(response.status_code, 400)
        self.assertEqual(ProductVariants.objects.count(), 1)

    def test_requires_at_least_one_selection_and_rejects_client_sku(self):
        empty = self.client.post(
            f"/api/catalog/products/{self.product.id}/variants",
            {"selections": []},
            format="json",
        )
        supplied_sku = self.client.post(
            f"/api/catalog/products/{self.product.id}/variants",
            {**self.variant_payload(), "sku": "CLIENT"},
            format="json",
        )
        self.assertEqual(empty.status_code, 400)
        self.assertEqual(supplied_sku.status_code, 400)

    def test_option_code_edit_regenerates_referencing_skus(self):
        self.create_variant()
        variant = ProductVariants.objects.get(product=self.product)

        response = self.client.patch(
            f"/api/catalog/variant-options/{self.black.id}",
            {"sku_code": "bk1"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        variant.refresh_from_db()
        self.assertEqual(variant.sku, f"CG{self.category.id}-PD{self.product.id}-BK1-128GB")

    def test_delete_variant_cascades_owned_selections(self):
        self.create_variant()
        variant = ProductVariants.objects.get(product=self.product)
        selection_id = variant.selections.first().id

        response = self.client.delete(f"/api/catalog/variants/{variant.id}")

        self.assertEqual(response.status_code, 200)
        self.assertFalse(ProductVariants.objects.filter(id=variant.id).exists())
        self.assertFalse(ProductVariantSelection.objects.filter(id=selection_id).exists())
