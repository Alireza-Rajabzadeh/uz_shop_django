from rest_framework import serializers
from domains.customer.models import CustomerAddress
from domains.location.models import Country, State, City


class CountryBriefSerializer(serializers.ModelSerializer):
    class Meta:
        model = Country
        fields = ["id", "name", "fa_title"]


class StateBriefSerializer(serializers.ModelSerializer):
    class Meta:
        model = State
        fields = ["id", "name", "fa_title"]


class CityBriefSerializer(serializers.ModelSerializer):
    class Meta:
        model = City
        fields = ["id", "name", "fa_title"]


class CustomerAddressSerializer(serializers.ModelSerializer):
    country_detail = CountryBriefSerializer(source="country", read_only=True)
    state_detail = StateBriefSerializer(source="state", read_only=True)
    city_detail = CityBriefSerializer(source="city", read_only=True)

    class Meta:
        model = CustomerAddress
        fields = [
            "id", "title", "country", "state", "city",
            "country_detail", "state_detail", "city_detail",
            "postal_code", "address_line1", "address_line2",
            "house_number", "latitude", "longitude", "is_default",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate(self, attrs):
        country = attrs.get("country", getattr(self.instance, "country", None))
        state = attrs.get("state", getattr(self.instance, "state", None))
        city = attrs.get("city", getattr(self.instance, "city", None))

        if country and state and state.country_id != country.id:
            raise serializers.ValidationError({"state": "State does not belong to country."})
        if state and city and city.state_id != state.id:
            raise serializers.ValidationError({"city": "City does not belong to state."})
        return attrs
