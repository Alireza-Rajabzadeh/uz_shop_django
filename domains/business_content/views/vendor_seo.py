from django.utils.translation import gettext as _
from rest_framework.exceptions import NotFound
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from core.responses import api_response
from domains.business.models import BusinessProfile
from domains.packages.permissions import RequiresContentLandingPage
from domains.vendor.auth import VendorJWTAuthentication
from ..models import LandingPage, Page, SEORecord
from ..serializers.seo_record_serializer import SEORecordSerializer


RESOURCE_CONFIG = {
    "landing_page": {
        "model": LandingPage,
        "not_found": _("Landing page not found."),
        "requires_landing_page_perm": True,
    },
    "page": {
        "model": Page,
        "not_found": _("Page not found."),
        "requires_landing_page_perm": False,
    },
}


class VendorSEOView(APIView):
    authentication_classes = [VendorJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def check_permissions(self, request):
        super().check_permissions(request)
        resource_type = self.kwargs.get("resource_type", "")
        config = RESOURCE_CONFIG.get(resource_type)
        if config and config["requires_landing_page_perm"]:
            landing_perm = RequiresContentLandingPage()
            if not landing_perm.has_permission(request, self):
                self.permission_denied(
                    request,
                    message=getattr(landing_perm, "message", None),
                    code=getattr(landing_perm, "code", None),
                )

    def resolve_resource(self, request, resource_type, resource_id):
        config = RESOURCE_CONFIG.get(resource_type)
        if not config:
            raise NotFound(_("SEO resource not found."))

        business = BusinessProfile.objects.filter(vendor=request.user).first()
        if business is None:
            raise NotFound(_("Business profile not found."))

        resource = config["model"].objects.filter(id=resource_id, business=business).first()
        if resource is None:
            raise NotFound(config["not_found"])
        return resource

    def get(self, request, resource_id, resource_type):
        self.resolve_resource(request, resource_type, resource_id)
        record = SEORecord.objects.filter(
            resource_type=resource_type,
            resource_id=resource_id,
        ).first()
        return api_response(data=SEORecordSerializer(record).data if record else None)

    def put(self, request, resource_id, resource_type):
        self.resolve_resource(request, resource_type, resource_id)
        record = SEORecord.objects.filter(
            resource_type=resource_type,
            resource_id=resource_id,
        ).first()
        serializer = SEORecordSerializer(record, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        record = serializer.save(
            resource_type=resource_type,
            resource_id=resource_id,
        )
        return api_response(data=SEORecordSerializer(record).data)

    def delete(self, request, resource_id, resource_type):
        self.resolve_resource(request, resource_type, resource_id)
        record = SEORecord.objects.filter(
            resource_type=resource_type,
            resource_id=resource_id,
        ).first()
        if record:
            record.delete()
        return api_response(data=None)
