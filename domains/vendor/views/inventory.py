from django.db import models
from django.shortcuts import get_object_or_404
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from core.responses import api_response
from domains.catalog.models import Product, ProductVariants
from domains.inventory.api.serializers import (
    InventoryVariantDetailSerializer,
    PricingStrategyOptionSerializer,
    SupplyCostTypeOptionSerializer,
    SupplyDetailSerializer,
    SupplyListSerializer,
    SupplyReceiveSerializer,
    SupplyWriteSerializer,
    VariantPricingOverviewSerializer,
    VariantPricingWriteSerializer,
    VariantPriceHistorySerializer,
)
from domains.inventory.enums.InventorySupplyCostTypeEnum import InventorySupplyCostTypeEnum
from domains.inventory.services.inventory_pricing_service import InventoryPricingService
from domains.inventory.services.inventory_service import InventoryService
from domains.inventory.services.inventory_supply_service import InventorySupplyService
from domains.inventory.services.price_history_mongo import get_price_history as mongo_price_history
from domains.location.api.options import (
    CountryFilterSerializer,
    CountryOptionSerializer,
    StateFilterSerializer,
    StateOptionSerializer,
    CityOptionSerializer,
)
from domains.location.models import City, Country, State
from domains.marketplace.models import BusinessOffer
from domains.vendor.auth import VendorJWTAuthentication
from domains.vendor.views.products import _get_business_category_ids



inventory_service = InventoryService()
pricing_service = InventoryPricingService()
supply_service = InventorySupplyService()


