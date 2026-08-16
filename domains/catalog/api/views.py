from django.utils.translation import gettext as _
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.pagination import PageNumberPagination
from core.permissions import AdminModelPermissions
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
    ProductBasicUpdateSerializer, ProductVariantWriteSerializer,
    ProductListQuerySerializer, ProductDetailReadSerializer,
    ProductFileReadSerializer, ProductFileUpdateSerializer,
    ProductFileReorderSerializer, ProductFileWriteSerializer,
    CategoryVariantAttributeAssignmentWriteSerializer,
    VariantAttributeSerializer, VariantAttributeWriteSerializer,
    VariantOptionSerializer, VariantOptionWriteSerializer,
    BrandSerializer, BrandWriteSerializer, BrandNameSuggestionQuerySerializer,
    BrandNameSuggestionSerializer,
)
from domains.catalog.models import (
    Brand,
    Category,
    CategoryDetail as CategoryDetailModel,
    Product,
    ProductDetails,
    ProductFile,
    ProductVariants,
    VariantAttribute,
    VariantOption,
)
from domains.catalog.services import (
    BrandService, CategoryService, DetailService, ProductFileService, ProductService,
    VariantAttributeService,
)
from domains.inventory.services import InventoryService
from domains.users.auth import AdminJWTAuthentication


