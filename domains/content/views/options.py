import json

from django.utils.translation import gettext as _
from rest_framework.exceptions import NotFound
from rest_framework.pagination import PageNumberPagination
from rest_framework.views import APIView

from core.permissions import AdminModelPermissions
from core.responses import api_response
from domains.catalog.services import CategoryService, ProductService
from domains.users.auth import AdminJWTAuthentication
from ..contracts import CONTRACTS_FILE


def read_component_contracts():
    """Return ``(payload, None)`` or ``(None, error_response)`` for the
    synced contracts file backing the admin contract view."""
    if not CONTRACTS_FILE.exists():
        return None, api_response(
            success=False,
            message=_("content contracts file not found"),
            errors={
                "detail": _("Run sync_content_contracts to generate the file.")
            },
            status_code=404,
        )
    try:
        return json.loads(CONTRACTS_FILE.read_text(encoding="utf-8")), None
    except json.JSONDecodeError:
        return None, api_response(
            success=False,
            message=_("content contracts file is invalid"),
            errors={"detail": _("The contracts file could not be parsed.")},
            status_code=500,
        )


def serialize_product_option(product):
    return {
        "id": product.id,
        "label": product.name,
        "description": product.description or "",
    }


def serialize_category_option(category):
    data = {
        "id": category.id,
        "label": category.fa_name or category.name,
    }
    if category.parent:
        data["description"] = category.parent.fa_name or category.parent.name
    if category.logo:
        data["image"] = category.logo
    return data


class AdminContentOptionsView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = []

    def check_permissions(self, request):
        super().check_permissions(request)
        option_type = self.kwargs.get("option_type")
        user = request.user
        if not (user and user.is_authenticated and user.is_active and user.is_staff):
            self.permission_denied(request)

        if option_type == "contracts":
            return

        perms = (
            "content.view_landingpage",
            "content.add_landingpage",
            "content.change_landingpage",
        )
        if not any(user.has_perm(perm) for perm in perms):
            self.permission_denied(request)

    def paginate_queryset(self, queryset, serializer=None):
        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(queryset, self.request, view=self)
        data = serializer(page, many=True).data if serializer else page
        return paginator.get_paginated_response(data).data

    def get(self, request, option_type):
        if option_type == "contracts":
            data, error = read_component_contracts()
            return error if error is not None else api_response(data=data)

        search = request.query_params.get("search", "").strip()
        if option_type == "products":
            queryset = ProductService().content_selector_options(search)
            serializer_fn = serialize_product_option
        elif option_type == "categories":
            queryset = CategoryService().content_selector_options(search)
            serializer_fn = serialize_category_option
        else:
            raise NotFound()

        data = self.paginate_queryset(queryset)
        data["results"] = [serializer_fn(item) for item in data["results"]]
        return api_response(data=data)
