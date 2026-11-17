from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from core.responses import api_response
from domains.catalog.api.static_data import STATIC_DATA_HANDLERS
from domains.catalog.api.storefront_serializers import (
    StorefrontStaticDataQuerySerializer,
)
from domains.catalog.services import CategoryService
from domains.business.services import BusinessService


class StorefrontStaticDataView(APIView):
    """Storefront static data loader (e.g. categories tree registry)."""

    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        serializer = StorefrontStaticDataQuerySerializer(
            data=request.query_params,
            context={"supported_data": STATIC_DATA_HANDLERS},
        )
        serializer.is_valid(raise_exception=True)
        requested_data = serializer.validated_data.get("data")
        handlers = (
            {requested_data: STATIC_DATA_HANDLERS[requested_data]}
            if requested_data
            else STATIC_DATA_HANDLERS
        )
        data = {name: handler() for name, handler in handlers.items()}
        return api_response(True, "", data)


class StorefrontCategoriesView(APIView):
    """Customer-facing category navigation tree.

    Returns the global category tree for the platform storefront, or only the
    categories registered by the active business when under a tenant context.
    """

    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        business = getattr(request, "business", None)
        full_tree = CategoryService().get_storefront_tree()
        if business is not None:
            profile_categories = BusinessService.profile_categories(business)
            allowed_ids = set(profile_categories.values_list("category_id", flat=True))
            data = [cat for cat in full_tree if cat["id"] in allowed_ids]
        else:
            data = full_tree
        return api_response(True, "", data)
