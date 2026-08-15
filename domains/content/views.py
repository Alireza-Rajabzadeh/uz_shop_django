import json

from django.utils.translation import gettext as _
from rest_framework.exceptions import NotFound
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import BasePermission
from rest_framework.views import APIView

from core.permissions import AdminModelPermissions
from core.responses import api_response
from domains.catalog.services import CategoryService, ProductService
from domains.users.auth import AdminJWTAuthentication

from .contracts import CONTRACTS_FILE
from .models import LandingPage
from .serializers import LandingPageSerializer


class AdminContentAPIView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [AdminModelPermissions]

    @staticmethod
    def paginated(queryset, request, view, serializer=None):
        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(queryset, request, view=view)
        data = serializer(page, many=True).data if serializer else page
        return paginator.get_paginated_response(data).data


class LandingPageAuthoringPermission(BasePermission):
    permissions = (
        "content.view_landingpage",
        "content.add_landingpage",
        "content.change_landingpage",
    )

    def has_permission(self, request, view):
        user = request.user
        return bool(
            user
            and user.is_authenticated
            and user.is_active
            and user.is_staff
            and any(user.has_perm(permission) for permission in self.permissions)
        )


class AdminLandingPageList(AdminContentAPIView):
    model = LandingPage
    ordering_fields = {"id", "title", "slug", "status", "created_at", "updated_at"}

    def get(self, request):
        ordering = request.query_params.get("ordering", "-updated_at")
        field = ordering.removeprefix("-")
        if field not in self.ordering_fields:
            ordering = "-updated_at"
        queryset = LandingPage.objects.all().order_by(ordering)
        data = self.paginated(queryset, request, self, LandingPageSerializer)
        return api_response(data=data)

    def post(self, request):
        serializer = LandingPageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        page = serializer.save()
        return api_response(data=LandingPageSerializer(page).data, status_code=201)


class AdminLandingPageDetail(AdminContentAPIView):
    model = LandingPage

    @staticmethod
    def get_page(landing_page_id):
        try:
            return LandingPage.objects.get(id=landing_page_id)
        except LandingPage.DoesNotExist as exc:
            raise NotFound(_("Landing page not found.")) from exc

    def get(self, request, landing_page_id):
        page = self.get_page(landing_page_id)
        return api_response(data=LandingPageSerializer(page).data)

    def patch(self, request, landing_page_id):
        page = self.get_page(landing_page_id)
        serializer = LandingPageSerializer(page, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        page = serializer.save()
        return api_response(data=LandingPageSerializer(page).data)


class AdminContentComponentContractList(AdminContentAPIView):
    model = LandingPage

    def get(self, request):
        if not CONTRACTS_FILE.exists():
            return api_response(
                success=False,
                message="content contracts file not found",
                errors={"detail": "Run sync_content_contracts to generate the file."},
                status_code=404,
            )
        try:
            data = json.loads(CONTRACTS_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return api_response(
                success=False,
                message="content contracts file is invalid",
                errors={"detail": "The contracts file could not be parsed."},
                status_code=500,
            )
        return api_response(data=data)


class AdminContentOptionList(AdminContentAPIView):
    permission_classes = [LandingPageAuthoringPermission]

    def serialize_option(self, item):
        raise NotImplementedError

    def get_queryset(self, search):
        raise NotImplementedError

    def get(self, request):
        queryset = self.get_queryset(request.query_params.get("search", "").strip())
        data = self.paginated(queryset, request, self)
        data["results"] = [self.serialize_option(item) for item in data["results"]]
        return api_response(data=data)


class AdminProductOptionList(AdminContentOptionList):
    def get_queryset(self, search):
        return ProductService().content_selector_options(search)

    def serialize_option(self, product):
        return {
            "id": product.id,
            "label": product.name,
            "description": product.description or "",
        }


class AdminCategoryOptionList(AdminContentOptionList):
    def get_queryset(self, search):
        return CategoryService().content_selector_options(search)

    def serialize_option(self, category):
        data = {
            "id": category.id,
            "label": category.fa_name or category.name,
        }
        if category.parent:
            data["description"] = category.parent.fa_name or category.parent.name
        if category.logo:
            data["image"] = category.logo
        return data
