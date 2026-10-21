from django.db.models import Q
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import BasePermission, DjangoModelPermissions
from rest_framework.views import APIView

from core.responses import api_response
from domains.business.models import BusinessProfile
from domains.catalog.models import Category, ProductVariants
from domains.inventory.enums.InventorySupplyCostTypeEnum import InventorySupplyCostTypeEnum
from domains.inventory.models import Warehouse, WarehouseStatus
from domains.inventory.services import (
    InventoryPricingService,
    InventoryReportingService,
    InventoryService,
    InventorySupplyService,
)
from domains.inventory.services.price_history_mongo import get_price_history as mongo_price_history
from domains.marketplace.models import BusinessOffer
from domains.users.auth import AdminJWTAuthentication

from .scope import (
    ADJUST_STOCK,
    VIEW_INVENTORY,
    is_aggregate,
    require_business,
    resolve_business,
    scope_permits,
)
from .serializers import (
    InventoryReportSummarySerializer,
    InventoryVariantQuerySerializer,
    InventoryVariantDetailSerializer,
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
    SupplyVariantContextSerializer,
    SupplyWriteSerializer,
    VariantMarketplaceStatusWriteSerializer,
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


class InventoryLookupPermission(BasePermission):
    """Reference-data reads that are the same for every business."""

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.has_perms([VIEW_INVENTORY])
        )


class InventoryScopePermission(BasePermission):
    """Scope-aware permission for inventory reads and stock writes.

    A named business is a plain ``view_inventory`` scope. An aggregate read
    additionally requires ``view_all_business``; an aggregate write is refused.
    """

    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        if not scope_permits(request):
            return False
        permissions = [VIEW_INVENTORY]
        if request.method == "PATCH":
            permissions.append(ADJUST_STOCK)
        return request.user.has_perms(permissions)


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

    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False
        if getattr(view, "business_scoped", True) and not scope_permits(request):
            return False
        return True


class InventoryAPIView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [InventoryScopePermission]


class InventoryVariantList(InventoryAPIView):
    def get(self, request):
        query = InventoryVariantQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        business = resolve_business(request)
        # A read never requires a default warehouse: the aggregate scope has no
        # single one to report, and a business that has not been stocked yet has
        # no warehouse either. The column is informational, so it is null then.
        warehouse = (
            inventory_service.find_default_warehouse(business=business)
            if business is not None
            else None
        )
        variants = inventory_service.search_variants(
            business=business, **query.validated_data
        )
        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(variants, request, view=self)
        # The marketplace price is per business; the aggregate scope has no
        # single offer per variant, so it reports none.
        offers = {}
        pricing_overviews = {}
        if business is not None:
            offers = {
                offer.variant_id: offer
                for offer in BusinessOffer.objects.filter(
                    business=business,
                    variant_id__in=[item.id for item in page],
                )
            }
            # The suggested price is part of the row preview, so reuse the
            # pricing list's batched overview instead of recomputing per row.
            pricing_overviews = pricing_service.get_pricing_overview_map(
                page, business=business
            )
        rows = [
            inventory_service.serialize_variant_overview(
                item,
                warehouse,
                business=business,
                offer=offers.get(item.id),
                pricing=pricing_overviews.get(item.id),
            )
            for item in page
        ]
        data = paginator.get_paginated_response(InventoryVariantRowSerializer(rows, many=True).data).data
        return api_response(True, "", data)


