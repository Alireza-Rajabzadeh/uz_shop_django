from django.utils.translation import gettext as _
from rest_framework import serializers

from domains.customer.models import CustomerAddress
from domains.location.models import City, Country, State


class CartAddressWriteSerializer(serializers.Serializer):
    saved_address_id = serializers.IntegerField(required=False)
    receiver_name = serializers.CharField(required=False, max_length=100)
    receiver_phone = serializers.CharField(required=False, max_length=20)
    country_id = serializers.IntegerField(required=False)
    state_id = serializers.IntegerField(required=False)
    city_id = serializers.IntegerField(required=False)
    postal_code = serializers.CharField(required=False, max_length=20)
    address_line1 = serializers.CharField(required=False, max_length=255)
    address_line2 = serializers.CharField(required=False, max_length=255, allow_blank=True, default="")
    house_number = serializers.CharField(required=False, max_length=20, allow_blank=True, default="")

    MANUAL_REQUIRED = (
        "country_id",
        "state_id",
        "city_id",
        "postal_code",
        "address_line1",
        "receiver_name",
        "receiver_phone",
    )

    def validate(self, attrs):
        if attrs.get("saved_address_id") is not None:
            receiver_name = attrs.get("receiver_name")
            receiver_phone = attrs.get("receiver_phone")
            if (receiver_name is None) != (receiver_phone is None):
                raise serializers.ValidationError({
                    "receiver_name": _(
                        "Provide both receiver name and receiver phone, or neither."
                    )
                })
            attrs["mode"] = "saved"
            return attrs
        missing = [field for field in self.MANUAL_REQUIRED if attrs.get(field) is None]
        if missing:
            raise serializers.ValidationError({
                "address": _("Provide a saved address or fill the full address "
                             "(missing: %s).") % ", ".join(missing)
            })
        attrs["mode"] = "manual"
        return attrs


class AddressInfoService:
    class ValidationError(Exception):
        def __init__(self, errors):
            self.errors = errors
            super().__init__(str(errors))

    def build(self, customer, data):
        mode = data.get("mode")
        if mode == "saved":
            return self._from_saved(customer, data)
        if mode == "manual":
            return self._from_manual(customer, data)
        raise self.ValidationError({"address": [_("Choose a saved address or fill the full address.")]})

    @staticmethod
    def _locality(country, state, city):
        return {
            "country_id": country.id,
            "country_name": country.name,
            "country_fa_title": country.fa_title,
            "state_id": state.id,
            "state_name": state.name,
            "state_fa_title": state.fa_title,
            "city_id": city.id,
            "city_name": city.name,
            "city_fa_title": city.fa_title,
        }

    @staticmethod
    def _validate_hierarchy(country, state, city):
        if state.country_id != country.id:
            raise AddressInfoService.ValidationError({
                "state_id": [_("The state does not belong to the selected country.")]
            })
        if city.state_id != state.id:
            raise AddressInfoService.ValidationError({
                "city_id": [_("The city does not belong to the selected state.")]
            })

    def _from_saved(self, customer, data):
        try:
            address = customer.addresses.select_related(
                "country", "state", "city"
            ).get(id=data["saved_address_id"])
        except CustomerAddress.DoesNotExist as exc:
            raise self.ValidationError({
                "saved_address": [_("Saved address not found.")]
            }) from exc
        receiver_name = data.get("receiver_name") or (
            f"{customer.first_name} {customer.last_name}".strip()
        )
        receiver_phone = data.get("receiver_phone") or customer.phone
        info = self._locality(address.country, address.state, address.city)
        info.update({
            "postal_code": address.postal_code,
            "address_line1": address.address_line1,
            "address_line2": address.address_line2 or "",
            "house_number": address.house_number or "",
            "receiver_name": receiver_name,
            "receiver_phone": receiver_phone,
        })
        return info

    def _from_manual(self, customer, data):
        try:
            country = Country.objects.get(id=data["country_id"])
            state = State.objects.get(id=data["state_id"])
            city = City.objects.get(id=data["city_id"])
        except (Country.DoesNotExist, State.DoesNotExist, City.DoesNotExist) as exc:
            raise self.ValidationError({
                "address": [_("One or more selected locations do not exist.")]
            }) from exc
        self._validate_hierarchy(country, state, city)
        info = self._locality(country, state, city)
        info.update({
            "postal_code": data["postal_code"],
            "address_line1": data["address_line1"],
            "address_line2": data.get("address_line2") or "",
            "house_number": data.get("house_number") or "",
            "receiver_name": data["receiver_name"],
            "receiver_phone": data["receiver_phone"],
        })
        return info