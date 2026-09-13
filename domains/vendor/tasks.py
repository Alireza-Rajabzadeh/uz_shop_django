import logging

from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task(bind=True, ignore_result=True, max_retries=2)
def deliver_vendor_sms(self, vendor_id, message, expires_at_iso):
    from domains.notifications.services import NotificationError, SMSService

    expires_at = timezone.datetime.fromisoformat(expires_at_iso)
    if vendor_id is None or expires_at <= timezone.now():
        return

    from domains.vendor.models import Vendor

    vendor = Vendor.objects.filter(pk=vendor_id).first()
    if vendor is None:
        return
    try:
        SMSService().send(
            receiver=vendor.phone,
            message=message,
            sensitive=True,
            expires_at=expires_at,
        )
    except NotificationError:
        logger.warning(
            "SMS could not be created for vendor %s", vendor.pk
        )
