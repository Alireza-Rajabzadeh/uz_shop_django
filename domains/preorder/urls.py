from django.urls import path

from .admin_views import AdminPreOrderDetail, AdminPreOrderList
from .views import PreOrderExists, PreOrderListCreate, PreOrderRemove

urlpatterns = [
    path("", PreOrderListCreate.as_view()),
    path("exists", PreOrderExists.as_view()),
    path("admin/preorders", AdminPreOrderList.as_view()),
    path("admin/preorders/<int:preorder_id>", AdminPreOrderDetail.as_view()),
    path("products/<int:product_id>", PreOrderRemove.as_view()),
]