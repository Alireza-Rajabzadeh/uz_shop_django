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

        PaymentsSeeder().run()
        customer_status = CustomerStatus.objects.create(name="payments-active", title="Active")
        self.customer = Customer.objects.create_user(
            phone="09120000801", password="password", first_name="Payment",
            last_name="Customer", customer_code="CUS-PAY-001", status=customer_status,
        )
        self.card_method = PaymentMethod.objects.get(code="card_to_card")
        self.channel = PaymentChannel.objects.create(
            code="manual_test", name="Manual test", fa_name="درگاه دستی",
            card_number="6104337890123456",
        )
        PaymentChannelSupportedMethod.objects.create(
            payment_channel=self.channel, payment_method=self.card_method
        )

    def make_order(self, **values):
        defaults = {
            "customer": self.customer,
            "status": OrderStatus.objects.get(name="payment_pending"),
            "address_info": {},
            "subtotal": Decimal("100.00"),
            "discount_amount": Decimal("0.00"),
            "shipping_amount": Decimal("0.00"),
            "total_amount": Decimal("100.00"),
            "reservation_expires_at": timezone.now() + timezone.timedelta(minutes=10),
        }
        defaults.update(values)
        return Order.objects.create(**defaults)

    def test_fixed_method_seeder_preserves_admin_values(self):
        self.card_method.name = "Edited label"
        self.card_method.fa_name = "ویرایش شده"
        self.card_method.is_active = False
        self.card_method.save()
        PaymentsSeeder().run()
        self.card_method.refresh_from_db()
        self.assertEqual(self.card_method.name, "Edited label")
        self.assertEqual(self.card_method.fa_name, "ویرایش شده")
        self.assertFalse(self.card_method.is_active)

    def test_codes_are_immutable(self):
        self.card_method.code = "changed"
        with self.assertRaises(ValueError):
            self.card_method.save()
        self.channel.code = "changed"
        with self.assertRaises(ValueError):
            self.channel.save()

    def test_online_support_requires_provider(self):
        online = PaymentMethod.objects.get(code="online")
        channel = PaymentChannel.objects.create(code="saman", name="Saman", fa_name="سامان")
        relation = PaymentChannelSupportedMethod(
            payment_channel=channel, payment_method=online
        )
        with self.assertRaises(DjangoValidationError):
            relation.save()
        self.assertIsNone(provider_class("saman"))
        self.assertEqual(
            provider_availability("saman"),
            (False, "Online payment provider is not implemented."),
        )

    def test_payment_constraints(self):
        order = self.make_order()
        Payment.objects.create(
            order=order, payment_method=self.card_method, payment_channel=self.channel,
            amount="100.00", status=Payment.Status.SUCCESSFUL,
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            Payment.objects.create(
                order=order, payment_method=self.card_method, payment_channel=self.channel,
                amount="100.00", status=Payment.Status.SUCCESSFUL,
            )
        with self.assertRaises(IntegrityError), transaction.atomic():
            Payment.objects.create(
                order=self.make_order(), payment_method=self.card_method,
                amount="0.00", status=Payment.Status.PENDING,
            )

    def test_customer_options_exclude_inactive_and_old_routes_are_removed(self):
        self.channel.extra_data = {"secret": "internal"}
        self.channel.save()
        self.client.force_authenticate(self.customer)
        response = self.client.get("/api/order/payment-methods")
        self.assertEqual(response.status_code, 200)
        card = next(row for row in response.data["data"]["methods"] if row["code"] == "card_to_card")
        self.assertEqual(card["channels"][0]["card_number"], "6104337890123456")
        self.assertNotIn("extra_data", card["channels"][0])
        self.channel.is_active = False
        self.channel.save()
        response = self.client.get("/api/order/payment-methods")
        card = next(row for row in response.data["data"]["methods"] if row["code"] == "card_to_card")
        self.assertEqual(card["channels"], [])
        self.assertEqual(self.client.get("/api/payments/methods").status_code, 404)
        self.assertEqual(self.client.post("/api/payments/orders/1/pay", {}).status_code, 404)

    def test_expired_reservation_is_rejected_before_success(self):
        self.client.force_authenticate(self.customer)
        order = self.make_order(
            reservation_expires_at=timezone.now() - timezone.timedelta(seconds=1)
        )
        response = self.client.post(
            f"/api/order/{order.id}/pay",
            {"payment_method": "card_to_card", "payment_channel_id": self.channel.id},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        order.refresh_from_db()
        self.assertEqual(order.status.name, "payment_expired")
        self.assertFalse(Payment.objects.filter(order=order).exists())

    def test_required_document_is_stored_for_pending_admin_review(self):
        self.card_method.requires_documents = True
        self.card_method.point_to_channel_field = "card_number"
        self.card_method.save()
        self.client.force_authenticate(self.customer)
        order = self.make_order()
        missing = self.client.post(
            f"/api/order/{order.id}/pay",
            {"payment_method": "card_to_card", "payment_channel_id": self.channel.id},
            format="multipart",
        )
        self.assertEqual(missing.status_code, 400)
        image = SimpleUploadedFile(
            "receipt.png", b"payment-receipt", content_type="image/png"
        )
        response = self.client.post(
            f"/api/order/{order.id}/pay",
            {
                "payment_method": "card_to_card",
                "payment_channel_id": self.channel.id,
                "documents": [image],
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, 202, response.data)
        order.refresh_from_db()
        payment = Payment.objects.get(order=order)
        document = PaymentDocument.objects.get(payment=payment)
        self.assertEqual(order.status.name, "payment_processing")
        self.assertEqual(payment.status, Payment.Status.PENDING)
        self.assertTrue(document.file.object_key.startswith(
            f"orders/{order.id}/payments/{payment.id}/"
        ))
        with self.assertRaises(ProtectedError):
            document.file.delete()

