from decimal import Decimal

from django.shortcuts import get_object_or_404
from rest_framework.exceptions import ValidationError, NotFound, PermissionDenied
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from core.responses import api_response
from domains.business.models import BusinessProfile
from domains.catalog.api.serializers import (
    ProductDetailReadSerializer,
    ProductFileReadSerializer,
    ProductFileUpdateSerializer,
    ProductFileWriteSerializer,
    ProductFileReorderSerializer,
    ProductListSerializer,
    ProductVariantSerializer,
    ProductVariantWriteSerializer,
    ProductVariantStatusSerializer,
)
from domains.catalog.models import (
    Brand,
    Category,
    Product,
    ProductFile,
    ProductStatus,
    ProductVariantStatus,
    ProductVariants,
)
from domains.catalog.services import ProductService, ProductFileService
from domains.files.api.serializers import FileUploadSerializer
from domains.files.services import FileService
from domains.inventory.services import InventoryService
from domains.inventory.services.inventory_pricing_service import InventoryPricingService
from domains.marketplace.models import BusinessOffer
from domains.marketplace.services import MarketplacePricingService
from domains.vendor.auth import VendorJWTAuthentication
from domains.vendor.services.vendor_product_service import VendorProductService
from domains.vendor.serializers.products import (
    VendorProductSimilarSerializer,
    VendorProductCreateSerializer,
    VendorProductUpdateSerializer,
    VendorProductListSerializer,
    VendorProductDetailSerializer,
)


product_service = ProductService()
product_file_service = ProductFileService()
file_service = FileService()
inventory_service = InventoryService()
pricing_service = InventoryPricingService()
vendor_product_service = VendorProductService()


def _get_business_category_ids(vendor):
    business = BusinessProfile.objects.filter(vendor=vendor).first()
    if not business:
        return None, []
    category_ids = list(business.categories.values_list("category_id", flat=True))
    return business, category_ids


def _get_vendor_product(product_id, category_ids):
    return get_object_or_404(Product, id=product_id, categories__id__in=category_ids)


# ─────────────────────── Filter Options ───────────────────────


