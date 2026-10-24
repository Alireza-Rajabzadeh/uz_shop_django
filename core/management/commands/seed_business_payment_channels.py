from django.core.management.base import BaseCommand
from django.db import transaction

from core.management.seeders.business_payments import BusinessPaymentMethodsSeeder
from domains.banks.models import Bank
from domains.business.models import BusinessProfile
from domains.business_payments.models import (
    BusinessPaymentChannel,
    BusinessPaymentChannelSupportedMethod,
    BusinessPaymentMethod,
)

# Saman Bank's seeded card prefix; the seeded bank regex expects it.
CARD_PREFIX = "621986"
DEFAULT_BANK_FA_NAME = "بانک سامان"
CHANNEL_CODES = ("card_to_card", "deposit_to_account")


class Command(BaseCommand):
    help = (
        "Give existing businesses (vendors) a card-to-card and a "
        "deposit-to-account payment channel, using generated placeholder "
        "numbers of the right shape so the vendor payment flow can be "
        "checked against real data. Idempotent: a channel is only created "
        "when that business has no channel with the same code, and other "
        "channels the business configured are left alone."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--business-id",
            type=int,
            action="append",
            dest="business_ids",
            default=None,
            help="Only seed these business ids (repeatable).",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Seed at most this many businesses.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would be created without writing anything.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        if not dry_run:
            BusinessPaymentMethodsSeeder().run()

        methods = {
            method.code: method
            for method in BusinessPaymentMethod.objects.filter(
                code__in=CHANNEL_CODES, is_active=True
            )
        }
        missing = set(CHANNEL_CODES) - set(methods)
        if missing and not dry_run:
            self.stderr.write(
                self.style.ERROR(
                    "Missing payment methods: " + ", ".join(sorted(missing))
                )
            )
            return

        businesses = BusinessProfile.objects.order_by("id")
        if options["business_ids"]:
            businesses = businesses.filter(id__in=options["business_ids"])
        if options["limit"]:
            businesses = businesses[: options["limit"]]

        bank = (
            Bank.objects.filter(fa_name=DEFAULT_BANK_FA_NAME, is_active=True).first()
            or Bank.objects.filter(is_active=True).order_by("id").first()
        )

        created = existing = 0
        for business in businesses.iterator():
            pending = self._pending_codes(business)
            if dry_run:
                if pending:
                    self.stdout.write(
                        f"[dry-run] would add {', '.join(pending)} channels to "
                        f"business {business.id} "
                        f"({business.display_name or business.business_name})"
                    )
                created += len(pending)
                existing += len(CHANNEL_CODES) - len(pending)
                continue
            if not pending:
                existing += len(CHANNEL_CODES)
                continue
            created += self._create_channels(business, methods, bank, pending)
            existing += len(CHANNEL_CODES) - len(pending)

        verb = "would create" if dry_run else "created"
        self.stdout.write(
            self.style.SUCCESS(
                f"{verb} {created} payment channels, left {existing} existing "
                "canonical channels untouched."
            )
        )

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
        """A 16-digit placeholder that no other channel already uses."""
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
        """A 12-digit placeholder account number."""
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
