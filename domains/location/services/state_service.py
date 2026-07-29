from django.db.models import Count

from domains.location.models import State
from .base import LocationService


class StateService(LocationService):
    model = State
    search_fields = ("name", "fa_title")
    select_related = ("country",)
    unique_scope = ("country", "name")
    ordering_fields = {
        **LocationService.ordering_fields,
        "country_name": "country__name", "city_count": "city_count",
        "address_count": "address_count", "warehouse_count": "warehouse_count",
    }

    def annotate_counts(self, queryset):
        return queryset.annotate(
            city_count=Count("cities", distinct=True),
            address_count=Count("customer_addresses", distinct=True),
            warehouse_count=Count("cities__warehouses", distinct=True),
        ).annotate(
            can_delete=self.can_delete_case("city_count", "address_count")
        )

    def apply_filters(self, queryset, country_id=None, **filters):
        return queryset.filter(country_id=country_id) if country_id else queryset

    def delete_blockers(self, instance):
        return {
            "cities": instance.cities.count(),
            "customer_addresses": instance.customer_addresses.count(),
        }
