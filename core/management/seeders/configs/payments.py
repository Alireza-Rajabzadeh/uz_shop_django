from core.management.seeders.base import BaseSeeder
from domains.payments.enums import PaymentMethodEnum
from domains.payments.models import PaymentMethod


class PaymentsSeeder(BaseSeeder):
    METHODS = {
        PaymentMethodEnum.ONLINE: ("online", "Online payment", "پرداخت آنلاین"),
        PaymentMethodEnum.CARD_TO_CARD: ("card_to_card", "Card to card", "کارت به کارت"),
        PaymentMethodEnum.DEPOSIT_TO_ACCOUNT: ("deposit_to_account", "Deposit to account", "واریز به حساب"),
        PaymentMethodEnum.CREDIT: ("credit", "Credit", "اعتبار"),
    }

    def run(self):
        for method_enum, (code, name, fa_name) in self.METHODS.items():
            PaymentMethod.objects.update_or_create(
                id=method_enum.value,
                defaults={
                    "code": code,
                    "name": name,
                    "fa_name": fa_name,
                    "is_active": True,
                },
            )
        self.sync_sequence(PaymentMethod)
