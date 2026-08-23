import re

from rest_framework import serializers

from domains.location.models import City, Country, State


class LocationListQuerySerializer(serializers.Serializer):
    search = serializers.CharField(required=False, allow_blank=False, trim_whitespace=True)
    ordering = serializers.CharField(required=False, allow_blank=False)
    country_id = serializers.IntegerField(required=False, min_value=1)
    state_id = serializers.IntegerField(required=False, min_value=1)


class CountryWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Country
        fields = ["name", "fa_title", "code", "phone_code"]

    def validate_code(self, value):
        value = value.strip().upper()
        if not re.fullmatch(r"[A-Z]{2}", value):
            raise serializers.ValidationError("Use exactly two ASCII letters.")
        return value

    def validate_phone_code(self, value):
        digits = re.sub(r"[\s()-]", "", value)
        if not digits.startswith("+"):
            digits = f"+{digits}"
        if not re.fullmatch(r"\+[1-9][0-9]{0,8}", digits):
            raise serializers.ValidationError("Use an international code such as +98.")
        return digits


class StateWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = State
        fields = ["country", "name", "fa_title"]


class CityWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = City
        fields = ["state", "name", "fa_title", "latitude", "longitude"]

    def validate(self, attrs):
        latitude = attrs.get("latitude", getattr(self.instance, "latitude", None))
        longitude = attrs.get("longitude", getattr(self.instance, "longitude", None))
        if (latitude is None) != (longitude is None):
            raise serializers.ValidationError({
                "coordinates": "Provide both latitude and longitude, or neither."
            })
        if latitude is not None and not -90 <= latitude <= 90:
            raise serializers.ValidationError({
                "latitude": "Latitude must be between -90 and 90."
            })
        if longitude is not None and not -180 <= longitude <= 180:
            raise serializers.ValidationError({
                "longitude": "Longitude must be between -180 and 180."
            })
        return attrs


class CountryReadSerializer(serializers.ModelSerializer):
    state_count = serializers.IntegerField(read_only=True, default=0)
    address_count = serializers.IntegerField(read_only=True, default=0)
    warehouse_count = serializers.IntegerField(read_only=True, default=0)
    can_delete = serializers.BooleanField(read_only=True, default=True)

    class Meta:
        model = Country
        fields = [
            "id", "name", "fa_title", "code", "phone_code", "state_count",
            "address_count", "warehouse_count", "can_delete",
        ]


class StateReadSerializer(serializers.ModelSerializer):
    country_name = serializers.CharField(source="country.name", read_only=True)
    country_fa_title = serializers.CharField(source="country.fa_title", read_only=True)
    city_count = serializers.IntegerField(read_only=True, default=0)
    address_count = serializers.IntegerField(read_only=True, default=0)
    warehouse_count = serializers.IntegerField(read_only=True, default=0)
    can_delete = serializers.BooleanField(read_only=True, default=True)

    class Meta:
        model = State
        fields = [
            "id", "country", "country_name", "country_fa_title", "name", "fa_title",
            "city_count", "address_count", "warehouse_count", "can_delete",
        ]


class CityReadSerializer(serializers.ModelSerializer):
    state_name = serializers.CharField(source="state.name", read_only=True)
    state_fa_title = serializers.CharField(source="state.fa_title", read_only=True)
    country = serializers.IntegerField(source="state.country_id", read_only=True)
    country_name = serializers.CharField(source="state.country.name", read_only=True)
    country_fa_title = serializers.CharField(source="state.country.fa_title", read_only=True)
    address_count = serializers.IntegerField(read_only=True, default=0)
    warehouse_count = serializers.IntegerField(read_only=True, default=0)
    can_delete = serializers.BooleanField(read_only=True, default=True)

    class Meta:
        model = City
        fields = [
            "id", "state", "state_name", "state_fa_title", "country", "country_name",
            "country_fa_title", "name", "fa_title", "latitude", "longitude",
            "address_count", "warehouse_count", "can_delete",
        ]
