from django.urls import path

from . import views

urlpatterns = [
    path("offers", views.BusinessOfferListCreate.as_view()),
    path("offers/<int:pk>", views.BusinessOfferDetail.as_view()),
]
