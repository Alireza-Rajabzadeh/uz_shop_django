from django.urls import path

from .views import (
    CartAddressView,
    CartItemDetail,
    CartItemMoveToPreOrder,
    CartItemMoveToWishlist,
    CartItemsView,
    CartValidateView,
    CartView,
)

urlpatterns = [
    path("", CartView.as_view()),
    path("items", CartItemsView.as_view()),
    path("items/<int:item_id>", CartItemDetail.as_view()),
    path("items/<int:item_id>/move-to-wishlist", CartItemMoveToWishlist.as_view()),
    path("items/<int:item_id>/move-to-preorder", CartItemMoveToPreOrder.as_view()),
    path("address", CartAddressView.as_view()),
    path("validate", CartValidateView.as_view()),
]