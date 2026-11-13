from decimal import Decimal

from django.contrib.auth.models import Permission, User
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db.models.deletion import ProtectedError
from django.test import override_settings
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.test import APITestCase

from core.management.seeders.configs.order import OrderSeeder
from core.management.seeders.configs.payments import PaymentsSeeder
from domains.customer.models import Customer, CustomerStatus
from domains.files.models import File, FileStatus
from domains.order.models import Order, OrderStatus

from domains.payments.models import (
    Payment, PaymentChannel, PaymentChannelSupportedMethod, PaymentDocument,
    PaymentMethod,
)
from domains.payments.online_payment_providers import provider_availability, provider_class


@override_settings(
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    },
    FILE_STORAGE_ALIASES=["default"],
)
class PaymentDomainTests(APITestCase):
    def setUp(self):
        OrderSeeder().run()

        admin = User.objects.create_superuser("payment-reviewer", password="password")
        self.client.force_authenticate(admin)
        approved = self.client.post(
            f"/api/payments/admin/payments/{payment.id}/approve", {}, format="json"
        )
        self.assertEqual(approved.status_code, 200)
        order.refresh_from_db()
        payment.refresh_from_db()
        self.assertEqual(order.status.name, "paid")
        self.assertEqual(order.successful_payment_id, payment.id)
        self.assertEqual(payment.status, Payment.Status.SUCCESSFUL)


class PaymentAdminAPITests(APITestCase):
    def setUp(self):
        PaymentsSeeder().run()
        self.admin = User.objects.create_superuser("payments-admin", password="password")
        self.client.force_authenticate(self.admin)
        self.method = PaymentMethod.objects.get(code="card_to_card")
        self.channel = PaymentChannel.objects.create(
            code="admin_channel", name="Admin channel", fa_name="درگاه مدیریت",
            card_number="6104337890123456", account_number="123456789012",
        )
        PaymentChannelSupportedMethod.objects.create(
            payment_channel=self.channel, payment_method=self.method
        )

    def test_method_list_filters_and_patch_rejects_code(self):
        response = self.client.get("/api/payments/admin/methods", {"search": "card"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["count"], 1)
        response = self.client.patch(
            f"/api/payments/admin/methods/{self.method.id}",
            {
                "name": "Edited", "point_to_channel_field": "card_number",
                "requires_documents": True, "is_active": False,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["point_to_channel_field"], "card_number")
        self.assertTrue(response.data["data"]["requires_documents"])
        self.method.refresh_from_db()
        self.assertEqual(self.method.point_to_channel_field, "card_number")
        response = self.client.patch(
            f"/api/payments/admin/methods/{self.method.id}",
            {"code": "changed"}, format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_channel_list_masks_and_detail_is_full(self):
        listing = self.client.get("/api/payments/admin/channels")
        row = listing.data["data"]["results"][0]
        self.assertNotEqual(row["card_number"], self.channel.card_number)
        self.assertTrue(row["card_number"].endswith("3456"))
        detail = self.client.get(f"/api/payments/admin/channels/{self.channel.id}")
        self.assertEqual(detail.data["data"]["card_number"], self.channel.card_number)
        self.assertEqual(detail.data["data"]["account_number"], self.channel.account_number)

    def test_view_only_admin_cannot_access_unmasked_channel_detail(self):
        admin = User.objects.create_user(
            "payments-viewer", password="password", is_staff=True
        )
        admin.user_permissions.add(
            Permission.objects.get(codename="view_paymentchannel")
        )
        self.client.force_authenticate(admin)

        self.assertEqual(
            self.client.get("/api/payments/admin/channels").status_code, 200
        )
        self.assertEqual(
            self.client.get(
                f"/api/payments/admin/channels/{self.channel.id}"
            ).status_code,
            403,
        )

    def test_channel_create_and_atomic_method_replacement(self):
        deposit = PaymentMethod.objects.get(code="deposit_to_account")
        response = self.client.post(
            "/api/payments/admin/channels",
            {
                "code": "new_manual", "name": "New manual", "fa_name": "جدید",
                "is_active": True, "payment_method_ids": [self.method.id, deposit.id],
            }, format="json",
        )
        self.assertEqual(response.status_code, 201)
        channel_id = response.data["data"]["id"]
        response = self.client.post(
            f"/api/payments/admin/channels/{channel_id}/methods",
            {"payment_method_ids": [deposit.id]}, format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            PaymentChannelSupportedMethod.objects.get(payment_channel_id=channel_id).payment_method,
            deposit,
        )

    def test_logo_must_be_available_image(self):
        available, _ = FileStatus.objects.get_or_create(name="available")
        file = File.objects.create(
            status=available, storage_alias="default", object_key="payments/logo.txt",
            original_name="logo.txt", file_type="document", content_type="text/plain",
            extension="txt", size=4, checksum="a" * 64,
        )
        response = self.client.patch(
            f"/api/payments/admin/channels/{self.channel.id}",
            {"logo_file_id": str(file.id)}, format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_online_channel_creation_exposes_validation_reason(self):
        online = PaymentMethod.objects.get(code="online")
        response = self.client.post(
            "/api/payments/admin/channels",
            {
                "code": "saman", "name": "Saman", "fa_name": "سامان",
                "payment_method_ids": [online.id],
            }, format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("payment_method_ids", response.data["errors"])

    def test_admin_contract_fields_and_filters(self):
        methods = self.client.get("/api/payments/admin/methods").data["data"]["results"]
        card = next(row for row in methods if row["code"] == "card_to_card")
        online = next(row for row in methods if row["code"] == "online")
        self.assertEqual(card["supported_channel_count"], 1)
        self.assertTrue(card["provider_available"])
        self.assertFalse(online["provider_available"])
        self.assertTrue(online["provider_unavailable_reason"])

        response = self.client.get(
            "/api/payments/admin/channels",
            {"supported_method": self.method.id},
        )
        self.assertEqual(response.data["data"]["count"], 1)
        row = response.data["data"]["results"][0]
        self.assertEqual(row["masked_card_number"], "************3456")
        self.assertEqual(row["payment_count"], 0)

    def test_channel_can_be_created_without_initial_methods(self):
        response = self.client.post(
            "/api/payments/admin/channels",
            {"code": "empty", "name": "Empty", "fa_name": "خالی"},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["data"]["supported_methods"], [])

    def test_channel_create_rejects_invalid_card_number(self):
        response = self.client.post(
            "/api/payments/admin/channels",
            {
                "code": "bad_card", "name": "Bad card", "fa_name": "خراب",
                "card_number": "1234",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("card_number", response.data["errors"])

    def test_channel_create_normalizes_persian_card_number(self):
        response = self.client.post(
            "/api/payments/admin/channels",
            {
                "code": "persian_card", "name": "Persian card", "fa_name": "فارسی",
                "card_number": "۶۱۰۴ ۳۳۷۸ ۹۰۱۲ ۳۴۵۶",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        channel = PaymentChannel.objects.get(id=response.data["data"]["id"])
        self.assertEqual(channel.card_number, "6104337890123456")

    def test_channel_patch_rejects_invalid_card_number(self):
        response = self.client.patch(
            f"/api/payments/admin/channels/{self.channel.id}",
            {"card_number": "610433789012345a"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.channel.refresh_from_db()
        self.assertEqual(self.channel.card_number, "6104337890123456")

    def test_delete_routes_do_not_exist(self):
        self.assertEqual(
            self.client.delete(f"/api/payments/admin/channels/{self.channel.id}").status_code,
            405,
        )
        self.assertEqual(
            self.client.delete(f"/api/payments/admin/methods/{self.method.id}").status_code,
            405,
        )

