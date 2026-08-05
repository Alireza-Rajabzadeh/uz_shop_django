from django.urls import path
from .views import (
    CustomerRegister,
    CustomerLogin,
    CustomerLoginConfirmation,
    CustomerPasswordForgot,
    CustomerPasswordForgotConfirmation,
    CustomerPhoneConfirmationRequest,
    CustomerPhoneConfirmationVerify,
    CustomerMe,
    CustomerChangePassword,
    CustomerAddressListCreate,
    CustomerAddressDetail,
    CustomerPreferenceView,
    CustomerCountryOptions,
    CustomerStateOptions,
    CustomerCityOptions,
)
from .admin_views import (
    AdminCustomerAddressDetail,
    AdminCustomerAddressListCreate,
    AdminCustomerDetail,
    AdminCustomerList,
    AdminCustomerStatusList,
)

urlpatterns = [
    path("register", CustomerRegister.as_view()),
    path("login", CustomerLogin.as_view()),
    path("login/confirmation", CustomerLoginConfirmation.as_view()),
    path("password/forgot", CustomerPasswordForgot.as_view()),
    path(
        "password/forgot/confirmation",
        CustomerPasswordForgotConfirmation.as_view(),
    ),
    path("me/phone/confirmation", CustomerPhoneConfirmationRequest.as_view()),
    path(
        "me/phone/confirmation/verify",
        CustomerPhoneConfirmationVerify.as_view(),
    ),
    path("me", CustomerMe.as_view()),
    path("me/password", CustomerChangePassword.as_view()),
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
    path("location-options/countries", CustomerCountryOptions.as_view()),
    path("location-options/states", CustomerStateOptions.as_view()),
    path("location-options/cities", CustomerCityOptions.as_view()),
]
