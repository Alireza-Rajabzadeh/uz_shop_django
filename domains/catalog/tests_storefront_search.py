from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APIClient

from domains.business.models import BusinessProfile
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
    ProductVariantStatus,
    VariantAttribute,
    VariantOption,
)
from domains.catalog.services import DetailService
from domains.inventory.models import Inventory, Warehouse, WarehouseStatus
from domains.location.models import City, Country, State
from domains.marketplace.models import BusinessOffer
from domains.vendor.models import Vendor, VendorStatus


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
        vendor_status, _ = VendorStatus.objects.get_or_create(
            name="active", defaults={"title": "Active"}
        )
        self.vendor, _ = Vendor.objects.get_or_create(
            phone="+9990000001",
            defaults={
                "first_name": "Test",
                "last_name": "Vendor",
                "national_id": "0000000001",
                "vendor_code": "STF01",
                "status": vendor_status,
            },
        )
        self.business, _ = BusinessProfile.objects.get_or_create(
            pk=1,
            defaults={
                "vendor": self.vendor,
                "business_name": "Test Business",
                "display_name": "Test Business",
            },
        )
        self.variant_status, _ = ProductVariantStatus.objects.get_or_create(
            name="active"
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
            status=self.variant_status,
            sku=f"{product.id}-{suffix}",
            combination_key=suffix,
        )
        offer_kwargs = {}
        for k, v in discount.items():
            if k == "discount_type":
                offer_kwargs[k] = v
            elif v is not None:
                offer_kwargs[k] = Decimal(str(v))
        BusinessOffer.objects.create(
            business=self.business,
            variant=variant,
            price=Decimal(str(price)),
            **offer_kwargs,
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

    def create_second_business(self, name="Second Business"):
        return BusinessProfile.objects.create(
            vendor=None,
            business_name=name,
            display_name=name,
        )

    def create_stock(self, business, variant, available=10):
        country, _ = Country.objects.get_or_create(
            code="ST", defaults={"name": "Storefront"}
        )
        state, _ = State.objects.get_or_create(
            name="Storefront State", country=country
        )
        city, _ = City.objects.get_or_create(
            name="Storefront City", state=state
        )
        status, _ = WarehouseStatus.objects.get_or_create(name="active")
        warehouse, _ = Warehouse.objects.get_or_create(
            code=f"WH-STF-{business.id}",
            defaults={
                "name": f"Warehouse {business.id}",
                "business": business,
                "city": city,
                "address": "Test address",
                "lat": "0",
                "lng": "0",
                "is_default": True,
                "status": status,
            },
        )
        return Inventory.objects.create(
            business=business,
            variant=variant,
            warehouse=warehouse,
            quantity=available,
            sellable=available,
            reserved=0,
            min_stock=0,
        )

    def test_search_returns_pricing_from_the_cheapest_effective_offer(self):
        product = self.create_product("Zeta Samsung Phone", self.samsung)
        variant = self.create_variant(product, "blue", "100.00", [self.blue])
        second = self.create_second_business()
        BusinessOffer.objects.create(
            business=second,
            variant=variant,
            price=Decimal("80.00"),
            discount_type="percentage",
            discount_value=Decimal("10.00"),
        )

        response = self.client.get(
            "/api/catalog/storefront/products",
            {"q": "zeta"},
        )

        self.assertEqual(response.status_code, 200, response.data)
        item = response.data["data"]["results"][0]
        self.assertEqual(item["pricing"]["minimum_price"], "80.00")
        self.assertEqual(item["pricing"]["minimum_effective_price"], "72.00")

    def test_search_filters_and_orders_by_effective_price(self):
        cheap = self.create_product("Zeta Cheap", self.samsung)
        dear = self.create_product("Zeta Dear", self.samsung)
        self.create_variant(cheap, "cheap", "80.00", [self.blue])
        self.create_variant(
            dear,
            "dear",
            "100.00",
            [self.black],
            discount_type="percentage",
            discount_value="10.00",
        )

        ascending = self.client.get(
            "/api/catalog/storefront/products",
            {"q": "zeta", "ordering": "price_asc"},
        )
        descending = self.client.get(
            "/api/catalog/storefront/products",
            {"q": "zeta", "ordering": "price_desc"},
        )
        above_85 = self.client.get(
            "/api/catalog/storefront/products",
            {"q": "zeta", "price_min": "85"},
        )
        below_85 = self.client.get(
            "/api/catalog/storefront/products",
            {"q": "zeta", "price_max": "85"},
        )

        self.assertEqual(
            [item["id"] for item in ascending.data["data"]["results"]],
            [cheap.id, dear.id],
        )
        self.assertEqual(
            [item["id"] for item in descending.data["data"]["results"]],
            [dear.id, cheap.id],
        )
        self.assertEqual(
            [item["id"] for item in above_85.data["data"]["results"]],
            [dear.id],
        )
        self.assertEqual(
            [item["id"] for item in below_85.data["data"]["results"]],
            [cheap.id],
        )
        price = ascending.data["data"]["facets"]["price"]
        self.assertEqual(price["minimum"], "80.00")
        self.assertEqual(price["maximum"], "90.00")

    def test_detail_uses_the_cheapest_active_offer(self):
        product = self.create_product("Zeta Detail Phone", self.samsung)
        variant = self.create_variant(product, "blue", "100.00", [self.blue])
        second = self.create_second_business()
        BusinessOffer.objects.create(
            business=second,
            variant=variant,
            price=Decimal("80.00"),
            discount_type="percentage",
            discount_value=Decimal("10.00"),
        )

        response = self.client.get(
            f"/api/catalog/storefront/products/{product.slug}"
        )

        self.assertEqual(response.status_code, 200, response.data)
        payload = response.data["data"]["variants"][0]
        self.assertEqual(payload["id"], variant.id)
        self.assertEqual(payload["price"], Decimal("80.00"))
        self.assertEqual(payload["effective_price"], Decimal("72.00"))

    def test_detail_ignores_unlisted_variants_in_price_range(self):
        product = self.create_product("Zeta Unlisted Phone", self.samsung)
        unlisted = ProductVariants.objects.create(
            product=product,
            status=self.variant_status,
            sku=f"{product.id}-unlisted",
            combination_key="unlisted",
        )
        listed = self.create_variant(
            product,
            "listed",
            "100.00",
            [self.blue],
            discount_type="fixed",
            discount_value="10.00",
        )

        response = self.client.get(
            f"/api/catalog/storefront/products/{product.slug}"
        )

        self.assertEqual(response.status_code, 200, response.data)
        data = response.data["data"]
        self.assertEqual(data["pricing"]["minimum_price"], Decimal("100.00"))
        self.assertEqual(
            data["pricing"]["minimum_effective_price"], Decimal("90.00")
        )
        self.assertEqual(
            data["pricing"]["maximum_effective_price"], Decimal("90.00")
        )
        self.assertEqual(data["default_variant"]["id"], listed.id)
        unlisted_payload = next(
            row for row in data["variants"] if row["id"] == unlisted.id
        )
        self.assertIsNone(unlisted_payload["price"])

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

    def test_detail_returns_similar_products_from_shared_category(self):
        target = self.create_product("Samsung Galaxy A55", self.samsung)
        same_category = self.create_product("Samsung Galaxy S24", self.samsung)
        other_category = Category.objects.create(name="Home Appliances", status=self.category_status)
        other_product = Product.objects.create(name="Fridge", status=self.product_status)
        other_product.categories.add(other_category)

        self.create_variant(target, "blue", "100.00", [self.blue])
        self.create_variant(same_category, "black", "200.00", [self.black])
        self.create_variant(other_product, "blue", "50.00", [self.blue])

        response = self.client.get(f"/api/catalog/storefront/products/{target.slug}")

        self.assertEqual(response.status_code, 200, response.data)
        similar_ids = [item["id"] for item in response.data["data"]["similar_products"]]
        self.assertIn(same_category.id, similar_ids)
        self.assertNotIn(target.id, similar_ids)
        self.assertNotIn(other_product.id, similar_ids)

    def test_similar_products_are_capped_at_fifteen(self):
        target = self.create_product("Samsung Galaxy A55", self.samsung)
        for index in range(16):
            sibling = self.create_product(f"Sibling {index}", self.samsung)
            self.create_variant(sibling, f"s{index}", "10.00", [self.blue])

        response = self.client.get(f"/api/catalog/storefront/products/{target.slug}")

        self.assertEqual(response.status_code, 200, response.data)
        self.assertLessEqual(len(response.data["data"]["similar_products"]), 15)

    def test_detail_returns_discounted_products_as_suggestions(self):
        on_sale = self.create_product("Samsung On Sale", self.samsung)
        regular = self.create_product("Samsung Regular", self.samsung)
        self.create_variant(
            on_sale,
            "blue",
            "100.00",
            [self.blue],
            discount_type="percentage",
            discount_value="10.00",
        )
        self.create_variant(regular, "black", "90.00", [self.black])

        response = self.client.get(f"/api/catalog/storefront/products/{regular.slug}")

        self.assertEqual(response.status_code, 200, response.data)
        suggestion_ids = [item["id"] for item in response.data["data"]["suggested_products"]]
        self.assertIn(on_sale.id, suggestion_ids)
        self.assertNotIn(regular.id, suggestion_ids)

    def test_detail_includes_product_seo_record(self):
        from domains.content.models import SEORecord

        product = self.create_product("Samsung Galaxy A55", self.samsung)
        self.create_variant(product, "blue", "100.00", [self.blue])
        SEORecord.objects.create(
            resource_type="product",
            resource_id=product.id,
            title="Buy Samsung Galaxy A55",
            description="Product SEO description",
            canonical_url="https://example.com/products/samsung-galaxy-a55",
        )

        response = self.client.get(f"/api/catalog/storefront/products/{product.slug}")

        self.assertEqual(response.status_code, 200, response.data)
        seo = response.data["data"]["seo"]
        self.assertEqual(seo["title"], "Buy Samsung Galaxy A55")
        self.assertEqual(seo["description"], "Product SEO description")
        self.assertEqual(
            seo["canonical_url"], "https://example.com/products/samsung-galaxy-a55"
        )

    def test_detail_returns_null_seo_without_record(self):
        product = self.create_product("Samsung Galaxy A55", self.samsung)
        self.create_variant(product, "blue", "100.00", [self.blue])

        response = self.client.get(f"/api/catalog/storefront/products/{product.slug}")

        self.assertEqual(response.status_code, 200, response.data)
        self.assertIsNone(response.data["data"]["seo"])

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

    def test_search_filters_by_category_slug_including_descendants(self):
        child = Category.objects.create(
            name="Smartphones",
            status=self.category_status,
            parent=self.category,
        )
        root_product = self.create_product("Root Phone", self.samsung)
        child_product = self.create_product("Child Phone", self.samsung)
        child_product.categories.add(child)
        self.create_variant(root_product, "root", "100.00", [self.blue])
        self.create_variant(child_product, "child", "110.00", [self.black])

        response = self.client.get(
            "/api/catalog/storefront/products",
            {"category": self.category.slug},
        )

        self.assertEqual(response.status_code, 200, response.data)
        ids = {item["id"] for item in response.data["data"]["results"]}
        self.assertEqual(ids, {root_product.id, child_product.id})

    def test_search_filters_by_brand_slug(self):
        samsung = self.create_product("Samsung Galaxy A55", self.samsung)
        xiaomi = self.create_product("Xiaomi A55", self.xiaomi)
        self.create_variant(samsung, "s", "100.00", [self.blue])
        self.create_variant(xiaomi, "x", "90.00", [self.black])

        response = self.client.get(
            "/api/catalog/storefront/products",
            {"brand": self.samsung.slug},
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(
            [item["id"] for item in response.data["data"]["results"]],
            [samsung.id],
        )

    def test_search_mixes_category_ids_and_slugs(self):
        product = self.create_product("Mixed Filter Phone", self.samsung)
        self.create_variant(product, "mixed", "100.00", [self.blue])

        response = self.client.get(
            "/api/catalog/storefront/products",
            {"category": [str(self.category.id), self.category.slug]},
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(
            [item["id"] for item in response.data["data"]["results"]],
            [product.id],
        )

    def test_search_rejects_unknown_category_slug(self):
        response = self.client.get(
            "/api/catalog/storefront/products",
            {"category": "does-not-exist"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("category", response.data["errors"])

    def test_search_rejects_unknown_brand_slug(self):
        response = self.client.get(
            "/api/catalog/storefront/products",
            {"brand": "does-not-exist"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("brand", response.data["errors"])

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

    def test_detail_exposes_selected_offer_and_seller_preview(self):
        product = self.create_product("Seller Preview Phone", self.samsung)
        variant = self.create_variant(product, "blue", "100.00", [self.blue])
        second = self.create_second_business()
        second_offer = BusinessOffer.objects.create(
            business=second,
            variant=variant,
            price=Decimal("80.00"),
            discount_type="percentage",
            discount_value=Decimal("10.00"),
        )

        response = self.client.get(
            f"/api/catalog/storefront/products/{product.slug}"
        )

        self.assertEqual(response.status_code, 200, response.data)
        data = response.data["data"]
        payload = data["variants"][0]
        self.assertEqual(payload["selected_offer"]["id"], second_offer.id)
        self.assertEqual(
            payload["selected_offer"]["business"]["id"], second.id
        )
        self.assertEqual(
            payload["selected_offer"]["business"]["name"], second.display_name
        )
        self.assertEqual(payload["offer_summary"]["total"], 2)
        self.assertEqual(payload["offer_summary"]["seller_count"], 2)
        self.assertEqual(len(payload["offers"]), 2)
        self.assertEqual(payload["offers"][0]["id"], second_offer.id)
        self.assertNotIn(
            "expected_profit_percentage", payload["selected_offer"]
        )
        self.assertEqual(data["offers"]["seller_count"], 2)
        self.assertEqual(
            data["default_variant"]["selected_offer"]["id"], second_offer.id
        )

    def test_search_returns_seller_counts_and_filters_by_business(self):
        product = self.create_product("Seller Count Phone", self.samsung)
        variant = self.create_variant(product, "blue", "100.00", [self.blue])
        second = self.create_second_business()
        BusinessOffer.objects.create(
            business=second,
            variant=variant,
            price=Decimal("80.00"),
        )

        response = self.client.get(
            "/api/catalog/storefront/products", {"q": "seller count"}
        )

        self.assertEqual(response.status_code, 200, response.data)
        item = response.data["data"]["results"][0]
        self.assertEqual(item["offers"]["seller_count"], 2)
        self.assertEqual(item["offers"]["in_stock_seller_count"], 0)

        filtered = self.client.get(
            "/api/catalog/storefront/products",
            {"q": "seller count", "business": second.id},
        )
        self.assertEqual(filtered.status_code, 200, filtered.data)
        self.assertEqual(
            [row["id"] for row in filtered.data["data"]["results"]],
            [product.id],
        )
        filtered_item = filtered.data["data"]["results"][0]
        self.assertEqual(filtered_item["pricing"]["minimum_price"], "80.00")
        self.assertEqual(filtered_item["offers"]["seller_count"], 1)

    def test_business_filter_scopes_prices_to_that_business(self):
        product = self.create_product("Scoped Price Phone", self.samsung)
        variant = self.create_variant(product, "blue", "100.00", [self.blue])
        second = self.create_second_business()
        BusinessOffer.objects.create(
            business=second,
            variant=variant,
            price=Decimal("80.00"),
        )

        global_result = self.client.get(
            "/api/catalog/storefront/products", {"q": "scoped price"}
        )
        second_result = self.client.get(
            "/api/catalog/storefront/products",
            {"q": "scoped price", "business": second.id},
        )
        owner_result = self.client.get(
            "/api/catalog/storefront/products",
            {"q": "scoped price", "business": self.business.id},
        )

        self.assertEqual(
            global_result.data["data"]["results"][0]["pricing"]["minimum_price"],
            "80.00",
        )
        self.assertEqual(
            second_result.data["data"]["results"][0]["pricing"]["minimum_price"],
            "80.00",
        )
        self.assertEqual(
            owner_result.data["data"]["results"][0]["pricing"]["minimum_price"],
            "100.00",
        )

    def test_in_stock_offer_wins_over_a_cheaper_out_of_stock_offer(self):
        product = self.create_product("In Stock Seller Phone", self.samsung)
        variant = self.create_variant(product, "blue", "100.00", [self.blue])
        self.create_stock(self.business, variant)
        second = self.create_second_business()
        cheaper = BusinessOffer.objects.create(
            business=second,
            variant=variant,
            price=Decimal("80.00"),
        )

        search = self.client.get(
            "/api/catalog/storefront/products", {"q": "in stock seller"}
        )
        detail = self.client.get(
            f"/api/catalog/storefront/products/{product.slug}"
        )

        self.assertEqual(search.status_code, 200, search.data)
        item = search.data["data"]["results"][0]
        self.assertEqual(item["pricing"]["minimum_price"], "100.00")
        self.assertEqual(item["pricing"]["minimum_effective_price"], "100.00")
        self.assertEqual(item["offers"]["seller_count"], 2)
        self.assertEqual(item["offers"]["in_stock_seller_count"], 1)

        second_search = self.client.get(
            "/api/catalog/storefront/products",
            {"q": "in stock seller", "business": second.id},
        )
        second_item = second_search.data["data"]["results"][0]
        self.assertEqual(second_item["pricing"]["minimum_price"], "80.00")
        self.assertFalse(second_item["availability"]["in_stock"])
        self.assertEqual(second_item["offers"]["seller_count"], 1)
        self.assertEqual(second_item["offers"]["in_stock_seller_count"], 0)
        self.assertEqual(
            detail.data["data"]["variants"][0]["selected_offer"]["id"],
            BusinessOffer.objects.get(
                business=self.business, variant=variant
            ).id,
        )
        self.assertNotEqual(
            detail.data["data"]["variants"][0]["selected_offer"]["id"],
            cheaper.id,
        )

    def test_variant_offers_endpoint_is_paginated_and_public(self):
        product = self.create_product("Offer List Phone", self.samsung)
        variant = self.create_variant(product, "blue", "100.00", [self.blue])
        for index, price in enumerate(("90.00", "80.00", "70.00"), start=1):
            business = self.create_second_business(f"Seller {index}")
            BusinessOffer.objects.create(
                business=business,
                variant=variant,
                price=Decimal(price),
            )

        first = self.client.get(
            f"/api/catalog/storefront/products/{product.slug}"
            f"/variants/{variant.id}/offers",
            {"page_size": 2},
        )
        second = self.client.get(
            f"/api/catalog/storefront/products/{product.slug}"
            f"/variants/{variant.id}/offers",
            {"page_size": 2, "page": 2},
        )

        self.assertEqual(first.status_code, 200, first.data)
        data = first.data["data"]
        self.assertEqual(data["count"], 4)
        self.assertEqual(len(data["results"]), 2)
        self.assertIsNotNone(data["next"])
        self.assertEqual(
            [row["price"] for row in data["results"]],
            [Decimal("70.00"), Decimal("80.00")],
        )
        self.assertNotIn("expected_profit_percentage", data["results"][0])
        self.assertEqual(second.status_code, 200, second.data)
        self.assertEqual(len(second.data["data"]["results"]), 2)
        self.assertIsNone(second.data["data"]["next"])

    def test_offers_endpoint_rejects_a_variant_from_another_product(self):
        product = self.create_product("First Product", self.samsung)
        other = self.create_product("Second Product", self.samsung)
        variant = self.create_variant(product, "blue", "100.00", [self.blue])
        other_variant = self.create_variant(other, "black", "90.00", [self.black])

        response = self.client.get(
            f"/api/catalog/storefront/products/{product.slug}"
            f"/variants/{other_variant.id}/offers"
        )

        self.assertEqual(response.status_code, 404)
