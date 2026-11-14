import io
import json
from django.conf import settings
from django.http import JsonResponse, QueryDict
from django.utils.translation import gettext as _

HEADER_NAME = "X-Tenant-Subdomain"
HTTP_HEADER_NAME = "HTTP_X_TENANT_SUBDOMAIN"


class TenantMiddleware:
    """Centralized tenant resolution and request normalization middleware.

    Resolves the active Business using the `X-Tenant-Subdomain` HTTP header and
    normalizes the incoming request (query parameters, JSON body, form data,
    and multipart form data) so that controllers, serializers, and domain
    services receive the authoritative `business_id` transparently without
    knowing about subdomains or tenant headers.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        raw_subdomain = self._get_tenant_header(request)

        if not raw_subdomain:
            request.business = None
            request.business_id = None
            return self.get_response(request)

        # Optional trusted proxy IP validation
        if not self._is_trusted_proxy(request):
            return JsonResponse(
                {
                    "success": False,
                    "message": _("Untrusted tenant proxy."),
                    "data": None,
                    "errors": {"detail": _("Tenant header rejected from untrusted source.")},
                },
                status=403,
            )

        resolution = self._resolve_subdomain(raw_subdomain)
        status = resolution["status"]

        if status == "INVALID":
            return JsonResponse(
                {
                    "success": False,
                    "message": _("Invalid subdomain format."),
                    "data": None,
                    "errors": {"subdomain": [resolution["error"]]},
                },
                status=400,
            )

        if status == "RESERVED":
            return JsonResponse(
                {
                    "success": False,
                    "message": _("This subdomain is reserved."),
                    "data": None,
                    "errors": {"detail": _("This subdomain is reserved.")},
                },
                status=404,
            )

        if status == "REDIRECT":
            response = JsonResponse(
                {
                    "success": False,
                    "message": _("Subdomain has moved."),
                    "data": {
                        "status": "REDIRECT",
                        "subdomain": resolution["subdomain"],
                        "canonical_subdomain": resolution["canonical_subdomain"],
                        "business_id": resolution["business"].id if resolution["business"] else None,
                    },
                    "errors": {"detail": _("Subdomain has moved.")},
                },
                status=308,
            )
            if resolution["canonical_subdomain"]:
                response["X-Canonical-Subdomain"] = resolution["canonical_subdomain"]
            return response

        if status == "ACTIVE":
            business = resolution["business"]
            request.business = business
            request.business_id = business.id

            self._normalize_request_data(request, business.id)
            return self.get_response(request)

        # UNKNOWN or any other unrecognized status
        return JsonResponse(
            {
                "success": False,
                "message": _("Business not found."),
                "data": None,
                "errors": {"detail": _("Business not found.")},
            },
            status=404,
        )

    def _get_tenant_header(self, request):
        """Read X-Tenant-Subdomain header from request."""
        header = request.headers.get(HEADER_NAME)
        if header is None:
            header = request.META.get(HTTP_HEADER_NAME)
        if header is not None:
            header = header.strip()
        return header or None

    def _is_trusted_proxy(self, request):
        """Verify request arrives from an authorized proxy if configured."""
        trusted_ips = getattr(settings, "TRUSTED_TENANT_PROXY_IPS", None)
        if not trusted_ips:
            return True

        client_ip = request.META.get("REMOTE_ADDR")
        return client_ip in trusted_ips

    def _resolve_subdomain(self, subdomain):
        """Resolve subdomain using BusinessSubdomainService."""
        from domains.business.services.business_subdomain_service import BusinessSubdomainService

        return BusinessSubdomainService.resolve_subdomain(subdomain)

    def _normalize_request_data(self, request, business_id):
        """Make the resolved business_id authoritative across all request channels."""
        # 1. Query parameters (normalize both business_id and business aliases)
        get_dict = request.GET.copy()
        get_dict["business_id"] = str(business_id)
        get_dict["business"] = str(business_id)
        get_dict._mutable = False
        request.GET = get_dict

        # 2. Body normalization based on content type
        content_type = ""
        if hasattr(request, "content_type") and request.content_type:
            content_type = request.content_type.lower()
        elif "CONTENT_TYPE" in request.META:
            content_type = request.META["CONTENT_TYPE"].split(";")[0].strip().lower()

        if content_type == "application/json" or content_type.endswith("+json"):
            self._normalize_json_body(request, business_id)
        elif content_type == "application/x-www-form-urlencoded":
            self._normalize_form_body(request, business_id)
        elif content_type.startswith("multipart/form-data"):
            self._normalize_multipart_body(request, business_id)

    def _normalize_json_body(self, request, business_id):
        """Inject or replace business_id in JSON payload."""
        raw_body = request.body
        if not raw_body or not raw_body.strip():
            if request.method in ("POST", "PUT", "PATCH"):
                payload = {"business_id": business_id}
                new_body = json.dumps(payload).encode("utf-8")
                request._body = new_body
                request._stream = io.BytesIO(new_body)
                request.META["CONTENT_LENGTH"] = str(len(new_body))
            return

        try:
            payload = json.loads(raw_body.decode("utf-8"))
            if isinstance(payload, dict):
                payload["business_id"] = business_id
                if "business" in payload:
                    payload["business"] = business_id
                new_body = json.dumps(payload).encode("utf-8")
                request._body = new_body
                request._stream = io.BytesIO(new_body)
                request.META["CONTENT_LENGTH"] = str(len(new_body))
            elif isinstance(payload, list):
                for item in payload:
                    if isinstance(item, dict):
                        item["business_id"] = business_id
                        if "business" in item:
                            item["business"] = business_id
                new_body = json.dumps(payload).encode("utf-8")
                request._body = new_body
                request._stream = io.BytesIO(new_body)
                request.META["CONTENT_LENGTH"] = str(len(new_body))
        except (json.JSONDecodeError, UnicodeDecodeError):
            pass

    def _normalize_form_body(self, request, business_id):
        """Inject or replace business_id in URL-encoded form data."""
        if request.method == "POST":
            post_dict = request.POST.copy()
            post_dict["business_id"] = str(business_id)
            if "business" in post_dict:
                post_dict["business"] = str(business_id)
            post_dict._mutable = False
            request.POST = post_dict
            new_body = post_dict.urlencode().encode("utf-8")
            request._body = new_body
            request._stream = io.BytesIO(new_body)
            request.META["CONTENT_LENGTH"] = str(len(new_body))
        elif request.method in ("PUT", "PATCH"):
            try:
                post_dict = QueryDict(request.body.decode("utf-8"), mutable=True)
                post_dict["business_id"] = str(business_id)
                if "business" in post_dict:
                    post_dict["business"] = str(business_id)
                post_dict._mutable = False
                new_body = post_dict.urlencode().encode("utf-8")
                request._body = new_body
                request._stream = io.BytesIO(new_body)
                request.META["CONTENT_LENGTH"] = str(len(new_body))
            except Exception:
                pass

    def _normalize_multipart_body(self, request, business_id):
        """Inject or replace business_id in multipart form data while preserving files."""
        if request.method in ("POST", "PUT", "PATCH"):
            post_dict = request.POST.copy()
            post_dict["business_id"] = str(business_id)
            if "business" in post_dict:
                post_dict["business"] = str(business_id)
            post_dict._mutable = False
            request.POST = post_dict
