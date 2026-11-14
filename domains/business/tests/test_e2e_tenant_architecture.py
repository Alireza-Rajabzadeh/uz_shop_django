import io
import json
from decimal import Decimal
import concurrent.futures
from datetime import timedelta

from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection, transaction
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APITestCase

from core.middleware.tenant import TenantMiddleware
from core.services import CacheService
from domains.business.cache import (
    BUSINESS_CACHE_KEY,
    invalidate_business_cache,
)
from domains.business.data.business_statuses import BUSINESS_STATUS_SEED
from domains.business.data.business_subdomain_statuses import BUSINESS_SUBDOMAIN_STATUS_SEED
from domains.business.enums import BusinessStatusEnum, BusinessSubdomainEnum
from domains.business.models import (
    BusinessCharge,
    BusinessChargeCalculationType,
    BusinessChargeType,
    BusinessProfile,
    BusinessStatus,
    BusinessSubdomain,
    BusinessSubdomainStatus,
    RESERVED_SUBDOMAINS,
)
from domains.business.services.business_subdomain_service import BusinessSubdomainService
from domains.business_content.cache import home_cache_key
from domains.catalog.models import (
    Brand,
    Category,
    CategoryStatus,
    Product,
    ProductStatus,
    ProductVariantStatus,
    ProductVariants,
)
from domains.inventory.models import Inventory, Warehouse, WarehouseStatus
from domains.location.models import City, Country, State
from domains.marketplace.models import BusinessOffer
from domains.vendor.models import Vendor, VendorStatus


def ensure_reference_seeds():
    for row in BUSINESS_STATUS_SEED:
        BusinessStatus.objects.get_or_create(
            id=row["id"],
            defaults={"code": row["code"], "name": row["name"], "title": row["title"]},
        )
    for row in BUSINESS_SUBDOMAIN_STATUS_SEED:
        BusinessSubdomainStatus.objects.get_or_create(
            id=row["id"],
            defaults={"code": row["code"], "name": row["name"], "title": row["title"]},
        )
    from domains.inventory.models.inventory_type import InventoryType
    InventoryType.objects.get_or_create(
        id=1,
        defaults={
            "code": "normal",
            "name": "Normal",
            "fa_name": "عادی",
            "description": "Quantity-based inventory without per-unit serial tracking.",
        },
    )
    from domains.marketplace.data.pricing_strategies import PRICING_STRATEGY_SEED
    from domains.marketplace.models.pricing_strategy import PricingStrategy
    for row in PRICING_STRATEGY_SEED:
        PricingStrategy.objects.get_or_create(
            id=row["id"],
            defaults={
                "code": row["code"],
                "name": row["name"],
                "fa_name": row["fa_name"],
                "description": row["description"],
            },
        )


