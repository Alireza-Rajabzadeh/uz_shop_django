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
)


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
            name="Phone", category=self.category, status=self.product_status
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
        self.product_status = ProductStatus.objects.create(name="pending")
        self.category = Category.objects.create(name="Phones", status=self.category_status)
        self.color = CategoryDetail.objects.create(
            name="Color",
            type="select",
            required=True,
            options="Red,Blue",
        )
        self.weight = CategoryDetail.objects.create(name="Weight", type="number")
        CategoryDetailRelation.objects.create(
            category=self.category, detail=self.color, value=""
        )
        CategoryDetailRelation.objects.create(
            category=self.category, detail=self.weight, value=""
        )

    def test_form_options_and_category_detail_definitions(self):
        options_response = self.client.get("/api/catalog/product-form-options")

        self.assertEqual(options_response.status_code, 200)
        self.assertEqual(options_response.data["data"]["categories"][0]["path"], "Phones")
        self.assertEqual(
            options_response.data["data"]["statuses"][0]["id"],
            self.product_status.id,
        )

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
                "status": self.product_status.id,
                "category_ids": [self.category.id],
                "description": "**Reliable** phone",
                "details": [
                    {"detail_id": self.color.id, "value": "Red"},
                    {"detail_id": self.weight.id, "value": "180.5"},
                ],
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        product = Product.objects.get(name="Smart Phone")
        self.assertEqual(product.category, self.category)
        self.assertEqual(product.details.count(), 2)

    def test_complete_create_rejects_missing_required_detail_without_product(self):
        response = self.client.post(
            "/api/catalog/products/create",
            {
                "name": "Incomplete Phone",
                "status": self.product_status.id,
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
                "status": self.product_status.id,
                "category_ids": [self.category.id],
                "details": [{"detail_id": self.color.id, "value": "Green"}],
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(Product.objects.filter(name="Invalid Phone").exists())
