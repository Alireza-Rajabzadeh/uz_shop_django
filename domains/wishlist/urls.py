from django.urls import path

from .views import WishlistExists, WishlistListCreate, WishlistRemove

urlpatterns = [
    path("", WishlistListCreate.as_view()),
    path("exists", WishlistExists.as_view()),
    path("products/<int:product_id>", WishlistRemove.as_view()),
]