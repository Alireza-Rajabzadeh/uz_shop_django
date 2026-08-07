from decimal import Decimal, InvalidOperation

from django.db import IntegrityError, transaction
from django.db.models import Count, Exists, OuterRef, Prefetch, Q, Subquery
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext as _

from core.services.base import BaseService
from domains.catalog.models import (
    Brand,
    Category,
    CategoryDetail,
    CategoryDetailOption,
    CategoryDetailRelation,
    Product,
    ProductDetails,
    ProductFile,
    ProductStatus,
    ProductVariants,
    ProductVariantSelection,
    VariantAttribute,
)
from domains.inventory.models import InventoryStrategy
from domains.inventory.services import InventoryService


class ProductService(BaseService):
    model = Product
    inventory_service = InventoryService()

    class ValidationError(Exception):
        def __init__(self, errors):
            self.errors = errors
            super().__init__(str(errors))

    def create_product(self, **data):
        data["status"] = ProductStatus.objects.get(name__iexact="pending")
        return self._create(**data)

    def update_product(self, instance, **data):
        return self._update(instance, **data)

    def delete_product(self, instance):
        self._delete(instance)

    def get_product(self, id):
        return self._get(id)

    def get_product_details(self, id):
        variants = self._variant_queryset()
        return get_object_or_404(
            self.model.objects.select_related("status").prefetch_related(
                "categories",
                Prefetch(
                    "details",
                    queryset=ProductDetails.objects.select_related("detail").order_by("detail__name", "id"),
                ),
                Prefetch("variants", queryset=variants),
                Prefetch(
                    "product_files",
                    queryset=ProductFile.objects.select_related(
                        "file", "file__status"
                    ).order_by("position", "id"),
                    to_attr="ordered_files",
                ),
            ),
            id=id,
        )

    @staticmethod
    def _primary_category_id(product):
        return product.categories.order_by("id").values_list("id", flat=True).first()

    def get_filter_options(self):
        return {
            "categories": self.get_form_options(),
            "brands": self._brand_options(),
            "statuses": list(ProductStatus.objects.order_by("name").values("id", "name")),
        }

    @staticmethod
    def _brand_options():
        return list(
            Brand.objects.order_by("name", "id").values("id", "name", "fa_name")
        )

    @staticmethod
    def _numeric_values(search):
        integer = int(search) if search.isdigit() and int(search) > 0 else None
        try:
            decimal = Decimal(search)
            if not decimal.is_finite() or decimal < 0:
                decimal = None
        except (InvalidOperation, ValueError):
            decimal = None
        return integer, decimal

    def _variant_search_queryset(self, search):
        variants = self.inventory_service.annotate_variant_summaries(ProductVariants.objects.all())
        query = (
            Q(sku__icontains=search)
            | Q(discount_type__icontains=search)
            | Q(inventory_strategy__code__icontains=search)
            | Q(inventory_strategy__name__icontains=search)
            | Q(selections__attribute__name__icontains=search)
            | Q(selections__option__name__icontains=search)
            | Q(selections__option__sku_code__icontains=search)
        )
        integer, decimal = self._numeric_values(search)
        if integer is not None:
            query |= (
                Q(id=integer) | Q(product_id=integer) | Q(inventory_strategy_id=integer)
                | Q(selections__attribute_id=integer) | Q(selections__option_id=integer)
                | Q(total_item_count=integer) | Q(sellable_item_count=integer)
                | Q(available_item_count=integer)
            )
        if decimal is not None:
            query |= Q(price=decimal) | Q(discount_value=decimal)
        return variants.filter(query)

    def search_products(self, ordering=None, **filters):
        ordering_fields = {
            "id": "id",
            "name": "name",
            "category_name": "primary_category_name",
            "brand_name": "brand__name",
            "status_name": "status__name",
            "variant_count": "variant_count",
        }
        name = filters.pop("name", None)
        search = filters.pop("search", None)
        category_id = filters.pop("category_id", None)
        price_operator = filters.pop("price_operator", None)
        price = filters.pop("price", None)
        price_min = filters.pop("price_min", None)
        price_max = filters.pop("price_max", None)
        list_media = ProductFile.objects.filter(
            file__file_type="image",
            file__status__name="available",
            file__deleted_at__isnull=True,
        ).select_related("file", "file__status").order_by("-is_primary", "position", "id")
        primary_category = Category.objects.filter(
            products=OuterRef("pk")
        ).order_by("id").values("name")[:1]
        queryset = (
            self.model.objects.filter(**filters)
            .select_related("status")
            .prefetch_related(
                "categories",
                Prefetch("product_files", queryset=list_media, to_attr="list_media"),
            )
            .annotate(primary_category_name=Subquery(primary_category))
        )
        if name:
            queryset = queryset.filter(name__icontains=name)
        if category_id:
            queryset = queryset.filter(categories__id=category_id).distinct()
        if price_operator:
            matching_prices = ProductVariants.objects.filter(product_id=OuterRef("pk"))
            if price_operator == "equal":
                matching_prices = matching_prices.filter(price=price)
            elif price_operator == "less_than":
                matching_prices = matching_prices.filter(price__lt=price)
            elif price_operator == "greater_than":
                matching_prices = matching_prices.filter(price__gt=price)
            else:
                matching_prices = matching_prices.filter(price__gte=price_min, price__lte=price_max)
            queryset = queryset.filter(Exists(matching_prices))
        if search:
            base_query = (
                Q(name__icontains=search) | Q(description__icontains=search)
                | Q(categories__name__icontains=search) | Q(status__name__icontains=search)
            )
            integer, _ = self._numeric_values(search)
            if integer is not None:
                base_query |= Q(id=integer) | Q(categories__id=integer) | Q(status_id=integer)
            matching_details = ProductDetails.objects.filter(product_id=OuterRef("pk")).filter(
                Q(detail__name__icontains=search) | Q(detail__type__icontains=search)
                | Q(value__icontains=search) | Q(extra_value__icontains=search)
            )
            matching_variants = self._variant_search_queryset(search).filter(product_id=OuterRef("pk"))
            queryset = queryset.filter(
                base_query | Exists(matching_details) | Exists(matching_variants)
            ).distinct()
        queryset = queryset.annotate(variant_count=Count("variants", distinct=True))
        descending = ordering and ordering.startswith("-")
        requested_field = ordering.lstrip("-") if ordering else "id"
        order_field = ordering_fields.get(requested_field, "id")
        return queryset.order_by(f"-{order_field}" if descending else order_field)

    def list_by_category(self, category_id):
        return self.model.objects.filter(categories__id=category_id)

    def get_form_options(self):
        categories = list(Category.objects.select_related("parent").order_by("name"))
        category_map = {category.id: category for category in categories}
        options = []
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
            options.append({
                "id": category.id,
                "name": category.name,
                "path": " / ".join(reversed(path)),
            })
        return options

    def get_detail_definitions(self, categories):
        details = CategoryDetail.objects.filter(
            categorydetailrelation__category__in=categories
        ).distinct().order_by("name")
        category_ids_by_detail = {}
        for detail_id, category_id in CategoryDetailRelation.objects.filter(
            category__in=categories
        ).values_list("detail_id", "category_id"):
            category_ids_by_detail.setdefault(detail_id, []).append(category_id)
        return details, category_ids_by_detail

    @transaction.atomic
    def create_complete_product(
        self, *, name, category_ids, description=None, brand=None, details=()
    ):
        categories = list(category_ids)
        self._validate_complete_product_details(categories, details)

        product = self.model.objects.create(
            name=name.strip(),
            status=ProductStatus.objects.get(name__iexact="pending"),
            brand=brand,
            description=description or "",
        )
        product.categories.set(categories)
        self._replace_product_details(product, details)
        return product

    @transaction.atomic
    def update_complete_product(
        self, product, *, name, category_ids, description=None, brand=None, details=()
    ):
        product = self.model.objects.select_for_update().get(pk=product.pk)
        categories = list(category_ids)
        previous_ids = set(product.categories.values_list("id", flat=True))
        self._validate_complete_product_details(categories, details)

        product.name = name.strip()
        product.brand = brand
        product.description = description or ""
        product.save(update_fields=["name", "brand", "description"])
        product.categories.set(categories)
        self._replace_product_details(product, details)
        if {category.id for category in categories} != previous_ids:
            try:
                with transaction.atomic():
                    self.regenerate_product_variant_skus(product)
            except IntegrityError as exc:
                raise self.ValidationError({
                    "category_ids": [_('Changing the category caused a generated SKU conflict.')]
                }) from exc
        return product

    def _validate_complete_product_details(self, categories, details):
        assigned_details = {
            detail.id: detail
            for detail in CategoryDetail.objects.filter(
                categorydetailrelation__category__in=categories
            ).distinct()
        }
        supplied_details = {item["detail"].id: item for item in details}

        if set(supplied_details) - set(assigned_details):
            raise self.ValidationError({
                "details": [_("One or more details are not assigned to the selected category.")]
            })
        self._validate_detail_values(
            definitions=assigned_details,
            supplied=supplied_details,
            items=details,
        )

    def _replace_product_details(self, product, details):
        product.details.all().delete()
        ProductDetails.objects.bulk_create([
            ProductDetails(
                product=product,
                detail=item["detail"],
                option=self._get_detail_option(item["detail"], item["value"]),
                value=item["value"],
            )
            for item in details
            if item["value"] or item["detail"].required
        ])

    @staticmethod
    def _get_detail_option(detail, value):
        if not value or not detail.filterable or not detail.options:
            return None
        return CategoryDetailOption.objects.filter(
            detail=detail,
            name__iexact=value,
        ).first()

    def _validate_detail_values(self, *, definitions, supplied, items):
        missing_required = [
            detail.name
            for detail in definitions.values()
            if detail.required and not supplied.get(detail.id, {}).get("value", "").strip()
        ]
        if missing_required:
            raise self.ValidationError({
                "details": [
                    _("Required product details are missing: {names}.").format(
                        names=", ".join(sorted(missing_required))
                    )
                ]
            })

        for item in items:
            detail = item["detail"]
            value = item["value"].strip()
            if detail.type == "select" and value:
                options = [option.strip() for option in detail.options.split(",") if option.strip()]
                if value not in options:
                    raise self.ValidationError({
                        "details": [
                            _("'{value}' is not valid for {name}.").format(
                                value=value, name=detail.name
                            )
                        ]
                    })
            if detail.type == "number" and value:
                try:
                    number = Decimal(value)
                except InvalidOperation as exc:
                    raise self.ValidationError({
                        "details": [_('{name} must be a number.').format(name=detail.name)]
                    }) from exc
                if not number.is_finite():
                    raise self.ValidationError({
                        "details": [_('{name} must be a finite number.').format(name=detail.name)]
                    })
                value = "0" if number == 0 else format(number.normalize(), "f")
            item["value"] = value

    @transaction.atomic
    def add_detail_to_product(self, product, details_data):
        detail_ids = [item.get("detail_id") for item in details_data]
        if len(detail_ids) != len(set(detail_ids)):
            raise self.ValidationError({
                "details": [_("Each product detail can only be submitted once.")]
            })
        definitions = {
            detail.id: detail
            for detail in CategoryDetail.objects.filter(
                id__in=detail_ids,
                categorydetailrelation__category__in=product.categories.all(),
            ).distinct()
        }
        if set(detail_ids) != set(definitions):
            raise self.ValidationError({
                "details": [_("One or more details are not assigned to the selected category.")]
            })
        items = [
            {"detail": definitions[item["detail_id"]], "value": item.get("value", "")}
            for item in details_data
        ]
        self._validate_detail_values(definitions={}, supplied={}, items=items)
        instances = []
        for raw_item, item in zip(details_data, items):
            obj, _created = ProductDetails.objects.update_or_create(
                product=product,
                detail=item["detail"],
                defaults={
                    "value": item["value"],
                    "option": self._get_detail_option(item["detail"], item["value"]),
                    "extra_value": raw_item.get("extra_value"),
                },
            )
            instances.append(obj)
        return instances

    def list_product_details(self, product):
        return ProductDetails.objects.filter(product=product).select_related("detail")

    def get_variant_form_options(self, product, search=None):
        category_attribute_ids = set(VariantAttribute.objects.filter(
            category_assignments__category__in=product.categories.all()
        ).values_list("id", flat=True))
        attributes = VariantAttribute.objects.prefetch_related("options").order_by("name", "id")
        result = []
        search = search.casefold() if search else None
        for attribute in attributes:
            options = list(attribute.options.all())
            attribute_matches = search and search in attribute.name.casefold()
            option_matches = search and any(
                search in value.casefold()
                for option in options
                for value in (option.name, option.fa_name, option.sku_code)
            )
            if search and not attribute_matches and not option_matches:
                continue
            result.append({
                "id": attribute.id,
                "name": attribute.name,
                "category_default": attribute.id in category_attribute_ids,
                "options": [
                    {
                        "id": option.id,
                        "name": option.name,
                        "fa_name": option.fa_name,
                        "info": option.info,
                        "sku_code": option.sku_code,
                    }
                    for option in options
                ],
            })
        return result

    @transaction.atomic
    def add_variant_to_product(
        self,
        product,
        *,
        selections=(),
        inventory_strategy_code,
        inventory=None,
        serial_items=None,
        inventory_submitted=True,
        **variant_data,
    ):
        selections = self._validate_variant_selections(selections)
        combination_key = self._build_combination_key(selections)
        sku = self._build_sku(product, selections)
        try:
            with transaction.atomic():
                variant = ProductVariants.objects.create(
                    product=product,
                    inventory_strategy=InventoryStrategy.objects.get(code=inventory_strategy_code),
                    combination_key=combination_key,
                    sku=sku,
                    **variant_data,
                )
                self._replace_variant_selections(variant, selections)
        except IntegrityError as exc:
            raise self.ValidationError({
                "selections": [_('This option combination or generated SKU already exists.')]
            }) from exc
        try:
            self.inventory_service.apply_variant_inventory(
                variant,
                strategy_code=inventory_strategy_code,
                inventory=inventory,
                serial_items=serial_items,
                inventory_submitted=inventory_submitted,
            )
        except InventoryService.ValidationError as exc:
            raise self.ValidationError(exc.errors) from exc
        return variant

    def _variant_queryset(self):
        queryset = ProductVariants.objects.select_related(
            "inventory_strategy"
        ).prefetch_related(
            "selections__attribute", "selections__option",
            "warehouse_stocks", "serialized_stocks__status",
        )
        return self.inventory_service.annotate_variant_summaries(queryset).order_by("id")

    def list_product_variants(self, product, search=None):
        queryset = self._variant_queryset().filter(product=product)
        if search:
            matching_ids = self._variant_search_queryset(search).values("id")
            queryset = queryset.filter(id__in=matching_ids)
        return queryset

    def get_variant(self, id):
        return get_object_or_404(
            ProductVariants.objects.select_related("product", "inventory_strategy").prefetch_related(
                "selections__attribute", "selections__option",
                "warehouse_stocks", "serialized_stocks__status",
            ),
            id=id,
        )

    @transaction.atomic
    def update_variant(
        self,
        instance,
        *,
        selections=None,
        inventory_strategy_code=None,
        inventory=None,
        serial_items=None,
        inventory_submitted=False,
        **data,
    ):
        instance = ProductVariants.objects.select_for_update().select_related("product").get(
            pk=instance.pk
        )
        normalized = None
        if selections is not None:
            normalized = self._validate_variant_selections(selections)
            instance.combination_key = self._build_combination_key(normalized)
            instance.sku = self._build_sku(instance.product, normalized)
        for attr, value in data.items():
            setattr(instance, attr, value)
        try:
            with transaction.atomic():
                instance.save()
                if normalized is not None:
                    self._replace_variant_selections(instance, normalized)
        except IntegrityError as exc:
            raise self.ValidationError({
                "selections": [_('This option combination or generated SKU already exists.')]
            }) from exc
        try:
            self.inventory_service.apply_variant_inventory(
                instance,
                strategy_code=inventory_strategy_code or instance.inventory_strategy.code,
                inventory=inventory,
                serial_items=serial_items,
                inventory_submitted=inventory_submitted,
            )
        except InventoryService.ValidationError as exc:
            raise self.ValidationError(exc.errors) from exc
        return instance

    def _validate_variant_selections(self, selections):
        if not selections:
            raise self.ValidationError({
                "selections": [_('At least one variant selection is required.')]
            })
        attribute_ids = [item["attribute"].id for item in selections]
        if len(attribute_ids) != len(set(attribute_ids)):
            raise self.ValidationError({
                "selections": [_('Each attribute can only be selected once.')]
            })
        for item in selections:
            if item["option"].attribute_id != item["attribute"].id:
                raise self.ValidationError({
                    "selections": [_('Each option must belong to its submitted attribute.')]
                })
        return sorted(selections, key=lambda item: item["attribute"].id)

    @staticmethod
    def _build_combination_key(selections):
        return "|".join(
            f'{item["attribute"].id}:{item["option"].id}' for item in selections
        )

    @staticmethod
    def _build_sku(product, selections):
        suffix = "-".join(item["option"].sku_code for item in selections)
        return f"CG{ProductService._primary_category_id(product) or 0}-PD{product.id}-{suffix}"

    def _replace_variant_selections(self, variant, selections):
        variant.selections.all().delete()
        ProductVariantSelection.objects.bulk_create([
            ProductVariantSelection(
                variant=variant,
                attribute=item["attribute"],
                option=item["option"],
            )
            for item in selections
        ])

    def regenerate_variants_for_option(self, option):
        variants = ProductVariants.objects.select_for_update().filter(
            selections__option=option
        ).select_related("product").prefetch_related(
            "selections__attribute", "selections__option"
        )
        self._regenerate_variant_skus(variants)

    def regenerate_product_variant_skus(self, product):
        variants = ProductVariants.objects.select_for_update().filter(
            product=product
        ).select_related("product").prefetch_related(
            "selections__attribute", "selections__option"
        )
        self._regenerate_variant_skus(variants)

    def _regenerate_variant_skus(self, variants):
        for variant in variants:
            selections = sorted(
                ({"attribute": row.attribute, "option": row.option} for row in variant.selections.all()),
                key=lambda item: item["attribute"].id,
            )
            variant.sku = self._build_sku(variant.product, selections)
            variant.save(update_fields=["sku"])

    def delete_variant(self, instance):
        try:
            self.inventory_service.validate_variant_deletion(instance)
        except InventoryService.ValidationError as exc:
            raise self.ValidationError(exc.errors) from exc
        instance.delete()

    def search_variants(self, search=None, **filters):
        queryset = self._variant_queryset().filter(**filters)
        if search:
            queryset = queryset.filter(id__in=self._variant_search_queryset(search).values("id"))
        return queryset