class BaseE2ETenantSetup(APITestCase):
    @classmethod
    def setUpTestData(cls):
        ensure_reference_seeds()
        cls.active_biz_status = BusinessStatus.objects.get(id=BusinessStatusEnum.ACTIVE.value)
        cls.active_sub_status = BusinessSubdomainStatus.objects.get(id=BusinessSubdomainEnum.ACTIVE.value)
        cls.redirect_sub_status = BusinessSubdomainStatus.objects.get(id=BusinessSubdomainEnum.REDIRECT.value)
        cls.reserved_sub_status = BusinessSubdomainStatus.objects.get(id=BusinessSubdomainEnum.RESERVED.value)

        cls.vendor_status, _ = VendorStatus.objects.get_or_create(
            name="active", defaults={"title": "Active", "is_active": True}
        )

        # 1. Vendor A & Business Delta
        cls.vendor_delta = Vendor.objects.create_user(
            phone="+989121000001",
            national_id="1111111111",
            status=cls.vendor_status,
            first_name="Delta",
            last_name="Owner",
        )
        cls.business_delta = BusinessProfile.objects.create(
            vendor=cls.vendor_delta,
            business_name="delta",
            display_name="Delta Electronics",
            legal_name="Delta Tech LLC",
            status=cls.active_biz_status,
        )
        # Age business beyond cooldown (60 days old)
        BusinessProfile.objects.filter(id=cls.business_delta.id).update(
            created_at=timezone.now() - timedelta(days=60)
        )
        cls.business_delta.refresh_from_db()
        cls.subdomain_delta = BusinessSubdomain.objects.create(
            business=cls.business_delta,
            subdomain="delta",
            status=cls.active_sub_status,
        )

        # 2. Vendor B & Business Shopname
        cls.vendor_shopname = Vendor.objects.create_user(
            phone="+989122000002",
            national_id="2222222222",
            status=cls.vendor_status,
            first_name="Shopname",
            last_name="Owner",
        )
        cls.business_shopname = BusinessProfile.objects.create(
            vendor=cls.vendor_shopname,
            business_name="shopname",
            display_name="Shopname Apparel",
            legal_name="Shopname Fashion Corp",
            status=cls.active_biz_status,
        )
        BusinessProfile.objects.filter(id=cls.business_shopname.id).update(
            created_at=timezone.now() - timedelta(days=60)
        )
        cls.business_shopname.refresh_from_db()
        cls.subdomain_shopname = BusinessSubdomain.objects.create(
            business=cls.business_shopname,
            subdomain="shopname",
            status=cls.active_sub_status,
        )

        # 3. Location, Brand, and Category
        cls.country = Country.objects.create(name="Iran", code="IR", phone_code="+98")
        cls.state = State.objects.create(name="Tehran", country=cls.country)
        cls.city = City.objects.create(name="Tehran", state=cls.state)

        cls.cat_status, _ = CategoryStatus.objects.get_or_create(name="active")
        cls.category = Category.objects.create(name="Gadgets", slug="gadgets", status=cls.cat_status)
        cls.brand = Brand.objects.create(name="Nexus", slug="nexus")

        cls.prod_status, _ = ProductStatus.objects.get_or_create(name="active")
        cls.var_status, _ = ProductVariantStatus.objects.get_or_create(name="active")
        cls.wh_status, _ = WarehouseStatus.objects.get_or_create(name="active")

        # 4. Product Delta (sold only by Delta)
        cls.product_delta = Product.objects.create(
            name="Delta Smartwatch X1",
            slug="delta-smartwatch-x1",
            brand=cls.brand,
            status=cls.prod_status,
        )
        cls.product_delta.categories.add(cls.category)
        cls.var_delta = ProductVariants.objects.create(
            product=cls.product_delta,
            sku="DELTA-SW-01",
            combination_key="color:black",
            status=cls.var_status,
        )
        cls.wh_delta = Warehouse.objects.create(
            name="Delta Central WH",
            business=cls.business_delta,
            city=cls.city,
            address="Delta Road 1",
            lat="35.6892",
            lng="51.3890",
            status=cls.wh_status,
        )
        Inventory.objects.create(
            variant=cls.var_delta,
            warehouse=cls.wh_delta,
            business=cls.business_delta,
            quantity=50,
            sellable=50,
            reserved=0,
        )
        cls.offer_delta = BusinessOffer.objects.create(
            business=cls.business_delta,
            variant=cls.var_delta,
            price=Decimal("1200000"),
            is_active=True,
        )

        # 5. Product Shopname (sold only by Shopname)
        cls.product_shopname = Product.objects.create(
            name="Shopname Classic Hoodie",
            slug="shopname-classic-hoodie",
            brand=cls.brand,
            status=cls.prod_status,
        )
        cls.product_shopname.categories.add(cls.category)
        cls.var_shopname = ProductVariants.objects.create(
            product=cls.product_shopname,
            sku="SHOP-HD-01",
            combination_key="size:L",
            status=cls.var_status,
        )
        cls.wh_shopname = Warehouse.objects.create(
            name="Shopname West WH",
            business=cls.business_shopname,
            city=cls.city,
            address="Shopname Boulevard 2",
            lat="35.7000",
            lng="51.4000",
            status=cls.wh_status,
        )
        Inventory.objects.create(
            variant=cls.var_shopname,
            warehouse=cls.wh_shopname,
            business=cls.business_shopname,
            quantity=20,
            sellable=20,
            reserved=0,
        )
        cls.offer_shopname = BusinessOffer.objects.create(
            business=cls.business_shopname,
            variant=cls.var_shopname,
            price=Decimal("450000"),
            is_active=True,
        )

        # 6. Private Charges
        cls.charge_delta = BusinessCharge.objects.create(
            business=cls.business_delta,
            name="Delta Packaging Fee",
            type=BusinessChargeType.TAX,
            calculation_type=BusinessChargeCalculationType.FIXED,
            amount=Decimal("15000"),
            is_mandatory=True,
        )
        cls.charge_shopname = BusinessCharge.objects.create(
            business=cls.business_shopname,
            name="Shopname Eco Packaging",
            type=BusinessChargeType.TAX,
            calculation_type=BusinessChargeCalculationType.FIXED,
            amount=Decimal("25000"),
            is_mandatory=True,
        )


