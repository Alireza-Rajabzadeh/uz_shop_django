from django.utils.translation import gettext as _
from rest_framework.exceptions import NotFound
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from core.responses import api_response
from domains.business.models import BusinessProfile
from domains.vendor.auth import VendorJWTAuthentication
from ..models import Page
from ..serializers.page_content_serializer import PageContentSerializer
from ..serializers.page_detail_serializer import PageDetailSerializer
from ..serializers.page_serializer import PageSerializer
from ..services.landing_page_content_resolver import LandingPageContentResolver
from ..services.page_service import PageService


class VendorPageView(APIView):
    authentication_classes = [VendorJWTAuthentication]
    permission_classes = [IsAuthenticated]

    model = Page
    ordering_fields = {"id", "title", "slug", "status", "created_at", "updated_at"}

    @staticmethod
    def _get_business(request):
        business = BusinessProfile.objects.filter(vendor=request.user).first()
        if business is None:
            raise NotFound(_("Business profile not found."))
        return business

    def get_object(self, request, resource_id):
        business = self._get_business(request)
        instance = self.model.objects.filter(
            id=resource_id, business=business
        ).first()
        if instance is None:
            raise NotFound(_("Page not found."))
        return business, instance

    def paginate_queryset(self, queryset, serializer=None):
        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(queryset, self.request, view=self)
        data = serializer(page, many=True).data if serializer else page
        return paginator.get_paginated_response(data).data

    def get(self, request, resource_id=None, action=None):
        if action == "preview":
            _, instance = self.get_object(request, resource_id)
            if instance.status not in (Page.Status.DRAFT, Page.Status.PUBLISHED):
                raise NotFound(_("Page not found."))
            instance.selected_content = LandingPageContentResolver.for_authoring().resolve(
                instance.draft_content
            )
            return api_response(data=PageContentSerializer(instance).data)

        if resource_id is not None:
            _, instance = self.get_object(request, resource_id)
            return api_response(data=PageDetailSerializer(instance).data)

        business = self._get_business(request)
        ordering = request.query_params.get("ordering", "-updated_at")
        field = ordering.removeprefix("-")
        if field not in self.ordering_fields:
            ordering = "-updated_at"
        queryset = self.model.objects.filter(business=business).order_by(ordering)
        data = self.paginate_queryset(queryset, PageSerializer)
        return api_response(data=data)

    def post(self, request, resource_id=None, action=None):
        if action == "publish":
            _, instance = self.get_object(request, resource_id)
            PageService().publish_page(instance)
            return api_response(data=PageDetailSerializer(instance).data)

        business = self._get_business(request)
        serializer = PageSerializer(
            data=request.data, context={"business": business}
        )
        serializer.is_valid(raise_exception=True)
        instance = serializer.save(business=business)
        return api_response(
            data=PageDetailSerializer(instance).data, status_code=201
        )

    def patch(self, request, resource_id=None, action=None):
        business, instance = self.get_object(request, resource_id)
        serializer = PageSerializer(
            instance, data=request.data, partial=True, context={"business": business}
        )
        serializer.is_valid(raise_exception=True)
        instance = serializer.save()
        return api_response(data=PageDetailSerializer(instance).data)

    def delete(self, request, resource_id=None, action=None):
        _, instance = self.get_object(request, resource_id)
        PageService().delete_page(instance)
        return api_response(data=None)
