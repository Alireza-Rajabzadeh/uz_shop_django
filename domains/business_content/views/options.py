import json

from django.utils.translation import gettext as _
from rest_framework.exceptions import NotFound
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from core.responses import api_response
from domains.business.models import BusinessProfile
from domains.catalog.services import CategoryService, ProductService
from domains.vendor.auth import VendorJWTAuthentication
from ..contracts import CONTRACTS_FILE
from ..models import SuggestionPage
from ..serializers.suggestion_page_serializer import SuggestionPageSerializer


def read_component_contracts():
    if not CONTRACTS_FILE.exists():
        return None, api_response(
            success=False,
            message=_("content contracts file not found"),
            errors={
                "detail": _("Run sync_business_content_contracts to generate the file.")
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


class VendorContentOptionsView(APIView):
    authentication_classes = [VendorJWTAuthentication]
    permission_classes = [IsAuthenticated]

    @staticmethod
    def _get_business(request):
        business = BusinessProfile.objects.filter(vendor=request.user).first()
        if business is None:
            raise NotFound(_("Business profile not found."))
        return business

    def paginate_queryset(self, queryset, serializer=None):
        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(queryset, self.request, view=self)
        data = serializer(page, many=True).data if serializer else page
        return paginator.get_paginated_response(data).data

    def get(self, request, option_type):
        if option_type == "contracts":
            data, error = read_component_contracts()
            return error if error is not None else api_response(data=data)

        if option_type == "suggestions":
            suggestions = SuggestionPage.objects.filter(activate=True)
            return api_response(
                data=SuggestionPageSerializer(suggestions, many=True).data
            )

        business = self._get_business(request)
        search = request.query_params.get("search", "").strip()

        if option_type == "products":
            category_ids = business.categories.values_list("category_id", flat=True)
            queryset = (
                ProductService()
                .content_selector_options(search)
                .filter(categories__id__in=category_ids)
                .distinct()
            )
            serializer_fn = serialize_product_option
        elif option_type == "categories":
            category_ids = business.categories.values_list("category_id", flat=True)
            queryset = CategoryService().content_selector_options(search).filter(
                id__in=category_ids
            )
            serializer_fn = serialize_category_option
        else:
            raise NotFound()

        data = self.paginate_queryset(queryset)
        data["results"] = [serializer_fn(item) for item in data["results"]]
        return api_response(data=data)
