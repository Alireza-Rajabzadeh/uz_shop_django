from decimal import Decimal

from django.contrib.postgres.search import SearchQuery, SearchRank, SearchVector, TrigramSimilarity
from django.db.models import (
    BooleanField,
    Case,
    Count,
    DecimalField,
    Exists,
    ExpressionWrapper,
    F,
    IntegerField,
    Max,
    Min,
    OuterRef,
    Prefetch,
    Q,
    Subquery,
    Value,
    When,
)
from django.db.models.functions import Coalesce, Lower, Replace

from domains.catalog.models import (
    Category,
    CategoryDetail,
    Product,
    ProductDetails,
    ProductFile,
    ProductVariants,
    ProductVariantSelection,
    VariantAttribute,
)
from domains.files.services import FileService
from domains.inventory.services import InventoryService

from .contracts import ProductSearchCriteria, ProductSearchResult
from .normalization import normalize_search_text


PRICE_FIELD = DecimalField(max_digits=15, decimal_places=2)


def normalized_text_expression(field):
    expression = Lower(Coalesce(F(field), Value("")))
    for source, replacement in (
        ("ي", "ی"), ("ى", "ی"), ("ك", "ک"), ("ة", "ه"),
        ("ۀ", "ه"), ("ؤ", "و"), ("إ", "ا"), ("أ", "ا"),
        ("ٱ", "ا"), ("ـ", ""), ("\u200c", " "), ("\u200d", " "),
    ):
        expression = Replace(expression, Value(source), Value(replacement))
    return expression


def effective_price_expression(prefix=""):
    price = F(f"{prefix}price")
    discount_value = F(f"{prefix}discount_value")
    percentage_discount = ExpressionWrapper(
        price * discount_value / Value(Decimal("100")),
        output_field=PRICE_FIELD,
    )
    return Case(
        When(
            **{
                f"{prefix}discount_type": "percentage",
                f"{prefix}discount_value__isnull": False,
                "then": ExpressionWrapper(price - percentage_discount, output_field=PRICE_FIELD),
            },
        ),
        When(
            **{
                f"{prefix}discount_type": "fixed",
                f"{prefix}discount_value__isnull": False,
                "then": ExpressionWrapper(price - discount_value, output_field=PRICE_FIELD),
            },
        ),
        default=price,
        output_field=PRICE_FIELD,
    )


