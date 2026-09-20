from django.urls import path

from .views import (
    VendorBusinessPaymentChannelDetail,
    VendorBusinessPaymentChannelList,
    VendorBusinessPaymentChannelMethods,
    VendorBusinessPaymentDetail,
    VendorBusinessPaymentDocumentList,
    VendorBusinessPaymentList,
    VendorBusinessPaymentMethodDetail,
    VendorBusinessPaymentMethodList,
)

urlpatterns = [
    path("methods", VendorBusinessPaymentMethodList.as_view()),
    path("methods/<int:method_id>", VendorBusinessPaymentMethodDetail.as_view()),
    path("channels", VendorBusinessPaymentChannelList.as_view()),
    path("channels/<int:channel_id>", VendorBusinessPaymentChannelDetail.as_view()),
    path(
        "channels/<int:channel_id>/methods",
        VendorBusinessPaymentChannelMethods.as_view(),
    ),
    path("payments", VendorBusinessPaymentList.as_view()),
    path("payments/<int:payment_id>", VendorBusinessPaymentDetail.as_view()),
    path(
        "payments/<int:payment_id>/documents",
        VendorBusinessPaymentDocumentList.as_view(),
    ),
]
