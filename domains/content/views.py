import json

from django.utils.translation import gettext as _
from rest_framework.exceptions import NotFound
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import AllowAny, BasePermission, IsAuthenticated
from rest_framework.views import APIView

from core.permissions import AdminModelPermissions, CustomActionPermission
from core.responses import api_response
from core.services import CacheService
from domains.business.models import BusinessProfile
from domains.catalog.models import Brand, Category, Product
from domains.catalog.services import CategoryService, ProductService
from domains.users.auth import AdminJWTAuthentication
from domains.vendor.auth import VendorJWTAuthentication

from .contracts import CONTRACTS_FILE
from .cache import HOME_CACHE_KEY, landing_page_cache_key, page_cache_key
from .models import LandingPage, Page, SEORecord
from .serializers import (
    LandingPageContentSerializer,
    LandingPageDetailSerializer,
    LandingPageSerializer,
    PageContentSerializer,
    PageDetailSerializer,
    PageSerializer,
    SEORecordSerializer,
)
from .services import (
    LandingPageContentResolver,
    LandingPageService,
    PageService,
    SEOService,
)


def paginate_content(queryset, request, view, serializer=None):
    """Page a queryset and serialize the page inside the standard envelope."""
    paginator = PageNumberPagination()
    page = paginator.paginate_queryset(queryset, request, view=view)
    data = serializer(page, many=True).data if serializer else page
    return paginator.get_paginated_response(data).data


class AdminContentAPIView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [AdminModelPermissions]

    @staticmethod
    def paginated(queryset, request, view, serializer=None):
        return paginate_content(queryset, request, view, serializer)


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


class CategorySEOPermission(ResourceSEOPermission):
    resource_permissions = {
        "GET": ("catalog.view_category",),
        "PUT": ("catalog.change_category",),
        "DELETE": ("catalog.change_category",),
    }


