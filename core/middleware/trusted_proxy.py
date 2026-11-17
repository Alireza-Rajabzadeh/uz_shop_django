from django.conf import settings
from django.utils.translation import gettext as _
from rest_framework.renderers import JSONRenderer

from core.responses import api_response


class TrustedProxyMiddleware:
    """Validates that incoming requests arrive from an authorized proxy if configured.

    Responsible only for validating the request source IP against `TRUSTED_TENANT_PROXY_IPS`.
    Does not perform tenant resolution or modify tenant-related request attributes.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        trusted_ips = getattr(settings, "TRUSTED_TENANT_PROXY_IPS", None)
        if not trusted_ips:
            return self.get_response(request)

        client_ip = request.META.get("REMOTE_ADDR")
        if client_ip in trusted_ips:
            return self.get_response(request)

        response = api_response(
            success=False,
            message=_("Untrusted tenant proxy."),
            data=None,
            errors={
                "detail": _("Tenant header rejected from untrusted source.")
            },
            status_code=403,
        )
        response.accepted_renderer = JSONRenderer()
        response.accepted_media_type = "application/json"
        response.renderer_context = {}
        return response.render()
