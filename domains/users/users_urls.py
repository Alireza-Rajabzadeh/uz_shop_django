from django.urls import path
from .views import adminLogin
urlpatterns = [
    path("login", adminLogin.as_view()),
    path("register", adminLogin.as_view()),
]
