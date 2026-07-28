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
    ProductVariantsDetails,
)
from domains.inventory.models import InventoryStrategy


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
        self.color = CategoryDetail.objects.create(
            name="Variant Color", type="select", options="Black,White"
        )
        self.storage = CategoryDetail.objects.create(name="Variant Storage", type="number")
        CategoryDetailRelation.objects.create(
            category=self.category, detail=self.color, value=""
        )
        self.normal, _ = InventoryStrategy.objects.get_or_create(
            code="normal", defaults={"name": "Normal"}
        )
        InventoryStrategy.objects.get_or_create(
            code="serialized", defaults={"name": "Serialized"}
        )

    def test_form_options_prioritize_category_details_without_restricting_others(self):
        response = self.client.get(
            f"/api/catalog/products/{self.product.id}/variant-form-options"
        )

        self.assertEqual(response.status_code, 200)
        details = {item["id"]: item for item in response.data["data"]["details"]}
        self.assertTrue(details[self.color.id]["category_default"])
        self.assertFalse(details[self.storage.id]["category_default"])

    def test_create_variant_uses_normal_strategy_and_accepts_any_detail(self):
        response = self.client.post(
            f"/api/catalog/products/{self.product.id}/variants",
            {
                "sku": "PHONE-BLACK",
                "price": "100.00",
                "discount_type": "percentage",
                "discount_value": "10.00",
                "details": [
                    {"detail_id": self.color.id, "value": "Black"},
                    {"detail_id": self.storage.id, "value": "256"},
                ],
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        variant = ProductVariants.objects.get(product=self.product)
        self.assertEqual(variant.inventory_strategy, self.normal)
        self.assertEqual(
            set(variant.details.values_list("detail_id", "value")),
            {(self.color.id, "Black"), (self.storage.id, "256")},
        )

    def test_update_replaces_details_and_keeps_normal_strategy(self):
        variant = ProductVariants.objects.create(
            product=self.product,
            inventory_strategy=self.normal,
            sku="OLD",
            price="100.00",
        )
        ProductVariantsDetails.objects.create(
            variant=variant, detail=self.color, value="White"
        )

        response = self.client.patch(
            f"/api/catalog/variants/{variant.id}",
            {
                "sku": "NEW",
                "details": [{"detail_id": self.storage.id, "value": "128"}],
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        variant.refresh_from_db()
        self.assertEqual(variant.sku, "NEW")
        self.assertEqual(variant.inventory_strategy, self.normal)
        self.assertEqual(
            list(variant.details.values_list("detail_id", "value")),
            [(self.storage.id, "128")],
        )

    def test_update_preserves_existing_serialized_strategy(self):
        serialized = InventoryStrategy.objects.get(code="serialized")
        variant = ProductVariants.objects.create(
            product=self.product,
            inventory_strategy=serialized,
            sku="SERIALIZED",
            price="100.00",
        )

        response = self.client.patch(
            f"/api/catalog/variants/{variant.id}",
            {"price": "120.00"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        variant.refresh_from_db()
        self.assertEqual(variant.inventory_strategy, serialized)

    def test_delete_variant_cascades_owned_detail_values(self):
        variant = ProductVariants.objects.create(
            product=self.product,
            inventory_strategy=self.normal,
            sku="DELETE-ME",
            price="100.00",
        )
        detail_value = ProductVariantsDetails.objects.create(
            variant=variant, detail=self.color, value="Black"
        )

        response = self.client.delete(f"/api/catalog/variants/{variant.id}")

        self.assertEqual(response.status_code, 200)
        self.assertFalse(ProductVariants.objects.filter(id=variant.id).exists())
        self.assertFalse(ProductVariantsDetails.objects.filter(id=detail_value.id).exists())


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