class BrandSEOPermission(ResourceSEOPermission):
    resource_permissions = {
        "GET": ("catalog.view_brand",),
        "PUT": ("catalog.change_brand",),
        "DELETE": ("catalog.change_brand",),
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


class AdminPageList(AdminContentAPIView):
    model = Page
    ordering_fields = {"id", "title", "slug", "status", "created_at", "updated_at"}

    def get(self, request):
        ordering = request.query_params.get("ordering", "-updated_at")
        field = ordering.removeprefix("-")
        if field not in self.ordering_fields:
            ordering = "-updated_at"
        queryset = Page.objects.all().order_by(ordering)
        data = self.paginated(queryset, request, self, PageSerializer)
        return api_response(data=data)

    def post(self, request):
        serializer = PageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        page = serializer.save()
        return api_response(data=PageSerializer(page).data, status_code=201)


class AdminPageDetail(AdminContentAPIView):
    model = Page

    @staticmethod
    def get_page(page_id):
        try:
            return Page.objects.get(id=page_id)
        except Page.DoesNotExist as exc:
            raise NotFound(_("Page not found.")) from exc

    def get(self, request, page_id):
        page = self.get_page(page_id)
        return api_response(data=PageDetailSerializer(page).data)

    def patch(self, request, page_id):
        page = self.get_page(page_id)
        serializer = PageSerializer(page, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        page = serializer.save()
        return api_response(data=PageDetailSerializer(page).data)

    def delete(self, request, page_id):
        page = self.get_page(page_id)
        PageService().delete_page(page)
        return api_response(data=None)


class AdminPagePublish(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [CustomActionPermission]
    required_permissions = ("content.change_page",)

    def post(self, request, page_id):
        try:
            page = Page.objects.get(id=page_id)
        except Page.DoesNotExist as exc:
            raise NotFound(_("Page not found.")) from exc
        PageService().publish_page(page)
        return api_response(data=PageDetailSerializer(page).data)


class ResourceSEOView(APIView):
    """Shared SEO get/put/delete contract.

    Subclasses fix authentication and how the resource is resolved:
    the admin subclasses look resources up globally, while a subclass may
    override ``resolve_resource`` to enforce its own scoping before the
    record is touched.
    """

    authentication_classes = [AdminJWTAuthentication]
    resource_type = ""

    @staticmethod
    def get_resource(resource_id):
        raise NotImplementedError

    def resolve_resource(self, request, resource_id):
        return self.get_resource(resource_id)

    @classmethod
    def get_record(cls, resource_id):
        return SEORecord.objects.filter(
            resource_type=cls.resource_type,
            resource_id=resource_id,
        ).first()

    def get(self, request, resource_id):
        self.resolve_resource(request, resource_id)
        record = self.get_record(resource_id)
        return api_response(data=SEORecordSerializer(record).data if record else None)

    def put(self, request, resource_id):
        self.resolve_resource(request, resource_id)
        record = self.get_record(resource_id)
        serializer = SEORecordSerializer(record, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        record = serializer.save(
            resource_type=self.resource_type,
            resource_id=resource_id,
        )
        return api_response(data=SEORecordSerializer(record).data)

    def delete(self, request, resource_id):
        self.resolve_resource(request, resource_id)
        record = self.get_record(resource_id)
        if record:
            record.delete()
        return api_response(data=None)


class AdminLandingPageSEO(ResourceSEOView):
    permission_classes = [LandingPageSEOPermission]
    resource_type = "landing_page"

    @staticmethod
    def get_resource(resource_id):
        try:
            return LandingPage.objects.get(id=resource_id)
        except LandingPage.DoesNotExist as exc:
            raise NotFound(_("Landing page not found.")) from exc


class AdminProductSEO(ResourceSEOView):
    permission_classes = [ProductSEOPermission]
    resource_type = "product"

    @staticmethod
    def get_resource(resource_id):
        try:
            return Product.objects.get(id=resource_id)
        except Product.DoesNotExist as exc:
            raise NotFound(_("Product not found.")) from exc


class AdminCategorySEO(ResourceSEOView):
    permission_classes = [CategorySEOPermission]
    resource_type = "category"

    @staticmethod
    def get_resource(resource_id):
        try:
            return Category.objects.get(id=resource_id)
        except Category.DoesNotExist as exc:
            raise NotFound(_("Category not found.")) from exc


class AdminBrandSEO(ResourceSEOView):
    permission_classes = [BrandSEOPermission]
    resource_type = "brand"

    @staticmethod
    def get_resource(resource_id):
        try:
            return Brand.objects.get(id=resource_id)
        except Brand.DoesNotExist as exc:
            raise NotFound(_("Brand not found.")) from exc


class PublicResourceSEO(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request, resource_type, slug):
        payload = SEOService.get_public_resource(resource_type, slug)
        if payload is None:
            raise NotFound(_("SEO resource not found."))
        return api_response(data=payload)


class PageSEOPermission(ResourceSEOPermission):
    resource_permissions = {
        "GET": ("content.view_page",),
        "PUT": ("content.change_page",),
        "PATCH": ("content.change_page",),
        "DELETE": ("content.change_page",),
    }


class AdminPageSEO(ResourceSEOView):
    permission_classes = [PageSEOPermission]
    resource_type = "page"

    @staticmethod
    def get_resource(resource_id):
        try:
            return Page.objects.get(id=resource_id)
        except Page.DoesNotExist as exc:
            raise NotFound(_("Page not found.")) from exc


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

    def get(self, request, slug):
        key = landing_page_cache_key(slug)
        cached = CacheService().get_public(key)
        if cached is not None:
            return api_response(data=cached)
        response = super().get(request, slug)
        page = LandingPage.objects.only("cache_ttl").get(
            slug=slug, business__isnull=True
        )
        if page.cache_ttl > 0:
            CacheService().put_public(key, response.data["data"], ttl=page.cache_ttl)
        return response


class PublicHomePage(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        cached = CacheService().get_public(HOME_CACHE_KEY)
        if cached is not None:
            return api_response(data=cached)
        try:
            page = PageService().get_home_page()
        except Page.DoesNotExist as exc:
            raise NotFound(_("Page not found.")) from exc

        if page.status != Page.Status.PUBLISHED:
            raise NotFound(_("Page not found."))

        page.selected_content = LandingPageContentResolver().resolve(page.published_content)
        data = PageContentSerializer(page).data
        if page.cache_ttl > 0:
            CacheService().put_public(HOME_CACHE_KEY, data, ttl=page.cache_ttl)
        return api_response(data=data)


class PageBySlug(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    allowed_statuses = ()
    content_field = ""

    def get(self, request, slug):
        try:
            page = PageService().get_by_slug(slug)
        except Page.DoesNotExist as exc:
            raise NotFound(_("Page not found.")) from exc

        if page.status not in self.allowed_statuses:
            raise NotFound(_("Page not found."))

        page.selected_content = LandingPageContentResolver().resolve(
            getattr(page, self.content_field)
        )
        return api_response(data=PageContentSerializer(page).data)


class PagePreview(PageBySlug):
    allowed_statuses = (Page.Status.DRAFT, Page.Status.PUBLISHED)
    content_field = "draft_content"


class PublicPage(PageBySlug):
    allowed_statuses = (Page.Status.PUBLISHED,)
    content_field = "published_content"

    def get(self, request, slug):
        key = page_cache_key(slug)
        cached = CacheService().get_public(key)
        if cached is not None:
            return api_response(data=cached)
        response = super().get(request, slug)
        page = Page.objects.only("cache_ttl").get(slug=slug, business__isnull=True)
        if page.cache_ttl > 0:
            CacheService().put_public(key, response.data["data"], ttl=page.cache_ttl)
        return response


def read_component_contracts():
    """Return ``(payload, None)`` or ``(None, error_response)`` for the
    synced contracts file, shared by the admin and vendor contract views."""
    if not CONTRACTS_FILE.exists():
        return None, api_response(
            success=False,
            message="content contracts file not found",
            errors={"detail": "Run sync_content_contracts to generate the file."},
            status_code=404,
        )
    try:
        return json.loads(CONTRACTS_FILE.read_text(encoding="utf-8")), None
    except json.JSONDecodeError:
        return None, api_response(
            success=False,
            message="content contracts file is invalid",
            errors={"detail": "The contracts file could not be parsed."},
            status_code=500,
        )


class AdminContentComponentContractList(AdminContentAPIView):
    model = LandingPage

    def get(self, request):
        data, error = read_component_contracts()
        return error if error is not None else api_response(data=data)


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


class AdminProductOptionList(AdminContentOptionList):
    def get_queryset(self, search):
        return ProductService().content_selector_options(search)

    serialize_option = staticmethod(serialize_product_option)


class AdminCategoryOptionList(AdminContentOptionList):
    def get_queryset(self, search):
        return CategoryService().content_selector_options(search)

    serialize_option = staticmethod(serialize_category_option)


# ─────────────────────── Vendor content management ───────────────────────
# Vendor-authenticated authoring scoped to the caller's business. Rows with
# `business IS NULL` are the shared/admin storefront content, so a vendor
# never sees or touches them through these endpoints, and public slug routes
# never serve business rows.


class VendorContentAPIView(APIView):
    authentication_classes = [VendorJWTAuthentication]
    permission_classes = [IsAuthenticated]

    model = None
    serializer_class = None
    detail_serializer = None
    service_class = None
    not_found_message = ""
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
            raise NotFound(_(self.not_found_message))
        return business, instance


class VendorContentList(VendorContentAPIView):
    def get(self, request):
        business = self._get_business(request)
        ordering = request.query_params.get("ordering", "-updated_at")
        field = ordering.removeprefix("-")
        if field not in self.ordering_fields:
            ordering = "-updated_at"
        queryset = self.model.objects.filter(business=business).order_by(ordering)
        data = paginate_content(queryset, request, self, self.serializer_class)
        return api_response(data=data)

    def post(self, request):
        business = self._get_business(request)
        serializer = self.serializer_class(
            data=request.data, context={"business": business}
        )
        serializer.is_valid(raise_exception=True)
        instance = serializer.save(business=business)
        return api_response(
            data=self.detail_serializer(instance).data, status_code=201
        )


class VendorContentDetail(VendorContentAPIView):
    def get(self, request, resource_id):
        _, instance = self.get_object(request, resource_id)
        return api_response(data=self.detail_serializer(instance).data)

    def patch(self, request, resource_id):
        business, instance = self.get_object(request, resource_id)
        serializer = self.serializer_class(
            instance, data=request.data, partial=True, context={"business": business}
        )
        serializer.is_valid(raise_exception=True)
        instance = serializer.save()
        return api_response(data=self.detail_serializer(instance).data)

    def delete(self, request, resource_id):
        _, instance = self.get_object(request, resource_id)
        self.service_class().delete_page(instance)
        return api_response(data=None)


class VendorContentPublish(VendorContentAPIView):
    def post(self, request, resource_id):
        _, instance = self.get_object(request, resource_id)
        self.service_class().publish_page(instance)
        return api_response(data=self.detail_serializer(instance).data)


class VendorContentPreview(VendorContentAPIView):
    content_serializer = None
    allowed_statuses = ()

    def get(self, request, resource_id):
        _, instance = self.get_object(request, resource_id)
        if instance.status not in self.allowed_statuses:
            raise NotFound(_(self.not_found_message))
        instance.selected_content = LandingPageContentResolver().resolve(
            instance.draft_content
        )
        return api_response(data=self.content_serializer(instance).data)


class VendorResourceSEOView(ResourceSEOView):
    authentication_classes = [VendorJWTAuthentication]
    permission_classes = [IsAuthenticated]

    model = None
    not_found_message = ""

    def resolve_resource(self, request, resource_id):
        business = VendorContentAPIView._get_business(request)
        resource = (
            self.model.objects.filter(id=resource_id, business=business).first()
        )
        if resource is None:
            raise NotFound(_(self.not_found_message))
        return resource


class VendorContentOptionList(VendorContentAPIView):
    def serialize_option(self, item):
        raise NotImplementedError

    def get_queryset(self, business, search):
        raise NotImplementedError

    def get(self, request):
        business = self._get_business(request)
        search = request.query_params.get("search", "").strip()
        queryset = self.get_queryset(business, search)
        data = paginate_content(queryset, request, self)
        data["results"] = [self.serialize_option(item) for item in data["results"]]
        return api_response(data=data)


class VendorComponentContractList(VendorContentAPIView):
    """The editor-facing contract vocabulary.

    Vendors author against the same synced contracts file the admin editor
    uses, so ``contract_version`` and component definitions always match what
    ``validate_draft_content`` accepts. The panel-local registry is only the
    rendering half.
    """

    def get(self, request):
        data, error = read_component_contracts()
        return error if error is not None else api_response(data=data)


class VendorLandingPageList(VendorContentList):
    model = LandingPage
    serializer_class = LandingPageSerializer
    detail_serializer = LandingPageDetailSerializer


class VendorLandingPageDetail(VendorContentDetail):
    model = LandingPage
    serializer_class = LandingPageSerializer
    detail_serializer = LandingPageDetailSerializer
    service_class = LandingPageService
    not_found_message = "Landing page not found."


class VendorLandingPagePublish(VendorContentPublish):
    model = LandingPage
    detail_serializer = LandingPageDetailSerializer
    service_class = LandingPageService
    not_found_message = "Landing page not found."


class VendorLandingPagePreview(VendorContentPreview):
    model = LandingPage
    content_serializer = LandingPageContentSerializer
    allowed_statuses = (LandingPage.Status.DRAFT, LandingPage.Status.PUBLISHED)
    not_found_message = "Landing page not found."


class VendorLandingPageSEO(VendorResourceSEOView):
    resource_type = "landing_page"
    model = LandingPage
    not_found_message = "Landing page not found."


class VendorPageList(VendorContentList):
    model = Page
    serializer_class = PageSerializer
    detail_serializer = PageDetailSerializer


class VendorPageDetail(VendorContentDetail):
    model = Page
    serializer_class = PageSerializer
    detail_serializer = PageDetailSerializer
    service_class = PageService
    not_found_message = "Page not found."


class VendorPagePublish(VendorContentPublish):
    model = Page
    detail_serializer = PageDetailSerializer
    service_class = PageService
    not_found_message = "Page not found."


class VendorPagePreview(VendorContentPreview):
    model = Page
    content_serializer = PageContentSerializer
    allowed_statuses = (Page.Status.DRAFT, Page.Status.PUBLISHED)
    not_found_message = "Page not found."


class VendorPageSEO(VendorResourceSEOView):
    resource_type = "page"
    model = Page
    not_found_message = "Page not found."


class VendorProductOptionList(VendorContentOptionList):
    serialize_option = staticmethod(serialize_product_option)

    def get_queryset(self, business, search):
        # Same scope as every other vendor product route: the products that
        # sit in the business's registered categories.
        category_ids = business.categories.values_list("category_id", flat=True)
        return (
            ProductService()
            .content_selector_options(search)
            .filter(categories__id__in=category_ids)
            .distinct()
        )


class VendorCategoryOptionList(VendorContentOptionList):
    serialize_option = staticmethod(serialize_category_option)

    def get_queryset(self, business, search):
        category_ids = business.categories.values_list("category_id", flat=True)
        return CategoryService().content_selector_options(search).filter(
            id__in=category_ids
        )
