import json

from django.utils.translation import gettext as _
from rest_framework.exceptions import NotFound
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import AllowAny, BasePermission
from rest_framework.views import APIView

from core.permissions import AdminModelPermissions, CustomActionPermission
from core.responses import api_response
from domains.catalog.models import Product
from domains.catalog.services import CategoryService, ProductService
from domains.users.auth import AdminJWTAuthentication

from .contracts import CONTRACTS_FILE
from .models import LandingPage, SEORecord
from .serializers import (
    LandingPageContentSerializer,
    LandingPageDetailSerializer,
    LandingPageSerializer,
    SEORecordSerializer,
)
from .services import LandingPageContentResolver, LandingPageService


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


class ResourceSEOPermission(BasePermission):
    resource_permissions = {}

    def has_permission(self, request, view):
        user = request.user
        if not (
            user
            and user.is_authenticated
            and user.is_active
            and user.is_staff
        ):
            return False
        permissions = self.resource_permissions.get(request.method, ())
        return bool(permissions) and all(user.has_perm(permission) for permission in permissions)


class LandingPageSEOPermission(ResourceSEOPermission):
    resource_permissions = {
        "GET": ("content.view_landingpage",),
        "PUT": ("content.change_landingpage",),
        "PATCH": ("content.change_landingpage",),
        "DELETE": ("content.change_landingpage",),
    }


class ProductSEOPermission(ResourceSEOPermission):
    resource_permissions = {
        "GET": ("catalog.view_product",),
        "PUT": ("catalog.change_product",),
        "PATCH": ("catalog.change_product",),
        "DELETE": ("catalog.change_product",),
    }


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
        return api_response(data=LandingPageDetailSerializer(page).data)

    def patch(self, request, landing_page_id):
        page = self.get_page(landing_page_id)
        serializer = LandingPageSerializer(page, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        page = serializer.save()
        return api_response(data=LandingPageDetailSerializer(page).data)

    def delete(self, request, landing_page_id):
        page = self.get_page(landing_page_id)
        LandingPageService().delete_page(page)
        return api_response(data=None)


class AdminLandingPagePublish(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [CustomActionPermission]
    required_permissions = ("content.change_landingpage",)

    def post(self, request, landing_page_id):
        try:
            page = LandingPage.objects.get(id=landing_page_id)
        except LandingPage.DoesNotExist as exc:
            raise NotFound(_("Landing page not found.")) from exc
        LandingPageService().publish_page(page)
        return api_response(data=LandingPageDetailSerializer(page).data)


class AdminResourceSEOView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    resource_type = ""

    @staticmethod
    def get_resource(resource_id):
        raise NotImplementedError

    @classmethod
    def get_record(cls, resource_id):
        return SEORecord.objects.filter(
            resource_type=cls.resource_type,
            resource_id=resource_id,
        ).first()

    def get(self, request, resource_id):
        self.get_resource(resource_id)
        record = self.get_record(resource_id)
        return api_response(data=SEORecordSerializer(record).data if record else None)

    def put(self, request, resource_id):
        self.get_resource(resource_id)
        record = self.get_record(resource_id)
        serializer = SEORecordSerializer(record, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        record = serializer.save(
            resource_type=self.resource_type,
            resource_id=resource_id,
        )
        return api_response(data=SEORecordSerializer(record).data)

    def delete(self, request, resource_id):
        self.get_resource(resource_id)
        record = self.get_record(resource_id)
        if record:
            record.delete()
        return api_response(data=None)


class AdminLandingPageSEO(AdminResourceSEOView):
    permission_classes = [LandingPageSEOPermission]
    resource_type = "landing_page"

    @staticmethod
    def get_resource(resource_id):
        try:
            return LandingPage.objects.get(id=resource_id)
        except LandingPage.DoesNotExist as exc:
            raise NotFound(_("Landing page not found.")) from exc


class AdminProductSEO(AdminResourceSEOView):
    permission_classes = [ProductSEOPermission]
    resource_type = "product"

    @staticmethod
    def get_resource(resource_id):
        try:
            return Product.objects.get(id=resource_id)
        except Product.DoesNotExist as exc:
            raise NotFound(_("Product not found.")) from exc


class LandingPageBySlug(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    allowed_statuses = ()
    content_field = ""

    def get(self, request, slug):
        try:
            page = LandingPageService().get_by_slug(slug)
        except LandingPage.DoesNotExist as exc:
            raise NotFound(_("Landing page not found.")) from exc

        if page.status not in self.allowed_statuses:
            raise NotFound(_("Landing page not found."))

        page.selected_content = LandingPageContentResolver().resolve(
            getattr(page, self.content_field)
        )
        return api_response(data=LandingPageContentSerializer(page).data)


class LandingPagePreview(LandingPageBySlug):
    allowed_statuses = (LandingPage.Status.DRAFT, LandingPage.Status.PUBLISHED)
    content_field = "draft_content"


class PublicLandingPage(LandingPageBySlug):
    allowed_statuses = (LandingPage.Status.PUBLISHED,)
    content_field = "published_content"


class PublicHomeLandingPage(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        try:
            page = LandingPageService().get_home_page()
        except LandingPage.DoesNotExist as exc:
            raise NotFound(_("Landing page not found.")) from exc

        if page.status != LandingPage.Status.PUBLISHED:
            raise NotFound(_("Landing page not found."))

        page.selected_content = LandingPageContentResolver().resolve(page.published_content)
        return api_response(data=LandingPageContentSerializer(page).data)


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
