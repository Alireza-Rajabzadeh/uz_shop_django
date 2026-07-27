from django.utils.translation import gettext as _
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.pagination import PageNumberPagination
from core.responses import api_response
from .permissions import CatalogModelPermissions, CustomActionPermission, MethodPermission
from .serializers import (
    CategorySerializer, CategoryListSerializer, CategoryDetailSerializer,
    CategoryDetailRelationSerializer, ProductSerializer, ProductListSerializer,
    ProductDetailsSerializer, ProductStatusSerializer, CategoryStatusSerializer,
    ProductVariantSerializer, CategoryNameSuggestionQuerySerializer,
    CategoryNameSuggestionSerializer, CategoryDetailNameSuggestionQuerySerializer,
    CategoryDetailNameSuggestionSerializer,
    CategoryDetailAssignmentWriteSerializer, CategoryDetailAssignmentOptionSerializer,
    ProductCategorySelectionSerializer, ProductCompleteCreateSerializer,
)
from domains.catalog.models import (
    Category,
    CategoryDetail as CategoryDetailModel,
    Product,
    ProductDetails,
    ProductVariants,
)
from domains.catalog.services import CategoryService, DetailService, ProductService


category_service = CategoryService()
detail_service = DetailService()
product_service = ProductService()


# ─────────────────────── Categories ───────────────────────

def save_category(serializer, instance=None):
    try:
        if instance:
            return category_service.update_category(instance, **serializer.validated_data)
        return category_service.create_category(**serializer.validated_data)
    except CategoryService.ValidationError as exc:
        raise ValidationError(exc.errors) from exc

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
        categories = category_service.search_categories(
            ordering=request.query_params.get("ordering"),
            **filters,
        )
        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(categories, request, view=self)
        serializer = CategoryListSerializer(page, many=True)
        return api_response(True, "", paginator.get_paginated_response(serializer.data).data)

    def post(self, request):
        serializer = CategorySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        category = save_category(serializer)
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
        category = save_category(serializer, category)
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


class CategoryNameSuggestions(APIView):
    permission_classes = [CustomActionPermission]
    required_permission = "catalog.view_category"

    def get(self, request):
        query = CategoryNameSuggestionQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        exact_duplicate, matches = category_service.find_name_matches(
            query.validated_data["name"],
            query.validated_data.get("exclude_id"),
        )
        suggestions = [
            {
                "id": category.id,
                "name": category.name,
                "parent": category.parent_id,
                "parent_name": category.parent.name if category.parent else None,
                "status": category.status_id,
                "status_name": category.status.name,
                "logo": category.logo,
                "similarity": score,
                "exact": exact,
            }
            for exact, score, category in matches
        ]
        serializer = CategoryNameSuggestionSerializer(suggestions, many=True)
        return api_response(
            True,
            "",
            {"exact_duplicate": exact_duplicate, "suggestions": serializer.data},
        )


class CategoryStatusList(APIView):
    permission_classes = [CustomActionPermission]
    required_permission = "catalog.view_category"

    def get(self, request):
        statuses = category_service.list_statuses()
        serializer = CategoryStatusSerializer(statuses, many=True)
        return api_response(True, "", serializer.data)


class CategoryAssignDetails(APIView):
    permission_classes = [CustomActionPermission]
    required_permission = "catalog.assign_details_to_category"

    def get_category(self, id):
        try:
            return category_service.get_category(id)
        except Exception:
            raise NotFound(_("Category not found."))

    def get(self, request, id):
        category = self.get_category(id)
        assigned_details = list(category_service.get_assigned_details(category))
        assigned_ids = {detail.id for detail in assigned_details}
        used_ids = category_service.get_used_detail_ids(category)

        filters = {}
        name = request.query_params.get("name")
        detail_type = request.query_params.get("type")
        if name:
            filters["name__icontains"] = name
        if detail_type:
            filters["type"] = detail_type
        details = detail_service.search_category_details(ordering="name", **filters)
        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(details, request, view=self)
        context = {"assigned_ids": assigned_ids, "used_ids": used_ids}
        page_data = CategoryDetailAssignmentOptionSerializer(
            page, many=True, context=context
        ).data
        assignment_data = CategoryDetailAssignmentOptionSerializer(
            assigned_details, many=True, context=context
        ).data
        return api_response(True, "", {
            "category": {"id": category.id, "name": category.name},
            "assignments": assignment_data,
            "details": paginator.get_paginated_response(page_data).data,
        })

    def post(self, request, id):
        category = self.get_category(id)
        serializer = CategoryDetailAssignmentWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            assigned_details = category_service.assign_multiple_detail_to_category(
                category, serializer.validated_data["details"]
            )
        except CategoryService.ValidationError as exc:
            raise ValidationError(exc.errors) from exc

        assigned_details = list(assigned_details)
        assigned_ids = {detail.id for detail in assigned_details}
        used_ids = category_service.get_used_detail_ids(category)
        result = CategoryDetailAssignmentOptionSerializer(
            assigned_details,
            many=True,
            context={"assigned_ids": assigned_ids, "used_ids": used_ids},
        ).data
        return api_response(
            True,
            _("Category details updated."),
            {"assignments": result},
        )


