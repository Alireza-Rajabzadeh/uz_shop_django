from django.urls import path
from .views import test_api,crash_test

urlpatterns = [
    path("test/", test_api),
    path("crash/", crash_test),
]