import json
from django.conf import settings
from django.http import HttpResponse
from django.test import RequestFactory, TestCase, override_settings

from domains.business.enums import BusinessStatusEnum, BusinessSubdomainEnum
from domains.business.models import (
    BusinessProfile,
    BusinessStatus,
    BusinessSubdomain,
    BusinessSubdomainStatus,
)
from core.middleware.tenant import TenantMiddleware
from core.middleware.trusted_proxy import TrustedProxyMiddleware


def dummy_view(request):
    return HttpResponse("OK")


class TrustedProxyMiddlewareTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.middleware = TrustedProxyMiddleware(dummy_view)

    @override_settings(TRUSTED_TENANT_PROXY_IPS=["127.0.0.1", "10.0.0.1"])
    def test_trusted_ip_request_allowed(self):
        request = self.factory.get("/api/v1/storefront/layout", REMOTE_ADDR="127.0.0.1")
        response = self.middleware(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"OK")

    @override_settings(TRUSTED_TENANT_PROXY_IPS=["127.0.0.1"])
    def test_untrusted_ip_returns_403(self):
        request = self.factory.get("/api/v1/storefront/layout", REMOTE_ADDR="192.168.1.100")
        response = self.middleware(request)

        self.assertEqual(response.status_code, 403)
        body = json.loads(response.content.decode("utf-8"))
        self.assertFalse(body["success"])
        self.assertEqual(body["message"], "Untrusted tenant proxy.")
        self.assertEqual(
            body["errors"]["detail"],
            "Tenant header rejected from untrusted source.",
        )

    @override_settings(TRUSTED_TENANT_PROXY_IPS=None)
    def test_trusted_proxy_configuration_none_allows_request(self):
        request = self.factory.get("/api/v1/storefront/layout", REMOTE_ADDR="192.168.1.100")
        response = self.middleware(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"OK")

    @override_settings(TRUSTED_TENANT_PROXY_IPS=[])
    def test_trusted_proxy_configuration_empty_list_allows_request(self):
        request = self.factory.get("/api/v1/storefront/layout", REMOTE_ADDR="192.168.1.100")
        response = self.middleware(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"OK")


class TenantMiddlewareTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.active_status, _ = BusinessStatus.objects.get_or_create(
            id=BusinessStatusEnum.ACTIVE.value,
            defaults={"name": "Active", "title": "Active"},
        )
        cls.active_sub_status, _ = BusinessSubdomainStatus.objects.get_or_create(
            id=BusinessSubdomainEnum.ACTIVE.value,
            defaults={"code": "active", "name": "Active", "title": "Active"},
        )

        cls.business = BusinessProfile.objects.create(
            business_name="acme",
            display_name="Acme Corp",
            status=cls.active_status,
        )
        cls.active_sub = BusinessSubdomain.objects.create(
            business=cls.business,
            subdomain="acme",
            status=cls.active_sub_status,
        )

    def setUp(self):
        self.factory = RequestFactory()
        self.middleware = TenantMiddleware(dummy_view)

    def test_missing_tenant_header_leaves_business_none(self):
        request = self.factory.get("/api/v1/storefront/layout")
        response = self.middleware(request)

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(request.business)

    def test_active_subdomain_attaches_business(self):
        request = self.factory.get(
            "/api/v1/storefront/layout",
            HTTP_X_TENANT_SUBDOMAIN="acme",
        )
        response = self.middleware(request)

        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(request.business)
        self.assertEqual(request.business.id, self.business.id)

    def test_inactive_or_invalid_subdomain_leaves_business_none(self):
        request = self.factory.get(
            "/api/v1/storefront/layout",
            HTTP_X_TENANT_SUBDOMAIN="non-existent-sub",
        )
        response = self.middleware(request)

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(request.business)


class MiddlewareOrderAndPipelineTests(TestCase):
    def test_middleware_order_in_settings(self):
        middleware_list = list(settings.MIDDLEWARE)
        self.assertIn(
            "core.middleware.trusted_proxy.TrustedProxyMiddleware",
            middleware_list,
        )
        self.assertIn(
            "core.middleware.tenant.TenantMiddleware",
            middleware_list,
        )
        proxy_idx = middleware_list.index(
            "core.middleware.trusted_proxy.TrustedProxyMiddleware"
        )
        tenant_idx = middleware_list.index(
            "core.middleware.tenant.TenantMiddleware"
        )
        self.assertLess(
            proxy_idx,
            tenant_idx,
            "TrustedProxyMiddleware must be executed before TenantMiddleware",
        )

    @override_settings(TRUSTED_TENANT_PROXY_IPS=["127.0.0.1"])
    def test_pipeline_untrusted_ip_blocks_before_tenant_middleware(self):
        factory = RequestFactory()
        pipeline = TrustedProxyMiddleware(TenantMiddleware(dummy_view))

        request = factory.get(
            "/api/v1/storefront/layout",
            HTTP_X_TENANT_SUBDOMAIN="acme",
            REMOTE_ADDR="198.51.100.1",
        )
        response = pipeline(request)

        self.assertEqual(response.status_code, 403)
        body = json.loads(response.content.decode("utf-8"))
        self.assertEqual(body["message"], "Untrusted tenant proxy.")
        self.assertFalse(hasattr(request, "business"))
