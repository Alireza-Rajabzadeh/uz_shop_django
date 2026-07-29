from django.db.models import BooleanField, Case, Count, Value, When

from domains.location.models import City
from .base import LocationService


class CityService(LocationService):
    model = City
    search_fields = ("name", "fa_title")
    select_related = ("state", "state__country")
    unique_scope = ("state", "name")
    ordering_fields = {
        **LocationService.ordering_fields,
        "state_name": "state__name", "country_name": "state__country__name",
        "address_count": "address_count", "warehouse_count": "warehouse_count",
    }

    def annotate_counts(self, queryset):
        return queryset.annotate(
            address_count=Count("customer_addresses", distinct=True),
            warehouse_count=Count("warehouses", distinct=True),
        ).annotate(
            can_delete=Case(
                When(address_count=0, warehouse_count=0, then=Value(True)),
                default=Value(False), output_field=BooleanField(),
            )
        )

    def apply_filters(self, queryset, country_id=None, state_id=None, **filters):
        if country_id:
            queryset = queryset.filter(state__country_id=country_id)
        if state_id:
            queryset = queryset.filter(state_id=state_id)
        return queryset

    def delete_blockers(self, instance):
        return {
            "customer_addresses": instance.customer_addresses.count(),
            "warehouses": instance.warehouses.count(),
        }
