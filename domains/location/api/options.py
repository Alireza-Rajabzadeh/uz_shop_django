from rest_framework import serializers
from rest_framework.permissions import BasePermission
from rest_framework.views import APIView

from core.responses import api_response
from domains.location.models import City, Country, State
from domains.users.auth import AdminJWTAuthentication


class LocationOptionSerializer(serializers.ModelSerializer):
    class Meta:
        fields = ["id", "name", "fa_title"]


class CountryOptionSerializer(LocationOptionSerializer):
    class Meta(LocationOptionSerializer.Meta):
        model = Country
        fields = LocationOptionSerializer.Meta.fields + ["code", "phone_code"]


class StateOptionSerializer(LocationOptionSerializer):
    class Meta(LocationOptionSerializer.Meta):
        model = State


class CityOptionSerializer(LocationOptionSerializer):
    class Meta(LocationOptionSerializer.Meta):
        model = City
        fields = LocationOptionSerializer.Meta.fields + ["latitude", "longitude"]


class CountryFilterSerializer(serializers.Serializer):
    country_id = serializers.IntegerField(min_value=1)


class StateFilterSerializer(serializers.Serializer):
    state_id = serializers.IntegerField(min_value=1)


class LocationOptionPermissions(BasePermission):
    permissions = (
        "customer.view_customeraddress",
        "inventory.view_warehouse",
        "inventory.add_warehouse",
        "inventory.change_warehouse",
        "location.view_country",
        "location.view_state",
        "location.view_city",
        "location.add_state",
        "location.change_state",
        "location.add_city",
        "location.change_city",
    )

    def has_permission(self, request, view):
        return any(request.user.has_perm(permission) for permission in self.permissions)


class AdminLocationOptionView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [LocationOptionPermissions]


class CountryOptions(AdminLocationOptionView):
    def get(self, request):
        countries = Country.objects.order_by("fa_title", "name")
        return api_response(data=CountryOptionSerializer(countries, many=True).data)


class StateOptions(AdminLocationOptionView):
    def get(self, request):
        query = CountryFilterSerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        states = State.objects.filter(
            country_id=query.validated_data["country_id"]
        ).order_by("fa_title", "name")
        return api_response(data=StateOptionSerializer(states, many=True).data)


class CityOptions(AdminLocationOptionView):
    def get(self, request):
        query = StateFilterSerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        cities = City.objects.filter(
            state_id=query.validated_data["state_id"]
        ).order_by("fa_title", "name")
        return api_response(data=CityOptionSerializer(cities, many=True).data)
