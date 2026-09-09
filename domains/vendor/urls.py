from django.urls import path
from .views import (
    VendorRegister,
    VendorLogin,
    VendorLoginConfirmation,
    VendorPasswordForgot,
    VendorPasswordForgotConfirmation,
    VendorPhoneConfirmationRequest,
    VendorPhoneConfirmationVerify,
    VendorMe,
    VendorChangePassword,
    VendorPreferenceView,
)
from .admin_views import (
    AdminVendorList,
    AdminVendorDetail,
    AdminVendorStatusList,
)

urlpatterns = [
    path("register", VendorRegister.as_view()),
    path("login", VendorLogin.as_view()),
    path("login/confirmation", VendorLoginConfirmation.as_view()),
    path("password/forgot", VendorPasswordForgot.as_view()),
    path(
        "password/forgot/confirmation",
        VendorPasswordForgotConfirmation.as_view(),
    ),
    path("me/phone/confirmation", VendorPhoneConfirmationRequest.as_view()),
    path(
        "me/phone/confirmation/verify",
        VendorPhoneConfirmationVerify.as_view(),
    ),
    path("me", VendorMe.as_view()),
    path("me/password", VendorChangePassword.as_view()),
    path("preferences", VendorPreferenceView.as_view()),
    path("vendors", AdminVendorList.as_view()),
    path("vendors/<int:vendor_id>", AdminVendorDetail.as_view()),
    path("statuses", AdminVendorStatusList.as_view()),
]
