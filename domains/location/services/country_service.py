from django.db.models import Count

from domains.location.models import Country
from .base import LocationService, LocationValidationError, normalize_text


class CountryService(LocationService):
    model = Country
    search_fields = ("name", "fa_title", "code", "phone_code")
    select_related = ()
    unique_scope = ("name",)
    ordering_fields = {
        **LocationService.ordering_fields,
        "code": "code", "phone_code": "phone_code", "state_count": "state_count",
        "address_count": "address_count", "warehouse_count": "warehouse_count",
    }

    def annotate_counts(self, queryset):
        return queryset.annotate(
            state_count=Count("states", distinct=True),
            address_count=Count("customer_addresses", distinct=True),
            warehouse_count=Count("states__cities__warehouses", distinct=True),
        ).annotate(
            can_delete=self.can_delete_case("state_count", "address_count")
        )

    def normalize_data(self, data):
        data = super().normalize_data(data)
        if "code" in data:
            data["code"] = normalize_text(data["code"]).upper()
        if "phone_code" in data:
            data["phone_code"] = normalize_text(data["phone_code"])
        return data

    def validate_duplicate(self, data, instance=None):
        super().validate_duplicate(data, instance)
        if "code" in data:
            duplicate = Country.objects.filter(code__iexact=data["code"])
            if instance:
                duplicate = duplicate.exclude(pk=instance.pk)
            if duplicate.exists():
                raise LocationValidationError({"code": ["A country with this code already exists."]})

    def delete_blockers(self, instance):
        return {
            "states": instance.states.count(),
            "customer_addresses": instance.customer_addresses.count(),
        }