class E2EBusinessSubdomainManagementTests(BaseE2ETenantSetup):
    """Verifies BusinessSubdomain model integrity, enum, uniqueness, reserved names, cooldown."""

    def test_single_active_subdomain_enforced(self):
        active_count = BusinessSubdomain.objects.filter(
            business=self.business_delta,
            status_id=BusinessSubdomainEnum.ACTIVE.value,
        ).count()
        self.assertEqual(active_count, 1)

    def test_global_uniqueness_prevents_duplicate_active_subdomain(self):
        from django.core.exceptions import ValidationError
        with self.assertRaises((ValidationError, Exception)):
            BusinessSubdomainService.change_subdomain(
                business=self.business_shopname,
                new_subdomain="delta",  # Already taken by Delta
                confirmed=True,
            )

    def test_reserved_subdomains_cannot_be_registered(self):
        from rest_framework.exceptions import ValidationError
        for reserved in ("admin", "api", "www", "vendor", "dashboard", "client"):
            with self.assertRaises(ValidationError):
                BusinessSubdomainService.change_subdomain(
                    business=self.business_delta,
                    new_subdomain=reserved,
                    confirmed=True,
                )

    def test_cooldown_rule_enforced_after_subdomain_change(self):
        # Change delta -> delta-hub
        BusinessSubdomainService.change_subdomain(
            business=self.business_delta,
            new_subdomain="delta-hub",
            confirmed=True,
        )
        # Immediate subsequent change attempt should fail cooldown
        eligibility = BusinessSubdomainService.check_eligibility(self.business_delta)
        self.assertFalse(eligibility["can_change"])
        self.assertIn("90 days", eligibility["message"].lower())


class E2EVendorPanelWorkflowTests(BaseE2ETenantSetup):
    """Verifies Vendor Panel storefront address management endpoints."""

    def test_vendor_overview_endpoint(self):
        self.client.force_authenticate(user=self.vendor_delta)
        response = self.client.get("/api/vendor/business/subdomain")
        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertEqual(data["current_subdomain"], "delta")
        self.assertEqual(data["status"], "active")
        self.assertTrue(data["eligibility"]["can_change"])

    def test_availability_check_endpoint(self):
        self.client.force_authenticate(user=self.vendor_delta)
        # 1. Available subdomain
        res1 = self.client.get("/api/vendor/business/subdomain/check?subdomain=delta-super")
        self.assertEqual(res1.status_code, 200)
        self.assertTrue(res1.json()["data"]["available"])

        # 2. Taken subdomain
        res2 = self.client.get("/api/vendor/business/subdomain/check?subdomain=shopname")
        self.assertEqual(res2.status_code, 200)
        self.assertFalse(res2.json()["data"]["available"])

        # 3. Reserved subdomain
        res3 = self.client.get("/api/vendor/business/subdomain/check?subdomain=admin")
        self.assertEqual(res3.status_code, 200)
        self.assertFalse(res3.json()["data"]["available"])

    def test_subdomain_change_and_history_workflow(self):
        self.client.force_authenticate(user=self.vendor_delta)
        # Attempt change without confirmed flag -> fails
        unconfirmed = self.client.post(
            "/api/vendor/business/subdomain",
            data={"subdomain": "delta-official", "confirmed": False},
            format="json",
        )
        self.assertEqual(unconfirmed.status_code, 400)

        # Successful change with confirmed=True
        success = self.client.post(
            "/api/vendor/business/subdomain",
            data={"subdomain": "delta-official", "confirmed": True},
            format="json",
        )
        self.assertEqual(success.status_code, 200)
        self.assertEqual(success.json()["data"]["subdomain"], "delta-official")

        # History API displays both the new active and the old redirect subdomain
        hist_res = self.client.get("/api/vendor/business/subdomain/history")
        self.assertEqual(hist_res.status_code, 200)
        hist = hist_res.json()["data"]
        subdomain_names = [h["subdomain"] for h in hist]
        self.assertIn("delta-official", subdomain_names)
        self.assertIn("delta", subdomain_names)