category_service = CategoryService()
brand_service = BrandService()
detail_service = DetailService()
product_service = ProductService()
product_file_service = ProductFileService()
variant_attribute_service = VariantAttributeService()
inventory_service = InventoryService()


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
            icon_state=request.query_params.get("icon_state"),
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
            parent=query.validated_data.get("parent_id"),
            exclude_id=query.validated_data.get("exclude_id"),
        )
        suggestions = [
            {
                "id": category.id,
                "name": category.name,
                "fa_name": category.fa_name,
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


class CategoryAssignVariantAttributes(APIView):
    permission_classes = [CustomActionPermission]
    required_permission = "catalog.assign_variant_attributes_to_category"

    def get_category(self, id):
        try:
            return category_service.get_category(id)
        except Exception:
            raise NotFound(_("Category not found."))

    def get(self, request, id):
        category = self.get_category(id)
        assigned = list(category_service.get_assigned_variant_attributes(category))
        assigned_ids = {attribute.id for attribute in assigned}
        candidates = list(variant_attribute_service.list_attributes(
            request.query_params.get("search")
        ))
        candidates.sort(key=lambda attribute: (attribute.id not in assigned_ids, attribute.name.casefold()))
        return api_response(True, "", {
            "category": {"id": category.id, "name": category.name},
            "assignments": VariantAttributeSerializer(assigned, many=True).data,
            "attributes": [
                {**VariantAttributeSerializer(attribute).data, "assigned": attribute.id in assigned_ids}
                for attribute in candidates
            ],
        })

    def post(self, request, id):
        category = self.get_category(id)
        serializer = CategoryVariantAttributeAssignmentWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        assigned = category_service.assign_variant_attributes(
            category, serializer.validated_data["attributes"]
        )
        return api_response(True, _("Category variant attributes updated."), {
            "assignments": VariantAttributeSerializer(assigned, many=True).data,
        })


# ─────────────────────── Brands ───────────────────────

def save_brand(serializer, instance=None):
    try:
        if instance:
            return brand_service.update_brand(instance, **serializer.validated_data)
        return brand_service.create_brand(**serializer.validated_data)
    except BrandService.ValidationError as exc:
        raise ValidationError(exc.errors) from exc


class BrandListCreate(APIView):
    model = Brand
    permission_classes = [CatalogModelPermissions]

    def get(self, request):
        filters = {}
        name = request.query_params.get("name")
        if name:
            filters["name__icontains"] = name
        brands = brand_service.search_brands(
            ordering=request.query_params.get("ordering"),
            **filters,
        )
        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(brands, request, view=self)
        serializer = BrandSerializer(page, many=True)
        return api_response(True, "", paginator.get_paginated_response(serializer.data).data)

    def post(self, request):
        serializer = BrandWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        brand = save_brand(serializer)
        return api_response(True, _("Brand created."), BrandSerializer(brand).data, status_code=201)


class BrandDetail(APIView):
    model = Brand
    permission_classes = [CatalogModelPermissions]

    def get_object(self, id):
        try:
            return brand_service.get_brand(id)
        except Exception:
            raise NotFound(_("Brand not found."))

    def get(self, request, id):
        return api_response(True, "", BrandSerializer(self.get_object(id)).data)

    def patch(self, request, id):
        brand = self.get_object(id)
        serializer = BrandWriteSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        brand = save_brand(serializer, brand)
        return api_response(True, _("Brand updated."), BrandSerializer(brand).data)

    def delete(self, request, id):
        try:
            brand_service.delete_brand(self.get_object(id))
        except BrandService.ValidationError as exc:
            raise ValidationError(exc.errors) from exc
        return api_response(True, _("Brand deleted."), None)


class BrandNameSuggestions(APIView):
    permission_classes = [CustomActionPermission]
    required_permission = "catalog.view_brand"

    def get(self, request):
        query = BrandNameSuggestionQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        exact_duplicate, matches = brand_service.find_name_matches(
            query.validated_data["name"],
            exclude_id=query.validated_data.get("exclude_id"),
        )
        suggestions = [
            {
                "id": brand.id,
                "name": brand.name,
                "fa_name": brand.fa_name,
                "similarity": score,
                "exact": exact,
            }
            for exact, score, brand in matches
        ]
        serializer = BrandNameSuggestionSerializer(suggestions, many=True)
        return api_response(
            True,
            "",
            {"exact_duplicate": exact_duplicate, "suggestions": serializer.data},
        )


# ─────────────────────── Variant Attributes and Options ───────────────────────

class VariantAttributeListCreate(APIView):
    model = VariantAttribute
    permission_classes = [CatalogModelPermissions]

    def get(self, request):
        attributes = variant_attribute_service.list_attributes(request.query_params.get("search"))
        return api_response(True, "", VariantAttributeSerializer(attributes, many=True).data)

    def post(self, request):
        serializer = VariantAttributeWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            attribute = variant_attribute_service.create_attribute(**serializer.validated_data)
        except VariantAttributeService.ValidationError as exc:
            raise ValidationError(exc.errors) from exc
        return api_response(
            True, _("Variant attribute created."),
            VariantAttributeSerializer(attribute).data, status_code=201,
        )


class VariantAttributeDetail(APIView):
    model = VariantAttribute
    permission_classes = [CatalogModelPermissions]

    def get_object(self, id):
        try:
            return variant_attribute_service.get_attribute(id)
        except VariantAttribute.DoesNotExist:
            raise NotFound(_("Variant attribute not found."))

    def get(self, request, id):
        return api_response(True, "", VariantAttributeSerializer(self.get_object(id)).data)

    def patch(self, request, id):
        attribute = self.get_object(id)
        serializer = VariantAttributeWriteSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        try:
            attribute = variant_attribute_service.update_attribute(
                attribute, name=serializer.validated_data.get("name", attribute.name)
            )
        except VariantAttributeService.ValidationError as exc:
            raise ValidationError(exc.errors) from exc
        return api_response(True, _("Variant attribute updated."), VariantAttributeSerializer(attribute).data)

    def delete(self, request, id):
        try:
            variant_attribute_service.delete_attribute(self.get_object(id))
        except VariantAttributeService.ValidationError as exc:
            raise ValidationError(exc.errors) from exc
        return api_response(True, _("Variant attribute deleted."), None)


class VariantOptionListCreate(APIView):
    model = VariantOption
    permission_classes = [CatalogModelPermissions]

    def get(self, request):
        options = variant_attribute_service.list_options(
            request.query_params.get("search"), request.query_params.get("attribute_id")
        )
        return api_response(True, "", VariantOptionSerializer(options, many=True).data)

    def post(self, request):
        serializer = VariantOptionWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            option = variant_attribute_service.create_option(**serializer.validated_data)
        except VariantAttributeService.ValidationError as exc:
            raise ValidationError(exc.errors) from exc
        return api_response(
            True, _("Variant option created."), VariantOptionSerializer(option).data,
            status_code=201,
        )


class VariantOptionDetail(APIView):
    model = VariantOption
    permission_classes = [CatalogModelPermissions]

    def get_object(self, id):
        try:
            return variant_attribute_service.get_option(id)
        except VariantOption.DoesNotExist:
            raise NotFound(_("Variant option not found."))

    def get(self, request, id):
        return api_response(True, "", VariantOptionSerializer(self.get_object(id)).data)

    def patch(self, request, id):
        option = self.get_object(id)
        serializer = VariantOptionWriteSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        try:
            option = variant_attribute_service.update_option(option, **serializer.validated_data)
        except VariantAttributeService.ValidationError as exc:
            raise ValidationError(exc.errors) from exc
        return api_response(True, _("Variant option updated."), VariantOptionSerializer(option).data)

    def delete(self, request, id):
        try:
            variant_attribute_service.delete_option(self.get_object(id))
        except VariantAttributeService.ValidationError as exc:
            raise ValidationError(exc.errors) from exc
        return api_response(True, _("Variant option deleted."), None)


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
    required_permissions = ["catalog.add_product", "catalog.change_product"]

    def get(self, request):
        return api_response(True, "", {
            "categories": product_service.get_form_options(),
            "brands": product_service._brand_options(),
        })


class ProductFilterOptions(APIView):
    permission_classes = [CustomActionPermission]
    required_permission = "catalog.view_product"

    def get(self, request):
        return api_response(True, "", product_service.get_filter_options())


class ProductDetailDefinitions(APIView):
    permission_classes = [CustomActionPermission]
    required_permissions = ["catalog.add_product", "catalog.change_product"]

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


class ProductCompleteUpdate(APIView):
    permission_classes = [CustomActionPermission]
    required_permission = "catalog.change_product"

    def get_product(self, id):
        try:
            return product_service.get_product(id)
        except Exception:
            raise NotFound(_("Product not found."))

    def get(self, request, id):
        return api_response(True, "", ProductSerializer(self.get_product(id)).data)

    def patch(self, request, id):
        product = self.get_product(id)
        serializer = ProductCompleteCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            product = product_service.update_complete_product(
                product, **serializer.validated_data
            )
        except ProductService.ValidationError as exc:
            raise ValidationError(exc.errors) from exc
        return api_response(
            True,
            _("Product updated."),
            ProductSerializer(product).data,
        )


class ProductListCreate(APIView):
    model = Product
    permission_classes = [CatalogModelPermissions]

    def get(self, request):
        query = ProductListQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        products = product_service.search_products(**query.validated_data)
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
            return product_service.get_product_details(id)
        except Exception:
            raise NotFound(_("Product not found."))

    def get(self, request, id):
        product = self.get_object(id)
        serializer = ProductDetailReadSerializer(product)
        return api_response(True, "", serializer.data)

    def patch(self, request, id):
        product = self.get_object(id)
        serializer = ProductBasicUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        product_service.update_product(product, **serializer.validated_data)
        result = ProductSerializer(product).data
        return api_response(True, _("Product updated."), result)

    def delete(self, request, id):
        product = self.get_object(id)
        product_service.delete_product(product)
        return api_response(True, _("Product deleted."), None)


class AdminProductFileAPIView(APIView):
    model = ProductFile
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [AdminModelPermissions]

    @staticmethod
    def get_product(product_id):
        product = Product.objects.filter(pk=product_id).first()
        if product is None:
            raise NotFound(_("Product not found."))
        return product


class ProductFileListCreate(AdminProductFileAPIView):
    def get(self, request, product_id):
        product = self.get_product(product_id)
        relations = product_file_service.list_for_product(product)
        return api_response(
            True, "", ProductFileReadSerializer(relations, many=True).data
        )

    def post(self, request, product_id):
        product = self.get_product(product_id)
        serializer = ProductFileWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            relation = product_file_service.attach(
                product, **serializer.validated_data
            )
        except ProductFileService.ValidationError as exc:
            raise ValidationError(exc.errors) from exc
        return api_response(
            True,
            _("File attached to product."),
            ProductFileReadSerializer(relation).data,
            status_code=201,
        )


class ProductFileDetail(AdminProductFileAPIView):
    def get_object(self, product_id, relation_id):
        product = self.get_product(product_id)
        relation = product_file_service.get_for_product(product, relation_id)
        if relation is None:
            raise NotFound(_("Product file not found."))
        return relation

    def get(self, request, product_id, relation_id):
        return api_response(
            True,
            "",
            ProductFileReadSerializer(
                self.get_object(product_id, relation_id)
            ).data,
        )

    def patch(self, request, product_id, relation_id):
        serializer = ProductFileUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            relation = product_file_service.update(
                self.get_object(product_id, relation_id),
                **serializer.validated_data,
            )
        except ProductFileService.ValidationError as exc:
            raise ValidationError(exc.errors) from exc
        return api_response(
            True,
            _("Product file updated."),
            ProductFileReadSerializer(relation).data,
        )

    def delete(self, request, product_id, relation_id):
        product_file_service.delete(self.get_object(product_id, relation_id))
        return api_response(True, _("File detached from product."), None)


class ProductFileReorder(AdminProductFileAPIView):
    def patch(self, request, product_id):
        product = self.get_product(product_id)
        serializer = ProductFileReorderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            relations = product_file_service.reorder(
                product, serializer.validated_data["files"]
            )
        except ProductFileService.ValidationError as exc:
            raise ValidationError(exc.errors) from exc
        return api_response(
            True,
            _("Product files reordered."),
            ProductFileReadSerializer(relations, many=True).data,
        )


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
        try:
            instances = product_service.add_detail_to_product(product, details_data)
        except ProductService.ValidationError as exc:
            raise ValidationError(exc.errors) from exc
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
        variants = product_service.list_product_variants(
            product, search=request.query_params.get("search", "").strip() or None
        )
        serializer = ProductVariantSerializer(variants, many=True)
        return api_response(True, "", serializer.data)

    def post(self, request, product_id):
        try:
            product = product_service.get_product(product_id)
        except Exception:
            raise NotFound(_("Product not found."))
        serializer = ProductVariantWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            variant = product_service.add_variant_to_product(
                product, **serializer.validated_data
            )
        except ProductService.ValidationError as exc:
            raise ValidationError(exc.errors) from exc
        result = ProductVariantSerializer(variant).data
        return api_response(True, _("Variant added."), result, status_code=201)


class ProductVariantFormOptions(APIView):
    permission_classes = [CustomActionPermission]
    required_permissions = [
        "catalog.view_productvariants",
        "catalog.add_variant_to_product",
        "catalog.change_productvariants",
    ]

    def get(self, request, product_id):
        try:
            product = product_service.get_product(product_id)
        except Exception:
            raise NotFound(_("Product not found."))
        try:
            warehouse = inventory_service.get_default_warehouse()
        except InventoryService.ValidationError as exc:
            raise ValidationError(exc.errors) from exc
        return api_response(True, "", {
            "product": {
                "id": product.id,
                "name": product.name,
                "category": (lambda c: c.id if c else None)(product.categories.order_by("id").first()),
                "category_name": (lambda c: c.name if c else None)(product.categories.order_by("id").first()),
            },
            "inventory_strategies": [
                {"id": strategy.id, "code": strategy.code, "name": strategy.name}
                for strategy in inventory_service.get_strategies()
            ],
            "default_warehouse": inventory_service.serialize_warehouse(warehouse),
            "attributes": product_service.get_variant_form_options(
                product, request.query_params.get("search")
            ),
        })


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
        serializer = ProductVariantWriteSerializer(
            variant, data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)
        try:
            variant = product_service.update_variant(variant, **serializer.validated_data)
        except ProductService.ValidationError as exc:
            raise ValidationError(exc.errors) from exc
        result = ProductVariantSerializer(variant).data
        return api_response(True, _("Variant updated."), result)

    def delete(self, request, id):
        variant = self.get_object(id)
        try:
            product_service.delete_variant(variant)
        except ProductService.ValidationError as exc:
            raise ValidationError(exc.errors) from exc
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
        variants = product_service.search_variants(
            search=request.query_params.get("search", "").strip() or None,
            **filters,
        )
        serializer = ProductVariantSerializer(variants, many=True)
        return api_response(True, "", serializer.data)
