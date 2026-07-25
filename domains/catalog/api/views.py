from django.utils.translation import gettext as _
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import NotFound, PermissionDenied
from core.responses import api_response
from .permissions import CatalogModelPermissions, CustomActionPermission, MethodPermission
from .serializers import (
    CategorySerializer, CategoryListSerializer, CategoryDetailSerializer,
    CategoryDetailRelationSerializer, ProductSerializer, ProductListSerializer,
    ProductDetailsSerializer, ProductStatusSerializer, CategoryStatusSerializer,
    ProductVariantSerializer,
)
from domains.catalog.models import Category, CategoryDetail, Product, ProductDetails, ProductVariants
from domains.catalog.services import CategoryService, DetailService, ProductService


category_service = CategoryService()
detail_service = DetailService()
product_service = ProductService()


# ─────────────────────── Categories ───────────────────────

class CategoryListCreate(APIView):
    model = Category
    permission_classes = [CatalogModelPermissions]

    def get(self, request):
        filters = {}
        name = request.query_params.get("name")
        status_id = request.query_params.get("status_id")
        if name:
            filters["name__icontains"] = name
        if status_id:
            filters["status_id"] = status_id
        categories = category_service.search_categories(**filters)
        serializer = CategoryListSerializer(categories, many=True)
        return api_response(True, "", serializer.data)

    def post(self, request):
        serializer = CategorySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        category = category_service.create_category(**serializer.validated_data)
        result = CategorySerializer(category).data
        return api_response(True, _("Category created."), result, status_code=201)


