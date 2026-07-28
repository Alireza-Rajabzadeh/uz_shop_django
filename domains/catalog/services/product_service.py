from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.db.models import Count
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext as _

from core.services.base import BaseService
from domains.catalog.models import (
    Category,
    CategoryDetail,
    CategoryDetailRelation,
    Product,
    ProductDetails,
    ProductStatus,
    ProductVariants,
    ProductVariantsDetails,
)
from domains.inventory.models import InventoryStrategy


class ProductService(BaseService):
    model = Product

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

    def search_products(self, ordering=None, **filters):
        ordering_fields = {
            "id": "id",
            "name": "name",
            "category_name": "category__name",
            "status_name": "status__name",
            "variant_count": "variant_count",
        }
        queryset = (
            self.model.objects.filter(**filters)
            .select_related("category", "status")
            .annotate(variant_count=Count("variants"))
        )
        descending = ordering and ordering.startswith("-")
        requested_field = ordering.lstrip("-") if ordering else "id"
        order_field = ordering_fields.get(requested_field, "id")
        return queryset.order_by(f"-{order_field}" if descending else order_field)

    def list_by_category(self, category_id):
        return self.model.objects.filter(category_id=category_id)

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
        self, *, name, category_ids, description=None, details=()
    ):
        category = Category.objects.select_for_update().get(pk=category_ids[0].pk)
        self._validate_complete_product_details(category, details)

        product = self.model.objects.create(
            name=name.strip(),
            status=ProductStatus.objects.get(name__iexact="pending"),
            category=category,
            description=description or "",
        )
        self._replace_product_details(product, details)
        return product

    @transaction.atomic
    def update_complete_product(
        self, product, *, name, category_ids, description=None, details=()
    ):
        product = self.model.objects.select_for_update().get(pk=product.pk)
        category = Category.objects.select_for_update().get(pk=category_ids[0].pk)
        self._validate_complete_product_details(category, details)

        product.name = name.strip()
        product.category = category
        product.description = description or ""
        product.save(update_fields=["name", "category", "description"])
        self._replace_product_details(product, details)
        return product

    def _validate_complete_product_details(self, category, details):
        assigned_details = {
            detail.id: detail
            for detail in CategoryDetail.objects.filter(
                categorydetailrelation__category=category
            )
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
            ProductDetails(product=product, detail=item["detail"], value=item["value"])
            for item in details
            if item["value"] or item["detail"].required
        ])

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
                categorydetailrelation__category=product.category,
            )
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
                defaults={"value": item["value"], "extra_value": raw_item.get("extra_value")},
            )
            instances.append(obj)
        return instances

    def list_product_details(self, product):
        return ProductDetails.objects.filter(product=product).select_related("detail")

    def get_variant_form_options(self, product):
        category_detail_ids = set(CategoryDetailRelation.objects.filter(
            category=product.category
        ).values_list("detail_id", flat=True))
        details = CategoryDetail.objects.order_by(
            "name"
        )
        return [{
            "id": detail.id,
            "name": detail.name,
            "type": detail.type,
            "required": detail.required,
            "filterable": detail.filterable,
            "options": [
                option.strip() for option in detail.options.split(",") if option.strip()
            ],
            "category_default": detail.id in category_detail_ids,
        } for detail in details]

    @transaction.atomic
    def add_variant_to_product(self, product, *, details=(), **variant_data):
        self._validate_variant_details(details)
        variant = ProductVariants.objects.create(
            product=product,
            inventory_strategy=InventoryStrategy.objects.get(code="normal"),
            **variant_data,
        )
        self._replace_variant_details(variant, details)
        return variant

    def list_product_variants(self, product):
        return ProductVariants.objects.filter(product=product).select_related(
            "inventory_strategy"
        ).prefetch_related("details__detail").order_by("id")

    def get_variant(self, id):
        return get_object_or_404(ProductVariants, id=id)

    @transaction.atomic
    def update_variant(self, instance, *, details=None, **data):
        if details is not None:
            self._validate_variant_details(details)
        for attr, value in data.items():
            setattr(instance, attr, value)
        instance.save()
        if details is not None:
            self._replace_variant_details(instance, details)
        return instance

    def _validate_variant_details(self, details):
        definitions = {item["detail"].id: item["detail"] for item in details}
        supplied = {item["detail"].id: item for item in details}
        self._validate_detail_values(
            definitions=definitions,
            supplied=supplied,
            items=details,
        )

    def _replace_variant_details(self, variant, details):
        variant.details.all().delete()
        ProductVariantsDetails.objects.bulk_create([
            ProductVariantsDetails(
                variant=variant,
                detail=item["detail"],
                value=item["value"],
            )
            for item in details
        ])

    def delete_variant(self, instance):
        instance.delete()

    def search_variants(self, **filters):
        return ProductVariants.objects.filter(**filters).select_related(
            "inventory_strategy"
        ).prefetch_related("details__detail")
