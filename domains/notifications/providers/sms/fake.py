import uuid

from .base import BaseSMSProvider, SMSBalance, SMSDeliveryResult, SMSHealth, SMSSendResult


class FakeSMSProvider(BaseSMSProvider):
    def send(self, receiver, message):
        return SMSSendResult(external_id=f"fake-{uuid.uuid4()}")

    def get_delivery_status(self, external_id):
        return SMSDeliveryResult(status="delivered")

    def get_health(self):
        return SMSHealth(healthy=True, message="Fake SMS provider is available.")

    def get_balance(self):
        return SMSBalance(amount=None, currency="")
