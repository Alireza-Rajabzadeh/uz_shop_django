from django.utils.translation import gettext as _
from rest_framework.exceptions import NotFound
from rest_framework.views import APIView

from core.responses import api_response
from domains.catalog.models import Brand, Category, Product
from domains.users.auth import AdminJWTAuthentication
from ..models.landing_page import LandingPage
from ..models.page import Page
from ..models.seo_record import SEORecord
from ..serializers.seo_record_serializer import SEORecordSerializer


RESOURCE_CONFIG = {
    "landing_page": {
        "model": LandingPage,
        "not_found": _("Landing page not found."),
        "perms": {
            "GET": ("content.view_landingpage",),
            "PUT": ("content.change_landingpage",),
            "PATCH": ("content.change_landingpage",),
            "DELETE": ("content.change_landingpage",),
        },
    },
    "page": {
        "model": Page,
        "not_found": _("Page not found."),
        "perms": {
            "GET": ("content.view_page",),
            "PUT": ("content.change_page",),
            "PATCH": ("content.change_page",),
            "DELETE": ("content.change_page",),
        },
    },
    "product": {
        "model": Product,
        "not_found": _("Product not found."),
        "perms": {
            "GET": ("catalog.view_product",),
            "PUT": ("catalog.change_product",),
            "PATCH": ("catalog.change_product",),
            "DELETE": ("catalog.change_product",),
        },
    },
    "category": {
        "model": Category,
        "not_found": _("Category not found."),
        "perms": {
            "GET": ("catalog.view_category",),
            "PUT": ("catalog.change_category",),
            "DELETE": ("catalog.change_category",),
        },
    },
    "brand": {
        "model": Brand,
        "not_found": _("Brand not found."),
        "perms": {
            "GET": ("catalog.view_brand",),
            "PUT": ("catalog.change_brand",),
            "DELETE": ("catalog.change_brand",),
        },
    },
}


class AdminSEOView(APIView):
    authentication_classes = [AdminJWTAuthentication]

    def check_permissions(self, request):
        super().check_permissions(request)
        user = request.user
        if not (user and user.is_authenticated and user.is_active and user.is_staff):
            self.permission_denied(request)

        resource_type = self.kwargs.get("resource_type", "")
        config = RESOURCE_CONFIG.get(resource_type)
        if not config:
            self.permission_denied(request)

        required = config["perms"].get(request.method, ())
        if not all(user.has_perm(perm) for perm in required):
            self.permission_denied(request)

    def resolve_resource(self, resource_type, resource_id):
        config = RESOURCE_CONFIG.get(resource_type)
        if not config:
            raise NotFound(_("SEO resource not found."))
        try:
            return config["model"].objects.get(id=resource_id)
        except config["model"].DoesNotExist as exc:
            raise NotFound(config["not_found"]) from exc

    def get(self, request, resource_id, resource_type):
        self.resolve_resource(resource_type, resource_id)
        record = SEORecord.objects.filter(
            resource_type=resource_type,
            resource_id=resource_id,
        ).first()
        return api_response(data=SEORecordSerializer(record).data if record else None)

    def put(self, request, resource_id, resource_type):
        self.resolve_resource(resource_type, resource_id)
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
        self.resolve_resource(resource_type, resource_id)
        record = SEORecord.objects.filter(
            resource_type=resource_type,
            resource_id=resource_id,
        ).first()
        if record:
            record.delete()
        return api_response(data=None)
