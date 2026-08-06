import json
import tempfile
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APITestCase

from domains.catalog.integrations.digikala.filesystem import (
    sha256_json,
    write_json_atomic,
)
from domains.catalog.models import (
    Brand,
    Category,
    CategoryDetail,
    CategoryDetailRelation,
    CategoryStatus,
    CategoryVariantAttribute,
    Product,
    ProductDetails,
    ProductStatus,
    ProductVariants,
    VariantOption,
)
from domains.catalog.services.digikala_import_service import DigikalaImportService
from domains.inventory.models import InventoryStrategy


class DigikalaImportServiceTests(TestCase):
    def setUp(self):
        status, _ = CategoryStatus.objects.get_or_create(name="active")
        ProductStatus.objects.get_or_create(name="pending")
        self.active_product_status, _ = ProductStatus.objects.get_or_create(name="active")
        InventoryStrategy.objects.get_or_create(code="normal", defaults={"name": "Normal"})
        self.category = Category.objects.create(
            id=1003, name="Chargers", fa_name="شارژر گوشی", status=status
        )
        self.manual_category = Category.objects.create(
            id=3001, name="Manual", status=status
        )
        self.service = DigikalaImportService()

    @staticmethod
    def detail(*, title="شارژر تست", selling=800, rrp=1000):
        return {
            "source": {"id": 12345, "url": "https://api.digikala.com/v2/product/12345/"},
            "title_fa": title,
            "title_en": "Test Charger",
            "description": "توضیحات محصول",
            "brand": {
                "id": 50,
                "code": "test-brand",
                "title_fa": "برند تست",
                "title_en": "Test Brand",
            },
            "specifications": [
                {
                    "title": "عمومی",
                    "attributes": [
                        {"id": 1, "title": "توان خروجی", "values": ["20 وات"]}
                    ],
                }
            ],
            "variants": [
                {
                    "id": 10,
                    "status": "marketable",
                    "themes": [],
                    "color": {
                        "id": 1,
                        "title_fa": "مشکی",
                        "title_en": "Black",
                    },
                    "price": {"selling_price": selling, "rrp_price": rrp},
                },
                {
                    "id": 11,
                    "status": "marketable",
                    "themes": [],
                    "color": {
                        "id": 1,
                        "title_fa": "مشکی",
                        "title_en": "Black",
                    },
                    "price": {"selling_price": selling + 100, "rrp_price": rrp},
                },
            ],
            "images": {"main": ["https://example.test/image.jpg"], "gallery": []},
            "raw_status": "marketable",
        }

    def test_import_creates_complete_pending_catalog_structure_without_stock(self):
        result = self.service.import_product(self.detail(), [self.category.id])

        product = Product.objects.get(slug="digikala-12345")
        self.assertEqual(result["status"], "created")
        self.assertEqual(product.status.name, "pending")
        self.assertEqual(product.brand.name, "Test Brand")
        self.assertEqual(product.brand.fa_name, "برند تست")
        self.assertEqual(list(product.categories.values_list("id", flat=True)), [1003])
        definition = CategoryDetail.objects.get(name="توان خروجی")
        self.assertEqual(definition.type, "text")
        self.assertFalse(definition.filterable)
        self.assertTrue(
            CategoryDetailRelation.objects.filter(
                category=self.category, detail=definition
            ).exists()
        )
        self.assertEqual(
            ProductDetails.objects.get(product=product, detail=definition).value,
            "20 وات",
        )
        variant = ProductVariants.objects.get(product=product)
        self.assertEqual(variant.price, 1000)
        self.assertEqual(variant.discount_type, "fixed")
        self.assertEqual(variant.discount_value, 200)
        self.assertFalse(variant.warehouse_stocks.exists())
        option = VariantOption.objects.get(variant_selections__variant=variant)
        self.assertEqual(option.name, "Black")
        self.assertEqual(option.fa_name, "مشکی")
        self.assertTrue(
            CategoryVariantAttribute.objects.filter(
                category=self.category, attribute=option.attribute
            ).exists()
        )
        self.assertEqual(Brand.objects.count(), 1)

    def test_refresh_updates_source_fields_and_preserves_local_state(self):
        self.service.import_product(self.detail(), [self.category.id])
        product = Product.objects.get(slug="digikala-12345")
        product.status = self.active_product_status
        product.save(update_fields=["status"])
        product.categories.add(self.manual_category)

        result = self.service.import_product(
            self.detail(title="شارژر تازه", selling=700, rrp=1200),
            [self.category.id],
        )

        product.refresh_from_db()
        variant = ProductVariants.objects.get(product=product)
        self.assertEqual(result["status"], "updated")
        self.assertEqual(product.name, "شارژر تازه")
        self.assertEqual(product.status, self.active_product_status)
        self.assertEqual(
            set(product.categories.values_list("id", flat=True)), {1003, 3001}
        )
        self.assertEqual(variant.price, 1200)
        self.assertEqual(variant.discount_value, 500)
        self.assertEqual(Product.objects.count(), 1)
        self.assertEqual(ProductVariants.objects.count(), 1)


