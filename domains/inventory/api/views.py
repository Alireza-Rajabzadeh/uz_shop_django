from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import BasePermission, DjangoModelPermissions
from rest_framework.views import APIView

from core.responses import api_response
from domains.catalog.models import ProductVariants
from domains.inventory.enums.InventorySupplyCostTypeEnum import InventorySupplyCostTypeEnum
from domains.inventory.models import (
    SerializedStockStatus,
    Warehouse,
    WarehouseStatus,
)
from domains.inventory.services import (
    InventoryPricingService,
    InventoryReportingService,
    InventoryService,
    InventorySupplyService,
)
from domains.inventory.services.price_history_mongo import get_price_history as mongo_price_history
from domains.users.auth import AdminJWTAuthentication

from .serializers import (
    CodeOptionSerializer,
    InventoryReportSummarySerializer,
    InventoryVariantQuerySerializer,
    InventoryVariantRowSerializer,
    OptionSerializer,
    PricingListRowSerializer,
    PricingQuerySerializer,
    PricingStrategyOptionSerializer,
    ReportSupplyRowSerializer,
    ReportSupplyQuerySerializer,
    ReportVariantQuerySerializer,
    ReportVariantRowSerializer,
    SupplyCostTypeOptionSerializer,
    SupplyDetailSerializer,
    SupplyListSerializer,
    SupplyQuerySerializer,
    SupplyReceiveSerializer,
    SupplyWriteSerializer,
    VariantInventoryDetailSerializer,
    VariantPriceApplySerializer,
    VariantPriceHistorySerializer,
    VariantPricingOverviewSerializer,
    VariantPricingWriteSerializer,
    VariantStockWriteSerializer,
    WarehouseQuerySerializer,
    WarehouseSerializer,
    WarehouseWriteSerializer,
)


inventory_service = InventoryService()
supply_service = InventorySupplyService()
pricing_service = InventoryPricingService()
reporting_service = InventoryReportingService()


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


class SupplyActionPermission(BasePermission):
    def has_permission(self, request, view):
        permissions = ["inventory.view_inventory"]
        if request.method in ("POST", "PATCH", "DELETE"):
            permissions.append("inventory.adjust_stock")
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.has_perms(permissions)
        )


class SupplyAPIView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [SupplyActionPermission]


class SupplyListCreate(SupplyAPIView):
    def get(self, request):
        query = SupplyQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        supplies = supply_service.search_supplies(**query.validated_data)
        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(supplies, request, view=self)
        rows = [supply_service.serialize_supply_row(item) for item in page]
        data = paginator.get_paginated_response(SupplyListSerializer(rows, many=True).data).data
        return api_response(True, "", data)

    def post(self, request):
        serializer = SupplyWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            supply = supply_service.create_supply(**serializer.validated_data)
        except InventorySupplyService.ValidationError as exc:
            raise ValidationError(exc.errors) from exc
        return api_response(
            True,
            "Supply created.",
            SupplyDetailSerializer(supply_service.serialize_supply_detail(supply)).data,
            status_code=201,
        )


class SupplyDetail(SupplyAPIView):
    def get_object(self, supply_id):
        supply = supply_service.get_supply(supply_id)
        if supply is None:
            raise NotFound("Supply not found.")
        return supply

    def get(self, request, supply_id):
        return api_response(
            True,
            "",
            SupplyDetailSerializer(supply_service.serialize_supply_detail(self.get_object(supply_id))).data,
        )

    def patch(self, request, supply_id):
        serializer = SupplyWriteSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        try:
            supply = supply_service.update_supply(self.get_object(supply_id), **serializer.validated_data)
        except InventorySupplyService.ValidationError as exc:
            raise ValidationError(exc.errors) from exc
        return api_response(
            True,
            "Supply updated.",
            SupplyDetailSerializer(supply_service.serialize_supply_detail(supply)).data,
        )

    def delete(self, request, supply_id):
        try:
            supply_service.delete_supply(self.get_object(supply_id))
        except InventorySupplyService.ValidationError as exc:
            raise ValidationError(exc.errors) from exc
        return api_response(True, "Supply deleted.", None)


class SupplyReceive(SupplyAPIView):
    def post(self, request, supply_id):
        supply = supply_service.get_supply(supply_id)
        if supply is None:
            raise NotFound("Supply not found.")
        serializer = SupplyReceiveSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serial_items = serializer.validated_data.get("serial_items")
        try:
            supply = supply_service.receive_supply(supply, serial_items=serial_items)
        except InventorySupplyService.ValidationError as exc:
            raise ValidationError(exc.errors) from exc
        return api_response(
            True,
            "Supply received.",
            SupplyDetailSerializer(supply_service.serialize_supply_detail(supply)).data,
        )


