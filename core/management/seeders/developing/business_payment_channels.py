from django.db import transaction

from core.management.seeders.base import BaseSeeder
from core.management.seeders.configs.business_payments import BusinessPaymentMethodsSeeder
from domains.banks.models import Bank
from domains.business.models import BusinessProfile
from domains.business_payments.models import (
    BusinessPaymentChannel,
    BusinessPaymentChannelSupportedMethod,
    BusinessPaymentMethod,
)

CARD_PREFIX = "621986"
DEFAULT_BANK_FA_NAME = "بانک سامان"
CHANNEL_CODES = ("card_to_card", "deposit_to_account")


class BusinessPaymentChannelsSeeder(BaseSeeder):
    """Seed test payment channels for existing businesses."""

    def __init__(self, business_ids=None, limit=None):
        self.business_ids = business_ids
        self.limit = limit

    def run(self):
        BusinessPaymentMethodsSeeder().run()
        methods = {
            method.code: method
            for method in BusinessPaymentMethod.objects.filter(
                code__in=CHANNEL_CODES, is_active=True
            )
        }
        missing = set(CHANNEL_CODES) - set(methods)
        if missing:
            return 0

        businesses = BusinessProfile.objects.order_by("id")
        if self.business_ids:
            businesses = businesses.filter(id__in=self.business_ids)
        if self.limit:
            businesses = businesses[:self.limit]

        bank = (
            Bank.objects.filter(fa_name=DEFAULT_BANK_FA_NAME, is_active=True).first()
            or Bank.objects.filter(is_active=True).order_by("id").first()
        )

        created = 0
        for business in businesses.iterator():
            pending = self._pending_codes(business)
            if not pending:
                continue
            created += self._create_channels(business, methods, bank, pending)

        return created

    @staticmethod
    def _pending_codes(business):
        present = set(
            BusinessPaymentChannel.objects.filter(
                business=business, code__in=CHANNEL_CODES
            ).values_list("code", flat=True)
        )
        return [code for code in CHANNEL_CODES if code not in present]

    @transaction.atomic
    def _create_channels(self, business, methods, bank, pending):
        specs = {
            "card_to_card": {
                "name": "Card to card",
                "fa_name": "کارت به کارت",
                "card_number": self._card_number(business),
            },
            "deposit_to_account": {
                "name": "Deposit to account",
                "fa_name": "واریز به حساب",
                "account_number": self._account_number(business),
            },
        }
        created = 0
        for code in pending:
            channel = BusinessPaymentChannel.objects.create(
                business=business,
                code=code,
                owner_name=(business.display_name or business.business_name)[:150],
                bank=bank,
                is_active=True,
                **specs[code],
            )
            BusinessPaymentChannelSupportedMethod.objects.create(
                payment_channel=channel,
                payment_method=methods[code],
            )
            created += 1
        return created

    @staticmethod
    def _card_number(business):
        used = set(
            BusinessPaymentChannel.objects.exclude(card_number__isnull=True)
            .values_list("card_number", flat=True)
        )
        index = business.pk
        while True:
            candidate = f"{CARD_PREFIX}{index:010d}"
            if candidate not in used:
                return candidate
            index += 1

    @staticmethod
    def _account_number(business):
        used = set(
            BusinessPaymentChannel.objects.exclude(account_number__isnull=True)
            .values_list("account_number", flat=True)
        )
        index = business.pk
        while True:
            candidate = f"{index:012d}"
            if candidate not in used:
                return candidate
            index += 1
