"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.contrib import admin
from django.urls import path, include

from domains.order.views import OrderListCreateView
from domains.preorder.views import PreOrderListCreate
from domains.wishlist.views import WishlistListCreate

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/users/", include("domains.users.users_urls")),
    path("api/business/", include("domains.business.api.urls")),
    path("api/customer/", include("domains.customer.urls")),
    path("api/catalog/", include("domains.catalog.api.urls")),
    path("api/importing/", include("domains.importing.api.urls")),
    path("api/inventory/", include("domains.inventory.api.urls")),
    path("api/location/", include("domains.location.urls")),
    path("api/files/", include("domains.files.api.urls")),
    path("api/notifications/", include("domains.notifications.api.urls")),
    path("api/payments/", include("domains.payments.urls")),
    path("api/content/", include("domains.content.urls")),
    path("api/wishlist", WishlistListCreate.as_view()),
    path("api/wishlist/", include("domains.wishlist.urls")),
    path("api/preorder", PreOrderListCreate.as_view()),
    path("api/preorder/", include("domains.preorder.urls")),
    path("api/cart/", include("domains.cart.urls")),
    path("api/order", OrderListCreateView.as_view()),
    path("api/order/", include("domains.order.urls")),
]