class PostgresProductSearchBackend:
    inventory_service = InventoryService()

    def search(self, criteria):
        queryset = self._apply_filters(self._base_queryset(criteria), criteria)
        queryset = self._annotate_result_fields(queryset, criteria)
        count = queryset.order_by().count()
        queryset = self._order(queryset, criteria)
        start = (criteria.page - 1) * criteria.page_size
        products = list(self._load_result_relations(queryset[start:start + criteria.page_size]))
        return ProductSearchResult(
            count=count,
            page=criteria.page,
            page_size=criteria.page_size,
            results=[self._serialize_product(product) for product in products],
            facets=self._build_facets(criteria) if criteria.include_facets else {},
        )

    def _public_products(self):
        inactive_category_ids = self._inactive_category_tree_ids()
        queryset = Product.objects.filter(
            status__name__iexact="active",
            category__status__name__iexact="active",
        )
        if inactive_category_ids:
            queryset = queryset.exclude(category_id__in=inactive_category_ids)
        return queryset

    @staticmethod
    def _inactive_category_tree_ids():
        categories = list(Category.objects.values("id", "parent_id", "status__name"))
        children = {}
        inactive = set()
        for category in categories:
            children.setdefault(category["parent_id"], []).append(category["id"])
            if category["status__name"].casefold() != "active":
                inactive.add(category["id"])
        pending = list(inactive)
        while pending:
            child_ids = children.get(pending.pop(), ())
            for child_id in child_ids:
                if child_id not in inactive:
                    inactive.add(child_id)
                    pending.append(child_id)
        return inactive

    def _base_queryset(self, criteria):
        queryset = self._public_products()
        if not criteria.query:
            return queryset.annotate(search_rank=Value(0.0))

        query_text = normalize_search_text(criteria.query)
        vector = (
            SearchVector("name", config="simple", weight="A")
            + SearchVector("brand__name", config="simple", weight="A")
            + SearchVector("category__name", config="simple", weight="B")
            + SearchVector("description", config="simple", weight="D")
        )
        search_query = SearchQuery(query_text, config="simple", search_type="websearch")
        matching_details = ProductDetails.objects.filter(product_id=OuterRef("pk")).annotate(
            normalized_detail_name=normalized_text_expression("detail__name"),
            normalized_value=normalized_text_expression("value"),
            normalized_extra_value=normalized_text_expression("extra_value"),
        ).filter(
            Q(normalized_detail_name__icontains=query_text)
            | Q(normalized_value__icontains=query_text)
            | Q(normalized_extra_value__icontains=query_text)
        )
        matching_variants = ProductVariantSelection.objects.filter(
            variant__product_id=OuterRef("pk")
        ).annotate(
            normalized_attribute=normalized_text_expression("attribute__name"),
            normalized_option=normalized_text_expression("option__name"),
        ).filter(
            Q(normalized_attribute__icontains=query_text)
            | Q(normalized_option__icontains=query_text)
        )
        return queryset.annotate(
            normalized_name=normalized_text_expression("name"),
            normalized_brand=normalized_text_expression("brand__name"),
            normalized_category=normalized_text_expression("category__name"),
            search_rank=(
                SearchRank(vector, search_query)
                + TrigramSimilarity(normalized_text_expression("name"), query_text)
            ),
        ).filter(
            Q(search_rank__gt=0.02)
            | Q(normalized_name__icontains=query_text)
            | Q(normalized_brand__icontains=query_text)
            | Q(normalized_category__icontains=query_text)
            | Exists(matching_details)
            | Exists(matching_variants)
        )

    def _apply_filters(self, queryset, criteria, excluded=None):
        excluded = excluded or ""
        if criteria.category_ids and excluded != "category":
            queryset = queryset.filter(category_id__in=self._category_tree_ids(criteria.category_ids))
        if criteria.brand_ids and excluded != "brand":
            queryset = queryset.filter(brand_id__in=criteria.brand_ids)

        for selection in criteria.detail_filters:
            if excluded == f"detail:{selection.field_id}":
                continue
            matching = ProductDetails.objects.filter(
                product_id=OuterRef("pk"),
                detail_id=selection.field_id,
                option_id__in=selection.value_ids,
            )
            queryset = queryset.filter(Exists(matching))

        for selection in criteria.variant_filters:
            if excluded == f"variant:{selection.field_id}":
                continue
            matching = ProductVariantSelection.objects.filter(
                variant__product_id=OuterRef("pk"),
                attribute_id=selection.field_id,
                option_id__in=selection.value_ids,
            )
            queryset = queryset.filter(Exists(matching))

        variants = ProductVariants.objects.filter(product_id=OuterRef("pk")).annotate(
            effective_price=effective_price_expression()
        )
        if excluded != "price":
            if criteria.minimum_price is not None:
                variants = variants.filter(effective_price__gte=criteria.minimum_price)
            if criteria.maximum_price is not None:
                variants = variants.filter(effective_price__lte=criteria.maximum_price)
            if criteria.minimum_price is not None or criteria.maximum_price is not None:
                queryset = queryset.filter(Exists(variants))

        if criteria.in_stock is not None and excluded != "availability":
            queryset = queryset.annotate(_filter_in_stock=Exists(self._available_variants()))
            queryset = queryset.filter(_filter_in_stock=criteria.in_stock)
        if criteria.on_sale is not None and excluded != "sale":
            queryset = queryset.annotate(_filter_on_sale=Exists(self._sale_variants()))
            queryset = queryset.filter(_filter_on_sale=criteria.on_sale)
        return queryset

    @staticmethod
    def _category_tree_ids(category_ids):
        selected = set(category_ids)
        pending = list(category_ids)
        children = {}
        for category_id, parent_id in Category.objects.values_list("id", "parent_id"):
            children.setdefault(parent_id, []).append(category_id)
        while pending:
            for child_id in children.get(pending.pop(), ()):
                if child_id not in selected:
                    selected.add(child_id)
                    pending.append(child_id)
        return selected

    def _available_variants(self):
        variants = ProductVariants.objects.filter(product_id=OuterRef("pk"))
        return self.inventory_service.annotate_variant_summaries(variants).filter(
            available_item_count__gt=0
        )

    @staticmethod
    def _sale_variants():
        return ProductVariants.objects.filter(
            product_id=OuterRef("pk"),
            discount_value__gt=0,
        ).exclude(discount_type__isnull=True)

    def _exact_variants(self, criteria):
        variants = ProductVariants.objects.filter(product_id=OuterRef("pk"))
        for selection in criteria.variant_filters:
            matching = ProductVariantSelection.objects.filter(
                variant_id=OuterRef("pk"),
                attribute_id=selection.field_id,
                option_id__in=selection.value_ids,
            )
            variants = variants.filter(Exists(matching))
        return variants.order_by("id")

    def _annotate_result_fields(self, queryset, criteria):
        price = effective_price_expression("variants__")
        queryset = queryset.annotate(
            minimum_price=Min("variants__price"),
            minimum_effective_price=Min(price),
            maximum_effective_price=Max(price),
            in_stock=Exists(self._available_variants()),
            on_sale=Exists(self._sale_variants()),
        )
        if criteria.variant_filters:
            exact = self._exact_variants(criteria)
            queryset = queryset.annotate(
                exact_variant_id=Subquery(exact.values("id")[:1]),
                exact_combination=Case(
                    When(exact_variant_id__isnull=False, then=Value(True)),
                    default=Value(False),
                    output_field=BooleanField(),
                ),
            )
        else:
            queryset = queryset.annotate(
                exact_variant_id=Value(None, output_field=IntegerField()),
                exact_combination=Value(False, output_field=BooleanField()),
            )
        return queryset

    @staticmethod
    def _order(queryset, criteria):
        exact_prefix = ["-exact_combination"] if criteria.variant_filters else []
        if criteria.ordering == "price_asc":
            ordering = ["minimum_effective_price", "id"]
        elif criteria.ordering == "price_desc":
            ordering = ["-maximum_effective_price", "id"]
        elif criteria.ordering == "name":
            ordering = ["name", "id"]
        else:
            ordering = ["-in_stock", "-search_rank", "id"]
        return queryset.order_by(*exact_prefix, *ordering)

    @staticmethod
    def _load_result_relations(queryset):
        media = ProductFile.objects.filter(
            file__file_type="image",
            file__status__name="available",
            file__deleted_at__isnull=True,
        ).select_related("file").order_by("-is_primary", "position", "id")
        return queryset.select_related("category", "brand").prefetch_related(
            Prefetch("product_files", queryset=media, to_attr="storefront_media")
        )

    @staticmethod
    def _serialize_product(product):
        thumbnail_url = None
        if product.storefront_media:
            try:
                thumbnail_url = FileService().url(product.storefront_media[0].file)
            except FileService.Error:
                pass
        return {
            "id": product.id,
            "slug": product.slug,
            "name": product.name,
            "category": {"id": product.category_id, "name": product.category.name},
            "brand": (
                {"id": product.brand_id, "name": product.brand.name}
                if product.brand_id else None
            ),
            "thumbnail_url": thumbnail_url,
            "pricing": {
                "minimum_price": product.minimum_price,
                "minimum_effective_price": product.minimum_effective_price,
                "maximum_effective_price": product.maximum_effective_price,
            },
            "availability": {"in_stock": product.in_stock},
            "on_sale": product.on_sale,
            "variant_match": {
                "exact_combination": product.exact_combination,
                "variant_id": product.exact_variant_id,
            },
        }

    def _build_facets(self, criteria):
        base = self._base_queryset(criteria)
        return {
            "categories": self._category_facet(base, criteria),
            "brands": self._brand_facet(base, criteria),
            "price": self._price_facet(base, criteria),
            "details": self._detail_facets(base, criteria),
            "variants": self._variant_facets(base, criteria),
            "availability": self._boolean_facet(base, criteria, "availability"),
            "sale": self._boolean_facet(base, criteria, "sale"),
        }

    def _category_facet(self, base, criteria):
        queryset = self._apply_filters(base, criteria, "category")
        direct_counts = {
            row["category_id"]: row["count"]
            for row in queryset.order_by().values("category_id").annotate(
                count=Count("id", distinct=True)
            )
        }
        categories = {
            category.id: category
            for category in Category.objects.select_related("parent").filter(
                status__name__iexact="active"
            )
        }
        counts = dict(direct_counts)
        for category_id, count in direct_counts.items():
            parent_id = categories.get(category_id).parent_id if categories.get(category_id) else None
            seen = {category_id}
            while parent_id and parent_id not in seen and parent_id in categories:
                seen.add(parent_id)
                counts[parent_id] = counts.get(parent_id, 0) + count
                parent_id = categories[parent_id].parent_id
        return {
            "type": "tree",
            "values": [
                {
                    "id": category.id,
                    "label": category.name,
                    "parent_id": category.parent_id,
                    "count": counts[category.id],
                    "selected": category.id in criteria.category_ids,
                }
                for category in sorted(categories.values(), key=lambda item: (item.name.casefold(), item.id))
                if category.id in counts
            ],
        }

    def _brand_facet(self, base, criteria):
        queryset = self._apply_filters(base, criteria, "brand").exclude(brand_id__isnull=True)
        counts = queryset.order_by().values("brand_id", "brand__name").annotate(
            count=Count("id", distinct=True)
        ).order_by("brand__name")
        return {
            "type": "multi_select",
            "values": [
                {
                    "id": row["brand_id"],
                    "label": row["brand__name"],
                    "count": row["count"],
                    "selected": row["brand_id"] in criteria.brand_ids,
                }
                for row in counts
            ],
        }

    def _price_facet(self, base, criteria):
        products = self._apply_filters(base, criteria, "price")
        variants = ProductVariants.objects.filter(product_id__in=Subquery(products.values("id"))).annotate(
            effective_price=effective_price_expression()
        )
        values = variants.aggregate(minimum=Min("effective_price"), maximum=Max("effective_price"))
        return {
            "type": "range",
            **values,
            "selected_minimum": criteria.minimum_price,
            "selected_maximum": criteria.maximum_price,
        }

    def _detail_facets(self, base, criteria):
        result = []
        selected = {item.field_id: set(item.value_ids) for item in criteria.detail_filters}
        detail_ids = ProductDetails.objects.filter(
            product_id__in=Subquery(base.order_by().values("id")),
            detail__filterable=True,
            option_id__isnull=False,
        ).values_list("detail_id", flat=True).distinct()
        details = CategoryDetail.objects.filter(id__in=detail_ids).prefetch_related(
            "normalized_options", "categorydetailrelation_set"
        ).order_by("name")
        for detail in details:
            products = self._apply_filters(base, criteria, f"detail:{detail.id}")
            counts = {
                row["option_id"]: row["count"]
                for row in ProductDetails.objects.filter(
                    product_id__in=Subquery(products.order_by().values("id")),
                    detail=detail,
                    option_id__isnull=False,
                ).values("option_id").annotate(count=Count("product_id", distinct=True))
            }
            values = [
                {
                    "id": option.id,
                    "label": option.name,
                    "count": counts.get(option.id, 0),
                    "selected": option.id in selected.get(detail.id, set()),
                }
                for option in detail.normalized_options.all()
                if counts.get(option.id, 0) or option.id in selected.get(detail.id, set())
            ]
            if values:
                result.append({
                    "id": detail.id,
                    "label": detail.name,
                    "type": "multi_select",
                    "category_ids": [
                        relation.category_id
                        for relation in detail.categorydetailrelation_set.all()
                    ],
                    "values": values,
                })
        return result

    def _variant_facets(self, base, criteria):
        result = []
        selected = {item.field_id: set(item.value_ids) for item in criteria.variant_filters}
        attribute_ids = ProductVariantSelection.objects.filter(
            variant__product_id__in=Subquery(base.order_by().values("id"))
        ).values_list("attribute_id", flat=True).distinct()
        attributes = VariantAttribute.objects.filter(id__in=attribute_ids).prefetch_related(
            "options", "category_assignments"
        ).order_by("name")
        for attribute in attributes:
            products = self._apply_filters(base, criteria, f"variant:{attribute.id}")
            selections = ProductVariantSelection.objects.filter(
                variant__product_id__in=Subquery(products.order_by().values("id")),
                attribute=attribute,
            )
            counts = {
                row["option_id"]: row["count"]
                for row in selections.values("option_id").annotate(
                    count=Count("variant__product_id", distinct=True)
                )
            }
            available_variants = self.inventory_service.annotate_variant_summaries(
                ProductVariants.objects.filter(
                    product_id__in=Subquery(products.order_by().values("id"))
                )
            ).filter(available_item_count__gt=0)
            available_counts = {
                row["option_id"]: row["count"]
                for row in selections.filter(
                    variant_id__in=Subquery(available_variants.values("id"))
                ).values("option_id").annotate(
                    count=Count("variant__product_id", distinct=True)
                )
            }
            values = [
                {
                    "option_id": option.id,
                    "label": option.name,
                    "count": counts.get(option.id, 0),
                    "in_stock_count": available_counts.get(option.id, 0),
                    "selected": option.id in selected.get(attribute.id, set()),
                }
                for option in attribute.options.all()
                if counts.get(option.id, 0) or option.id in selected.get(attribute.id, set())
            ]
            if values:
                result.append({
                    "attribute_id": attribute.id,
                    "label": attribute.name,
                    "type": "multi_select",
                    "category_ids": [
                        assignment.category_id
                        for assignment in attribute.category_assignments.all()
                    ],
                    "values": values,
                })
        return result

    def _boolean_facet(self, base, criteria, name):
        products = self._apply_filters(base, criteria, name)
        subquery = self._available_variants() if name == "availability" else self._sale_variants()
        count = products.annotate(matches=Exists(subquery)).filter(matches=True).order_by().count()
        selected = criteria.in_stock if name == "availability" else criteria.on_sale
        return {"type": "boolean", "count": count, "selected": selected}
