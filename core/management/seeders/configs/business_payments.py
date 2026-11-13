from core.management.seeders.base import BaseSeeder
from domains.business_payments.enums import BusinessPaymentMethodEnum
from domains.business_payments.models import BusinessPaymentMethod


class BusinessPaymentMethodsSeeder(BaseSeeder):
    """Reference rows for the methods a business can offer.

    Keyed on the BusinessPaymentMethodEnum values.
    """

    METHOD_METADATA = {
        BusinessPaymentMethodEnum.CARD_TO_CARD: {
            "name": "Card to card",
            "fa_name": "کارت به کارت",
            "point_to_channel_field": "card_number",
        },
        BusinessPaymentMethodEnum.DEPOSIT_TO_ACCOUNT: {
            "name": "Deposit to account",
            "fa_name": "واریز به حساب",
            "point_to_channel_field": "account_number",
        },
    }

    @property
    def METHODS(self):
        return [
            {"code": e.code, **self.METHOD_METADATA[e]}
            for e in self.METHOD_METADATA
        ]

    def run(self):
        methods = []
        for method_enum, defaults in self.METHOD_METADATA.items():
            method = BusinessPaymentMethod.objects.filter(code=method_enum.code).first()
            if method is None:
                if not BusinessPaymentMethod.objects.filter(id=method_enum.value).exists():
                    method = BusinessPaymentMethod.objects.create(
                        id=method_enum.value,
                        code=method_enum.code,
                        name=defaults["name"],
                        fa_name=defaults["fa_name"],
                        point_to_channel_field=defaults["point_to_channel_field"],
                        is_active=True,
                    )
                else:
                    method = BusinessPaymentMethod.objects.create(
                        code=method_enum.code,
                        name=defaults["name"],
                        fa_name=defaults["fa_name"],
                        point_to_channel_field=defaults["point_to_channel_field"],
                        is_active=True,
                    )
            methods.append(method)
        self.sync_sequence(BusinessPaymentMethod)
        return methods
