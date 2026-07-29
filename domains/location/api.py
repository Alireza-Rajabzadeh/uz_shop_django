from rest_framework import serializers
from rest_framework.views import APIView

from core.permissions import AdminModelPermissions
from core.responses import api_response
from domains.customer.models import CustomerAddress
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


class CountryFilterSerializer(serializers.Serializer):
    country_id = serializers.IntegerField(min_value=1)


class StateFilterSerializer(serializers.Serializer):
    state_id = serializers.IntegerField(min_value=1)


class AdminLocationOptionView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [AdminModelPermissions]


class CountryOptions(AdminLocationOptionView):
    model = CustomerAddress

    def get(self, request):
        countries = Country.objects.order_by("fa_title", "name")
        return api_response(True, "", CountryOptionSerializer(countries, many=True).data)


class StateOptions(AdminLocationOptionView):
    model = CustomerAddress

    def get(self, request):
        query = CountryFilterSerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        country_id = query.validated_data["country_id"]
        states = State.objects.filter(country_id=country_id).order_by("fa_title", "name")
        return api_response(True, "", StateOptionSerializer(states, many=True).data)


class CityOptions(AdminLocationOptionView):
    model = CustomerAddress

    def get(self, request):
        query = StateFilterSerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        state_id = query.validated_data["state_id"]
        cities = City.objects.filter(state_id=state_id).order_by("fa_title", "name")
        return api_response(True, "", CityOptionSerializer(cities, many=True).data)
