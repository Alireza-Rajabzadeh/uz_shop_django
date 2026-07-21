from django.urls import path
from .views import CustomerRegister, CustomerLogin, CustomerMe

urlpatterns = [
    path("register", CustomerRegister.as_view()),
    path("login", CustomerLogin.as_view()),
    path("me", CustomerMe.as_view()),
]