# ─────────────────────── Category Details ───────────────────────

def save_category_detail(serializer, instance=None):
    try:
        if instance:
            return detail_service.update_category_detail(instance, **serializer.validated_data)
        return detail_service.create_category_detail(**serializer.validated_data)
    except DetailService.ValidationError as exc:
        raise ValidationError(exc.errors) from exc

class CategoryDetailListCreate(APIView):
    model = CategoryDetailModel
    permission_classes = [CatalogModelPermissions]

    def get(self, request):
        filters = {}
        name = request.query_params.get("name")
        detail_type = request.query_params.get("type")
        if name:
            filters["name__icontains"] = name
        if detail_type:
            filters["type"] = detail_type
        details = detail_service.search_category_details(
            ordering=request.query_params.get("ordering"),
            **filters,
        )
        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(details, request, view=self)
        serializer = CategoryDetailSerializer(page, many=True)
        return api_response(True, "", paginator.get_paginated_response(serializer.data).data)

    def post(self, request):
        serializer = CategoryDetailSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        detail = save_category_detail(serializer)
        result = CategoryDetailSerializer(detail).data
        return api_response(True, _("Category detail created."), result, status_code=201)


class CategoryDetailDetail(APIView):
    model = CategoryDetailModel
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
        detail = save_category_detail(serializer, detail)
        result = CategoryDetailSerializer(detail).data
        return api_response(True, _("Category detail updated."), result)

    def delete(self, request, id):
        detail = self.get_object(id)
        detail_service.delete_category_detail(detail)
        return api_response(True, _("Category detail deleted."), None)


class CategoryDetailNameSuggestions(APIView):
    permission_classes = [CustomActionPermission]
    required_permission = "catalog.view_categorydetail"

    def get(self, request):
        query = CategoryDetailNameSuggestionQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        exact_duplicate, matches = detail_service.find_name_matches(
            query.validated_data["name"],
            query.validated_data.get("exclude_id"),
        )
        suggestions = [
            {
                "id": detail.id,
                "name": detail.name,
                "type": detail.type,
                "required": detail.required,
                "options": detail.options,
                "filterable": detail.filterable,
                "similarity": score,
                "exact": exact,
            }
            for exact, score, detail in matches
        ]
        serializer = CategoryDetailNameSuggestionSerializer(suggestions, many=True)
        return api_response(
            True,
            "",
            {"exact_duplicate": exact_duplicate, "suggestions": serializer.data},
        )


# ─────────────────────── Products ───────────────────────

class ProductFormOptions(APIView):
    permission_classes = [CustomActionPermission]
    required_permission = "catalog.add_product"

    def get(self, request):
        categories, statuses = product_service.get_form_options()
        return api_response(True, "", {
            "categories": categories,
            "statuses": ProductStatusSerializer(statuses, many=True).data,
        })


class ProductDetailDefinitions(APIView):
    permission_classes = [CustomActionPermission]
    required_permission = "catalog.add_product"

    def get(self, request):
        raw_ids = request.query_params.getlist("category_ids")
        category_ids = [
            item
            for raw_id in raw_ids
            for item in raw_id.split(",")
            if item
        ]
        serializer = ProductCategorySelectionSerializer(
            data={"category_ids": category_ids}
        )
        serializer.is_valid(raise_exception=True)
        categories = serializer.validated_data["category_ids"]
        details, category_ids_by_detail = product_service.get_detail_definitions(categories)
        return api_response(True, "", [
            {
                "id": detail.id,
                "name": detail.name,
                "type": detail.type,
                "required": detail.required,
                "filterable": detail.filterable,
                "options": [
                    option.strip()
                    for option in detail.options.split(",")
                    if option.strip()
                ],
                "category_ids": category_ids_by_detail.get(detail.id, []),
            }
            for detail in details
        ])


class ProductCompleteCreate(APIView):
    permission_classes = [CustomActionPermission]
    required_permission = "catalog.add_product"

    def post(self, request):
        serializer = ProductCompleteCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            product = product_service.create_complete_product(**serializer.validated_data)
        except ProductService.ValidationError as exc:
            raise ValidationError(exc.errors) from exc
        return api_response(
            True,
            _("Product created."),
            ProductSerializer(product).data,
            status_code=201,
        )

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
        products = product_service.search_products(
            ordering=request.query_params.get("ordering"),
            **filters,
        )
        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(products, request, view=self)
        serializer = ProductListSerializer(page, many=True)
        return api_response(True, "", paginator.get_paginated_response(serializer.data).data)

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
