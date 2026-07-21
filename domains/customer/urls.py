from django.urls import path
from .views import (
    CustomerRegister,
    CustomerLogin,
    CustomerMe,
    CustomerAddressListCreate,
    CustomerAddressDetail,
    CustomerPreferenceView,
)

urlpatterns = [
    path("register", CustomerRegister.as_view()),
    path("login", CustomerLogin.as_view()),
    path("me", CustomerMe.as_view()),
    path("addresses", CustomerAddressListCreate.as_view()),
    path("addresses/<int:address_id>", CustomerAddressDetail.as_view()),
    path("preferences", CustomerPreferenceView.as_view()),
]
