from django.test import TestCase
from rest_framework.test import APIClient

from domains.catalog.models import (
    Brand,
    Category,
    CategoryDetail,
    CategoryDetailOption,
    CategoryDetailRelation,
    CategoryStatus,
    CategoryVariantAttribute,
    Product,
    ProductDetails,
    ProductStatus,
    ProductVariants,
    ProductVariantSelection,
    VariantAttribute,
    VariantOption,
)
from domains.catalog.services import DetailService
from domains.inventory.models import InventoryStrategy


class StorefrontProductSearchTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.category_status = CategoryStatus.objects.create(name="active")
        self.inactive_category_status = CategoryStatus.objects.create(name="inactive")
        self.product_status = ProductStatus.objects.create(name="active")
        self.inactive_product_status, _ = ProductStatus.objects.get_or_create(name="inactive")
        self.category = Category.objects.create(
            name="Mobile Phones",
            status=self.category_status,
        )
        self.samsung = Brand.objects.create(name="Samsung")
        self.xiaomi = Brand.objects.create(name="Xiaomi")
        self.strategy, _ = InventoryStrategy.objects.get_or_create(
            code="normal",
            defaults={"name": "Normal"},
        )

        self.network = DetailService().create_category_detail(
            name="Network",
            type="select",
            options="4G,5G",
            filterable=True,
        )
        CategoryDetailRelation.objects.create(
            category=self.category,
            detail=self.network,
            value="",
        )
        self.five_g = self.network.normalized_options.get(name="5G")

        self.color = VariantAttribute.objects.create(name="Color")
        self.storage = VariantAttribute.objects.create(name="Storage")
        CategoryVariantAttribute.objects.create(category=self.category, attribute=self.color)
        CategoryVariantAttribute.objects.create(category=self.category, attribute=self.storage)
        self.blue = VariantOption.objects.create(
            attribute=self.color,
            name="Blue",
            sku_code="BLUE",
        )
        self.black = VariantOption.objects.create(
            attribute=self.color,
            name="Black",
            sku_code="BLACK",
        )
        self.storage_256 = VariantOption.objects.create(
            attribute=self.storage,
            name="256 GB",
            sku_code="256GB",
        )

    def create_product(self, name, brand, *, status=None, detail_option=None):
        product = Product.objects.create(
            name=name,
            brand=brand,
            status=status or self.product_status,
        )
        product.categories.add(self.category)
        if detail_option:
            ProductDetails.objects.create(
                product=product,
                detail=detail_option.detail,
                option=detail_option,
                value=detail_option.name,
            )
        return product

    def create_variant(self, product, suffix, price, selections, **discount):
        variant = ProductVariants.objects.create(
            product=product,
            inventory_strategy=self.strategy,
            sku=f"{product.id}-{suffix}",
            combination_key=suffix,
            price=price,
            **discount,
        )
        ProductVariantSelection.objects.bulk_create([
            ProductVariantSelection(
                variant=variant,
                attribute=option.attribute,
                option=option,
            )
            for option in selections
        ])
        return variant

    def test_search_is_public_and_excludes_inactive_products(self):
        visible = self.create_product("Samsung Galaxy A55", self.samsung)
        hidden = self.create_product(
            "Hidden Samsung A55",
            self.samsung,
            status=self.inactive_product_status,
        )
        self.create_variant(visible, "blue", "100.00", [self.blue])
        self.create_variant(hidden, "black", "90.00", [self.black])

        response = self.client.get("/api/catalog/storefront/products", {"q": "a55"})

        self.assertEqual(response.status_code, 200, response.data)
        ids = [item["id"] for item in response.data["data"]["results"]]
        self.assertEqual(ids, [visible.id])
        self.assertEqual(response.data["data"]["results"][0]["slug"], visible.slug)

    def test_product_slugs_are_unicode_and_unique(self):
        first = self.create_product("گوشی سامسونگ", self.samsung)
        second = self.create_product("گوشی سامسونگ", self.samsung)

        self.assertEqual(first.slug, "گوشی-سامسونگ")
        self.assertEqual(second.slug, "گوشی-سامسونگ-2")

    def test_quick_view_and_full_detail_have_separate_contracts(self):
        product = self.create_product("Samsung Galaxy A55", self.samsung, detail_option=self.five_g)
        variant = self.create_variant(
            product,
            "blue-256",
            "100.00",
            [self.blue, self.storage_256],
            discount_type="percentage",
            discount_value="10.00",
        )

        quick = self.client.get(
            f"/api/catalog/storefront/products/{product.slug}/quick-view"
        )
        detail = self.client.get(f"/api/catalog/storefront/products/{product.slug}")

        self.assertEqual(quick.status_code, 200, quick.data)
        self.assertNotIn("variants", quick.data["data"])
        self.assertIn("description", quick.data["data"])
        self.assertEqual(quick.data["data"]["details"][0]["value"], "5G")
        self.assertEqual(quick.data["data"]["default_variant"]["id"], variant.id)
        self.assertEqual(len(quick.data["data"]["variant_options"]), 2)
        self.assertEqual(detail.status_code, 200, detail.data)
        self.assertEqual(detail.data["data"]["details"][0]["value"], "5G")
        self.assertEqual(detail.data["data"]["variants"][0]["id"], variant.id)
        self.assertEqual(detail.data["data"]["variants"][0]["effective_price"], 90)

    def test_search_normalizes_persian_and_arabic_characters(self):
        product = self.create_product("گوشي سامسونگ", self.samsung)
        self.create_variant(product, "fa", "100.00", [self.blue])

        response = self.client.get(
            "/api/catalog/storefront/products",
            {"q": "گوشی"},
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(
            [item["id"] for item in response.data["data"]["results"]],
            [product.id],
        )

    def test_facets_are_contextual_and_brand_is_disjunctive(self):
        samsung = self.create_product("Samsung Galaxy A55", self.samsung, detail_option=self.five_g)
        xiaomi = self.create_product("Xiaomi A55 Alternative", self.xiaomi, detail_option=self.five_g)
        self.create_variant(
            samsung,
            "blue-256",
            "100.00",
            [self.blue, self.storage_256],
            discount_type="percentage",
            discount_value="10.00",
        )
        self.create_variant(xiaomi, "black", "80.00", [self.black])

        response = self.client.get(
            "/api/catalog/storefront/products",
            {"q": "a55", "brand": self.samsung.id},
        )

        self.assertEqual(response.status_code, 200, response.data)
        data = response.data["data"]
        self.assertEqual([item["id"] for item in data["results"]], [samsung.id])
        brand_values = {item["id"]: item for item in data["facets"]["brands"]["values"]}
        self.assertEqual(brand_values[self.samsung.id]["count"], 1)
        self.assertTrue(brand_values[self.samsung.id]["selected"])
        self.assertEqual(brand_values[self.xiaomi.id]["count"], 1)
        detail = data["facets"]["details"][0]
        self.assertEqual(detail["id"], self.network.id)
        self.assertEqual(detail["values"][0]["id"], self.five_g.id)
        self.assertEqual(data["results"][0]["pricing"]["minimum_effective_price"], 90)

    def test_loose_variant_matches_qualify_but_exact_combination_ranks_first(self):
        exact = self.create_product("Exact Combination", self.samsung)
        loose = self.create_product("Loose Combination", self.samsung)
        self.create_variant(exact, "exact", "100.00", [self.blue, self.storage_256])
        self.create_variant(loose, "blue", "90.00", [self.blue])
        self.create_variant(loose, "storage", "95.00", [self.storage_256])

        response = self.client.get(
            "/api/catalog/storefront/products",
            {
                f"variant[{self.color.id}]": self.blue.id,
                f"variant[{self.storage.id}]": self.storage_256.id,
            },
        )

        self.assertEqual(response.status_code, 200, response.data)
        results = response.data["data"]["results"]
        self.assertEqual([item["id"] for item in results], [exact.id, loose.id])
        self.assertTrue(results[0]["variant_match"]["exact_combination"])
        self.assertFalse(results[1]["variant_match"]["exact_combination"])

    def test_rejects_an_option_attached_to_the_wrong_dynamic_filter(self):
        other_detail = CategoryDetail.objects.create(
            name="Warranty",
            type="select",
            options="Official",
            filterable=True,
        )
        other_option = CategoryDetailOption.objects.create(
            detail=other_detail,
            name="Official",
        )

        response = self.client.get(
            "/api/catalog/storefront/products",
            {f"detail[{self.network.id}]": other_option.id},
        )

        self.assertEqual(response.status_code, 400)
