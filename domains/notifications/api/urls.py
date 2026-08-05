from django.urls import path

from .views import (
    ProviderDetail,
    ProviderList,
    ProviderOptionList,
    ProviderStatusList,
    SentNotificationDetail,
    SentNotificationList,
    SMSSend,
)

urlpatterns = [
    path("providers", ProviderList.as_view(), name="notification-provider-list"),
    path("providers/<int:provider_id>", ProviderDetail.as_view(), name="notification-provider-detail"),
    path("provider-statuses", ProviderStatusList.as_view(), name="notification-provider-status-list"),
    path("provider-options", ProviderOptionList.as_view(), name="notification-provider-option-list"),
    path("sent", SentNotificationList.as_view(), name="sent-notification-list"),
    path("sent/<uuid:notification_id>", SentNotificationDetail.as_view(), name="sent-notification-detail"),
    path("sms/send", SMSSend.as_view(), name="sms-send"),
]
