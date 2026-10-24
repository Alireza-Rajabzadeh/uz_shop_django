from core.management.seeders.base import BaseSeeder
from domains.business_payments.models import BusinessPaymentMethod


class BusinessPaymentMethodsSeeder(BaseSeeder):
    """Reference rows for the methods a business can offer.

    The shop-side ``PaymentsSeeder`` only seeds ``domains.payments``; the
    vendor/business payment flow reads this table instead. Codes are the API
    contract (``BusinessPaymentService.MANUAL_METHODS``), so they are the
    lookup key and are never rewritten.
    """

    METHODS = [
        {
            "code": "card_to_card",
            "name": "Card to card",
            "fa_name": "کارت به کارت",
            "point_to_channel_field": "card_number",
        },
        {
            "code": "deposit_to_account",
            "name": "Deposit to account",
            "fa_name": "واریز به حساب",
            "point_to_channel_field": "account_number",
        },
    ]

    def run(self):
        methods = []
        for record in self.METHODS:
            method, _ = BusinessPaymentMethod.objects.get_or_create(
                code=record["code"],
                defaults={
                    "name": record["name"],
                    "fa_name": record["fa_name"],
                    "point_to_channel_field": record["point_to_channel_field"],
                    "is_active": True,
                },
            )
            methods.append(method)
        return methods
