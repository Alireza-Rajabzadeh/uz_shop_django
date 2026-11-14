import io
import json
from decimal import Decimal
from django.core.files.uploadedfile import SimpleUploadedFile
from django.http import HttpResponse
from django.test import RequestFactory, TestCase
from rest_framework.request import Request
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.test import APITestCase

from core.middleware.tenant import TenantMiddleware
from core.services import CacheService
from domains.business.cache import BUSINESS_CACHE_KEY, invalidate_business_cache
from domains.business.enums import BusinessStatusEnum, BusinessSubdomainEnum
from domains.business.models import (
    BusinessProfile,
    BusinessStatus,
    BusinessSubdomain,
    BusinessSubdomainStatus,
)
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


def dummy_view(request):
    """A minimal test view that exposes the DRF request and underlying Django request."""
    drf_request = Request(
        request,
        parsers=[JSONParser(), FormParser(), MultiPartParser()],
    )
    if hasattr(drf_request.data, "items"):
        safe_data = {
            k: v for k, v in drf_request.data.items()
            if not hasattr(v, "read") and not (isinstance(v, list) and v and hasattr(v[0], "read"))
        }
    else:
        safe_data = drf_request.data

    return HttpResponse(
        json.dumps({
            "business_id": getattr(request, "business_id", None),
            "drf_data": safe_data,
            "drf_query": dict(drf_request.query_params),
            "files": list(drf_request.FILES.keys()),
        }),
        content_type="application/json",
    )


class TenantMiddlewareUnitTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.active_status, _ = BusinessStatus.objects.get_or_create(
            id=BusinessStatusEnum.ACTIVE.value,
            defaults={"name": "Active", "title": "Active"},
        )
        cls.banned_status, _ = BusinessStatus.objects.get_or_create(
            id=BusinessStatusEnum.BANNED.value,
            defaults={"name": "Banned", "title": "Banned"},
        )
        cls.pending_status, _ = BusinessStatus.objects.get_or_create(
            id=BusinessStatusEnum.CONFIRMATION_AWAIT.value,
            defaults={"name": "Confirmation Await", "title": "Confirmation Await"},
        )

        cls.active_sub_status, _ = BusinessSubdomainStatus.objects.get_or_create(
            id=BusinessSubdomainEnum.ACTIVE.value,
            defaults={"code": "active", "name": "Active", "title": "Active"},
        )
        cls.redirect_sub_status, _ = BusinessSubdomainStatus.objects.get_or_create(
            id=BusinessSubdomainEnum.REDIRECT.value,
            defaults={"code": "redirect", "name": "Redirect", "title": "Redirect"},
        )
        cls.reserved_sub_status, _ = BusinessSubdomainStatus.objects.get_or_create(
            id=BusinessSubdomainEnum.RESERVED.value,
            defaults={"code": "reserved", "name": "Reserved", "title": "Reserved"},
        )

        cls.active_business = BusinessProfile.objects.create(
            business_name="delta",
            display_name="Delta Storefront",
            status=cls.active_status,
        )
        cls.banned_business = BusinessProfile.objects.create(
            business_name="banned-store",
            display_name="Banned Storefront",
            status=cls.banned_status,
        )
        cls.pending_business = BusinessProfile.objects.create(
            business_name="pending-store",
            display_name="Pending Storefront",
            status=cls.pending_status,
        )

        cls.subdomain_active = BusinessSubdomain.objects.create(
            business=cls.active_business,
            subdomain="delta",
            status=cls.active_sub_status,
        )
        cls.subdomain_redirect = BusinessSubdomain.objects.create(
            business=cls.active_business,
            subdomain="old-delta",
            status=cls.redirect_sub_status,
        )
        cls.subdomain_reserved = BusinessSubdomain.objects.create(
            subdomain="reserved-shop",
            status=cls.reserved_sub_status,
        )
        cls.subdomain_banned = BusinessSubdomain.objects.create(
            business=cls.banned_business,
            subdomain="banned-sub",
            status=cls.active_sub_status,
        )
        cls.subdomain_pending = BusinessSubdomain.objects.create(
            business=cls.pending_business,
            subdomain="pending-sub",
            status=cls.active_sub_status,
        )

        cls.factory = RequestFactory()
        cls.middleware = TenantMiddleware(dummy_view)

    # 1. Tenant Resolution: Valid active subdomain
    def test_valid_tenant_resolution_sets_request_business_and_id(self):
        request = self.factory.get("/api/test", HTTP_X_TENANT_SUBDOMAIN="delta")
        response = self.middleware(request)

        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(request.business)
        self.assertEqual(request.business.id, self.active_business.id)
        self.assertEqual(request.business_id, self.active_business.id)

    # 2. Tenant Resolution: Case normalization
    def test_valid_tenant_case_normalization(self):
        request = self.factory.get("/api/test", HTTP_X_TENANT_SUBDOMAIN="DELTA")
        response = self.middleware(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(request.business_id, self.active_business.id)

    # 3. Tenant Resolution: Unknown subdomain returns 404
    def test_unknown_subdomain_returns_404(self):
        request = self.factory.get("/api/test", HTTP_X_TENANT_SUBDOMAIN="non-existent")
        response = self.middleware(request)

        self.assertEqual(response.status_code, 404)
        body = json.loads(response.content.decode("utf-8"))
        self.assertFalse(body["success"])
        self.assertEqual(body["message"], "Business not found.")
        self.assertIsNone(body["data"])

    # 4. Tenant Resolution: Invalid subdomain format returns 400 Bad Request
    def test_invalid_subdomain_format_returns_400(self):
        invalid_formats = ["ab", "a" * 31, "in_valid", "with space", "-leading", "trailing-", "inv@lid"]
        for invalid in invalid_formats:
            request = self.factory.get("/api/test", HTTP_X_TENANT_SUBDOMAIN=invalid)
            response = self.middleware(request)

            self.assertEqual(response.status_code, 400, f"Expected 400 for {invalid}")
            body = json.loads(response.content.decode("utf-8"))
            self.assertFalse(body["success"])
            self.assertEqual(body["message"], "Invalid subdomain format.")
            self.assertIn("subdomain", body["errors"])

    # 5. Tenant Resolution: Historical subdomain returns 308 redirect with canonical info
    def test_historical_subdomain_returns_308_with_canonical(self):
        request = self.factory.get("/api/test", HTTP_X_TENANT_SUBDOMAIN="old-delta")
        response = self.middleware(request)

        self.assertEqual(response.status_code, 308)
        body = json.loads(response.content.decode("utf-8"))
        self.assertFalse(body["success"])
        self.assertEqual(body["data"]["status"], "REDIRECT")
        self.assertEqual(body["data"]["subdomain"], "old-delta")
        self.assertEqual(body["data"]["canonical_subdomain"], "delta")
        self.assertEqual(response.headers.get("X-Canonical-Subdomain"), "delta")

    # 6. Tenant Resolution: Reserved subdomain returns 404
    def test_reserved_subdomain_returns_404(self):
        # Database-recorded reserved subdomain
        request = self.factory.get("/api/test", HTTP_X_TENANT_SUBDOMAIN="reserved-shop")
        response = self.middleware(request)

        self.assertEqual(response.status_code, 404)
        body = json.loads(response.content.decode("utf-8"))
        self.assertFalse(body["success"])
        self.assertEqual(body["message"], "This subdomain is reserved.")

        # Hardcoded reserved subdomain (e.g. admin, api, www)
        for reserved in ("admin", "api", "www", "vendor"):
            req = self.factory.get("/api/test", HTTP_X_TENANT_SUBDOMAIN=reserved)
            res = self.middleware(req)
            self.assertEqual(res.status_code, 404)
            b = json.loads(res.content.decode("utf-8"))
            self.assertEqual(b["message"], "This subdomain is reserved.")

    # 7. Inactive business returns 404
    def test_banned_business_returns_404(self):
        request = self.factory.get("/api/test", HTTP_X_TENANT_SUBDOMAIN="banned-sub")
        response = self.middleware(request)

        self.assertEqual(response.status_code, 404)
        body = json.loads(response.content.decode("utf-8"))
        self.assertFalse(body["success"])

    def test_pending_business_returns_404(self):
        request = self.factory.get("/api/test", HTTP_X_TENANT_SUBDOMAIN="pending-sub")
        response = self.middleware(request)

        self.assertEqual(response.status_code, 404)
        body = json.loads(response.content.decode("utf-8"))
        self.assertFalse(body["success"])

    # 8. Missing tenant header preserves behavior
    def test_missing_tenant_header_preserves_behavior(self):
        request = self.factory.get("/api/test")
        response = self.middleware(request)

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(request.business)
        self.assertIsNone(request.business_id)

    def test_empty_tenant_header_preserves_behavior(self):
        request = self.factory.get("/api/test", HTTP_X_TENANT_SUBDOMAIN="   ")
        response = self.middleware(request)

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(request.business)
        self.assertIsNone(request.business_id)

    # 9. Request Integrity: JSON POST / PUT / PATCH normalization
    def test_json_post_injects_business_id(self):
        request = self.factory.post(
            "/api/test",
            data=json.dumps({"name": "product-1"}),
            content_type="application/json",
            HTTP_X_TENANT_SUBDOMAIN="delta",
        )
        response = self.middleware(request)
        data = json.loads(response.content.decode("utf-8"))

        self.assertEqual(data["business_id"], self.active_business.id)
        self.assertEqual(data["drf_data"]["business_id"], self.active_business.id)
        self.assertEqual(data["drf_data"]["name"], "product-1")

    def test_json_post_replaces_conflicting_business_id(self):
        request = self.factory.post(
            "/api/test",
            data=json.dumps({"name": "product-1", "business_id": 9999}),
            content_type="application/json",
            HTTP_X_TENANT_SUBDOMAIN="delta",
        )
        response = self.middleware(request)
        data = json.loads(response.content.decode("utf-8"))

        # 9999 must be replaced by delta's real id
        self.assertEqual(data["drf_data"]["business_id"], self.active_business.id)

    def test_json_put_and_patch_normalization(self):
        for method in ("put", "patch"):
            request = getattr(self.factory, method)(
                "/api/test",
                data=json.dumps({"title": f"update-{method}"}),
                content_type="application/json",
                HTTP_X_TENANT_SUBDOMAIN="delta",
            )
            response = self.middleware(request)
            data = json.loads(response.content.decode("utf-8"))

            self.assertEqual(data["drf_data"]["business_id"], self.active_business.id)
            self.assertEqual(data["drf_data"]["title"], f"update-{method}")

    def test_empty_json_body_post(self):
        request = self.factory.post(
            "/api/test",
            data=json.dumps({}),
            content_type="application/json",
            HTTP_X_TENANT_SUBDOMAIN="delta",
        )
        response = self.middleware(request)
        data = json.loads(response.content.decode("utf-8"))

        self.assertEqual(data["drf_data"]["business_id"], self.active_business.id)

    # 10. Request Integrity: Query parameter normalization
    def test_query_params_replaced_and_injected(self):
        request = self.factory.get(
            "/api/test?q=shoes&business_id=888&business=777",
            HTTP_X_TENANT_SUBDOMAIN="delta",
        )
        response = self.middleware(request)
        data = json.loads(response.content.decode("utf-8"))

        self.assertEqual(data["drf_query"]["business_id"], [str(self.active_business.id)])
        self.assertEqual(data["drf_query"]["business"], [str(self.active_business.id)])
        self.assertEqual(data["drf_query"]["q"], ["shoes"])

    def test_query_params_without_existing_business_id(self):
        request = self.factory.get(
            "/api/test?q=shoes",
            HTTP_X_TENANT_SUBDOMAIN="delta",
        )
        response = self.middleware(request)
        data = json.loads(response.content.decode("utf-8"))

        self.assertEqual(data["drf_query"]["business_id"], [str(self.active_business.id)])
        self.assertEqual(data["drf_query"]["business"], [str(self.active_business.id)])
        self.assertEqual(data["drf_query"]["q"], ["shoes"])

    # 11. Request Integrity: Form data normalization
    def test_form_data_post_normalization(self):
        request = self.factory.post(
            "/api/test",
            data={"item": "desk", "business_id": "777"},
            HTTP_X_TENANT_SUBDOMAIN="delta",
        )
        response = self.middleware(request)
        data = json.loads(response.content.decode("utf-8"))

        self.assertEqual(data["drf_data"]["business_id"], str(self.active_business.id))
        self.assertEqual(data["drf_data"]["item"], "desk")

    # 12. Request Integrity: Multipart requests and file preservation
    def test_multipart_post_preserves_files_and_injects_business_id(self):
        uploaded_file = SimpleUploadedFile("avatar.png", b"image-data", content_type="image/png")
        request = self.factory.post(
            "/api/test",
            data={"title": "logo", "file": uploaded_file, "business_id": "999"},
            format="multipart",
            HTTP_X_TENANT_SUBDOMAIN="delta",
        )
        response = self.middleware(request)
        data = json.loads(response.content.decode("utf-8"))

        self.assertEqual(data["drf_data"]["business_id"], str(self.active_business.id))
        self.assertEqual(data["drf_data"]["title"], "logo")
        self.assertIn("file", data["files"])


class TenantDataAndCacheIsolationIntegrationTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.active_status, _ = BusinessStatus.objects.get_or_create(
            id=BusinessStatusEnum.ACTIVE.value,
            defaults={"name": "Active", "title": "Active"},
        )
        cls.sub_active_status, _ = BusinessSubdomainStatus.objects.get_or_create(
            id=BusinessSubdomainEnum.ACTIVE.value,
            defaults={"code": "active", "name": "Active", "title": "Active"},
        )

        cls.vendor_status, _ = VendorStatus.objects.get_or_create(
            id=1, defaults={"name": "active", "title": "Active"}
        )

        cls.vendor_a = Vendor.objects.create_user(
            phone="09121111111", password="passwordA123", status=cls.vendor_status, national_id="0011111111"
        )
        cls.vendor_b = Vendor.objects.create_user(
            phone="09122222222", password="passwordB123", status=cls.vendor_status, national_id="0022222222"
        )

        cls.business_a = BusinessProfile.objects.create(
            business_name="alpha-store",
            display_name="Alpha Store",
            vendor=cls.vendor_a,
            status=cls.active_status,
        )
        cls.subdomain_a = BusinessSubdomain.objects.create(
            business=cls.business_a,
            subdomain="alpha-store",
            status=cls.sub_active_status,
        )

        cls.business_b = BusinessProfile.objects.create(
            business_name="beta-store",
            display_name="Beta Store",
            vendor=cls.vendor_b,
            status=cls.active_status,
        )
        cls.subdomain_b = BusinessSubdomain.objects.create(
            business=cls.business_b,
            subdomain="beta-store",
            status=cls.sub_active_status,
        )

        # Catalog setup
        cls.cat_status, _ = CategoryStatus.objects.get_or_create(id=1, defaults={"name": "active"})
        cls.category = Category.objects.create(name="Shoes", slug="shoes", status=cls.cat_status)
        cls.brand = Brand.objects.create(name="ShoeCo", slug="shoeco")
        cls.prod_status, _ = ProductStatus.objects.get_or_create(name="active")
        cls.var_status, _ = ProductVariantStatus.objects.get_or_create(name="active")

        cls.product_a = Product.objects.create(
            name="Alpha Running Shoes",
            slug="alpha-running-shoes",
            brand=cls.brand,
            status=cls.prod_status,
        )
        cls.product_a.categories.add(cls.category)

        cls.variant_a = ProductVariants.objects.create(
            product=cls.product_a,
            sku="SKU-A-1",
            combination_key="color:red",
            status=cls.var_status,
        )

        cls.country = Country.objects.create(name="Country", code="CO", phone_code="+1")
        cls.state = State.objects.create(name="State", country=cls.country)
        cls.city = City.objects.create(name="City", state=cls.state)

        cls.wh_status, _ = WarehouseStatus.objects.get_or_create(name="active")
        cls.wh_a = Warehouse.objects.create(
            name="WH A",
            business=cls.business_a,
            city=cls.city,
            address="Test address A",
            lat="0",
            lng="0",
            status=cls.wh_status,
        )
        Inventory.objects.create(
            variant=cls.variant_a,
            warehouse=cls.wh_a,
            business=cls.business_a,
            quantity=10,
            sellable=10,
            reserved=0,
        )
        cls.offer_a = BusinessOffer.objects.create(
            business=cls.business_a,
            variant=cls.variant_a,
            price=Decimal("150000"),
            is_active=True,
        )

        cls.product_b = Product.objects.create(
            name="Beta Hiking Boots",
            slug="beta-hiking-boots",
            brand=cls.brand,
            status=cls.prod_status,
        )
        cls.product_b.categories.add(cls.category)

        cls.variant_b = ProductVariants.objects.create(
            product=cls.product_b,
            sku="SKU-B-1",
            combination_key="color:blue",
            status=cls.var_status,
        )
        cls.wh_b = Warehouse.objects.create(
            name="WH B",
            business=cls.business_b,
            city=cls.city,
            address="Test address B",
            lat="0",
            lng="0",
            status=cls.wh_status,
        )
        Inventory.objects.create(
            variant=cls.variant_b,
            warehouse=cls.wh_b,
            business=cls.business_b,
            quantity=5,
            sellable=5,
            reserved=0,
        )
        cls.offer_b = BusinessOffer.objects.create(
            business=cls.business_b,
            variant=cls.variant_b,
            price=Decimal("250000"),
            is_active=True,
        )

    # 13. Global API endpoints without tenant continue working
    def test_global_endpoint_without_tenant_succeeds(self):
        response = self.client.get("/api/business/public/social-medias")
        self.assertEqual(response.status_code, 200)

    # 14. Data Isolation: Tenant header scopes storefront product search
    def test_tenant_header_scopes_storefront_products(self):
        # Without tenant header (marketplace view), products from all businesses are searched
        response_all = self.client.get("/api/catalog/storefront/products")
        self.assertEqual(response_all.status_code, 200)
        names_all = [p["name"] for p in response_all.json()["data"]["results"]]
        self.assertIn("Alpha Running Shoes", names_all)
        self.assertIn("Beta Hiking Boots", names_all)

        # With Alpha tenant header, only Alpha's products are returned
        response_alpha = self.client.get(
            "/api/catalog/storefront/products",
            HTTP_X_TENANT_SUBDOMAIN="alpha-store",
        )
        self.assertEqual(response_alpha.status_code, 200)
        names_alpha = [p["name"] for p in response_alpha.json()["data"]["results"]]
        self.assertIn("Alpha Running Shoes", names_alpha)
        self.assertNotIn("Beta Hiking Boots", names_alpha)

        # With Beta tenant header, only Beta's products are returned
        response_beta = self.client.get(
            "/api/catalog/storefront/products",
            HTTP_X_TENANT_SUBDOMAIN="beta-store",
        )
        self.assertEqual(response_beta.status_code, 200)
        names_beta = [p["name"] for p in response_beta.json()["data"]["results"]]
        self.assertNotIn("Alpha Running Shoes", names_beta)
        self.assertIn("Beta Hiking Boots", names_beta)

    # 15. Data Isolation: Storefront product detail returns 404 if product is not sold by tenant
    def test_storefront_product_detail_isolated_to_tenant(self):
        # Alpha storefront can view product_a
        res_a_view_a = self.client.get(
            f"/api/catalog/storefront/products/{self.product_a.slug}",
            HTTP_X_TENANT_SUBDOMAIN="alpha-store",
        )
        self.assertEqual(res_a_view_a.status_code, 200)
        self.assertEqual(res_a_view_a.json()["data"]["name"], "Alpha Running Shoes")

        # Alpha storefront CANNOT view product_b (Beta's product) -> 404
        res_a_view_b = self.client.get(
            f"/api/catalog/storefront/products/{self.product_b.slug}",
            HTTP_X_TENANT_SUBDOMAIN="alpha-store",
        )
        self.assertEqual(res_a_view_b.status_code, 404)

    # 16. Authentication & Permissions: Vendor A cannot manage Business B
    def test_vendor_cannot_manage_another_business_via_subdomain_header(self):
        # Authenticate as Vendor A
        self.client.force_authenticate(user=self.vendor_a)

        # Accessing with matching tenant header works
        res_own = self.client.get(
            "/api/vendor/business/profile",
            HTTP_X_TENANT_SUBDOMAIN="alpha-store",
        )
        self.assertEqual(res_own.status_code, 200)
        self.assertEqual(res_own.json()["data"]["business_name"], "alpha-store")

        # Accessing with another business's tenant header is rejected (404 / NotFound)
        res_other = self.client.get(
            "/api/vendor/business/profile",
            HTTP_X_TENANT_SUBDOMAIN="beta-store",
        )
        self.assertEqual(res_other.status_code, 404)

    # 17. Cache Isolation: Tenant cache keys are isolated and invalidated per business
    def test_tenant_cache_keys_are_isolated(self):
        cache = CacheService()
        key_a = f"{BUSINESS_CACHE_KEY}:{self.business_a.id}"
        key_b = f"{BUSINESS_CACHE_KEY}:{self.business_b.id}"

        cache.put_public(key_a, {"business": "Alpha", "id": self.business_a.id}, ttl=300)
        cache.put_public(key_b, {"business": "Beta", "id": self.business_b.id}, ttl=300)

        # Invalidate only Business A's cache
        invalidate_business_cache(self.business_a.id)

        # Business A cache is gone, Business B cache is intact
        self.assertIsNone(cache.get_public(key_a))
        self.assertEqual(cache.get_public(key_b), {"business": "Beta", "id": self.business_b.id})

        # Cleanup
        cache.delete_public(key_b)

    # 18. Public subdomain resolve endpoint returns status and canonical target
    def test_public_subdomain_resolve_endpoint(self):
        # Active subdomain
        res_active = self.client.get("/api/business/public/subdomain/resolve?subdomain=alpha-store")
        self.assertEqual(res_active.status_code, 200)
        self.assertEqual(res_active.json()["data"]["status"], "ACTIVE")
        self.assertEqual(res_active.json()["data"]["business_id"], self.business_a.id)

        # Reserved subdomain
        res_reserved = self.client.get("/api/business/public/subdomain/resolve?subdomain=admin")
        self.assertEqual(res_reserved.status_code, 200)
        self.assertEqual(res_reserved.json()["data"]["status"], "RESERVED")

        # Unknown subdomain
        res_unknown = self.client.get("/api/business/public/subdomain/resolve?subdomain=non-existent-sub")
        self.assertEqual(res_unknown.status_code, 200)
        self.assertEqual(res_unknown.json()["data"]["status"], "UNKNOWN")
