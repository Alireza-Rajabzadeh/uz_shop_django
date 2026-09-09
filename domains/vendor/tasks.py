import logging

from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=2)
def deliver_password_reset_sms(self, vendor_id, code, expires_at_iso):
    from domains.notifications.services import NotificationError, SMSService
    from django.utils.translation import gettext as _

    expires_at = timezone.datetime.fromisoformat(expires_at_iso)
    if vendor_id is None or expires_at <= timezone.now():
        return

    from domains.vendor.models import Vendor

    vendor = Vendor.objects.select_related("status").filter(
        pk=vendor_id,
        status__is_active=True,
    ).first()
    if vendor is None:
        return
    try:
        SMSService().send(
            receiver=vendor.phone,
            message=_(
                "Your UzShop password reset code is %(code)s. "
                "It expires in %(minutes)s minutes."
            ) % {
                "code": code,
                "minutes": max(int((expires_at - timezone.now()).total_seconds()) // 60, 1),
            },
            sensitive=True,
            expires_at=expires_at,
        )
    except NotificationError:
        logger.warning(
            "Password reset SMS could not be created for vendor %s", vendor.pk
        )
