from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from core.management.seeders.business_payments import BusinessPaymentMethodsSeeder
from domains.banks.models import Bank
from domains.business.models import BusinessProfile, BusinessStatus
from domains.business.enums.BusinessStatusEnum import BusinessStatusEnum
from domains.business_payments.models import (
    BusinessPaymentChannel,
    BusinessPaymentChannelSupportedMethod,
    BusinessPaymentMethod,
)


class BusinessPaymentMethodsSeederTests(TestCase):
    def setUp(self):
        self.seeder = BusinessPaymentMethodsSeeder()

    def test_seeder_creates_manual_methods(self):
        self.seeder.run()
        methods = {
            method.code: method for method in BusinessPaymentMethod.objects.all()
        }
        self.assertEqual(
            set(methods), {"card_to_card", "deposit_to_account"}
        )
        self.assertEqual(
            methods["card_to_card"].point_to_channel_field, "card_number"
        )
        self.assertEqual(
            methods["deposit_to_account"].point_to_channel_field,
            "account_number",
        )
        self.assertTrue(all(method.is_active for method in methods.values()))

    def test_seeder_is_idempotent(self):
        self.seeder.run()
        self.seeder.run()
        self.assertEqual(BusinessPaymentMethod.objects.count(), 2)

    def test_seeder_keeps_existing_rows_untouched(self):
        existing = BusinessPaymentMethod.objects.create(
            code="card_to_card",
            name="Legacy card",
            fa_name="کارت قدیمی",
        )
        self.seeder.run()
        existing.refresh_from_db()
        self.assertEqual(existing.name, "Legacy card")
        self.assertEqual(BusinessPaymentMethod.objects.count(), 2)


class SeedBusinessPaymentChannelsCommandTests(TestCase):
    def setUp(self):
        BusinessStatus.objects.get_or_create(
            id=BusinessStatusEnum.CONFIRMATION_AWAIT.value,
            defaults={
                "code": "confirmation_await",
                "name": "Confirmation await",
                "title": "در انتظار تایید",
            },
        )
        self.bank = Bank.objects.create(
            name="Saman Bank",
            fa_name="بانک سامان",
            card_number_regex=r"^621986\d{10}$",
            account_number_regex=r"^\d{10,24}$",
            sheba_regex=r"^IR\d{24}$",
        )
        self.business_a = BusinessProfile.objects.create(
            business_name="Atlas Market",
            display_name="اتلس مارکت",
        )
        self.business_b = BusinessProfile.objects.create(
            business_name="Bazaar Nour",
            display_name="بازار نور",
        )

    def _run(self, **options):
        options.setdefault(
            "business_ids", [self.business_a.id, self.business_b.id]
        )
        out = StringIO()
        call_command("seed_business_payment_channels", stdout=out, **options)
        return out.getvalue()

    def _businesses(self):
        return [self.business_a, self.business_b]

    def test_creates_two_channels_with_supported_methods(self):
        self._run()
        self.assertEqual(
            BusinessPaymentChannel.objects.filter(
                business__in=self._businesses()
            ).count(),
            4,
        )

        for business in (self.business_a, self.business_b):
            channels = {
                channel.code: channel
                for channel in BusinessPaymentChannel.objects.filter(
                    business=business
                )
            }
            self.assertEqual(
                set(channels), {"card_to_card", "deposit_to_account"}
            )
            card_channel = channels["card_to_card"]
            account_channel = channels["deposit_to_account"]
            self.assertEqual(len(card_channel.card_number), 16)
            self.assertTrue(card_channel.card_number.startswith("621986"))
            self.assertEqual(len(account_channel.account_number), 12)
            self.assertEqual(card_channel.bank_id, self.bank.id)
            self.assertEqual(card_channel.owner_name, business.display_name)
            self.assertEqual(
                [
                    support.payment_method.code
                    for support in card_channel.supported_methods.all()
                ],
                ["card_to_card"],
            )
            self.assertEqual(
                [
                    support.payment_method.code
                    for support in account_channel.supported_methods.all()
                ],
                ["deposit_to_account"],
            )

    def test_generated_numbers_are_unique_per_channel(self):
        self._run()
        channels = BusinessPaymentChannel.objects.filter(
            business__in=self._businesses()
        )
        card_numbers = list(
            channels.exclude(card_number__isnull=True).values_list(
                "card_number", flat=True
            )
        )
        account_numbers = list(
            channels.exclude(account_number__isnull=True).values_list(
                "account_number", flat=True
            )
        )
        self.assertEqual(len(card_numbers), len(set(card_numbers)))
        self.assertEqual(len(account_numbers), len(set(account_numbers)))

    def test_command_is_idempotent(self):
        self._run()
        output = self._run()
        self.assertEqual(
            BusinessPaymentChannel.objects.filter(
                business__in=self._businesses()
            ).count(),
            4,
        )
        self.assertEqual(
            BusinessPaymentChannelSupportedMethod.objects.filter(
                payment_channel__business__in=self._businesses()
            ).count(),
            4,
        )
        self.assertIn("left 4 existing canonical channels untouched", output)

    def test_command_keeps_channels_the_business_already_configured(self):
        method = BusinessPaymentMethodsSeeder().run()[0]
        channel = BusinessPaymentChannel.objects.create(
            business=self.business_a,
            code="existing",
            name="Existing",
        )
        BusinessPaymentChannelSupportedMethod.objects.create(
            payment_channel=channel, payment_method=method
        )
        self._run()
        self.assertEqual(
            set(
                BusinessPaymentChannel.objects.filter(
                    business=self.business_a
                ).values_list("code", flat=True)
            ),
            {"existing", "card_to_card", "deposit_to_account"},
        )
        self.assertEqual(
            BusinessPaymentChannel.objects.filter(
                business=self.business_b
            ).count(),
            2,
        )

    def test_dry_run_writes_nothing(self):
        output = self._run(dry_run=True)
        self.assertFalse(
            BusinessPaymentChannel.objects.filter(
                business__in=self._businesses()
            ).exists()
        )
        self.assertEqual(BusinessPaymentMethod.objects.count(), 0)
        self.assertIn("[dry-run]", output)

    def test_business_id_option_limits_scope(self):
        self._run(business_ids=[self.business_b.id])
        self.assertFalse(
            BusinessPaymentChannel.objects.filter(
                business=self.business_a
            ).exists()
        )
        self.assertEqual(
            BusinessPaymentChannel.objects.filter(
                business=self.business_b
            ).count(),
            2,
        )