class VariantInventoryDetail(InventoryAPIView):
    def get_object(self, variant_id):
        variant = ProductVariants.objects.select_related(
            "product"
        ).prefetch_related(
            "product__categories", "selections__attribute", "selections__option"
        ).filter(pk=variant_id).first()
        if variant is None:
            raise NotFound("Variant not found.")
        return variant

    def get(self, request, variant_id):
        business = resolve_business(request)
        try:
            details = inventory_service.get_variant_details(
                self.get_object(variant_id), business=business
            )
        except InventoryService.ValidationError as exc:
            raise ValidationError(exc.errors) from exc
        return api_response(True, "", InventoryVariantDetailSerializer(details).data)

    def patch(self, request, variant_id):
        variant = self.get_object(variant_id)
        business = require_business(request)
        serializer = VariantStockWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        inv_type = inventory_service._detect_inventory_type(variant, business=business)
        expected = "inventory" if inv_type == "normal" else "serial_items"
        if expected not in serializer.validated_data:
            raise ValidationError({expected: [f"This field is required for {inv_type} inventory."]})
        try:
            variant = inventory_service.adjust_variant_stock(
                variant, business=business, **serializer.validated_data
            )
            details = inventory_service.get_variant_details(variant, business=business)
        except InventoryService.ValidationError as exc:
            raise ValidationError(exc.errors) from exc
        return api_response(True, "Stock updated.", InventoryVariantDetailSerializer(details).data)


class VariantMarketplaceStatusView(InventoryAPIView):
    """Toggle the variant's marketplace listing flag for one business.

    ``BusinessOffer.is_active`` is the variant's status *for the selected
    business*; the catalog-wide ``ProductVariants.status`` is a separate,
    admin-owned lifecycle status changed from the catalog API. The offer must
    already exist (pricing apply creates it), matching the vendor contract.
    """

    def patch(self, request, variant_id):
        business = require_business(request)
        serializer = VariantMarketplaceStatusWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        variant = ProductVariants.objects.filter(pk=variant_id).first()
        if variant is None:
            raise NotFound("Variant not found.")
        offer = BusinessOffer.objects.filter(business=business, variant=variant).first()
        if offer is None:
            raise ValidationError({
                "is_active": ["Create a BusinessOffer before updating marketplace status."]
            })
        is_active = serializer.validated_data["is_active"]
        if offer.is_active != is_active:
            offer.is_active = is_active
            offer.save(update_fields=["is_active"])
        return api_response(True, "Marketplace status updated.", {
            "variant_id": variant.id,
            "marketplace_offer_status": "active" if is_active else "inactive",
        })


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
        business = resolve_business(request)
        warehouses = inventory_service.search_warehouses(
            business=business, **query.validated_data
        )
        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(warehouses, request, view=self)
        data = paginator.get_paginated_response(WarehouseSerializer(page, many=True).data).data
        return api_response(True, "", data)

    def post(self, request):
        business = require_business(request)
        serializer = WarehouseWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        body_business = data.pop("business", None)
        if body_business is not None and body_business.pk != business.pk:
            raise ValidationError({
                "business_id": ["Warehouse business must match the selected scope."]
            })
        data["business"] = business
        try:
            warehouse = inventory_service.create_warehouse(**data)
        except InventoryService.ValidationError as exc:
            self.service_error(exc)
        return api_response(True, "Warehouse created.", WarehouseSerializer(warehouse).data, status_code=201)


class WarehouseDetail(WarehouseAPIView):
    def get_object(self, warehouse_id):
        warehouse = inventory_service.get_warehouse(warehouse_id)
        business = resolve_business(self.request)
        if warehouse is None or (
            business is not None and warehouse.business_id != business.id
        ):
            raise NotFound("Warehouse not found.")
        return warehouse

    def get(self, request, warehouse_id):
        return api_response(True, "", WarehouseSerializer(self.get_object(warehouse_id)).data)

    def patch(self, request, warehouse_id):
        warehouse = self.get_object(warehouse_id)
        serializer = WarehouseWriteSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        body_business = data.pop("business", None)
        if body_business is not None and body_business.pk != warehouse.business_id:
            raise ValidationError({"business_id": ["Warehouse business cannot be changed."]})
        try:
            warehouse = inventory_service.update_warehouse(warehouse, **data)
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
    permission_classes = [InventoryLookupPermission]


class WarehouseStatusOptions(WarehouseAPIView):
    # Reference data shared by every business, so it carries no business scope.
    business_scoped = False

    def get(self, request):
        return api_response(True, "", OptionSerializer(WarehouseStatus.objects.order_by("id"), many=True).data)


