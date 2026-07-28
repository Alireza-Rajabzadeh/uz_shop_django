from django.urls import path

from .views import VariantInventoryDetail


urlpatterns = [
    path("variants/<int:variant_id>", VariantInventoryDetail.as_view()),
]
