import re

from rest_framework import serializers

from domains.catalog.models import (
    Brand,
    Category,
    CategoryDetailOption,
    VariantOption,
)
from domains.catalog.search.contracts import FacetSelection, ProductSearchCriteria


FACET_PARAMETER = re.compile(r"^(detail|variant)\[(\d+)]$")


class StorefrontStaticDataQuerySerializer(serializers.Serializer):
    data = serializers.CharField(required=False, max_length=100)

    def validate_data(self, value):
        if value not in self.context["supported_data"]:
            raise serializers.ValidationError("Unsupported static dataset.")
        return value


class StorefrontStaticCategorySerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    icon = serializers.CharField(allow_null=True, allow_blank=True)
    link = serializers.CharField()
    children = serializers.SerializerMethodField()

    def get_children(self, category):
        return StorefrontStaticCategorySerializer(
            category["children"], many=True
        ).data


class FacetSelectionSerializer(serializers.Serializer):
    field_id = serializers.IntegerField(min_value=1)
    value_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        allow_empty=False,
    )

    def validate_value_ids(self, value_ids):
        return list(dict.fromkeys(value_ids))


class StorefrontProductSearchQuerySerializer(serializers.Serializer):
    q = serializers.CharField(required=False, allow_blank=True, max_length=200, trim_whitespace=True)
    category_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1), required=False, default=list
    )
    brand_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1), required=False, default=list
    )
    detail_filters = FacetSelectionSerializer(many=True, required=False, default=list)
    variant_filters = FacetSelectionSerializer(many=True, required=False, default=list)
    price_min = serializers.DecimalField(
        max_digits=15, decimal_places=2, min_value=0, required=False
    )
    price_max = serializers.DecimalField(
        max_digits=15, decimal_places=2, min_value=0, required=False
    )
    in_stock = serializers.BooleanField(required=False, allow_null=True)
    on_sale = serializers.BooleanField(required=False, allow_null=True)
    ordering = serializers.ChoiceField(
        choices=["relevance", "price_asc", "price_desc", "name"],
        required=False,
        default="relevance",
    )
    page = serializers.IntegerField(min_value=1, required=False, default=1)
    page_size = serializers.IntegerField(min_value=1, max_value=100, required=False, default=24)
    include_facets = serializers.BooleanField(required=False, default=True)

    @classmethod
    def from_query_params(cls, query_params):
        scalar_fields = (
            "q", "price_min", "price_max", "in_stock", "on_sale",
            "ordering", "page", "page_size", "include_facets",
        )
        payload = {
            field: query_params.get(field)
            for field in scalar_fields
            if field in query_params
        }
        payload["category_ids"] = query_params.getlist("category")
        payload["brand_ids"] = query_params.getlist("brand")
        detail_filters = []
        variant_filters = []
        for key in query_params:
            match = FACET_PARAMETER.match(key)
            if not match:
                continue
            selection = {"field_id": match.group(2), "value_ids": query_params.getlist(key)}
            target = detail_filters if match.group(1) == "detail" else variant_filters
            target.append(selection)
        payload["detail_filters"] = detail_filters
        payload["variant_filters"] = variant_filters
        return cls(data=payload)

    def validate(self, attrs):
        if attrs.get("price_min") is not None and attrs.get("price_max") is not None:
            if attrs["price_min"] > attrs["price_max"]:
                raise serializers.ValidationError({
                    "price_max": "Maximum price must not be below minimum price."
                })
        self._validate_ids(Category, attrs["category_ids"], "category")
        self._validate_ids(Brand, attrs["brand_ids"], "brand")
        self._validate_facet_options(attrs["detail_filters"], detail=True)
        self._validate_facet_options(attrs["variant_filters"], detail=False)
        return attrs

    @staticmethod
    def _validate_ids(model, ids, field):
        unique_ids = set(ids)
        found = set(model.objects.filter(id__in=unique_ids).values_list("id", flat=True))
        if found != unique_ids:
            raise serializers.ValidationError({field: "One or more selected values do not exist."})

    @staticmethod
    def _validate_facet_options(selections, *, detail):
        option_model = CategoryDetailOption if detail else VariantOption
        relation_field = "detail_id" if detail else "attribute_id"
        error_field = "detail" if detail else "variant"
        for selection in selections:
            filters = {
                "id__in": selection["value_ids"],
                relation_field: selection["field_id"],
            }
            if detail:
                filters["detail__filterable"] = True
            found = set(option_model.objects.filter(**filters).values_list("id", flat=True))
            if found != set(selection["value_ids"]):
                raise serializers.ValidationError({
                    error_field: "One or more selected options do not belong to this filter."
                })

    def to_criteria(self):
        data = self.validated_data
        return ProductSearchCriteria(
            query=data.get("q", ""),
            category_ids=tuple(dict.fromkeys(data["category_ids"])),
            brand_ids=tuple(dict.fromkeys(data["brand_ids"])),
            detail_filters=tuple(
                FacetSelection(item["field_id"], tuple(item["value_ids"]))
                for item in data["detail_filters"]
            ),
            variant_filters=tuple(
                FacetSelection(item["field_id"], tuple(item["value_ids"]))
                for item in data["variant_filters"]
            ),
            minimum_price=data.get("price_min"),
            maximum_price=data.get("price_max"),
            in_stock=data.get("in_stock"),
            on_sale=data.get("on_sale"),
            ordering=data["ordering"],
            page=data["page"],
            page_size=data["page_size"],
            include_facets=data["include_facets"],
        )
