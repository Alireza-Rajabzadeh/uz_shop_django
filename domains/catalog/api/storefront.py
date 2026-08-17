from rest_framework.permissions import AllowAny
from rest_framework.exceptions import NotFound
from rest_framework.views import APIView

from core.responses import api_response
from domains.catalog.search import StorefrontSearchService
from domains.catalog.models import Product
from domains.catalog.services import StorefrontProductService

from .static_data import STATIC_DATA_HANDLERS
from .storefront_serializers import (
    StorefrontProductSearchQuerySerializer,
    StorefrontStaticDataQuerySerializer,
)


class StorefrontStaticData(APIView):
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


class StorefrontProductSearch(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        serializer = StorefrontProductSearchQuerySerializer.from_query_params(
            request.query_params
        )
        serializer.is_valid(raise_exception=True)
        result = StorefrontSearchService().search(serializer.to_criteria())
        data = {
            "count": result.count,
            "next": self._page_url(request, result.page + 1)
            if result.page * result.page_size < result.count else None,
            "previous": self._page_url(request, result.page - 1)
            if result.page > 1 else None,
            "results": result.results,
            "facets": result.facets,
        }
        return api_response(True, "", data)

    @staticmethod
    def _page_url(request, page):
        query = request.query_params.copy()
        query["page"] = page
        return request.build_absolute_uri(f"{request.path}?{query.urlencode()}")


class StorefrontProductQuickView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request, slug):
        try:
            data = StorefrontProductService().get_quick_view(slug)
        except Product.DoesNotExist as exc:
            raise NotFound("Product not found.") from exc
        return api_response(True, "", data)


class StorefrontProductDetail(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request, slug):
        try:
            data = StorefrontProductService().get_detail(slug)
        except Product.DoesNotExist as exc:
            raise NotFound("Product not found.") from exc
        return api_response(True, "", data)