class VendorInventoryAPIView(APIView):
    authentication_classes = [VendorJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def _get_business(self, request):
        business, _ = _get_business_category_ids(request.user)
        if not business:
            from rest_framework.exceptions import NotFound
            raise NotFound("Business profile not found.")
        return business

    def _get_vendor_variant(self, variant_id, business):
        variant = get_object_or_404(ProductVariants, id=variant_id)
        from domains.catalog.models import Product
        product_ids = set(
            Product.objects.filter(
                categories__id__in=business.categories.values_list("category_id", flat=True)
            ).values_list("id", flat=True)
        )
        if variant.product_id not in product_ids:
            from rest_framework.exceptions import NotFound
            raise NotFound("Variant not found.")
        return variant


class VendorVariantInventoryDetailView(VendorInventoryAPIView):
    def get(self, request, variant_id):
        business = self._get_business(request)
        variant = self._get_vendor_variant(variant_id, business)
        details = inventory_service.get_variant_details(variant)
        return api_response(data=InventoryVariantDetailSerializer(details).data)


class VendorVariantPricingView(VendorInventoryAPIView):
    def get(self, request, variant_id):
        business = self._get_business(request)
        variant = self._get_vendor_variant(variant_id, business)
        overview = pricing_service.get_variant_pricing_overview(variant)
        return api_response(data=VariantPricingOverviewSerializer(overview).data)

    def patch(self, request, variant_id):
        business = self._get_business(request)
        variant = self._get_vendor_variant(variant_id, business)
        serializer = VariantPricingWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            pricing_service.update_variant_pricing(variant, **serializer.validated_data)
        except InventoryPricingService.ValidationError as exc:
            from rest_framework.exceptions import ValidationError
            raise ValidationError(exc.errors) from exc
        overview = pricing_service.get_variant_pricing_overview(variant)
        return api_response(data=VariantPricingOverviewSerializer(overview).data)


class VendorVariantPricingHistoryView(VendorInventoryAPIView):
    def get(self, request, variant_id):
        business = self._get_business(request)
        variant = self._get_vendor_variant(variant_id, business)
        history = mongo_price_history(variant_id)
        return api_response(data=history)


class VendorPricingStrategiesView(VendorInventoryAPIView):
    def get(self, request):
        return api_response(
            data=PricingStrategyOptionSerializer(pricing_service.get_strategies(), many=True).data
        )


class VendorSupplyCostTypesView(VendorInventoryAPIView):
    def get(self, request):
        options = [
            {"code": member.value, "name": member.name.capitalize()}
            for member in InventorySupplyCostTypeEnum
        ]
        return api_response(
            data=SupplyCostTypeOptionSerializer(options, many=True).data
        )


class VendorWarehouseStatusesView(VendorInventoryAPIView):
    def get(self, request):
        from domains.inventory.models import WarehouseStatus
        statuses = WarehouseStatus.objects.all().order_by("id")
        data = [{"id": s.id, "name": s.name} for s in statuses]
        return api_response(data=data)


class VendorVariantSupplyListView(VendorInventoryAPIView):
    def get(self, request, variant_id):
        business = self._get_business(request)
        variant = self._get_vendor_variant(variant_id, business)
        supplies = supply_service.search_supplies(variant_id=variant.id)
        rows = [supply_service.serialize_supply_row(item) for item in supplies]
        return api_response(data=SupplyListSerializer(rows, many=True).data)

    def post(self, request, variant_id):
        business = self._get_business(request)
        variant = self._get_vendor_variant(variant_id, business)
        data = request.data.copy()
        data["variant_id"] = variant.id
        from rest_framework.parsers import JSONParser
        serializer = SupplyWriteSerializer(data=data)
        serializer.is_valid(raise_exception=True)
        try:
            supply = supply_service.create_supply(**serializer.validated_data)
            supply.business = business
            supply.save(update_fields=["business"])
        except InventorySupplyService.ValidationError as exc:
            from rest_framework.exceptions import ValidationError
            raise ValidationError(exc.errors) from exc
        return api_response(
            data=SupplyDetailSerializer(supply_service.serialize_supply_detail(supply)).data,
        )


class VendorSupplyDetailView(VendorInventoryAPIView):
    def _get_supply(self, supply_id, business):
        supply = supply_service.get_supply(supply_id)
        if supply is None:
            from rest_framework.exceptions import NotFound
            raise NotFound("Supply not found.")
        if supply.business_id and supply.business_id != business.id:
            from rest_framework.exceptions import NotFound
            raise NotFound("Supply not found.")
        return supply

    def get(self, request, supply_id):
        business = self._get_business(request)
        supply = self._get_supply(supply_id, business)
        return api_response(
            data=SupplyDetailSerializer(supply_service.serialize_supply_detail(supply)).data,
        )

    def patch(self, request, supply_id):
        business = self._get_business(request)
        supply = self._get_supply(supply_id, business)
        serializer = SupplyWriteSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        try:
            supply = supply_service.update_supply(supply, **serializer.validated_data)
        except InventorySupplyService.ValidationError as exc:
            from rest_framework.exceptions import ValidationError
            raise ValidationError(exc.errors) from exc
        return api_response(
            data=SupplyDetailSerializer(supply_service.serialize_supply_detail(supply)).data,
        )

    def delete(self, request, supply_id):
        business = self._get_business(request)
        supply = self._get_supply(supply_id, business)
        try:
            supply_service.delete_supply(supply)
        except InventorySupplyService.ValidationError as exc:
            from rest_framework.exceptions import ValidationError
            raise ValidationError(exc.errors) from exc
        return api_response(data=None)


class VendorSupplyReceiveView(VendorInventoryAPIView):
    def post(self, request, supply_id):
        business = self._get_business(request)
        supply = supply_service.get_supply(supply_id)
        if supply is None:
            from rest_framework.exceptions import NotFound
            raise NotFound("Supply not found.")
        if supply.business_id and supply.business_id != business.id:
            from rest_framework.exceptions import NotFound
            raise NotFound("Supply not found.")
        serializer = SupplyReceiveSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serial_items = serializer.validated_data.get("serial_items")
        try:
            supply = supply_service.receive_supply(supply, serial_items=serial_items)
        except InventorySupplyService.ValidationError as exc:
            from rest_framework.exceptions import ValidationError
            raise ValidationError(exc.errors) from exc
        return api_response(
            data=SupplyDetailSerializer(supply_service.serialize_supply_detail(supply)).data,
        )


class VendorWarehouseListView(VendorInventoryAPIView):
    def get(self, request):
        business = self._get_business(request)
        from domains.inventory.models import Warehouse
        warehouses = Warehouse.objects.filter(
            business=business
        ).order_by("-is_default", "name")
        data = [
            {
                "id": w.id,
                "code": w.code,
                "name": w.name,
                "status": w.status.name,
                "city": w.city_id,
                "city_name": w.city.name if w.city else None,
                "address": w.address,
                "is_default": w.is_default,
                "phone_numbers": w.phone_numbers,
                "postal_code": w.postal_code,
            }
            for w in warehouses
        ]
        return api_response(data=data)

    def post(self, request):
        business = self._get_business(request)
        from domains.inventory.api.serializers import WarehouseWriteSerializer
        from domains.inventory.models import Warehouse

        serializer = WarehouseWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        warehouse = Warehouse.objects.create(
            business=business,
            **serializer.validated_data,
        )
        return api_response(
            data={
                "id": warehouse.id,
                "code": warehouse.code,
                "name": warehouse.name,
                "status": warehouse.status.name,
            },
        )


class VendorWarehouseDetailView(VendorInventoryAPIView):
    def patch(self, request, warehouse_id):
        business = self._get_business(request)
        from domains.inventory.models import Warehouse
        from domains.inventory.api.serializers import WarehouseWriteSerializer

        warehouse = get_object_or_404(Warehouse, id=warehouse_id, business=business)

        serializer = WarehouseWriteSerializer(warehouse, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)

        for attr, value in serializer.validated_data.items():
            setattr(warehouse, attr, value)
        warehouse.save()

        return api_response(
            data={
                "id": warehouse.id,
                "code": warehouse.code,
                "name": warehouse.name,
                "status": warehouse.status.name,
                "city": warehouse.city_id,
                "city_name": warehouse.city.name if warehouse.city else None,
                "address": warehouse.address,
                "is_default": warehouse.is_default,
                "phone_numbers": warehouse.phone_numbers,
                "postal_code": warehouse.postal_code,
            },
        )


class VendorInventoryOverviewView(VendorInventoryAPIView):
    def get(self, request):
        business = self._get_business(request)
        if not business:
            return api_response(data=[])

        search = request.query_params.get("search", "").strip()
        strategy = request.query_params.get("strategy", "").strip()

        inventory_service = InventoryService()
        pricing_service = InventoryPricingService()

        variants = ProductVariants.objects.filter(
            product__category__in=business.categories.values_list("category_id", flat=True)
        ).select_related("product", "inventory").prefetch_related("files")

        if search:
            variants = variants.filter(
                models.Q(sku__icontains=search)
                | models.Q(product__title__icontains=search)
                | models.Q(title__icontains=search)
            )

        if strategy:
            variants = variants.filter(inventory__current_strategy=strategy)

        variant_ids = list(variants.values_list("id", flat=True))
        offers = {
            o.variant_id: o
            for o in BusinessOffer.objects.filter(
                business=business, variant_id__in=variant_ids
            )
        }

        result = []
        for v in variants:
            stock = inventory_service.get_stock_summary(v)
            offer = offers.get(v.id)
            discounted = pricing_service.calculate_discounted_price(v, offer)
            result.append({
                "id": v.id,
                "sku": v.sku,
                "title": v.title,
                "product_title": v.product.title,
                "product_id": v.product.id,
                "image": v.files.first().file.url if v.files.exists() else None,
                "total_stock": stock["total"],
                "sellable_stock": stock["sellable"],
                "available_stock": stock["available"],
                "strategy": v.inventory.current_strategy if v.inventory else None,
                "price": str(offer.price) if offer else None,
                "discounted_price": str(discounted) if discounted else None,
            })

        return api_response(data=result)


class VendorSupplyOverviewView(VendorInventoryAPIView):
    def get(self, request):
        business = self._get_business(request)
        if not business:
            return api_response(data=[])

        from domains.inventory.models import InventorySupply

        supplies = InventorySupply.objects.filter(
            variant__product__category__in=business.categories.values_list("category_id", flat=True)
        ).select_related("variant", "variant__product", "warehouse").order_by("-supplied_at")[:50]

        rows = [supply_service.serialize_supply_row(s) for s in supplies]
        return api_response(data=SupplyListSerializer(rows, many=True).data)


class VendorCountryOptionsView(VendorInventoryAPIView):
    def get(self, request):
        countries = Country.objects.order_by("fa_title", "name")
        return api_response(data=CountryOptionSerializer(countries, many=True).data)


class VendorStateOptionsView(VendorInventoryAPIView):
    def get(self, request):
        query = CountryFilterSerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        states = State.objects.filter(
            country_id=query.validated_data["country_id"]
        ).order_by("fa_title", "name")
        return api_response(data=StateOptionSerializer(states, many=True).data)


class VendorCityOptionsView(VendorInventoryAPIView):
    def get(self, request):
        query = StateFilterSerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        cities = City.objects.filter(
            state_id=query.validated_data["state_id"]
        ).order_by("fa_title", "name")
        return api_response(data=CityOptionSerializer(cities, many=True).data)