class SupplyCostTypeOptions(LookupAPIView):
    def get(self, request):
        options = [
            {"code": member.value, "name": member.name.capitalize()}
            for member in InventorySupplyCostTypeEnum
        ]
        return api_response(True, "", SupplyCostTypeOptionSerializer(options, many=True).data)


class VariantPricingView(APIView):
    # GET uses view_inventory; PATCH additionally requires adjust_stock via
    # the shared InventoryActionPermission.
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [InventoryActionPermission]

    def get_variant(self, variant_id):
        variant = ProductVariants.objects.filter(pk=variant_id).first()
        if variant is None:
            raise NotFound("Variant not found.")
        return variant

    def get(self, request, variant_id):
        variant = self.get_variant(variant_id)
        overview = pricing_service.get_variant_pricing_overview(variant)
        return api_response(True, "", VariantPricingOverviewSerializer(overview).data)

    def patch(self, request, variant_id):
        variant = self.get_variant(variant_id)
        serializer = VariantPricingWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            pricing_service.update_variant_pricing(variant, **serializer.validated_data)
        except InventoryPricingService.ValidationError as exc:
            raise ValidationError(exc.errors) from exc
        overview = pricing_service.get_variant_pricing_overview(variant)
        return api_response(True, "Pricing updated.", VariantPricingOverviewSerializer(overview).data)


class PricingApplyPermission(BasePermission):
    def has_permission(self, request, view):
        permissions = [
            "inventory.view_inventory",
            "inventory.adjust_stock",
            "catalog.change_productvariants",
        ]
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.has_perms(permissions)
        )


class VariantPricingApplyView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [PricingApplyPermission]

    def post(self, request, variant_id):
        variant = ProductVariants.objects.filter(pk=variant_id).first()
        if variant is None:
            raise NotFound("Variant not found.")
        serializer = VariantPriceApplySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            variant, history = pricing_service.apply_price(
                variant, **serializer.validated_data
            )
        except InventoryPricingService.ValidationError as exc:
            raise ValidationError(exc.errors) from exc
        overview = pricing_service.get_variant_pricing_overview(variant)
        return api_response(
            True,
            "Price applied.",
            {
                "pricing": VariantPricingOverviewSerializer(overview).data,
                "history": VariantPriceHistorySerializer(history).data,
            },
        )


class VariantPricingHistoryView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [InventoryActionPermission]

    def get(self, request, variant_id):
        variant = ProductVariants.objects.filter(pk=variant_id).first()
        if variant is None:
            raise NotFound("Variant not found.")
        history = mongo_price_history(variant_id)
        return api_response(True, "", history)


class PricingListView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [InventoryActionPermission]

    def get(self, request):
        query = PricingQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        variants = pricing_service.search_pricing(**query.validated_data)
        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(variants, request, view=self)
        overview_map = pricing_service.get_pricing_overview_map(page)
        rows = [pricing_service.serialize_pricing_row(variant, overview_map[variant.id]) for variant in page]
        data = paginator.get_paginated_response(PricingListRowSerializer(rows, many=True).data).data
        return api_response(True, "", data)


class PricingStrategyOptions(LookupAPIView):
    def get(self, request):
        return api_response(
            True, "", PricingStrategyOptionSerializer(pricing_service.get_strategies(), many=True).data
        )


class InventoryReportSummaryView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [InventoryActionPermission]

    def get(self, request):
        summary = reporting_service.get_summary()
        return api_response(True, "", InventoryReportSummarySerializer(summary).data)


class InventoryReportVariantListView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [InventoryActionPermission]

    def get(self, request):
        query = ReportVariantQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        variants = reporting_service.search_variants_for_report(**query.validated_data)
        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(variants, request, view=self)
        rows = reporting_service.variant_report_rows(page)
        data = paginator.get_paginated_response(
            ReportVariantRowSerializer([rows[variant.id] for variant in page], many=True).data
        ).data
        return api_response(True, "", data)


class InventoryReportSupplyListView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [InventoryActionPermission]

    def get(self, request):
        query = ReportSupplyQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        supplies = reporting_service.search_supplies_for_report(**query.validated_data)
        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(supplies, request, view=self)
        rows = [reporting_service.serialize_supply_report_row(supply) for supply in page]
        data = paginator.get_paginated_response(ReportSupplyRowSerializer(rows, many=True).data).data
        return api_response(True, "", data)
