from celery import shared_task

from domains.notifications.models import SentNotification
from domains.notifications.services import NotificationInProgress, SMSService


@shared_task(bind=True, ignore_result=True, max_retries=10)
def send_sms_notification(self, notification_id):
    try:
        SMSService().process(notification_id)
    except NotificationInProgress as exc:
        raise self.retry(exc=exc, countdown=60) from exc


@shared_task(bind=True, ignore_result=True, max_retries=10)
def refresh_sms_delivery_status(self, notification_id):
    try:
        notification = SMSService().refresh_delivery_status(notification_id)
    except Exception as exc:
        raise self.retry(exc=exc, countdown=60) from exc
    if notification.status == "sent":
        raise self.retry(countdown=60)


@shared_task(ignore_result=True)
def expire_sensitive_notification(notification_id):
    SentNotification.objects.filter(
        pk=notification_id,
        status=SentNotification.Status.PENDING,
        is_sensitive=True,
    ).update(
        status=SentNotification.Status.FAILED,
        message="[redacted]",
        error_message="The notification expired before it could be sent.",
    )