class InventoryBusinessOptions(LookupAPIView):
    """Business choices for the inventory scope selector.

    Gated by ``inventory.view_inventory`` rather than
    ``business.view_businessprofile`` so an inventory operator can pick a scope
    without holding the business module's read permission.
    """

    def get(self, request):
        businesses = BusinessProfile.objects.order_by("id")
        return api_response(True, "", [
            {
                "id": business.id,
                "name": business.display_name or business.business_name,
            }
            for business in businesses
        ])


class InventoryCategoryOptions(APIView):
    """Category choices for the inventory filter forms.

    A named business answers with the root categories it is registered under
    plus every descendant, so the filter can target a leaf category. The
    aggregate scope does the same from every root. Options arrive in tree order
    with a ``depth`` so the panel can indent children under their parent.
    Products live in leaf categories, so ``search_variants`` still matches the
    whole subtree of whatever the user picks.
    """

    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [InventoryScopePermission]

    def get(self, request):
        business = resolve_business(request)
        if business is None:
            root_ids = Category.objects.filter(
                parent__isnull=True
            ).values_list("id", flat=True)
        else:
            root_ids = business.categories.values_list("category_id", flat=True)
        return api_response(True, "", self._tree(root_ids))

    @staticmethod
    def _tree(root_ids):
        rows = list(
            Category.objects.values("id", "name", "fa_name", "parent_id")
        )
        by_id = {row["id"]: row for row in rows}
        children = {}
        for row in rows:
            children.setdefault(row["parent_id"], []).append(row)
        for group in children.values():
            group.sort(key=lambda row: row["id"])

        options = []
        visited = set()

        def walk(category_id, depth):
            if category_id in visited or category_id not in by_id:
                return
            visited.add(category_id)
            row = by_id[category_id]
            options.append({
                "id": row["id"],
                "name": row["name"],
                "fa_name": row["fa_name"],
                "depth": depth,
            })
            for child in children.get(category_id, []):
                walk(child["id"], depth + 1)

        for root_id in sorted(set(root_ids)):
            walk(root_id, 0)
        return options


class InventoryVariantOptions(LookupAPIView):
    """Catalog variants for the supply form's picker.

    Supply is the entry point into inventory — a variant is stocked first and
    priced afterwards — so this picker must offer variants that have no
    Inventory row yet, unlike the records-only ``/inventory/variants`` list. It
    is a lightweight, searchable, paginated projection of the catalog and is
    deliberately business-independent: it names no stock.
    """

    def get(self, request):
        search = request.query_params.get("search", "").strip()
        variants = ProductVariants.objects.select_related("product").order_by("sku", "id")
        if search:
            variants = variants.filter(
                Q(sku__icontains=search) | Q(product__name__icontains=search)
            )
        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(variants, request, view=self)
        rows = [
            {"id": variant.id, "sku": variant.sku, "product_name": variant.product.name}
            for variant in page
        ]
        data = paginator.get_paginated_response(
            SupplyVariantContextSerializer(rows, many=True).data
        ).data
        return api_response(True, "", data)


class SupplyScopePermission(BasePermission):
    """Scope-aware permission for supply reads and writes."""

    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        if not scope_permits(request):
            return False
        permissions = [VIEW_INVENTORY]
        if request.method in ("POST", "PATCH", "DELETE"):
            permissions.append(ADJUST_STOCK)
        return request.user.has_perms(permissions)


class SupplyAPIView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [SupplyScopePermission]


