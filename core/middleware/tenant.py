from domains.business.services.business_subdomain_service import (
    BusinessSubdomainService,
)

HEADER_NAME = "X-Tenant-Subdomain"
HTTP_HEADER_NAME = "HTTP_X_TENANT_SUBDOMAIN"


class TenantMiddleware:
    """
    Resolve business tenant context from X-Tenant-Subdomain.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.business = None

        subdomain = request.headers.get(HEADER_NAME)

        if subdomain:
            resolution = BusinessSubdomainService.resolve_subdomain(
                subdomain.strip()
            )

            if resolution.get("status") == "ACTIVE":
                request.business = resolution.get("business")

        return self.get_response(request)