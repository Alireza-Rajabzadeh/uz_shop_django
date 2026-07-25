from django.urls import path
from .views import adminLogin, UserPermissions

urlpatterns = [
    path("login", adminLogin.as_view()),
    path("permissions", UserPermissions.as_view()),
]
