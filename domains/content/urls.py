from django.urls import path

from .views import AdminLandingPageList

urlpatterns = [
    path("admin/landing-pages", AdminLandingPageList.as_view()),
]
