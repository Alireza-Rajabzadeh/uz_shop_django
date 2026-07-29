from django.urls import path

from domains.location.api.views import (
    CityDetail, CityListCreate, CountryDetail, CountryListCreate, StateDetail, StateListCreate,
)
from domains.location.api.options import CityOptions, CountryOptions, StateOptions

urlpatterns = [
    path("countries", CountryListCreate.as_view(), name="country-list"),
    path("countries/<int:id>", CountryDetail.as_view(), name="country-detail"),
    path("states", StateListCreate.as_view(), name="state-list"),
    path("states/<int:id>", StateDetail.as_view(), name="state-detail"),
    path("cities", CityListCreate.as_view(), name="city-list"),
    path("cities/<int:id>", CityDetail.as_view(), name="city-detail"),
    path("options/countries", CountryOptions.as_view(), name="country-options"),
    path("options/states", StateOptions.as_view(), name="state-options"),
    path("options/cities", CityOptions.as_view(), name="city-options"),
]