class CategoryDetail(APIView):
    model = Category
    permission_classes = [CatalogModelPermissions]

    def get_object(self, id):
        try:
            return category_service.get_category(id)
        except Exception:
            raise NotFound(_("Category not found."))

    def get(self, request, id):
        category = self.get_object(id)
        serializer = CategorySerializer(category)
        return api_response(True, "", serializer.data)

    def patch(self, request, id):
        category = self.get_object(id)
        serializer = CategorySerializer(category, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        category_service.update_category(category, **serializer.validated_data)
        result = CategorySerializer(category).data
        return api_response(True, _("Category updated."), result)

    def delete(self, request, id):
        category = self.get_object(id)
        category_service.delete_category(category)
        return api_response(True, _("Category deleted."), None)


class CategoryTree(APIView):
    model = Category
    permission_classes = [CatalogModelPermissions]

    def get(self, request):
        tree = category_service.get_tree()
        serializer = CategorySerializer(tree, many=True)
        return api_response(True, "", serializer.data)


class CategoryAssignDetails(APIView):
    permission_classes = [CustomActionPermission]
    required_permission = "catalog.assign_details_to_category"

    def post(self, request, id):
        try:
            category = category_service.get_category(id)
        except Exception:
            raise NotFound(_("Category not found."))

        detail_data_list = request.data.get("details", [])
        category_service.assign_multiple_detail_to_category(category, detail_data_list)
        return api_response(True, _("Details assigned to category."), None)


# ─────────────────────── Category Details ───────────────────────

class CategoryDetailListCreate(APIView):
    model = CategoryDetail
    permission_classes = [CatalogModelPermissions]

    def get(self, request):
        filters = {}
        name = request.query_params.get("name")
        detail_type = request.query_params.get("type")
        if name:
            filters["name__icontains"] = name
        if detail_type:
            filters["type"] = detail_type
        details = detail_service.search_category_details(**filters)
        serializer = CategoryDetailSerializer(details, many=True)
        return api_response(True, "", serializer.data)

    def post(self, request):
        serializer = CategoryDetailSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        detail = detail_service.create_category_detail(**serializer.validated_data)
        result = CategoryDetailSerializer(detail).data
        return api_response(True, _("Category detail created."), result, status_code=201)


class CategoryDetailDetail(APIView):
    model = CategoryDetail
    permission_classes = [CatalogModelPermissions]

    def get_object(self, id):
        try:
            return detail_service.get_category_detail(id)
        except Exception:
            raise NotFound(_("Category detail not found."))

    def get(self, request, id):
        detail = self.get_object(id)
        serializer = CategoryDetailSerializer(detail)
        return api_response(True, "", serializer.data)

    def patch(self, request, id):
        detail = self.get_object(id)
        serializer = CategoryDetailSerializer(detail, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        detail_service.update_category_detail(detail, **serializer.validated_data)
        result = CategoryDetailSerializer(detail).data
        return api_response(True, _("Category detail updated."), result)

    def delete(self, request, id):
        detail = self.get_object(id)
        detail_service.delete_category_detail(detail)
        return api_response(True, _("Category detail deleted."), None)


# ─────────────────────── Products ───────────────────────

class ProductListCreate(APIView):
    model = Product
    permission_classes = [CatalogModelPermissions]

    def get(self, request):
        filters = {}
        name = request.query_params.get("name")
        category_id = request.query_params.get("category_id")
        status_id = request.query_params.get("status_id")
        if name:
            filters["name__icontains"] = name
        if category_id:
            filters["category_id"] = category_id
        if status_id:
            filters["status_id"] = status_id
        products = product_service.search_products(**filters)
        serializer = ProductListSerializer(products, many=True)
        return api_response(True, "", serializer.data)

    def post(self, request):
        serializer = ProductSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        product = product_service.create_product(**serializer.validated_data)
        result = ProductSerializer(product).data
        return api_response(True, _("Product created."), result, status_code=201)


class ProductDetail(APIView):
    model = Product
    permission_classes = [CatalogModelPermissions]

    def get_object(self, id):
        try:
            return product_service.get_product(id)
        except Exception:
            raise NotFound(_("Product not found."))

    def get(self, request, id):
        product = self.get_object(id)
        serializer = ProductSerializer(product)
        return api_response(True, "", serializer.data)

    def patch(self, request, id):
        product = self.get_object(id)
        serializer = ProductSerializer(product, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        product_service.update_product(product, **serializer.validated_data)
        result = ProductSerializer(product).data
        return api_response(True, _("Product updated."), result)

    def delete(self, request, id):
        product = self.get_object(id)
        product_service.delete_product(product)
        return api_response(True, _("Product deleted."), None)


# ─────────────────────── Product Details ───────────────────────

class ProductDetailListCreate(APIView):
    permission_classes = [MethodPermission]
    method_permissions = {
        "GET": "catalog.view_productdetails",
        "POST": "catalog.add_detail_to_product",
    }

    def get(self, request, product_id):
        try:
            product = product_service.get_product(product_id)
        except Exception:
            raise NotFound(_("Product not found."))
        details = product_service.list_product_details(product)
        serializer = ProductDetailsSerializer(details, many=True)
        return api_response(True, "", serializer.data)

    def post(self, request, product_id):
        try:
            product = product_service.get_product(product_id)
        except Exception:
            raise NotFound(_("Product not found."))
        details_data = request.data if isinstance(request.data, list) else [request.data]
        instances = product_service.add_detail_to_product(product, details_data)
        serializer = ProductDetailsSerializer(instances, many=True)
        return api_response(True, _("Product details added."), serializer.data, status_code=201)


# ─────────────────────── Product Variants ───────────────────────

class ProductVariantListCreate(APIView):
    permission_classes = [MethodPermission]
    method_permissions = {
        "GET": "catalog.view_productvariants",
        "POST": "catalog.add_variant_to_product",
    }

    def get(self, request, product_id):
        try:
            product = product_service.get_product(product_id)
        except Exception:
            raise NotFound(_("Product not found."))
        variants = product_service.list_product_variants(product)
        serializer = ProductVariantSerializer(variants, many=True)
        return api_response(True, "", serializer.data)

    def post(self, request, product_id):
        try:
            product = product_service.get_product(product_id)
        except Exception:
            raise NotFound(_("Product not found."))
        serializer = ProductVariantSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        variant = product_service.add_variant_to_product(product, **serializer.validated_data)
        result = ProductVariantSerializer(variant).data
        return api_response(True, _("Variant added."), result, status_code=201)


# ─────────────────────── Variants (standalone) ───────────────────────

class VariantDetail(APIView):
    model = ProductVariants
    permission_classes = [CatalogModelPermissions]

    def get_object(self, id):
        try:
            return product_service.get_variant(id)
        except Exception:
            raise NotFound(_("Variant not found."))

    def get(self, request, id):
        variant = self.get_object(id)
        serializer = ProductVariantSerializer(variant)
        return api_response(True, "", serializer.data)

    def patch(self, request, id):
        variant = self.get_object(id)
        serializer = ProductVariantSerializer(variant, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        product_service.update_variant(variant, **serializer.validated_data)
        result = ProductVariantSerializer(variant).data
        return api_response(True, _("Variant updated."), result)

    def delete(self, request, id):
        variant = self.get_object(id)
        product_service.delete_variant(variant)
        return api_response(True, _("Variant deleted."), None)


class VariantList(APIView):
    model = ProductVariants
    permission_classes = [CatalogModelPermissions]

    def get(self, request):
        filters = {}
        product_id = request.query_params.get("product_id")
        sku = request.query_params.get("sku")
        if product_id:
            filters["product_id"] = product_id
        if sku:
            filters["sku__icontains"] = sku
        variants = product_service.search_variants(**filters)
        serializer = ProductVariantSerializer(variants, many=True)
        return api_response(True, "", serializer.data)