class DigikalaAdminAPITests(APITestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "runtime"
        self.mapping = Path(self.temporary.name) / "mapping.json"
        write_json_atomic(
            self.mapping,
            {
                "categories": [
                    {
                        "category_id": 1003,
                        "name": "Chargers",
                        "digikala_category_id": 1271,
                        "api_url": "https://api.digikala.com/discovery/api/v2/categories/1271/products",
                    }
                ]
            },
        )
        self.settings_override = override_settings(
            DIGIKALA_RUNTIME_ROOT=self.root,
            DIGIKALA_CATEGORY_MAPPING_PATH=self.mapping,
        )
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)
        user = get_user_model().objects.create_superuser(
            username="admin", password="password"
        )
        self.client.force_authenticate(user)

    def create_listing(self):
        listing_id = str(uuid4())
        document = {
            "schema": "uzshop.digikala.listing/v1",
            "listing_id": listing_id,
            "generated_at": "2026-08-06T00:00:00+00:00",
            "source": {"name": "digikala", "currency": "IRR"},
            "options": {"products_per_category": 20},
            "categories": [{"category_id": 1003, "collected": 1}],
            "products": [
                {
                    "product_id": 12345,
                    "category_ids": [1003],
                    "title_fa": "شارژر",
                    "title_en": "Charger",
                    "status": "marketable",
                    "brand": {"title_fa": "برند"},
                    "image_url": None,
                    "default_variant": {"price": {"selling_price": 1000}},
                }
            ],
            "summary": {
                "category_count": 1,
                "unique_product_count": 1,
                "category_product_count": 1,
            },
        }
        document["sha256"] = sha256_json(document)
        path = self.root / "listings" / f"{listing_id}.json"
        write_json_atomic(path, document)
        return document

    def test_options_and_listing_job_creation(self):
        options = self.client.get("/api/catalog/digikala/listing-options")
        self.assertEqual(options.status_code, 200)
        self.assertEqual(options.data["data"]["currency"], "IRR")

        with patch(
            "domains.catalog.api.digikala_views.collect_digikala_listing.apply_async"
        ) as queued:
            response = self.client.post(
                "/api/catalog/digikala/listings",
                {
                    "category_ids": [1003],
                    "products_per_category": 20,
                    "timeout_seconds": 30,
                    "retries": 3,
                    "delay_seconds": 1,
                    "include_ads": False,
                },
                format="json",
            )
        self.assertEqual(response.status_code, 202)
        queued.assert_called_once()
        jobs = self.client.get("/api/catalog/digikala/jobs")
        self.assertEqual(jobs.data["data"]["count"], 1)

    def test_generated_listing_products_and_import_job_creation(self):
        listing = self.create_listing()
        products = self.client.get(
            f"/api/catalog/digikala/listings/{listing['listing_id']}/products"
        )
        self.assertEqual(products.status_code, 200)
        self.assertEqual(products.data["data"]["results"][0]["product_id"], 12345)

        with patch(
            "domains.catalog.api.digikala_views.import_digikala_products.apply_async"
        ) as queued:
            response = self.client.post(
                "/api/catalog/digikala/import-jobs",
                {
                    "listing_id": listing["listing_id"],
                    "listing_sha256": listing["sha256"],
                    "selection": {"mode": "all"},
                    "options": {
                        "update_existing": True,
                        "download_media": False,
                        "dry_run": False,
                    },
                },
                format="json",
            )
        self.assertEqual(response.status_code, 202)
        queued.assert_called_once()
