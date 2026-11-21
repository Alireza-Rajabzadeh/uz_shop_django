from django.utils.translation import gettext as _
from rest_framework.exceptions import NotFound
from rest_framework.pagination import PageNumberPagination
from rest_framework.views import APIView

from core.responses import api_response
from domains.users.auth import AdminJWTAuthentication
from ..models.landing_page import LandingPage
from ..serializers.landing_page_detail_serializer import (
    LandingPageDetailSerializer,
)
from ..serializers.landing_page_serializer import LandingPageSerializer
from ..services.landing_page_service import LandingPageService


class AdminLandingPageView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    model = LandingPage
    ordering_fields = {"id", "title", "slug", "status", "created_at", "updated_at"}

    def check_permissions(self, request):
        super().check_permissions(request)
        action = self.kwargs.get("action")
        user = request.user
        if not (user and user.is_authenticated and user.is_active and user.is_staff):
            self.permission_denied(request)

        if action == "publish":
            if not user.has_perm("content.change_landingpage"):
                self.permission_denied(request)
            return

        method_perms = {
            "GET": ("content.view_landingpage",),
            "POST": ("content.add_landingpage",),
            "PATCH": ("content.change_landingpage",),
            "DELETE": ("content.delete_landingpage",),
        }
        required = method_perms.get(request.method, ())
        if not all(user.has_perm(perm) for perm in required):
            self.permission_denied(request)

    @staticmethod
    def get_page(landing_page_id):
        try:
            return LandingPage.objects.get(id=landing_page_id)
        except LandingPage.DoesNotExist as exc:
            raise NotFound(_("Landing page not found.")) from exc

    def paginate_queryset(self, queryset, serializer=None):
        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(queryset, self.request, view=self)
        data = serializer(page, many=True).data if serializer else page
        return paginator.get_paginated_response(data).data

    def get(self, request, landing_page_id=None, action=None):
        if landing_page_id is not None:
            page = self.get_page(landing_page_id)
            return api_response(data=LandingPageDetailSerializer(page).data)

        ordering = request.query_params.get("ordering", "-updated_at")
        field = ordering.removeprefix("-")
        if field not in self.ordering_fields:
            ordering = "-updated_at"
        queryset = LandingPage.objects.all().order_by(ordering)
        data = self.paginate_queryset(queryset, LandingPageSerializer)
        return api_response(data=data)

    def post(self, request, landing_page_id=None, action=None):
        if action == "publish":
            page = self.get_page(landing_page_id)
            LandingPageService().publish_page(page)
            return api_response(data=LandingPageDetailSerializer(page).data)

        serializer = LandingPageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        page = serializer.save()
        return api_response(data=LandingPageSerializer(page).data, status_code=201)

    def patch(self, request, landing_page_id=None, action=None):
        page = self.get_page(landing_page_id)
        serializer = LandingPageSerializer(page, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        page = serializer.save()
        return api_response(data=LandingPageDetailSerializer(page).data)

    def delete(self, request, landing_page_id=None, action=None):
        page = self.get_page(landing_page_id)
        LandingPageService().delete_page(page)
        return api_response(data=None)
