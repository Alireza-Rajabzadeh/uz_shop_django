from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import BasePermission, DjangoModelPermissions
from rest_framework.views import APIView

from core.responses import api_response
from domains.catalog.models import ProductVariants
from domains.inventory.models import (
    SerializedStockStatus,
    Warehouse,
    WarehouseStatus,
)
from domains.inventory.services import InventoryService
from domains.users.auth import AdminJWTAuthentication

from .serializers import (
    CodeOptionSerializer,
    InventoryVariantQuerySerializer,
    InventoryVariantRowSerializer,
    OptionSerializer,
    VariantInventoryDetailSerializer,
    VariantStockWriteSerializer,
    WarehouseQuerySerializer,
    WarehouseSerializer,
    WarehouseWriteSerializer,
)


inventory_service = InventoryService()


class InventoryActionPermission(BasePermission):
    def has_permission(self, request, view):
        permissions = ["inventory.view_inventory"]
        if request.method == "PATCH":
            permissions.append("inventory.adjust_stock")
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.has_perms(permissions)
        )


class WarehouseModelPermissions(DjangoModelPermissions):
    perms_map = {
        "GET": ["%(app_label)s.view_%(model_name)s"],
        "OPTIONS": [],
        "HEAD": [],
        "POST": ["%(app_label)s.add_%(model_name)s"],
        "PATCH": ["%(app_label)s.change_%(model_name)s"],
        "DELETE": ["%(app_label)s.delete_%(model_name)s"],
    }

    def _queryset(self, view):
        return view.model._default_manager.all()


class InventoryAPIView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [InventoryActionPermission]


class InventoryVariantList(InventoryAPIView):
    def get(self, request):
        query = InventoryVariantQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        try:
            warehouse = inventory_service.get_default_warehouse()
        except InventoryService.ValidationError as exc:
            raise ValidationError(exc.errors) from exc
        variants = inventory_service.search_variants(**query.validated_data)
        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(variants, request, view=self)
        rows = [inventory_service.serialize_variant_overview(item, warehouse) for item in page]
        data = paginator.get_paginated_response(InventoryVariantRowSerializer(rows, many=True).data).data
        return api_response(True, "", data)


class VariantInventoryDetail(InventoryAPIView):
    def get_object(self, variant_id):
        variant = ProductVariants.objects.select_related(
            "inventory_strategy", "product"
        ).prefetch_related(
            "product__categories", "selections__attribute", "selections__option"
        ).filter(pk=variant_id).first()
        if variant is None:
            raise NotFound("Variant not found.")
        return variant

    def get(self, request, variant_id):
        try:
            details = inventory_service.get_variant_details(self.get_object(variant_id))
        except InventoryService.ValidationError as exc:
            raise ValidationError(exc.errors) from exc
        return api_response(True, "", VariantInventoryDetailSerializer(details).data)

    def patch(self, request, variant_id):
        variant = self.get_object(variant_id)
        serializer = VariantStockWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        strategy = variant.inventory_strategy.code
        expected = "inventory" if strategy == "normal" else "serial_items"
        if expected not in serializer.validated_data:
            raise ValidationError({expected: [f"This field is required for {strategy} inventory."]})
        try:
            variant = inventory_service.adjust_variant_stock(variant, **serializer.validated_data)
            details = inventory_service.get_variant_details(variant)
        except InventoryService.ValidationError as exc:
            raise ValidationError(exc.errors) from exc
        return api_response(True, "Stock updated.", VariantInventoryDetailSerializer(details).data)


class WarehouseAPIView(APIView):
    model = Warehouse
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [WarehouseModelPermissions]

    @staticmethod
    def service_error(exc):
        raise ValidationError(exc.errors) from exc


class WarehouseListCreate(WarehouseAPIView):
    def get(self, request):
        query = WarehouseQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        warehouses = inventory_service.search_warehouses(**query.validated_data)
        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(warehouses, request, view=self)
        data = paginator.get_paginated_response(WarehouseSerializer(page, many=True).data).data
        return api_response(True, "", data)

    def post(self, request):
        serializer = WarehouseWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            warehouse = inventory_service.create_warehouse(**serializer.validated_data)
        except InventoryService.ValidationError as exc:
            self.service_error(exc)
        return api_response(True, "Warehouse created.", WarehouseSerializer(warehouse).data, status_code=201)


class WarehouseDetail(WarehouseAPIView):
    def get_object(self, warehouse_id):
        warehouse = inventory_service.get_warehouse(warehouse_id)
        if warehouse is None:
            raise NotFound("Warehouse not found.")
        return warehouse

    def get(self, request, warehouse_id):
        return api_response(True, "", WarehouseSerializer(self.get_object(warehouse_id)).data)

    def patch(self, request, warehouse_id):
        warehouse = self.get_object(warehouse_id)
        serializer = WarehouseWriteSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        try:
            warehouse = inventory_service.update_warehouse(warehouse, **serializer.validated_data)
        except InventoryService.ValidationError as exc:
            self.service_error(exc)
        return api_response(True, "Warehouse updated.", WarehouseSerializer(warehouse).data)

    def delete(self, request, warehouse_id):
        try:
            inventory_service.delete_warehouse(self.get_object(warehouse_id))
        except InventoryService.ValidationError as exc:
            self.service_error(exc)
        return api_response(True, "Warehouse deleted.", None)


class LookupAPIView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [InventoryActionPermission]


class WarehouseStatusOptions(WarehouseAPIView):
    def get(self, request):
        return api_response(True, "", OptionSerializer(WarehouseStatus.objects.order_by("id"), many=True).data)


class InventoryStrategyOptions(LookupAPIView):
    def get(self, request):
        return api_response(True, "", CodeOptionSerializer(inventory_service.get_strategies(), many=True).data)


class SerializedStatusOptions(LookupAPIView):
    def get(self, request):
        return api_response(True, "", CodeOptionSerializer(SerializedStockStatus.objects.order_by("id"), many=True).data)
