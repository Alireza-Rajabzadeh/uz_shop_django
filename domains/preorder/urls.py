from django.urls import path

from .views import PreOrderExists, PreOrderListCreate, PreOrderRemove

urlpatterns = [
    path("", PreOrderListCreate.as_view()),
    path("exists", PreOrderExists.as_view()),
    path("products/<int:product_id>", PreOrderRemove.as_view()),
]