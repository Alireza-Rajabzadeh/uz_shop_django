from core.management.seeders.base import BaseSeeder
from domains.payments.models import PaymentMethod


class PaymentsSeeder(BaseSeeder):
    def run(self):
        methods = {
            1: ("online", "Online payment", "پرداخت آنلاین"),
            2: ("card_to_card", "Card to card", "کارت به کارت"),
            3: ("deposit_to_account", "Deposit to account", "واریز به حساب"),
            4: ("credit", "Credit", "اعتبار"),
        }
        for method_id, (code, name, fa_name) in methods.items():
            PaymentMethod.objects.get_or_create(
                code=code,
                defaults={
                    "id": method_id, "name": name, "fa_name": fa_name, "is_active": True,
                },
            )