class VendorProductFilterOptionsView(APIView):
    authentication_classes = [VendorJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        business, category_ids = _get_business_category_ids(request.user)
        if not business:
            return api_response(data={"categories": [], "brands": [], "statuses": []})

        categories = list(
            Category.objects.filter(id__in=category_ids)
            .order_by("name")
            .values("id", "name", "fa_name", "slug")
        )

        brand_ids = (
            Product.objects.filter(categories__id__in=category_ids)
            .values_list("brand_id", flat=True)
            .distinct()
        )
        brands = list(
            Brand.objects.filter(id__in=brand_ids)
            .order_by("name")
            .values("id", "name", "fa_name", "slug")
        )

        statuses = list(
            ProductStatus.objects.order_by("name").values("id", "name")
        )

        return api_response(data={
            "categories": categories,
            "brands": brands,
            "statuses": statuses,
        })


# ─────────────────────── Product List / Detail ───────────────────────


class VendorProductListView(APIView):
    authentication_classes = [VendorJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        _, category_ids = _get_business_category_ids(request.user)
        if not category_ids:
            return api_response(data={"count": 0, "next": None, "previous": None, "results": []})

        name = request.query_params.get("name")
        category_id = request.query_params.get("category_id")
        brand_id = request.query_params.get("brand_id")
        status_id = request.query_params.get("status_id")
        search = request.query_params.get("search")
        ordering = request.query_params.get("ordering")

        products = product_service.search_products(
            ordering=ordering,
            categories__id__in=category_ids,
            **({"name": name} if name else {}),
            **({"category_id": category_id} if category_id else {}),
            **({"brand_id": brand_id} if brand_id else {}),
            **({"status_id": status_id} if status_id else {}),
            **({"search": search} if search else {}),
        ).annotate(
            editable=vendor_product_service.get_editable_annotation(request.user),
            created_by_me=vendor_product_service.get_created_by_me_annotation(request.user),
        )

        from rest_framework.pagination import PageNumberPagination

        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(products, request, view=self)
        serializer = VendorProductListSerializer(page, many=True)
        return api_response(data=paginator.get_paginated_response(serializer.data).data)


class VendorProductDetailView(APIView):
    authentication_classes = [VendorJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, id):
        _, category_ids = _get_business_category_ids(request.user)
        if not category_ids:
            return api_response(False, "Business profile not found.", status_code=404)
        product = _get_vendor_product(id, category_ids)
        serialized = VendorProductDetailSerializer(product).data
        serialized["editable"] = vendor_product_service.can_vendor_edit(product, request.user)
        serialized["created_by_me"] = product.created_by_vendor_id == request.user.pk
        return api_response(data=serialized)


# ─────────────────────── Product Creation Flow ───────────────────────


class VendorProductSimilarSearchView(APIView):
    authentication_classes = [VendorJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        name = request.query_params.get("name", "").strip()
        if not name:
            return api_response(False, "Product name is required.", status_code=400)

        category_ids_raw = request.query_params.getlist("category_ids")
        category_ids = None
        if category_ids_raw:
            category_ids = []
            for raw_id in category_ids_raw:
                for part in raw_id.split(","):
                    part = part.strip()
                    if part:
                        try:
                            category_ids.append(int(part))
                        except ValueError:
                            pass
            if not category_ids:
                category_ids = None

        results = vendor_product_service.find_similar_products(
            name=name,
            category_ids=category_ids,
        )
        serializer = VendorProductSimilarSerializer(results, many=True)
        return api_response(data=serializer.data)


class VendorProductCreateView(APIView):
    authentication_classes = [VendorJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = VendorProductCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        brand = None
        if data.get("brand_id"):
            brand = Brand.objects.get(pk=data["brand_id"])

        try:
            product = vendor_product_service.create_vendor_product(
                vendor=request.user,
                name=data["name"],
                category_ids=data["category_ids"],
                brand=brand,
                description=data.get("description", ""),
                details=data.get("details", []),
            )
        except Exception as exc:
            raise ValidationError(str(exc)) from exc

        result = VendorProductDetailSerializer(product).data
        result["editable"] = True
        result["created_by_me"] = True
        return api_response(True, "Product created.", result, status_code=201)


class VendorProductEditableCheckView(APIView):
    authentication_classes = [VendorJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, id):
        _, category_ids = _get_business_category_ids(request.user)
        if not category_ids:
            return api_response(data={"editable": False})
        product = _get_vendor_product(id, category_ids)
        return api_response(data={
            "editable": vendor_product_service.can_vendor_edit(product, request.user),
        })


# ─────────────────────── Product Update (Edit) ───────────────────────


class VendorProductUpdateView(APIView):
    authentication_classes = [VendorJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, id):
        _, category_ids = _get_business_category_ids(request.user)
        if not category_ids:
            return api_response(False, "Business profile not found.", status_code=404)
        product = _get_vendor_product(id, category_ids)
        if not vendor_product_service.can_vendor_edit(product, request.user):
            raise PermissionDenied("You do not have permission to edit this product.")
        serialized = VendorProductDetailSerializer(product).data
        serialized["editable"] = True
        return api_response(data=serialized)

    def patch(self, request, id):
        _, category_ids = _get_business_category_ids(request.user)
        if not category_ids:
            return api_response(False, "Business profile not found.", status_code=404)
        product = _get_vendor_product(id, category_ids)
        if not vendor_product_service.can_vendor_edit(product, request.user):
            raise PermissionDenied("You do not have permission to edit this product.")
        serializer = VendorProductUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        vendor_product_service.update_vendor_product(product, request.user, **serializer.validated_data)
        product.refresh_from_db()
        result = VendorProductDetailSerializer(product).data
        result["editable"] = vendor_product_service.can_vendor_edit(product, request.user)
        return api_response(data=result)


# ─────────────────────── Product Form Options ───────────────────────


class VendorProductFormOptionsView(APIView):
    authentication_classes = [VendorJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        _, category_ids = _get_business_category_ids(request.user)
        if not category_ids:
            return api_response(data={"categories": [], "brands": []})

        categories = list(
            Category.objects.filter(id__in=category_ids)
            .select_related("parent")
            .order_by("name")
        )
        category_map = {category.id: category for category in categories}
        category_options = []
        for category in categories:
            path = [category.name]
            parent_id = category.parent_id
            seen = {category.id}
            while parent_id and parent_id not in seen:
                seen.add(parent_id)
                parent = category_map.get(parent_id)
                if not parent:
                    break
                path.append(parent.name)
                parent_id = parent.parent_id
            category_options.append({
                "id": category.id,
                "name": category.name,
                "fa_name": category.fa_name,
                "slug": category.slug,
                "path": " / ".join(reversed(path)),
            })

        brand_ids = (
            Product.objects.filter(categories__id__in=category_ids)
            .values_list("brand_id", flat=True)
            .distinct()
        )
        brands = list(
            Brand.objects.filter(id__in=brand_ids)
            .order_by("name")
            .values("id", "name", "fa_name", "slug")
        )

        return api_response(data={"categories": category_options, "brands": brands})


class VendorProductDetailDefinitionsView(APIView):
    authentication_classes = [VendorJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        _, category_ids = _get_business_category_ids(request.user)
        if not category_ids:
            return api_response(data=[])

        raw_ids = request.query_params.getlist("category_ids")
        requested_ids = [
            item
            for raw_id in raw_ids
            for item in raw_id.split(",")
            if item
        ]
        if requested_ids:
            valid_ids = [int(cid) for cid in requested_ids if int(cid) in category_ids]
        else:
            valid_ids = category_ids

        from domains.catalog.models import Category

        categories = Category.objects.filter(id__in=valid_ids)
        details, category_ids_by_detail = product_service.get_detail_definitions(categories)
        return api_response(data=[
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


# ─────────────────────── Product Files ───────────────────────


class VendorFileUploadView(APIView):
    authentication_classes = [VendorJWTAuthentication]
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        serializer = FileUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        try:
            file_obj = file_service.upload(
                values["file"],
                storage_alias=values["storage_alias"],
                metadata=values["metadata"],
                created_by=request.user,
            )
        except FileService.Error as exc:
            from rest_framework.exceptions import ValidationError
            raise ValidationError(str(exc)) from exc
        return api_response(
            True, "File uploaded.",
            {"id": str(file_obj.id), "url": file_service.url(file_obj)},
            status_code=201,
        )


class VendorProductFileListCreateView(APIView):
    authentication_classes = [VendorJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, product_id):
        _, category_ids = _get_business_category_ids(request.user)
        if not category_ids:
            return api_response(data=[])
        product = _get_vendor_product(product_id, category_ids)
        relations = product_file_service.list_for_product(product)
        return api_response(
            data=ProductFileReadSerializer(relations, many=True).data
        )

    def post(self, request, product_id):
        _, category_ids = _get_business_category_ids(request.user)
        if not category_ids:
            return api_response(False, "Business profile not found.", status_code=404)
        product = _get_vendor_product(product_id, category_ids)
        serializer = ProductFileWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            relation = product_file_service.attach(
                product, **serializer.validated_data
            )
        except ProductFileService.ValidationError as exc:
            from rest_framework.exceptions import ValidationError
            raise ValidationError(exc.errors) from exc
        return api_response(
            True,
            "File attached to product.",
            ProductFileReadSerializer(relation).data,
            status_code=201,
        )


class VendorProductFileDetailView(APIView):
    authentication_classes = [VendorJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def _get_relation(self, product_id, relation_id, category_ids):
        product = _get_vendor_product(product_id, category_ids)
        relation = product_file_service.get_for_product(product, relation_id)
        if relation is None:
            from rest_framework.exceptions import NotFound
            raise NotFound("Product file not found.")
        return relation

    def patch(self, request, product_id, relation_id):
        _, category_ids = _get_business_category_ids(request.user)
        if not category_ids:
            return api_response(False, "Business profile not found.", status_code=404)
        relation = self._get_relation(product_id, relation_id, category_ids)
        serializer = ProductFileUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            relation = product_file_service.update(
                relation, **serializer.validated_data
            )
        except ProductFileService.ValidationError as exc:
            from rest_framework.exceptions import ValidationError
            raise ValidationError(exc.errors) from exc
        return api_response(
            True,
            "Product file updated.",
            ProductFileReadSerializer(relation).data,
        )

    def delete(self, request, product_id, relation_id):
        _, category_ids = _get_business_category_ids(request.user)
        if not category_ids:
            return api_response(False, "Business profile not found.", status_code=404)
        relation = self._get_relation(product_id, relation_id, category_ids)
        product_file_service.delete(relation)
        return api_response(True, "File detached from product.", None)


class VendorProductFileReorderView(APIView):
    authentication_classes = [VendorJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def patch(self, request, product_id):
        _, category_ids = _get_business_category_ids(request.user)
        if not category_ids:
            return api_response(False, "Business profile not found.", status_code=404)
        product = _get_vendor_product(product_id, category_ids)
        serializer = ProductFileReorderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            relations = product_file_service.reorder(
                product, serializer.validated_data["files"]
            )
        except ProductFileService.ValidationError as exc:
            from rest_framework.exceptions import ValidationError
            raise ValidationError(exc.errors) from exc
        return api_response(
            True,
            "Product files reordered.",
            ProductFileReadSerializer(relations, many=True).data,
        )


# ─────────────────────── Product Variants ───────────────────────


class VendorProductVariantListCreateView(APIView):
    authentication_classes = [VendorJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, product_id):
        _, category_ids = _get_business_category_ids(request.user)
        if not category_ids:
            return api_response(data=[])
        product = _get_vendor_product(product_id, category_ids)
        variants = product_service.list_product_variants(
            product, search=request.query_params.get("search", "").strip() or None
        )
        return api_response(
            data=ProductVariantSerializer(variants, many=True).data
        )

    def post(self, request, product_id):
        _, category_ids = _get_business_category_ids(request.user)
        if not category_ids:
            return api_response(False, "Business profile not found.", status_code=404)
        product = _get_vendor_product(product_id, category_ids)
        if not vendor_product_service.can_add_variant(product):
            raise PermissionDenied("Variants cannot be added until the product is confirmed by an admin.")
        serializer = ProductVariantWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            variant = product_service.add_variant_to_product(
                product, **serializer.validated_data
            )
        except ProductService.ValidationError as exc:
            raise ValidationError(exc.errors) from exc
        result = ProductVariantSerializer(variant).data
        return api_response(True, "Variant added.", result, status_code=201)


class VendorProductVariantFormOptionsView(APIView):
    authentication_classes = [VendorJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, product_id):
        _, category_ids = _get_business_category_ids(request.user)
        if not category_ids:
            return api_response(False, "Business profile not found.", status_code=404)
        product = _get_vendor_product(product_id, category_ids)
        try:
            warehouse = inventory_service.get_default_warehouse()
        except InventoryService.ValidationError as exc:
            from rest_framework.exceptions import ValidationError
            raise ValidationError(exc.errors) from exc
        return api_response(data={
            "product": {
                "id": product.id,
                "name": product.name,
                "category": (lambda c: c.id if c else None)(product.categories.order_by("id").first()),
                "category_name": (lambda c: c.name if c else None)(product.categories.order_by("id").first()),
            },
            "inventory_strategies": pricing_service.get_strategies(),
            "default_warehouse": inventory_service.serialize_warehouse(warehouse),
            "attributes": product_service.get_variant_form_options(
                product, request.query_params.get("search")
            ),
        })


class VendorProductVariantDetailView(APIView):
    authentication_classes = [VendorJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def _get_vendor_variant(self, variant_id, category_ids):
        variant = get_object_or_404(ProductVariants, id=variant_id)
        if variant.product_id not in [
            pid for pid in
            Product.objects.filter(categories__id__in=category_ids).values_list("id", flat=True)
        ]:
            from rest_framework.exceptions import NotFound
            raise NotFound("Variant not found.")
        return variant

    def _sanitize_offer_payload(self, request_data):
        offer_fields = {"price", "discount_type", "discount_value"}
        offer_payload = {}
        for key in sorted(offer_fields):
            if key in request_data:
                value = request_data.get(key)
                if value == "":
                    value = None
                offer_payload[key] = value
        return offer_payload

    def _sync_business_offer(self, business, variant, payload):
        if not payload:
            return None
        cleaned = {}
        for key, value in payload.items():
            if value in ("", None):
                cleaned[key] = None
            else:
                cleaned[key] = value

        price = cleaned.get("price")
        discount_type = cleaned.get("discount_type")
        discount_value = cleaned.get("discount_value")
        offer = BusinessOffer.objects.filter(business=business, variant=variant).first()

        if price is None and discount_type is None and discount_value is None:
            return offer

        normalized = {
            "business": business,
            "variant": variant,
            "price": Decimal(str(price)) if price is not None else (offer.price if offer else Decimal("0")),
            "discount_type": discount_type if discount_type is not None else (offer.discount_type if offer else None),
            "discount_value": (
                Decimal(str(discount_value)) if discount_value is not None else (offer.discount_value if offer else None)
            ),
            "expected_profit_percentage": (
                offer.expected_profit_percentage if offer else Decimal("0")
            ),
            "cost_strategy": offer.cost_strategy if offer else "latest",
        }

        if offer is None:
            return MarketplacePricingService.create_offer(**normalized)

        return MarketplacePricingService.update_offer(offer, **{
            key: value
            for key, value in normalized.items()
            if key in {"price", "discount_type", "discount_value", "expected_profit_percentage", "cost_strategy"}
            if value is not None or key in {"expected_profit_percentage", "cost_strategy"}
        })

    def get(self, request, variant_id):
        _, category_ids = _get_business_category_ids(request.user)
        if not category_ids:
            return api_response(False, "Business profile not found.", status_code=404)
        variant = self._get_vendor_variant(variant_id, category_ids)
        variant_data = ProductVariantSerializer(variant).data

        business = BusinessProfile.objects.filter(vendor=request.user).first()
        offer = None
        if business:
            offer = BusinessOffer.objects.filter(
                business=business,
                variant=variant,
                is_active=True,
            ).first()

        return api_response(data={
            **variant_data,
            "product": {
                "id": variant.product_id,
                "name": variant.product.name,
                "category_name": variant.product.categories.first().name if variant.product.categories.exists() else None,
                "category_fa_name": variant.product.categories.first().fa_name if variant.product.categories.exists() else None,
            },
            "pricing": {
                "price": str(offer.price) if offer else "0",
                "discount_type": offer.discount_type if offer else None,
                "discount_value": str(offer.discount_value) if offer else None,
            } if offer else None,
        })

    def patch(self, request, variant_id):
        _, category_ids = _get_business_category_ids(request.user)
        if not category_ids:
            return api_response(False, "Business profile not found.", status_code=404)
        variant = self._get_vendor_variant(variant_id, category_ids)
        business = BusinessProfile.objects.filter(vendor=request.user).first()
        if not business:
            return api_response(False, "Business profile not found.", status_code=404)

        offer_payload = self._sanitize_offer_payload(request.data)
        if offer_payload:
            data = request.data.copy()
            for key in ["price", "discount_type", "discount_value"]:
                data.pop(key, None)
        else:
            data = request.data.copy()

        serializer = ProductVariantWriteSerializer(variant, data=data, partial=True)
        serializer.is_valid(raise_exception=True)
        try:
            variant = product_service.update_variant(
                variant,
                business=business,
                **serializer.validated_data,
            )
        except ProductService.ValidationError as exc:
            from rest_framework.exceptions import ValidationError
            raise ValidationError(exc.errors) from exc

        self._sync_business_offer(business, variant, offer_payload)
        result = ProductVariantSerializer(variant).data
        return api_response(data=result)


class VendorVariantStatusView(APIView):
    authentication_classes = [VendorJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def patch(self, request, variant_id):
        _, category_ids = _get_business_category_ids(request.user)
        if not category_ids:
            return api_response(False, "Business profile not found.", status_code=404)

        variant = get_object_or_404(ProductVariants, id=variant_id)
        product_ids = set(
            Product.objects.filter(categories__id__in=category_ids).values_list("id", flat=True)
        )
        if variant.product_id not in product_ids:
            from rest_framework.exceptions import NotFound
            raise NotFound("Variant not found.")

        status_id = request.data.get("status_id")
        if status_id is None:
            from rest_framework.exceptions import ValidationError
            raise ValidationError({"status_id": "This field is required."})
        try:
            variant = product_service.update_variant(variant, status_id=status_id)
        except ProductService.ValidationError as exc:
            from rest_framework.exceptions import ValidationError
            raise ValidationError(exc.errors) from exc
        result = ProductVariantSerializer(variant).data
        return api_response(data=result)


class VendorVariantStatusesView(APIView):
    authentication_classes = [VendorJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        statuses = ProductVariantStatus.objects.all().order_by("id")
        return api_response(
            data=ProductVariantStatusSerializer(statuses, many=True).data
        )
