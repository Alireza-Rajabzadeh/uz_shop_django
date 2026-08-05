from datetime import datetime

from celery import shared_task

from domains.customer.services.auth_service import CustomerAuthService


@shared_task(ignore_result=True)
def deliver_password_reset_sms(customer_id, code, expires_at):
    CustomerAuthService().deliver_password_reset_code(
        customer_id=customer_id,
        code=code,
        expires_at=datetime.fromisoformat(expires_at),
    )
