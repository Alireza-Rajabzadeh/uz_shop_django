from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from domains.catalog.models import (
    Category,
    CategoryDetail,
    CategoryDetailRelation,
    CategoryStatus,
    Product,
    ProductDetails,
    ProductStatus,
    ProductVariants,
    ProductVariantSelection,
    CategoryVariantAttribute,
    VariantAttribute,
    VariantOption,
)
from domains.inventory.models import InventoryStrategy, Warehouse, WarehouseStatus, WarehouseStock
from domains.location.models import City, Country, State


class ProductVariantWorkflowTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(username="variant-admin", password="password")
        self.client.force_authenticate(self.user)
        category_status = CategoryStatus.objects.create(name="variant-active")
        product_status = ProductStatus.objects.create(name="variant-pending")
        self.category = Category.objects.create(name="Variant Phones", status=category_status)
        self.product = Product.objects.create(
            name="Test Phone",
            category=self.category,
            status=product_status,
        )
        self.color = VariantAttribute.objects.create(name="Color")
        self.storage = VariantAttribute.objects.create(name="Storage")
        self.black = VariantOption.objects.create(
            attribute=self.color, name="Black", sku_code="BLK"
        )
        self.white = VariantOption.objects.create(
            attribute=self.color, name="White", sku_code="WHT"
        )
        self.gb128 = VariantOption.objects.create(
            attribute=self.storage, name="128 GB", sku_code="128GB"
        )
        CategoryVariantAttribute.objects.create(category=self.category, attribute=self.color)
        self.normal, _ = InventoryStrategy.objects.get_or_create(
            code="normal", defaults={"name": "Normal"}
        )
        InventoryStrategy.objects.get_or_create(
            code="serialized", defaults={"name": "Serialized"}
        )
        country = Country.objects.create(
            name="Variant Country", code="VC", phone_code="+1"
        )
        state = State.objects.create(name="Variant State", country=country)
        city = City.objects.create(name="Variant City", state=state)
        warehouse_status = WarehouseStatus.objects.create(name="variant-available")
        self.warehouse = Warehouse.objects.create(
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
            "price": "100.00",
            "inventory_strategy_code": "normal",
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
        response = self.client.get(
            f"/api/catalog/products/{self.product.id}/variant-form-options"
        )

        self.assertEqual(response.status_code, 200)
        attributes = {item["id"]: item for item in response.data["data"]["attributes"]}
        self.assertTrue(attributes[self.color.id]["category_default"])
        self.assertFalse(attributes[self.storage.id]["category_default"])

    def test_category_variant_attribute_assignment_is_full_replacement(self):
        get_response = self.client.get(
            f"/api/catalog/categories/{self.category.id}/assign-variant-attributes"
        )
        candidates = get_response.data["data"]["attributes"]
        self.assertEqual(candidates[0]["id"], self.color.id)
        self.assertTrue(candidates[0]["assigned"])

        post_response = self.client.post(
            f"/api/catalog/categories/{self.category.id}/assign-variant-attributes",
            {"attributes": [self.storage.id]}, format="json",
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
        self.assertEqual(variant.inventory_strategy, self.normal)
        self.assertEqual(
            variant.sku,
            f"CG{self.category.id}-PD{self.product.id}-BLK-128GB",
        )
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
        self.assertEqual(
            response.data["data"]["sku"],
            f"CG{self.category.id}-PD{self.product.id}-WHT",
        )
        variant.refresh_from_db()
        self.assertEqual(variant.sku, f"CG{self.category.id}-PD{self.product.id}-WHT")
        self.assertEqual(variant.inventory_strategy, self.normal)
        self.assertEqual(
            list(variant.selections.values_list("attribute_id", "option_id")),
            [(self.color.id, self.white.id)],
        )

    def test_update_preserves_existing_serialized_strategy(self):
        serialized = InventoryStrategy.objects.get(code="serialized")
        self.create_variant()
        variant = ProductVariants.objects.get(product=self.product)
        variant.warehouse_stocks.all().delete()
        variant.inventory_strategy = serialized
        variant.save(update_fields=["inventory_strategy"])

        response = self.client.patch(
            f"/api/catalog/variants/{variant.id}",
            {"price": "120.00"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        variant.refresh_from_db()
        self.assertEqual(variant.inventory_strategy, serialized)

    def test_rejects_duplicate_combination(self):
        self.assertEqual(self.create_variant().status_code, 201)
        response = self.create_variant()
        self.assertEqual(response.status_code, 400)
        self.assertEqual(ProductVariants.objects.count(), 1)

    def test_rejects_duplicate_attribute_and_mismatched_option(self):
        duplicate = self.create_variant([(self.color, self.black), (self.color, self.white)])
        mismatch = self.create_variant([(self.color, self.gb128)])
        self.assertEqual(duplicate.status_code, 400)
        self.assertEqual(mismatch.status_code, 400)

    def test_requires_at_least_one_selection_and_rejects_client_sku(self):
        empty = self.client.post(
            f"/api/catalog/products/{self.product.id}/variants",
            {"price": "10.00", "selections": []}, format="json",
        )
        supplied_sku = self.client.post(
            f"/api/catalog/products/{self.product.id}/variants",
            {**self.variant_payload(), "sku": "CLIENT"}, format="json",
        )
        self.assertEqual(empty.status_code, 400)
        self.assertEqual(supplied_sku.status_code, 400)

    def test_option_code_edit_regenerates_referencing_skus(self):
        self.create_variant()
        variant = ProductVariants.objects.get(product=self.product)
        response = self.client.patch(
            f"/api/catalog/variant-options/{self.black.id}",
            {"sku_code": "bk1"}, format="json",
        )
        self.assertEqual(response.status_code, 200)
        variant.refresh_from_db()
        self.assertEqual(variant.sku, f"CG{self.category.id}-PD{self.product.id}-BK1-128GB")

    def test_used_attribute_and_option_cannot_be_deleted(self):
        self.create_variant()

        option_response = self.client.delete(
            f"/api/catalog/variant-options/{self.black.id}"
        )
        attribute_response = self.client.delete(
            f"/api/catalog/variant-attributes/{self.color.id}"
        )

        self.assertEqual(option_response.status_code, 400)
        self.assertEqual(attribute_response.status_code, 400)
        self.assertTrue(VariantOption.objects.filter(id=self.black.id).exists())
        self.assertTrue(VariantAttribute.objects.filter(id=self.color.id).exists())

    def test_complete_product_category_change_regenerates_sku(self):
        self.create_variant()
        variant = ProductVariants.objects.get(product=self.product)
        new_category = Category.objects.create(
            name="Other Phones", status=self.category.status
        )
        response = self.client.patch(
            f"/api/catalog/products/{self.product.id}/update",
            {"name": self.product.name, "category_ids": [new_category.id], "details": []},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        variant.refresh_from_db()
        self.assertEqual(
            variant.sku, f"CG{new_category.id}-PD{self.product.id}-BLK-128GB"
        )

    def test_delete_variant_cascades_owned_selections(self):
        self.create_variant()
        variant = ProductVariants.objects.get(product=self.product)
        selection_id = variant.selections.first().id

        response = self.client.delete(f"/api/catalog/variants/{variant.id}")

        self.assertEqual(response.status_code, 200)
        self.assertFalse(ProductVariants.objects.filter(id=variant.id).exists())
        self.assertFalse(ProductVariantSelection.objects.filter(id=selection_id).exists())

    def test_attribute_option_crud_normalizes_values(self):
        attribute_response = self.client.post(
            "/api/catalog/variant-attributes", {"name": "  Material  "}, format="json"
        )
        self.assertEqual(attribute_response.status_code, 201)
        attribute_id = attribute_response.data["data"]["id"]
        option_response = self.client.post(
            "/api/catalog/variant-options",
            {"attribute": attribute_id, "name": "  Cotton  ", "sku_code": "ctn1"},
            format="json",
        )
        self.assertEqual(option_response.status_code, 201)
        self.assertEqual(option_response.data["data"]["sku_code"], "CTN1")


class CategoryWriteTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(username="admin", password="password")
        self.client.force_authenticate(self.user)
        self.status = CategoryStatus.objects.create(name="active")

    def test_create_category_with_optional_parent(self):
        parent = Category.objects.create(name="Electronics", status=self.status)

        response = self.client.post(
            "/api/catalog/categories",
            {"name": " Phones ", "parent": parent.id, "status": self.status.id},
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        category = Category.objects.get(name="Phones")
        self.assertEqual(category.parent, parent)

    def test_create_rejects_normalized_duplicate(self):
        Category.objects.create(name="Electronics Store", status=self.status)

        response = self.client.post(
            "/api/catalog/categories",
            {"name": " electronics  store ", "status": self.status.id},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(Category.objects.count(), 1)

    def test_update_excludes_current_category_from_duplicate_check(self):
        category = Category.objects.create(name="Phones", status=self.status)

        response = self.client.patch(
            f"/api/catalog/categories/{category.id}",
            {"name": "Phones"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)

    def test_update_rejects_descendant_as_parent(self):
        parent = Category.objects.create(name="Electronics", status=self.status)
        child = Category.objects.create(name="Phones", parent=parent, status=self.status)

        response = self.client.patch(
            f"/api/catalog/categories/{parent.id}",
            {"parent": child.id},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        parent.refresh_from_db()
        self.assertIsNone(parent.parent)

    def test_name_suggestions_return_ranked_matches_and_exact_flag(self):
        category = Category.objects.create(name="Smart Phones", status=self.status)
        Category.objects.create(name="Groceries", status=self.status)

        response = self.client.get(
            "/api/catalog/categories/name-suggestions",
            {"name": "smart phone"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["data"]["exact_duplicate"])
        self.assertEqual(response.data["data"]["suggestions"][0]["id"], category.id)

        exact_response = self.client.get(
            "/api/catalog/categories/name-suggestions",
            {"name": " SMART PHONES "},
        )
        self.assertTrue(exact_response.data["data"]["exact_duplicate"])

    def test_name_suggestions_exclude_edited_category(self):
        category = Category.objects.create(name="Smart Phones", status=self.status)

        response = self.client.get(
            "/api/catalog/categories/name-suggestions",
            {"name": "Smart Phones", "exclude_id": category.id},
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["data"]["exact_duplicate"])
        self.assertEqual(response.data["data"]["suggestions"], [])


class CategoryDetailWriteTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(username="admin", password="password")
        self.client.force_authenticate(self.user)

    def test_create_select_detail_normalizes_options(self):
        response = self.client.post(
            "/api/catalog/category-details",
            {
                "name": " Product Color ",
                "type": "select",
                "required": True,
                "options": " Red, Green , ,Blue ",
                "filterable": True,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        detail = CategoryDetail.objects.get(name="Product Color")
        self.assertEqual(detail.options, "Red,Green,Blue")

    def test_select_detail_requires_options(self):
        response = self.client.post(
            "/api/catalog/category-details",
            {"name": "Color", "type": "select", "options": " , "},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(CategoryDetail.objects.exists())

    def test_text_and_number_details_clear_options(self):
        detail = CategoryDetail.objects.create(
            name="Weight",
            type="select",
            options="Light,Heavy",
        )

        response = self.client.patch(
            f"/api/catalog/category-details/{detail.id}",
            {"type": "number"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        detail.refresh_from_db()
        self.assertEqual(detail.options, "")

    def test_create_rejects_normalized_duplicate(self):
        CategoryDetail.objects.create(name="Product Color", type="text")

        response = self.client.post(
            "/api/catalog/category-details",
            {"name": " product  color ", "type": "number"},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(CategoryDetail.objects.count(), 1)

    def test_update_excludes_current_detail_from_duplicate_check(self):
        detail = CategoryDetail.objects.create(name="Color", type="text")

        response = self.client.patch(
            f"/api/catalog/category-details/{detail.id}",
            {"name": "Color"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)

    def test_name_suggestions_return_matches_and_exclude_current_detail(self):
        detail = CategoryDetail.objects.create(name="Product Color", type="select", options="Red")

        response = self.client.get(
            "/api/catalog/category-details/name-suggestions",
            {"name": "product colors"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["suggestions"][0]["id"], detail.id)

        excluded_response = self.client.get(
            "/api/catalog/category-details/name-suggestions",
            {"name": "Product Color", "exclude_id": detail.id},
        )
        self.assertFalse(excluded_response.data["data"]["exact_duplicate"])
        self.assertEqual(excluded_response.data["data"]["suggestions"], [])


class CategoryDetailAssignmentTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(username="admin", password="password")
        self.client.force_authenticate(self.user)
        self.category_status = CategoryStatus.objects.create(name="active")
        self.product_status = ProductStatus.objects.create(name="active")
        self.category = Category.objects.create(name="Phones", status=self.category_status)
        self.color = CategoryDetail.objects.create(
            name="Color", type="select", options="Red,Blue"
        )
        self.weight = CategoryDetail.objects.create(name="Weight", type="number")

    @property
    def url(self):
        return f"/api/catalog/categories/{self.category.id}/assign-details"

    def test_get_returns_assignments_and_paginated_options(self):
        CategoryDetailRelation.objects.create(
            category=self.category, detail=self.color, value=""
        )

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["assignments"][0]["id"], self.color.id)
        options = response.data["data"]["details"]["results"]
        color_option = next(option for option in options if option["id"] == self.color.id)
        self.assertTrue(color_option["assigned"])
        self.assertFalse(color_option["in_use"])

    def test_post_atomically_assigns_and_deassigns_details(self):
        CategoryDetailRelation.objects.create(
            category=self.category, detail=self.color, value="legacy"
        )

        response = self.client.post(
            self.url,
            {"details": [self.weight.id]},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            set(CategoryDetailRelation.objects.filter(category=self.category).values_list(
                "detail_id", flat=True
            )),
            {self.weight.id},
        )

    def test_missing_details_does_not_clear_assignments(self):
        CategoryDetailRelation.objects.create(
            category=self.category, detail=self.color, value=""
        )

        response = self.client.post(self.url, {}, format="json")

        self.assertEqual(response.status_code, 400)
        self.assertTrue(
            CategoryDetailRelation.objects.filter(
                category=self.category, detail=self.color
            ).exists()
        )

    def test_deassigning_detail_used_by_product_is_blocked(self):
        CategoryDetailRelation.objects.create(
            category=self.category, detail=self.color, value=""
        )
        product = Product.objects.create(
            name="Phone",
            category=self.category,
            status=self.product_status,
        )
        ProductDetails.objects.create(product=product, detail=self.color, value="Red")

        response = self.client.post(self.url, {"details": []}, format="json")

        self.assertEqual(response.status_code, 400)
        self.assertTrue(
            CategoryDetailRelation.objects.filter(
                category=self.category, detail=self.color
            ).exists()
        )

        get_response = self.client.get(self.url)
        self.assertTrue(get_response.data["data"]["assignments"][0]["in_use"])


class ProductCompleteCreateTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(username="admin", password="password")
        self.client.force_authenticate(self.user)
        self.category_status = CategoryStatus.objects.create(name="active")
        self.product_status, _ = ProductStatus.objects.get_or_create(name="pending")
        self.category = Category.objects.create(name="Phones", status=self.category_status)
        self.color = CategoryDetail.objects.create(
            name="Color",
            type="select",
            required=True,
            options="Red,Blue",
        )
        self.weight = CategoryDetail.objects.create(name="Weight", type="number")
        self.storage = CategoryDetail.objects.create(
            name="Storage",
            type="select",
            required=True,
            options="128 GB,256 GB",
        )
        CategoryDetailRelation.objects.create(
            category=self.category, detail=self.color, value=""
        )
        CategoryDetailRelation.objects.create(
            category=self.category, detail=self.weight, value=""
        )
        CategoryDetailRelation.objects.create(
            category=self.category, detail=self.storage, value=""
        )

    def test_form_options_and_category_detail_definitions(self):
        options_response = self.client.get("/api/catalog/product-form-options")

        self.assertEqual(options_response.status_code, 200)
        self.assertEqual(options_response.data["data"]["categories"][0]["path"], "Phones")
        self.assertEqual(set(options_response.data["data"]), {"categories"})

        details_response = self.client.get(
            "/api/catalog/product-detail-definitions",
            {"category_ids": self.category.id},
        )
        self.assertEqual(details_response.status_code, 200)
        color = next(
            detail for detail in details_response.data["data"] if detail["id"] == self.color.id
        )
        self.assertEqual(color["options"], ["Red", "Blue"])
        self.assertEqual(color["category_ids"], [self.category.id])

    def test_complete_create_saves_product_and_valid_details_atomically(self):
        response = self.client.post(
            "/api/catalog/products/create",
            {
                "name": "Smart Phone",
                "category_ids": [self.category.id],
                "description": "**Reliable** phone",
                "details": [
                    {"detail_id": self.color.id, "value": "Red"},
                    {"detail_id": self.weight.id, "value": "180.5"},
                    {"detail_id": self.storage.id, "value": "128 GB"},
                ],
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        product = Product.objects.get(name="Smart Phone")
        self.assertEqual(product.category, self.category)
        self.assertEqual(product.status.name, "pending")
        self.assertEqual(product.details.count(), 3)

    def test_complete_create_rejects_missing_required_detail_without_product(self):
        response = self.client.post(
            "/api/catalog/products/create",
            {
                "name": "Incomplete Phone",
                "category_ids": [self.category.id],
                "details": [],
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(Product.objects.filter(name="Incomplete Phone").exists())

    def test_complete_create_rejects_invalid_select_value(self):
        response = self.client.post(
            "/api/catalog/products/create",
            {
                "name": "Invalid Phone",
                "category_ids": [self.category.id],
                "details": [
                    {"detail_id": self.color.id, "value": "Green"},
                    {"detail_id": self.storage.id, "value": "128 GB"},
                ],
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(Product.objects.filter(name="Invalid Phone").exists())

    def test_complete_create_rejects_unassigned_detail_atomically(self):
        unassigned = CategoryDetail.objects.create(name="Unassigned", type="text")
        payload = {
            "name": "Invalid Detail Phone",
            "category_ids": [self.category.id],
            "details": [
                {"detail_id": self.color.id, "value": "Red"},
                {"detail_id": self.storage.id, "value": "128 GB"},
                {"detail_id": unassigned.id, "value": "invalid"},
            ],
        }

        response = self.client.post("/api/catalog/products/create", payload, format="json")

        self.assertEqual(response.status_code, 400)
        self.assertFalse(Product.objects.filter(name="Invalid Detail Phone").exists())

    def test_complete_create_rejects_duplicate_product_details(self):
        response = self.client.post(
            "/api/catalog/products/create",
            {
                "name": "Duplicate Detail Phone",
                "category_ids": [self.category.id],
                "details": [
                    {"detail_id": self.color.id, "value": "Red"},
                    {"detail_id": self.color.id, "value": "Blue"},
                    {"detail_id": self.storage.id, "value": "128 GB"},
                ],
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(Product.objects.filter(name="Duplicate Detail Phone").exists())

    def test_basic_create_defaults_status_to_pending(self):
        response = self.client.post(
            "/api/catalog/products",
            {
                "name": "Basic Phone",
                "category": self.category.id,
                "description": "Created without an explicit status.",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(Product.objects.get(name="Basic Phone").status.name, "pending")

    def test_product_detail_endpoint_rejects_unassigned_detail(self):
        product = Product.objects.create(
            name="Existing Phone",
            category=self.category,
            status=self.product_status,
        )
        unassigned = CategoryDetail.objects.create(name="Unassigned", type="text")

        response = self.client.post(
            f"/api/catalog/products/{product.id}/details",
            {"detail_id": unassigned.id, "value": "invalid"},
            format="json",
        )

        self.assertEqual(response.status_code, 400)

    def test_numeric_product_detail_values_are_normalized(self):
        response = self.client.post(
            "/api/catalog/products/create",
            {
                "name": "Normalized Weight Phone",
                "category_ids": [self.category.id],
                "details": [
                    {"detail_id": self.color.id, "value": "Red"},
                    {"detail_id": self.storage.id, "value": "128 GB"},
                    {"detail_id": self.weight.id, "value": "180.500"},
                ],
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        product = Product.objects.get(name="Normalized Weight Phone")
        self.assertEqual(product.details.get(detail=self.weight).value, "180.5")

    def test_complete_update_replaces_details_and_preserves_status(self):
        product = Product.objects.create(
            name="Old Phone",
            category=self.category,
            status=self.product_status,
            description="Old description",
        )
        ProductDetails.objects.create(product=product, detail=self.color, value="Red")
        ProductDetails.objects.create(product=product, detail=self.storage, value="128 GB")

        response = self.client.patch(
            f"/api/catalog/products/{product.id}/update",
            {
                "name": "Updated Phone",
                "category_ids": [self.category.id],
                "description": "Updated description",
                "details": [
                    {"detail_id": self.color.id, "value": "Blue"},
                    {"detail_id": self.storage.id, "value": "256 GB"},
                    {"detail_id": self.weight.id, "value": "180.500"},
                ],
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        product.refresh_from_db()
        self.assertEqual(product.name, "Updated Phone")
        self.assertEqual(product.description, "Updated description")
        self.assertEqual(product.status, self.product_status)
        self.assertEqual(
            set(product.details.values_list("detail_id", "value")),
            {
                (self.color.id, "Blue"),
                (self.storage.id, "256 GB"),
                (self.weight.id, "180.5"),
            },
        )

    def test_complete_update_rolls_back_invalid_category_details(self):
        product = Product.objects.create(
            name="Stable Phone",
            category=self.category,
            status=self.product_status,
        )
        ProductDetails.objects.create(product=product, detail=self.color, value="Red")
        ProductDetails.objects.create(product=product, detail=self.storage, value="128 GB")
        other_category = Category.objects.create(
            name="Accessories",
            status=self.category_status,
        )

        response = self.client.patch(
            f"/api/catalog/products/{product.id}/update",
            {
                "name": "Broken Update",
                "category_ids": [other_category.id],
                "description": "Should not persist",
                "details": [{"detail_id": self.color.id, "value": "Blue"}],
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        product.refresh_from_db()
        self.assertEqual(product.name, "Stable Phone")
        self.assertEqual(product.category, self.category)
        self.assertEqual(
            set(product.details.values_list("detail_id", "value")),
            {(self.color.id, "Red"), (self.storage.id, "128 GB")},
        )

    def test_complete_update_changes_category_and_replaces_old_details(self):
        product = Product.objects.create(
            name="Phone",
            category=self.category,
            status=self.product_status,
        )
        ProductDetails.objects.create(product=product, detail=self.color, value="Red")
        ProductDetails.objects.create(product=product, detail=self.storage, value="128 GB")
        other_category = Category.objects.create(
            name="Wearables",
            status=self.category_status,
        )
        material = CategoryDetail.objects.create(
            name="Material",
            type="text",
            required=True,
        )
        CategoryDetailRelation.objects.create(
            category=other_category,
            detail=material,
            value="",
        )

        response = self.client.patch(
            f"/api/catalog/products/{product.id}/update",
            {
                "name": "Smart Watch",
                "category_ids": [other_category.id],
                "description": "Wearable",
                "details": [{"detail_id": material.id, "value": "Aluminum"}],
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        product.refresh_from_db()
        self.assertEqual(product.category, other_category)
        self.assertEqual(
            list(product.details.values_list("detail_id", "value")),
            [(material.id, "Aluminum")],
        )

    def test_basic_patch_preserves_existing_product_details(self):
        product = Product.objects.create(
            name="Phone",
            category=self.category,
            status=self.product_status,
        )
        ProductDetails.objects.create(product=product, detail=self.color, value="Red")

        response = self.client.patch(
            f"/api/catalog/products/{product.id}",
            {"description": "Updated only"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        product.refresh_from_db()
        self.assertEqual(product.description, "Updated only")
        self.assertEqual(product.details.get(detail=self.color).value, "Red")

    def test_basic_patch_cannot_change_category(self):
        product = Product.objects.create(
            name="Phone",
            category=self.category,
            status=self.product_status,
        )
        other_category = Category.objects.create(
            name="Unsafe Category",
            status=self.category_status,
        )

        response = self.client.patch(
            f"/api/catalog/products/{product.id}",
            {"category": other_category.id},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        product.refresh_from_db()
        self.assertEqual(product.category, self.category)


class CatalogSearchAndReadTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(username="search-admin", password="password")
        self.client.force_authenticate(self.user)
        self.category_status = CategoryStatus.objects.create(name="search-active")
        self.product_status = ProductStatus.objects.create(name="search-pending")
        self.category = Category.objects.create(name="Search Phones", status=self.category_status)
        self.normal, _ = InventoryStrategy.objects.get_or_create(
            code="normal", defaults={"name": "Search Normal"}
        )
        country = Country.objects.create(name="Search Country", code="SC", phone_code="+2")
        state = State.objects.create(name="Search State", country=country)
        city = City.objects.create(name="Search City", state=state)
        warehouse_status = WarehouseStatus.objects.create(name="search-available")
        self.warehouse = Warehouse.objects.create(
            code="WH-SEARCH",
            name="Search Warehouse",
            city=city,
            address="Search",
            lat="0",
            lng="0",
            is_default=True,
            status=warehouse_status,
        )
        self.attribute = VariantAttribute.objects.create(name="Search Color")
        self.option = VariantOption.objects.create(
            attribute=self.attribute, name="Ocean Blue", sku_code="OCN"
        )

    def create_product(self, name, prices):
        product = Product.objects.create(
            name=name, category=self.category, status=self.product_status
        )
        variants = []
        for index, price in enumerate(prices):
            variant = ProductVariants.objects.create(
                product=product,
                inventory_strategy=self.normal,
                sku=f"{name.upper().replace(' ', '-')}-{index}",
                combination_key=f"{index}",
                price=price,
            )
            variants.append(variant)
        return product, variants

    def result_ids(self, response):
        return [item["id"] for item in response.data["data"]["results"]]

    def test_product_price_filters_match_one_variant(self):
        split, _ = self.create_product("Split Prices", ["5.00", "20.00"])
        matching, _ = self.create_product("Matching Price", ["12.00"])

        response = self.client.get(
            "/api/catalog/products",
            {"price_operator": "between", "price_min": "10.00", "price_max": "15.00"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotIn(split.id, self.result_ids(response))
        self.assertIn(matching.id, self.result_ids(response))
        equal = self.client.get(
            "/api/catalog/products", {"price_operator": "equal", "price": "12.00"}
        )
        less_than = self.client.get(
            "/api/catalog/products", {"price_operator": "less_than", "price": "6.00"}
        )
        greater_than = self.client.get(
            "/api/catalog/products", {"price_operator": "greater_than", "price": "19.00"}
        )
        self.assertEqual(self.result_ids(equal), [matching.id])
        self.assertIn(split.id, self.result_ids(less_than))
        self.assertIn(split.id, self.result_ids(greater_than))

    def test_product_standard_filters_can_be_combined(self):
        matching, _ = self.create_product("Combined Search Phone", [])
        self.create_product("Different Phone", [])

        response = self.client.get(
            "/api/catalog/products",
            {
                "id": matching.id,
                "name": "combined search",
                "category_id": self.category.id,
                "status_id": self.product_status.id,
            },
        )

        self.assertEqual(self.result_ids(response), [matching.id])

    def test_product_search_covers_details_and_variant_fields(self):
        product, variants = self.create_product("Advanced Product", ["42.00"])
        detail = CategoryDetail.objects.create(name="Surface", type="text")
        ProductDetails.objects.create(product=product, detail=detail, value="Ceramic finish")
        ProductVariantSelection.objects.create(
            variant=variants[0], attribute=self.attribute, option=self.option
        )

        detail_response = self.client.get("/api/catalog/products", {"search": "ceramic"})
        option_response = self.client.get("/api/catalog/products", {"search": "ocean blue"})

        self.assertIn(product.id, self.result_ids(detail_response))
        self.assertIn(product.id, self.result_ids(option_response))

    def test_product_detail_read_payload_includes_names_pictures_and_children(self):
        product, variants = self.create_product("Readable Product", ["50.00"])
        detail = CategoryDetail.objects.create(name="Material", type="text")
        ProductDetails.objects.create(product=product, detail=detail, value="Steel")

        response = self.client.get(f"/api/catalog/products/{product.id}")

        self.assertEqual(response.status_code, 200)
        data = response.data["data"]
        self.assertEqual(data["category_name"], self.category.name)
        self.assertEqual(data["status_name"], self.product_status.name)
        self.assertEqual(data["pictures"], [])
        self.assertEqual(data["details"][0]["detail_name"], "Material")
        self.assertEqual(data["variants"][0]["id"], variants[0].id)

    def test_variant_search_covers_ids_options_and_inventory_counts(self):
        product, variants = self.create_product("Inventory Product", ["99.00"])
        variant = variants[0]
        ProductVariantSelection.objects.create(
            variant=variant, attribute=self.attribute, option=self.option
        )
        WarehouseStock.objects.create(
            variant=variant,
            warehouse=self.warehouse,
            quantity=987,
            sellable=987,
            reserved=0,
        )

        count_response = self.client.get(
            f"/api/catalog/products/{product.id}/variants", {"search": "987"}
        )
        option_id_response = self.client.get(
            "/api/catalog/variant-attributes", {"search": str(self.option.id)}
        )

        self.assertEqual([item["id"] for item in count_response.data["data"]], [variant.id])
        self.assertEqual(option_id_response.data["data"][0]["id"], self.attribute.id)

    def test_invalid_product_price_query_is_rejected(self):
        response = self.client.get(
            "/api/catalog/products",
            {"price_operator": "between", "price_min": "20", "price_max": "10"},
        )
        self.assertEqual(response.status_code, 400)
