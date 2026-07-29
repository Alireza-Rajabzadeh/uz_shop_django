from django.urls import path
from .views import (
    CustomerRegister,
    CustomerLogin,
    CustomerMe,
    CustomerAddressListCreate,
    CustomerAddressDetail,
    CustomerPreferenceView,
)
from .admin_views import (
    AdminCustomerAddressDetail,
    AdminCustomerAddressListCreate,
    AdminCustomerDetail,
    AdminCustomerList,
    AdminCustomerStatusList,
)
from domains.location.api import CityOptions, CountryOptions, StateOptions

urlpatterns = [
    path("register", CustomerRegister.as_view()),
    path("login", CustomerLogin.as_view()),
    path("me", CustomerMe.as_view()),
    path("addresses", CustomerAddressListCreate.as_view()),
    path("addresses/<int:address_id>", CustomerAddressDetail.as_view()),
    path("preferences", CustomerPreferenceView.as_view()),
    path("customers", AdminCustomerList.as_view()),
    path("customers/<int:customer_id>", AdminCustomerDetail.as_view()),
    path("statuses", AdminCustomerStatusList.as_view()),
    path(
        "customers/<int:customer_id>/addresses",
        AdminCustomerAddressListCreate.as_view(),
    ),
    path(
        "customers/<int:customer_id>/addresses/<int:address_id>",
        AdminCustomerAddressDetail.as_view(),
    ),
    path("location-options/countries", CountryOptions.as_view()),
    path("location-options/states", StateOptions.as_view()),
    path("location-options/cities", CityOptions.as_view()),
]
