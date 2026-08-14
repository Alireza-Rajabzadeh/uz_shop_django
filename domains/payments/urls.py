from django.urls import path

from .views import (
    AdminPaymentChannelDetail,
    AdminPaymentChannelList,
    AdminPaymentChannelMethods,
    AdminPaymentMethodDetail,
    AdminPaymentMethodList,
    AdminPaymentReview,
)

urlpatterns = [
    path("admin/methods", AdminPaymentMethodList.as_view()),
    path("admin/methods/<int:method_id>", AdminPaymentMethodDetail.as_view()),
    path("admin/payments/<int:payment_id>/<str:decision>", AdminPaymentReview.as_view()),
    path("admin/channels", AdminPaymentChannelList.as_view()),
    path("admin/channels/<int:channel_id>", AdminPaymentChannelDetail.as_view()),
    path(
        "admin/channels/<int:channel_id>/methods",
        AdminPaymentChannelMethods.as_view(),
    ),
]
