from django.http import Http404
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.views import APIView

from core.permissions import AdminModelPermissions
from core.responses import api_response
from domains.location.models import City, Country, State
from domains.location.services import CityService, CountryService, LocationValidationError, StateService
from domains.users.auth import AdminJWTAuthentication

from .serializers import (
    CityReadSerializer, CityWriteSerializer, CountryReadSerializer, CountryWriteSerializer,
    LocationListQuerySerializer, StateReadSerializer, StateWriteSerializer,
)


def service_call(callback):
    try:
        return callback()
    except LocationValidationError as exc:
        raise ValidationError(exc.errors) from exc


class LocationAPIView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [AdminModelPermissions]
    service_class = None
    read_serializer_class = None
    write_serializer_class = None

    @property
    def service(self):
        return self.service_class()

    def get_object(self, object_id):
        try:
            return self.service.get(object_id)
        except Http404 as exc:
            raise NotFound(f"{self.model._meta.verbose_name.title()} not found.") from exc

    def serialize_read(self, instance):
        return self.read_serializer_class(self.service.with_counts(instance.pk).get()).data


class LocationListCreateView(LocationAPIView):
    def get(self, request):
        query = LocationListQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        queryset = self.service.search(**query.validated_data)
        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        data = self.read_serializer_class(page, many=True).data
        return api_response(data=paginator.get_paginated_response(data).data)

    def post(self, request):
        serializer = self.write_serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        instance = service_call(lambda: self.service.create(**serializer.validated_data))
        return api_response(data=self.serialize_read(instance), status_code=201)


class LocationDetailView(LocationAPIView):
    def get(self, request, id):
        return api_response(data=self.serialize_read(self.get_object(id)))

    def patch(self, request, id):
        instance = self.get_object(id)
        serializer = self.write_serializer_class(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        instance = service_call(
            lambda: self.service.update(instance, **serializer.validated_data)
        )
        return api_response(data=self.serialize_read(instance))

    def delete(self, request, id):
        instance = self.get_object(id)
        service_call(lambda: self.service.delete(instance))
        return api_response(data=None)


class CountryListCreate(LocationListCreateView):
    model = Country
    service_class = CountryService
    read_serializer_class = CountryReadSerializer
    write_serializer_class = CountryWriteSerializer


class CountryDetail(LocationDetailView):
    model = Country
    service_class = CountryService
    read_serializer_class = CountryReadSerializer
    write_serializer_class = CountryWriteSerializer


class StateListCreate(LocationListCreateView):
    model = State
    service_class = StateService
    read_serializer_class = StateReadSerializer
    write_serializer_class = StateWriteSerializer


class StateDetail(LocationDetailView):
    model = State
    service_class = StateService
    read_serializer_class = StateReadSerializer
    write_serializer_class = StateWriteSerializer


class CityListCreate(LocationListCreateView):
    model = City
    service_class = CityService
    read_serializer_class = CityReadSerializer
    write_serializer_class = CityWriteSerializer


class CityDetail(LocationDetailView):
    model = City
    service_class = CityService
    read_serializer_class = CityReadSerializer
    write_serializer_class = CityWriteSerializer