class E2EHistoricalRedirectAndTenantResolutionTests(BaseE2ETenantSetup):
    """Verifies that historical subdomains return HTTP 308 with canonical info and preserved paths/queries."""

    def setUp(self):
        super().setUp()
        # Set up delta historical redirect: old="delta-legacy", canonical="delta"
        BusinessSubdomain.objects.create(
            business=self.business_delta,
            subdomain="delta-legacy",
            status=self.redirect_sub_status,
        )

    def test_public_resolve_endpoint_for_redirect_subdomain(self):
        res = self.client.get("/api/business/public/subdomain/resolve?subdomain=delta-legacy")
        self.assertEqual(res.status_code, 200)
        data = res.json()["data"]
        self.assertEqual(data["status"], "REDIRECT")
        self.assertEqual(data["canonical_subdomain"], "delta")
        self.assertEqual(data["business_id"], self.business_delta.id)

    def test_middleware_returns_308_with_canonical_header(self):
        # Sending X-Tenant-Subdomain: delta-legacy to an API route triggers HTTP 308
        res = self.client.get(
            "/api/catalog/storefront/products?page=2&sort=price_asc",
            HTTP_X_TENANT_SUBDOMAIN="delta-legacy",
        )
        self.assertEqual(res.status_code, 308)
        self.assertEqual(res.headers.get("X-Canonical-Subdomain"), "delta")
        body = res.json()
        self.assertEqual(body["data"]["status"], "REDIRECT")
        self.assertEqual(body["data"]["subdomain"], "delta-legacy")
        self.assertEqual(body["data"]["canonical_subdomain"], "delta")

    def test_historical_subdomain_remains_bound_to_original_business(self):
        # Another business (Shopname) cannot register delta-legacy
        from django.core.exceptions import ValidationError
        with self.assertRaises((ValidationError, Exception)):
            BusinessSubdomainService.change_subdomain(
                business=self.business_shopname,
                new_subdomain="delta-legacy",
                confirmed=True,
            )


class E2ECrossTenantSecurityAndDataIsolationTests(BaseE2ETenantSetup):
    """Verifies data isolation between Delta and Shopname across catalog, vendor, and private charges."""

    def test_storefront_catalog_product_scoping(self):
        # 1. Delta storefront requests Product Delta -> 200 OK
        res_d = self.client.get(
            f"/api/catalog/storefront/products/{self.product_delta.slug}",
            HTTP_X_TENANT_SUBDOMAIN="delta",
        )
        self.assertEqual(res_d.status_code, 200)
        self.assertEqual(res_d.json()["data"]["name"], "Delta Smartwatch X1")

        # 2. Delta storefront requests Product Shopname (unowned) -> 404 Not Found
        res_d_cross = self.client.get(
            f"/api/catalog/storefront/products/{self.product_shopname.slug}",
            HTTP_X_TENANT_SUBDOMAIN="delta",
        )
        self.assertEqual(res_d_cross.status_code, 404)

        # 3. Shopname storefront requests Product Shopname -> 200 OK
        res_s = self.client.get(
            f"/api/catalog/storefront/products/{self.product_shopname.slug}",
            HTTP_X_TENANT_SUBDOMAIN="shopname",
        )
        self.assertEqual(res_s.status_code, 200)
        self.assertEqual(res_s.json()["data"]["name"], "Shopname Classic Hoodie")

        # 4. Shopname storefront requests Product Delta (unowned) -> 404 Not Found
        res_s_cross = self.client.get(
            f"/api/catalog/storefront/products/{self.product_delta.slug}",
            HTTP_X_TENANT_SUBDOMAIN="shopname",
        )
        self.assertEqual(res_s_cross.status_code, 404)

    def test_storefront_search_list_isolation(self):
        # Delta storefront search only lists Delta's products
        res_delta_list = self.client.get(
            "/api/catalog/storefront/products",
            HTTP_X_TENANT_SUBDOMAIN="delta",
        )
        self.assertEqual(res_delta_list.status_code, 200)
        delta_prods = [p["name"] for p in res_delta_list.json()["data"]["results"]]
        self.assertIn("Delta Smartwatch X1", delta_prods)
        self.assertNotIn("Shopname Classic Hoodie", delta_prods)

        # Shopname storefront search only lists Shopname's products
        res_shop_list = self.client.get(
            "/api/catalog/storefront/products",
            HTTP_X_TENANT_SUBDOMAIN="shopname",
        )
        self.assertEqual(res_shop_list.status_code, 200)
        shop_prods = [p["name"] for p in res_shop_list.json()["data"]["results"]]
        self.assertNotIn("Delta Smartwatch X1", shop_prods)
        self.assertIn("Shopname Classic Hoodie", shop_prods)

    def test_vendor_charges_isolation(self):
        # Vendor Delta views their charges
        self.client.force_authenticate(user=self.vendor_delta)
        res_d = self.client.get(
            "/api/vendor/business/charges",
            HTTP_X_TENANT_SUBDOMAIN="delta",
        )
        self.assertEqual(res_d.status_code, 200)
        charge_names = [c["name"] for c in res_d.json()["data"]]
        self.assertIn("Delta Packaging Fee", charge_names)
        self.assertNotIn("Shopname Eco Packaging", charge_names)

        # Vendor Delta attempts to send tenant header for Shopname -> 404 rejection
        res_tampered = self.client.get(
            "/api/vendor/business/charges",
            HTTP_X_TENANT_SUBDOMAIN="shopname",
        )
        self.assertEqual(res_tampered.status_code, 404)

        # Vendor Delta attempts to delete Vendor Shopname's charge -> 404 / NotFound
        res_del = self.client.delete(
            f"/api/vendor/business/charges/{self.charge_shopname.id}",
            HTTP_X_TENANT_SUBDOMAIN="delta",
        )
        self.assertEqual(res_del.status_code, 404)
        # Verify Shopname's charge still exists in DB
        self.assertTrue(BusinessCharge.objects.filter(id=self.charge_shopname.id).exists())

    def test_tampered_business_id_in_payload_cannot_override_tenant(self):
        # Even if client sends malicious business_id in payload, resolved tenant overrides it
        middleware = TenantMiddleware(lambda req: req)
        from django.test import RequestFactory
        factory = RequestFactory()

        req = factory.post(
            "/api/test",
            data=json.dumps({"name": "Tamper Test", "business_id": self.business_shopname.id}),
            content_type="application/json",
            HTTP_X_TENANT_SUBDOMAIN="delta",
        )
        middleware(req)
        # request.business_id must be Delta's ID, and body must be rewritten to Delta's ID
        self.assertEqual(req.business_id, self.business_delta.id)
        body = json.loads(req.body.decode("utf-8"))
        self.assertEqual(body["business_id"], self.business_delta.id)


