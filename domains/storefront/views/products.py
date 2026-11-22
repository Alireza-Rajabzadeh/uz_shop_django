from django.core.exceptions import ObjectDoesNotExist
from rest_framework.exceptions import NotFound
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from core.responses import api_response
from domains.storefront.serializers import (
    StorefrontOfferQuerySerializer,
    StorefrontProductSearchQuerySerializer,
)
from domains.storefront.search import StorefrontSearchService
from domains.storefront.services import StorefrontProductService


class StorefrontProductSearchView(APIView):
    """Customer-facing product listing and search."""

    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        serializer = StorefrontProductSearchQuerySerializer.from_query_params(
            request.query_params
        )
        serializer.is_valid(raise_exception=True)
        business = getattr(request, "business", None)
        result = StorefrontSearchService().search(
            serializer.to_criteria(business=business)
        )
        data = {
            "count": result.count,
            "next": (
                self._page_url(request, result.page + 1)
                if result.page * result.page_size < result.count
                else None
            ),
            "previous": (
                self._page_url(request, result.page - 1)
                if result.page > 1
                else None
            ),
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
    """Customer-facing fast modal preview for a product."""

    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request, slug):
        business = getattr(request, "business", None)
        try:
            data = StorefrontProductService().get_quick_view(slug, business=business)
        except ObjectDoesNotExist as exc:
            raise NotFound("Product not found.") from exc
        return api_response(True, "", data)


class StorefrontProductDetailView(APIView):
    """Customer-facing full product detail view."""

    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request, slug):
        business = getattr(request, "business", None)
        try:
            data = StorefrontProductService().get_detail(slug, business=business)
        except ObjectDoesNotExist as exc:
            raise NotFound("Product not found.") from exc
        return api_response(True, "", data)


class StorefrontProductVariantOffersView(APIView):
    """Customer-facing variant vendor offers."""

    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request, slug, variant_id):
        serializer = StorefrontOfferQuerySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        business = getattr(request, "business", None)
        try:
            data = StorefrontProductService().get_variant_offers(
                slug,
                variant_id,
                page=serializer.validated_data["page"],
                page_size=serializer.validated_data["page_size"],
                business=business,
            )
        except ObjectDoesNotExist as exc:
            raise NotFound("Product variant not found.") from exc

        data["next"] = (
            self._page_url(request, data["page"] + 1)
            if data["page"] * data["page_size"] < data["count"]
            else None
        )
        data["previous"] = (
            self._page_url(request, data["page"] - 1)
            if data["page"] > 1
            else None
        )
        return api_response(True, "", data)

    @staticmethod
    def _page_url(request, page):
        query = request.query_params.copy()
        query["page"] = page
        return request.build_absolute_uri(f"{request.path}?{query.urlencode()}")
