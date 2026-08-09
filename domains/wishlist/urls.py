from django.urls import path

from .admin_views import AdminWishlistDetail, AdminWishlistList
from .views import WishlistExists, WishlistListCreate, WishlistRemove

urlpatterns = [
    path("", WishlistListCreate.as_view()),
    path("exists", WishlistExists.as_view()),
    path("admin/wishlists", AdminWishlistList.as_view()),
    path("admin/wishlists/<int:wishlist_id>", AdminWishlistDetail.as_view()),
    path("products/<int:product_id>", WishlistRemove.as_view()),
]