class SupplyListCreate(SupplyAPIView):
    def get(self, request):
        query = SupplyQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        business = resolve_business(request)
        supplies = supply_service.search_supplies(
            business_id=business.id if business is not None else None,
            **query.validated_data,
        )
        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(supplies, request, view=self)
        rows = [supply_service.serialize_supply_row(item) for item in page]
        data = paginator.get_paginated_response(SupplyListSerializer(rows, many=True).data).data
        return api_response(True, "", data)

    def post(self, request):
        business = require_business(request)
        serializer = SupplyWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        warehouse = serializer.validated_data["warehouse"]
        if warehouse.business_id != business.id:
            raise ValidationError({
                "warehouse_id": ["The warehouse must belong to the selected business."]
            })
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
        business = resolve_business(self.request)
        if supply is None or (
            business is not None and supply.business_id != business.id
        ):
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
        business = require_business(request)
        supply = supply_service.get_supply(supply_id)
        if supply is None or supply.business_id != business.id:
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
    permission_classes = [InventoryScopePermission]

    def get_variant(self, variant_id):
        variant = ProductVariants.objects.filter(pk=variant_id).first()
        if variant is None:
            raise NotFound("Variant not found.")
        return variant

    def get(self, request, variant_id):
        variant = self.get_variant(variant_id)
        business = require_business(request)
        overview = pricing_service.get_variant_pricing_overview(variant, business=business)
        return api_response(True, "", VariantPricingOverviewSerializer(overview).data)

    def patch(self, request, variant_id):
        variant = self.get_variant(variant_id)
        business = require_business(request)
        serializer = VariantPricingWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            pricing_service.update_variant_pricing(
                variant, business=business, **serializer.validated_data
            )
        except InventoryPricingService.ValidationError as exc:
            raise ValidationError(exc.errors) from exc
        overview = pricing_service.get_variant_pricing_overview(variant, business=business)
        return api_response(True, "Pricing updated.", VariantPricingOverviewSerializer(overview).data)


class PricingApplyPermission(BasePermission):
    def has_permission(self, request, view):
        # Pricing is single-business: applying a price always names a business.
        if is_aggregate(request):
            return False
        permissions = [
            VIEW_INVENTORY,
            ADJUST_STOCK,
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
        business = require_business(request)
        serializer = VariantPriceApplySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            variant, history = pricing_service.apply_price(
                variant, business=business, **serializer.validated_data
            )
        except InventoryPricingService.ValidationError as exc:
            raise ValidationError(exc.errors) from exc
        overview = pricing_service.get_variant_pricing_overview(variant, business=business)
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
    permission_classes = [InventoryScopePermission]

    def get(self, request, variant_id):
        variant = ProductVariants.objects.filter(pk=variant_id).first()
        if variant is None:
            raise NotFound("Variant not found.")
        business = resolve_business(request)
        history = mongo_price_history(
            variant_id, business.id if business is not None else None
        )
        return api_response(True, "", history)


class PricingListView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [InventoryScopePermission]

    def get(self, request):
        query = PricingQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        business = require_business(request)
        variants = pricing_service.search_pricing(
            business=business, **query.validated_data
        )
        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(variants, request, view=self)
        overview_map = pricing_service.get_pricing_overview_map(page, business=business)
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
    permission_classes = [InventoryScopePermission]

    def get(self, request):
        business = resolve_business(request)
        summary = reporting_service.get_summary(business=business)
        return api_response(True, "", InventoryReportSummarySerializer(summary).data)


class InventoryReportVariantListView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [InventoryScopePermission]

    def get(self, request):
        query = ReportVariantQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        business = resolve_business(request)
        variants = reporting_service.search_variants_for_report(
            business=business, **query.validated_data
        )
        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(variants, request, view=self)
        rows = reporting_service.variant_report_rows(page, business=business)
        data = paginator.get_paginated_response(
            ReportVariantRowSerializer([rows[variant.id] for variant in page], many=True).data
        ).data
        return api_response(True, "", data)


class InventoryReportSupplyListView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [InventoryScopePermission]

    def get(self, request):
        query = ReportSupplyQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        business = resolve_business(request)
        supplies = reporting_service.search_supplies_for_report(
            business=business, **query.validated_data
        )
        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(supplies, request, view=self)
        rows = [reporting_service.serialize_supply_report_row(supply) for supply in page]
        data = paginator.get_paginated_response(ReportSupplyRowSerializer(rows, many=True).data).data
        return api_response(True, "", data)
