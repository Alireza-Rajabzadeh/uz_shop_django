from core.management.seeders.base import BaseSeeder
from domains.order.models import (
    OrderPaymentChannel,
    OrderPaymentChannelSupportMethod,
    OrderPaymentMethod,
    OrderStatus,
)


class OrderSeeder(BaseSeeder):
    def run(self):
        self._seed_statuses()
        self._seed_payment_methods()
        self._seed_payment_channels()

    def _seed_statuses(self):
        statuses = {
            1: ("payment_waiting", "در انتظار پرداخت"),
            2: ("success", "موفق"),
            3: ("failed", "ناموفق"),
            4: ("expired", "منقضی"),
        }
        for status_id, (name, fa_name) in statuses.items():
            OrderStatus.objects.update_or_create(
                id=status_id,
                defaults={"name": name, "fa_name": fa_name},
            )

    def _seed_payment_methods(self):
        methods = {
            1: ("card_to_card", "کارت به کارت"),
            2: ("deposit_to_account", "واریز به حساب"),
            3: ("online", "پرداخت آنلاین"),
            4: ("credit", "اعتبار"),
        }
        for method_id, (name, fa_name) in methods.items():
            OrderPaymentMethod.objects.update_or_create(
                id=method_id,
                defaults={"name": name, "fa_name": fa_name, "available": True},
            )

    def _seed_payment_channels(self):
        channels = {
            "card-to-card": {
                "name": "Mellat card-to-card",
                "fa_name": "کارت بانک ملت",
                "card_number": "6104337890123456",
                "owner_name": "UzShop",
                "method": "card_to_card",
            },
            "deposit-to-account": {
                "name": "Shahr bank account",
                "fa_name": "حساب بانک شهر",
                "account_number": "3123456789012345",
                "owner_name": "UzShop",
                "method": "deposit_to_account",
            },
            "online": {
                "name": "Zarinpal online",
                "fa_name": "درگاه پرداخت زرین‌پال",
                "method": "online",
            },
            "credit": {
                "name": "UzShop wallet credit",
                "fa_name": "اعتبار کیف پول اوز شاپ",
                "method": "credit",
            },
        }
        for key, data in channels.items():
            channel, _ = OrderPaymentChannel.objects.update_or_create(
                defaults={
                    "name": data["name"],
                    "fa_name": data["fa_name"],
                    "account_number": data.get("account_number"),
                    "card_number": data.get("card_number"),
                    "owner_name": data.get("owner_name"),
                },
                name=data["name"],
            )
            method = OrderPaymentMethod.objects.filter(name=data["method"]).first()
            if method is None:
                continue
            OrderPaymentChannelSupportMethod.objects.update_or_create(
                payment_channel=channel,
                payment_method=method,
            )