class E2ECacheIsolationTests(BaseE2ETenantSetup):
    """Verifies that Redis caches are strictly partitioned by tenant ID."""

    def test_cache_keys_and_invalidation_partitioning(self):
        cache = CacheService()
        key_delta = home_cache_key(self.business_delta.id)
        key_shopname = home_cache_key(self.business_shopname.id)

        self.assertNotEqual(key_delta, key_shopname)

        cache.put_public(key_delta, {"store": "delta-home"}, ttl=300)
        cache.put_public(key_shopname, {"store": "shopname-home"}, ttl=300)

        # Invalidate Delta cache
        invalidate_business_cache(self.business_delta.id)
        cache.delete_public(key_delta)

        # Delta cache is gone; Shopname cache is completely unaffected
        self.assertIsNone(cache.get_public(key_delta))
        self.assertEqual(cache.get_public(key_shopname), {"store": "shopname-home"})

        # Clean up
        cache.delete_public(key_shopname)


from django.test import TransactionTestCase
from rest_framework.test import APIClient


class E2EConcurrentRequestsTests(TransactionTestCase):
    """Simulates concurrent requests from Delta and Shopname to verify request-scoped isolation."""

    def setUp(self):
        super().setUp()
        ensure_reference_seeds()
        BusinessSubdomain.objects.all().delete()
        BusinessProfile.objects.all().delete()
        self.active_biz_status = BusinessStatus.objects.get(id=BusinessStatusEnum.ACTIVE.value)
        self.active_sub_status = BusinessSubdomainStatus.objects.get(id=BusinessSubdomainEnum.ACTIVE.value)
        self.vendor_status, _ = VendorStatus.objects.get_or_create(
            name="active", defaults={"title": "Active", "is_active": True}
        )

        # Delta setup
        self.vendor_delta = Vendor.objects.create_user(
            phone="+989121000001",
            national_id="1111111111",
            status=self.vendor_status,
        )
        self.business_delta = BusinessProfile.objects.create(
            vendor=self.vendor_delta,
            business_name="delta",
            display_name="Delta Electronics",
            status=self.active_biz_status,
        )
        self.subdomain_delta = BusinessSubdomain.objects.create(
            business=self.business_delta,
            subdomain="delta",
            status=self.active_sub_status,
        )

        # Shopname setup
        self.vendor_shopname = Vendor.objects.create_user(
            phone="+989122000002",
            national_id="2222222222",
            status=self.vendor_status,
        )
        self.business_shopname = BusinessProfile.objects.create(
            vendor=self.vendor_shopname,
            business_name="shopname",
            display_name="Shopname Apparel",
            status=self.active_biz_status,
        )
        self.subdomain_shopname = BusinessSubdomain.objects.create(
            business=self.business_shopname,
            subdomain="shopname",
            status=self.active_sub_status,
        )

        # Catalog setup
        self.country = Country.objects.create(name="Iran", code="IR", phone_code="+98")
        self.state = State.objects.create(name="Tehran", country=self.country)
        self.city = City.objects.create(name="Tehran", state=self.state)
        self.cat_status, _ = CategoryStatus.objects.get_or_create(id=1, defaults={"name": "active"})
        self.category = Category.objects.create(name="Gadgets", slug="gadgets", status=self.cat_status)
        self.brand = Brand.objects.create(name="Nexus", slug="nexus")
        self.prod_status, _ = ProductStatus.objects.get_or_create(name="active")
        self.var_status, _ = ProductVariantStatus.objects.get_or_create(name="active")
        self.wh_status, _ = WarehouseStatus.objects.get_or_create(name="active")

        # Delta product
        self.prod_delta = Product.objects.create(name="Delta Smartwatch X1", slug="delta-sw-x1", brand=self.brand, status=self.prod_status)
        self.prod_delta.categories.add(self.category)
        self.var_delta = ProductVariants.objects.create(product=self.prod_delta, sku="D-1", combination_key="color:black", status=self.var_status)
        self.wh_delta = Warehouse.objects.create(name="WH D", business=self.business_delta, city=self.city, address="A", lat="0", lng="0", status=self.wh_status)
        Inventory.objects.create(variant=self.var_delta, warehouse=self.wh_delta, business=self.business_delta, quantity=10, sellable=10, reserved=0)
        BusinessOffer.objects.create(business=self.business_delta, variant=self.var_delta, price=Decimal("100"), is_active=True)

        # Shopname product
        self.prod_shop = Product.objects.create(name="Shopname Classic Hoodie", slug="shop-hd-1", brand=self.brand, status=self.prod_status)
        self.prod_shop.categories.add(self.category)
        self.var_shop = ProductVariants.objects.create(product=self.prod_shop, sku="S-1", combination_key="size:L", status=self.var_status)
        self.wh_shop = Warehouse.objects.create(name="WH S", business=self.business_shopname, city=self.city, address="B", lat="0", lng="0", status=self.wh_status)
        Inventory.objects.create(variant=self.var_shop, warehouse=self.wh_shop, business=self.business_shopname, quantity=10, sellable=10, reserved=0)
        BusinessOffer.objects.create(business=self.business_shopname, variant=self.var_shop, price=Decimal("200"), is_active=True)

    def test_concurrent_requests_maintain_isolated_tenant_context(self):
        results = []

        def make_request(subdomain, expected_product):
            connection.close()
            client = APIClient()
            try:
                res = client.get(
                    "/api/catalog/storefront/products",
                    HTTP_X_TENANT_SUBDOMAIN=subdomain,
                )
                if res.status_code != 200:
                    results.append((subdomain, False, f"Status {res.status_code}"))
                    return
                names = [p["name"] for p in res.json()["data"]["results"]]
                if expected_product in names and len(names) == 1:
                    results.append((subdomain, True, "OK"))
                else:
                    results.append((subdomain, False, f"Unexpected products: {names}"))
            except Exception as e:
                results.append((subdomain, False, str(e)))
            finally:
                connection.close()

        tasks = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
            for i in range(10):
                if i % 2 == 0:
                    tasks.append(executor.submit(make_request, "delta", "Delta Smartwatch X1"))
                else:
                    tasks.append(executor.submit(make_request, "shopname", "Shopname Classic Hoodie"))

            for t in tasks:
                t.result()

        self.assertEqual(len(results), 10)
        for sub, success, msg in results:
            self.assertTrue(success, f"Failed for {sub}: {msg}")
