from decimal import Decimal

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from core.management.seeders.order import OrderSeeder
from core.management.seeders.payments import PaymentsSeeder
from domains.business.models import BusinessProfile
from domains.customer.models import Customer, CustomerStatus
from domains.files.models import File, FileStatus
from domains.order.models import Order, OrderStatus
from domains.vendor.enums.VendorStatusEnum import VendorStatusEnum
from domains.vendor.models import Vendor, VendorStatus

from .models import (
    BusinessPayment,
    BusinessPaymentChannel,
    BusinessPaymentChannelSupportedMethod,
    BusinessPaymentDocument,
    BusinessPaymentMethod,
    BusinessPaymentStatus,
)
from .online_payment_providers import provider_availability, provider_class
from .services import BusinessPaymentService


def _make_vendor(phone, national_id, vendor_status):
    return Vendor.objects.create_user(
        phone=phone,
        password="pass1234",
        first_name="Test",
        last_name="Vendor",
        national_id=national_id,
        status=vendor_status,
    )


def _make_business(vendor):
    existing = BusinessProfile.objects.filter(vendor=vendor).first()
    if existing:
        return existing
    from django.db import connection
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT setval(pg_get_serial_sequence('business_profile', 'id'), "
            "(SELECT COALESCE(MAX(id), 0) + 1 FROM business_profile))"
        )
    return BusinessProfile.objects.create(
        vendor=vendor,
        business_name=f"Business {vendor.national_id}",
        display_name=f"Biz {vendor.national_id}",
    )


@override_settings(
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
        },
    },
    FILE_STORAGE_ALIASES=["default"],
)
class BusinessPaymentModelTests(APITestCase):
    def setUp(self):
        self.vendor_status, _ = VendorStatus.objects.get_or_create(
            id=VendorStatusEnum.ACTIVE.value,
            defaults={"name": "active", "title": "Active"},
        )
        self.vendor_a = _make_vendor("+9900000001", "1000000001", self.vendor_status)
        self.vendor_b = _make_vendor("+9900000002", "1000000002", self.vendor_status)
        self.business_a = _make_business(self.vendor_a)
        self.business_b = _make_business(self.vendor_b)
        self.status_pending, _ = BusinessPaymentStatus.objects.get_or_create(
            name="pending", defaults={"title": "Pending", "is_active": True}
        )
        self.status_successful, _ = BusinessPaymentStatus.objects.get_or_create(
            name="successful", defaults={"title": "Successful", "is_active": True}
        )
        self.status_failed, _ = BusinessPaymentStatus.objects.get_or_create(
            name="failed", defaults={"title": "Failed", "is_active": True}
        )

    def test_method_code_is_immutable(self):
        method = BusinessPaymentMethod.objects.create(
            code="card_to_card",
            name="Card", fa_name="کارت",
        )
        method.code = "changed"
        with self.assertRaises(ValueError):
            method.save()

    def test_channel_code_is_immutable(self):
        channel = BusinessPaymentChannel.objects.create(
            business=self.business_a,
            code="channel_a",
            name="Channel A", fa_name="کانال الف",
        )
        channel.code = "changed"
        with self.assertRaises(ValueError):
            channel.save()

    def test_method_code_is_unique(self):
        BusinessPaymentMethod.objects.create(
            code="card_to_card",
            name="Card", fa_name="کارت",
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            BusinessPaymentMethod.objects.create(
                code="card_to_card",
                name="Card 2", fa_name="کارت ۲",
            )

    def test_method_code_is_unique_across_all(self):
        BusinessPaymentMethod.objects.create(
            code="card_to_card",
            name="Card A", fa_name="کارت الف",
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            BusinessPaymentMethod.objects.create(
                code="card_to_card",
                name="Card B", fa_name="کارت ب",
            )

    def test_channel_code_is_unique(self):
        BusinessPaymentChannel.objects.create(
            business=self.business_a,
            code="channel_a",
            name="Channel A", fa_name="کانال الف",
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            BusinessPaymentChannel.objects.create(
                business=self.business_a,
                code="channel_a",
                name="Channel A2", fa_name="کانال الف ۲",
            )

    def test_channel_code_can_differ_across_businesses(self):
        BusinessPaymentChannel.objects.create(
            business=self.business_a,
            code="channel_a",
            name="Channel A", fa_name="کانال الف",
        )
        BusinessPaymentChannel.objects.create(
            business=self.business_b,
            code="channel_a",
            name="Channel A B", fa_name="کانال الف ب",
        )

    def test_payment_amount_must_be_positive(self):
        method = BusinessPaymentMethod.objects.create(
            code="card_to_card",
            name="Card", fa_name="کارت",
        )
        OrderSeeder().run()
        customer_status = CustomerStatus.objects.create(
            name="bp-test", title="Active"
        )
        customer = Customer.objects.create_user(
            phone="09120001001", password="password", first_name="T",
            last_name="C", customer_code="CUS-BP-001", status=customer_status,
        )
        order = Order.objects.create(
            customer=customer,
            status=OrderStatus.objects.get(name="payment_pending"),
            address_info={}, subtotal=Decimal("100.00"),
            discount_amount=Decimal("0.00"), shipping_amount=Decimal("0.00"),
            total_amount=Decimal("100.00"),
            reservation_expires_at=timezone.now() + timezone.timedelta(minutes=10),
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            BusinessPayment.objects.create(
                business=self.business_a, order=order,
                payment_method=method, amount=Decimal("0.00"),
                status=self.status_pending,
            )

    def test_only_one_successful_payment_per_order(self):
        PaymentsSeeder().run()
        method = BusinessPaymentMethod.objects.create(
            code="card_to_card",
            name="Card", fa_name="کارت",
        )
        OrderSeeder().run()
        customer_status = CustomerStatus.objects.create(
            name="bp-test-2", title="Active"
        )
        customer = Customer.objects.create_user(
            phone="09120001002", password="password", first_name="T",
            last_name="C", customer_code="CUS-BP-002", status=customer_status,
        )
        order = Order.objects.create(
            customer=customer,
            status=OrderStatus.objects.get(name="payment_pending"),
            address_info={}, subtotal=Decimal("100.00"),
            discount_amount=Decimal("0.00"), shipping_amount=Decimal("0.00"),
            total_amount=Decimal("100.00"),
            reservation_expires_at=timezone.now() + timezone.timedelta(minutes=10),
        )
        BusinessPayment.objects.create(
            business=self.business_a, order=order,
            payment_method=method, amount=Decimal("100.00"),
            status=self.status_successful,
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            BusinessPayment.objects.create(
                business=self.business_a, order=order,
                payment_method=method, amount=Decimal("100.00"),
                status=self.status_successful,
            )

    def test_online_support_requires_provider(self):
        method = BusinessPaymentMethod.objects.create(
            code="online",
            name="Online", fa_name="آنلاین",
        )
        channel = BusinessPaymentChannel.objects.create(
            business=self.business_a,
            code="saman",
            name="Saman", fa_name="سامان",
        )
        relation = BusinessPaymentChannelSupportedMethod(
            payment_channel=channel, payment_method=method
        )
        with self.assertRaises(DjangoValidationError):
            relation.save()
        self.assertIsNone(provider_class("saman"))
        self.assertEqual(
            provider_availability("saman"),
            (False, "Online payment provider is not implemented."),
        )

    def test_document_unique_per_payment(self):
        PaymentsSeeder().run()
        method = BusinessPaymentMethod.objects.create(
            code="card_to_card",
            name="Card", fa_name="کارت",
        )
        OrderSeeder().run()
        customer_status = CustomerStatus.objects.create(
            name="bp-doc", title="Active"
        )
        customer = Customer.objects.create_user(
            phone="09120001003", password="password", first_name="T",
            last_name="C", customer_code="CUS-BP-003", status=customer_status,
        )
        order = Order.objects.create(
            customer=customer,
            status=OrderStatus.objects.get(name="payment_pending"),
            address_info={}, subtotal=Decimal("100.00"),
            discount_amount=Decimal("0.00"), shipping_amount=Decimal("0.00"),
            total_amount=Decimal("100.00"),
            reservation_expires_at=timezone.now() + timezone.timedelta(minutes=10),
        )
        payment = BusinessPayment.objects.create(
            business=self.business_a, order=order,
            payment_method=method, amount=Decimal("100.00"),
            status=self.status_pending,
        )
        file_status, _ = FileStatus.objects.get_or_create(name="available")
        file = File.objects.create(
            status=file_status, storage_alias="default",
            object_key="bp/test.txt", original_name="test.txt",
            file_type="document", content_type="text/plain",
            extension="txt", size=4, checksum="a" * 64,
        )
        BusinessPaymentDocument.objects.create(payment=payment, file=file)
        with self.assertRaises(IntegrityError), transaction.atomic():
            BusinessPaymentDocument.objects.create(payment=payment, file=file)


@override_settings(
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
        },
    },
    FILE_STORAGE_ALIASES=["default"],
)
class BusinessPaymentVendorAPITests(APITestCase):
    def setUp(self):
        self.vendor_status, _ = VendorStatus.objects.get_or_create(
            id=VendorStatusEnum.ACTIVE.value,
            defaults={"name": "active", "title": "Active"},
        )
        self.vendor_a = _make_vendor("+9900000003", "1000000003", self.vendor_status)
        self.vendor_b = _make_vendor("+9900000004", "1000000004", self.vendor_status)
        self.business_a = _make_business(self.vendor_a)
        self.business_b = _make_business(self.vendor_b)
        self.status_pending, _ = BusinessPaymentStatus.objects.get_or_create(
            name="pending", defaults={"title": "Pending", "is_active": True}
        )
        self.status_successful, _ = BusinessPaymentStatus.objects.get_or_create(
            name="successful", defaults={"title": "Successful", "is_active": True}
        )
        self.status_failed, _ = BusinessPaymentStatus.objects.get_or_create(
            name="failed", defaults={"title": "Failed", "is_active": True}
        )
        self.method_a = BusinessPaymentMethod.objects.create(
            code="card_to_card",
            name="Card A", fa_name="کارت الف",
        )
        self.method_b = BusinessPaymentMethod.objects.create(
            code="deposit_to_account",
            name="Card B", fa_name="کارت ب",
        )
        self.channel_a = BusinessPaymentChannel.objects.create(
            business=self.business_a,
            code="channel_a",
            name="Channel A", fa_name="کانال الف",
            card_number="6104337890123456",
        )
        self.channel_b = BusinessPaymentChannel.objects.create(
            business=self.business_b,
            code="channel_b",
            name="Channel B", fa_name="کانال ب",
            card_number="6219861034567890",
        )
        BusinessPaymentChannelSupportedMethod.objects.create(
            payment_channel=self.channel_a, payment_method=self.method_a
        )
        BusinessPaymentChannelSupportedMethod.objects.create(
            payment_channel=self.channel_b, payment_method=self.method_b
        )

    def _auth(self, vendor):
        from rest_framework_simplejwt.tokens import RefreshToken

        token = RefreshToken.for_user(vendor)
        token["user_type"] = "vendor"
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {token.access_token}"
        )

    def test_vendor_a_sees_all_methods(self):
        self._auth(self.vendor_a)
        response = self.client.get("/api/vendor/business-payments/methods")
        self.assertEqual(response.status_code, 200)
        codes = [m["code"] for m in response.data["data"]["results"]]
        self.assertIn("card_to_card", codes)
        self.assertEqual(response.data["data"]["count"], 2)

    def test_vendor_b_sees_all_methods(self):
        self._auth(self.vendor_b)
        response = self.client.get("/api/vendor/business-payments/methods")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["count"], 2)

    def test_vendor_a_can_read_any_method_detail(self):
        self._auth(self.vendor_a)
        response = self.client.get(
            f"/api/vendor/business-payments/methods/{self.method_b.id}"
        )
        self.assertEqual(response.status_code, 200)

    def test_method_list_filters_by_point_to_channel_field(self):
        BusinessPaymentMethod.objects.create(
            code="deposit_acc",
            name="Deposit",
            fa_name="سپرده",
            point_to_channel_field="account_number",
        )
        self._auth(self.vendor_a)
        response = self.client.get(
            "/api/vendor/business-payments/methods?has_point_to_channel=true"
        )
        self.assertEqual(response.status_code, 200)
        results = response.data["data"]["results"]
        self.assertEqual(response.data["data"]["count"], 1)
        self.assertEqual(results[0]["code"], "deposit_acc")
        self.assertIsNotNone(results[0]["point_to_channel_field"])

        response = self.client.get(
            "/api/vendor/business-payments/methods?has_point_to_channel=false"
        )
        self.assertEqual(response.data["data"]["count"], 2)
        for method in response.data["data"]["results"]:
            self.assertIsNone(method["point_to_channel_field"])

    def test_vendor_a_sees_own_channels(self):
        self._auth(self.vendor_a)
        response = self.client.get("/api/vendor/business-payments/channels")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["count"], 1)
        self.assertEqual(
            response.data["data"]["results"][0]["code"], "channel_a"
        )

    def test_channel_list_ignores_method_only_query_params(self):
        self._auth(self.vendor_a)
        response = self.client.get(
            "/api/vendor/business-payments/channels?has_point_to_channel=true"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["count"], 1)

    def test_vendor_a_cannot_read_vendor_b_channel_detail(self):
        self._auth(self.vendor_a)
        response = self.client.get(
            f"/api/vendor/business-payments/channels/{self.channel_b.id}"
        )
        self.assertEqual(response.status_code, 404)

    def test_vendor_a_can_create_channel(self):
        self._auth(self.vendor_a)
        response = self.client.post(
            "/api/vendor/business-payments/channels",
            {
                "code": "new_channel",
                "name": "New",
                "fa_name": "جدید",
                "payment_method_ids": [self.method_a.id],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        channel_id = response.data["data"]["id"]
        channel = BusinessPaymentChannel.objects.get(id=channel_id)
        self.assertEqual(channel.code, "new_channel")
        self.assertEqual(channel.business, self.business_a)

    def test_vendor_a_can_create_channel_without_code_and_name(self):
        self._auth(self.vendor_a)
        response = self.client.post(
            "/api/vendor/business-payments/channels",
            {"fa_name": "بانک ملی"},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        channel = BusinessPaymentChannel.objects.get(
            id=response.data["data"]["id"]
        )
        self.assertTrue(channel.code)
        self.assertTrue(channel.code.isascii())
        self.assertTrue(channel.name)
        self.assertTrue(channel.name.isascii())
        self.assertEqual(channel.name, "bank meli")

    def test_vendor_a_can_create_channel_with_empty_payload(self):
        self._auth(self.vendor_a)
        response = self.client.post(
            "/api/vendor/business-payments/channels", {}, format="json"
        )
        self.assertEqual(response.status_code, 201)
        channel = BusinessPaymentChannel.objects.get(
            id=response.data["data"]["id"]
        )
        self.assertTrue(channel.code.isascii())
        self.assertTrue(channel.name.isascii())
        self.assertEqual(channel.name, channel.code)

    def test_vendor_create_channel_converts_persian_name_to_english(self):
        self._auth(self.vendor_a)
        response = self.client.post(
            "/api/vendor/business-payments/channels",
            {"code": "ali_acc", "name": "علی رضایی"},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        channel = BusinessPaymentChannel.objects.get(
            id=response.data["data"]["id"]
        )
        self.assertEqual(channel.name, "ali rezayi")

    def test_vendor_create_channel_rejects_non_ascii_name(self):
        self._auth(self.vendor_a)
        response = self.client.post(
            "/api/vendor/business-payments/channels",
            {"code": "emoji_ch", "name": "\U0001f600"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_vendor_update_channel_converts_persian_name_to_english(self):
        self._auth(self.vendor_a)
        response = self.client.patch(
            f"/api/vendor/business-payments/channels/{self.channel_a.id}",
            {"name": "بانک تجارت"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        channel = BusinessPaymentChannel.objects.get(id=self.channel_a.id)
        self.assertTrue(channel.name.isascii())
        self.assertNotEqual(channel.name, "بانک تجارت")

    def test_vendor_update_channel_blank_name_keeps_existing(self):
        self._auth(self.vendor_a)
        original = self.channel_a.name
        response = self.client.patch(
            f"/api/vendor/business-payments/channels/{self.channel_a.id}",
            {"name": ""},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.channel_a.refresh_from_db()
        self.assertEqual(self.channel_a.name, original)

    def test_vendor_a_can_update_own_channel(self):
        self._auth(self.vendor_a)
        response = self.client.patch(
            f"/api/vendor/business-payments/channels/{self.channel_a.id}",
            {"name": "Updated A"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["name"], "Updated A")

    def test_vendor_a_cannot_update_vendor_b_channel(self):
        self._auth(self.vendor_a)
        response = self.client.patch(
            f"/api/vendor/business-payments/channels/{self.channel_b.id}",
            {"name": "Updated"},
            format="json",
        )
        self.assertEqual(response.status_code, 404)

    def test_channel_create_rejects_invalid_card_number(self):
        self._auth(self.vendor_a)
        response = self.client.post(
            "/api/vendor/business-payments/channels",
            {
                "code": "bad_card",
                "card_number": "1234",
                "payment_method_ids": [self.method_a.id],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("card_number", response.data["errors"])

    def test_channel_create_normalizes_card_number(self):
        self._auth(self.vendor_a)
        response = self.client.post(
            "/api/vendor/business-payments/channels",
            {
                "code": "spaced_card",
                "card_number": "6104 3378-9012 3456",
                "payment_method_ids": [self.method_a.id],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        channel = BusinessPaymentChannel.objects.get(
            id=response.data["data"]["id"]
        )
        self.assertEqual(channel.card_number, "6104337890123456")

    def test_channel_update_rejects_invalid_card_number(self):
        self._auth(self.vendor_a)
        response = self.client.patch(
            f"/api/vendor/business-payments/channels/{self.channel_a.id}",
            {"card_number": "610433789012345a"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.channel_a.refresh_from_db()
        self.assertEqual(self.channel_a.card_number, "6104337890123456")

    def test_channel_update_allows_clearing_card_number(self):
        self._auth(self.vendor_a)
        response = self.client.patch(
            f"/api/vendor/business-payments/channels/{self.channel_a.id}",
            {"card_number": None},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.channel_a.refresh_from_db()
        self.assertIsNone(self.channel_a.card_number)

    def test_vendor_a_sees_only_own_payments(self):
        OrderSeeder().run()
        PaymentsSeeder().run()
        customer_status = CustomerStatus.objects.create(
            name="bp-api-test", title="Active"
        )
        customer = Customer.objects.create_user(
            phone="09120001010", password="password", first_name="T",
            last_name="C", customer_code="CUS-BP-010", status=customer_status,
        )
        order_a = Order.objects.create(
            customer=customer,
            status=OrderStatus.objects.get(name="payment_pending"),
            address_info={}, subtotal=Decimal("100.00"),
            discount_amount=Decimal("0.00"), shipping_amount=Decimal("0.00"),
            total_amount=Decimal("100.00"),
            reservation_expires_at=timezone.now() + timezone.timedelta(minutes=10),
        )
        order_b = Order.objects.create(
            customer=customer,
            status=OrderStatus.objects.get(name="payment_pending"),
            address_info={}, subtotal=Decimal("200.00"),
            discount_amount=Decimal("0.00"), shipping_amount=Decimal("0.00"),
            total_amount=Decimal("200.00"),
            reservation_expires_at=timezone.now() + timezone.timedelta(minutes=10),
        )
        BusinessPayment.objects.create(
            business=self.business_a, order=order_a,
            payment_method=self.method_a, amount=Decimal("100.00"),
            status=self.status_pending,
        )
        BusinessPayment.objects.create(
            business=self.business_b, order=order_b,
            payment_method=self.method_b, amount=Decimal("200.00"),
            status=self.status_pending,
        )
        self._auth(self.vendor_a)
        response = self.client.get("/api/vendor/business-payments/payments")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["count"], 1)

    def test_vendor_a_cannot_view_vendor_b_payment_detail(self):
        OrderSeeder().run()
        PaymentsSeeder().run()
        customer_status = CustomerStatus.objects.create(
            name="bp-api-det", title="Active"
        )
        customer = Customer.objects.create_user(
            phone="09120001011", password="password", first_name="T",
            last_name="C", customer_code="CUS-BP-011", status=customer_status,
        )
        order = Order.objects.create(
            customer=customer,
            status=OrderStatus.objects.get(name="payment_pending"),
            address_info={}, subtotal=Decimal("100.00"),
            discount_amount=Decimal("0.00"), shipping_amount=Decimal("0.00"),
            total_amount=Decimal("100.00"),
            reservation_expires_at=timezone.now() + timezone.timedelta(minutes=10),
        )
        payment_b = BusinessPayment.objects.create(
            business=self.business_b, order=order,
            payment_method=self.method_b, amount=Decimal("100.00"),
            status=self.status_pending,
        )
        self._auth(self.vendor_a)
        response = self.client.get(
            f"/api/vendor/business-payments/payments/{payment_b.id}"
        )
        self.assertEqual(response.status_code, 404)

    def test_vendor_a_can_list_own_documents(self):
        OrderSeeder().run()
        PaymentsSeeder().run()
        customer_status = CustomerStatus.objects.create(
            name="bp-api-doc", title="Active"
        )
        customer = Customer.objects.create_user(
            phone="09120001012", password="password", first_name="T",
            last_name="C", customer_code="CUS-BP-012", status=customer_status,
        )
        order = Order.objects.create(
            customer=customer,
            status=OrderStatus.objects.get(name="payment_pending"),
            address_info={}, subtotal=Decimal("100.00"),
            discount_amount=Decimal("0.00"), shipping_amount=Decimal("0.00"),
            total_amount=Decimal("100.00"),
            reservation_expires_at=timezone.now() + timezone.timedelta(minutes=10),
        )
        payment_a = BusinessPayment.objects.create(
            business=self.business_a, order=order,
            payment_method=self.method_a, amount=Decimal("100.00"),
            status=self.status_pending,
        )
        file_status, _ = FileStatus.objects.get_or_create(name="available")
        file = File.objects.create(
            status=file_status, storage_alias="default",
            object_key="bp/doc.txt", original_name="doc.txt",
            file_type="document", content_type="text/plain",
            extension="txt", size=4, checksum="b" * 64,
        )
        BusinessPaymentDocument.objects.create(payment=payment_a, file=file)
        self._auth(self.vendor_a)
        response = self.client.get(
            f"/api/vendor/business-payments/payments/{payment_a.id}/documents"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["data"]), 1)

    def test_vendor_a_cannot_view_vendor_b_documents(self):
        OrderSeeder().run()
        PaymentsSeeder().run()
        customer_status = CustomerStatus.objects.create(
            name="bp-api-doc2", title="Active"
        )
        customer = Customer.objects.create_user(
            phone="09120001013", password="password", first_name="T",
            last_name="C", customer_code="CUS-BP-013", status=customer_status,
        )
        order = Order.objects.create(
            customer=customer,
            status=OrderStatus.objects.get(name="payment_pending"),
            address_info={}, subtotal=Decimal("100.00"),
            discount_amount=Decimal("0.00"), shipping_amount=Decimal("0.00"),
            total_amount=Decimal("100.00"),
            reservation_expires_at=timezone.now() + timezone.timedelta(minutes=10),
        )
        payment_b = BusinessPayment.objects.create(
            business=self.business_b, order=order,
            payment_method=self.method_b, amount=Decimal("100.00"),
            status=self.status_pending,
        )
        file_status, _ = FileStatus.objects.get_or_create(name="available")
        file = File.objects.create(
            status=file_status, storage_alias="default",
            object_key="bp/doc2.txt", original_name="doc2.txt",
            file_type="document", content_type="text/plain",
            extension="txt", size=4, checksum="c" * 64,
        )
        BusinessPaymentDocument.objects.create(payment=payment_b, file=file)
        self._auth(self.vendor_a)
        response = self.client.get(
            f"/api/vendor/business-payments/payments/{payment_b.id}/documents"
        )
        self.assertEqual(response.status_code, 404)

    def test_unauthenticated_request_is_rejected(self):
        response = self.client.get("/api/vendor/business-payments/methods")
        self.assertEqual(response.status_code, 401)

    def test_vendor_without_business_can_access_methods(self):
        vendor_no_biz = _make_vendor(
            "+9900000005", "1000000005", self.vendor_status
        )
        self._auth(vendor_no_biz)
        response = self.client.get("/api/vendor/business-payments/methods")
        self.assertEqual(response.status_code, 200)

    def test_channel_list_masks_card_number(self):
        self._auth(self.vendor_a)
        response = self.client.get("/api/vendor/business-payments/channels")
        row = response.data["data"]["results"][0]
        self.assertNotEqual(row["card_number"], self.channel_a.card_number)
        self.assertTrue(row["card_number"].endswith("3456"))

    def test_channel_detail_shows_full_card_number(self):
        self._auth(self.vendor_a)
        response = self.client.get(
            f"/api/vendor/business-payments/channels/{self.channel_a.id}"
        )
        self.assertEqual(
            response.data["data"]["card_number"], self.channel_a.card_number
        )

    def test_method_list_has_supported_channel_count(self):
        self._auth(self.vendor_a)
        response = self.client.get("/api/vendor/business-payments/methods")
        method = response.data["data"]["results"][0]
        self.assertEqual(method["supported_channel_count"], 1)

    def test_method_list_includes_description(self):
        self.method_a.description = "Pay with card to card."
        self.method_a.save(update_fields=["description"])
        self._auth(self.vendor_a)
        response = self.client.get(
            f"/api/vendor/business-payments/methods/{self.method_a.id}"
        )
        self.assertEqual(
            response.data["data"]["description"], "Pay with card to card."
        )

    def test_channel_create_and_method_replacement(self):
        self._auth(self.vendor_a)
        deposit = BusinessPaymentMethod.objects.create(
            code="credit",
            name="Credit", fa_name="اعتباری",
        )
        response = self.client.post(
            "/api/vendor/business-payments/channels",
            {
                "code": "new_ch",
                "name": "New",
                "fa_name": "جدید",
                "payment_method_ids": [self.method_a.id, deposit.id],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        ch_id = response.data["data"]["id"]
        response = self.client.post(
            f"/api/vendor/business-payments/channels/{ch_id}/methods",
            {"payment_method_ids": [deposit.id]},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        support = BusinessPaymentChannelSupportedMethod.objects.get(
            payment_channel_id=ch_id
        )
        self.assertEqual(support.payment_method, deposit)

    def test_method_delete_not_allowed(self):
        self._auth(self.vendor_a)
        self.assertEqual(
            self.client.delete(
                f"/api/vendor/business-payments/methods/{self.method_a.id}"
            ).status_code,
            405,
        )

    def test_delete_channel_without_payments(self):
        self._auth(self.vendor_a)
        response = self.client.delete(
            f"/api/vendor/business-payments/channels/{self.channel_a.id}"
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            BusinessPaymentChannel.objects.filter(id=self.channel_a.id).exists()
        )
        self.assertFalse(
            BusinessPaymentChannelSupportedMethod.objects.filter(
                payment_channel_id=self.channel_a.id
            ).exists()
        )

    def test_delete_channel_cross_business_returns_404(self):
        self._auth(self.vendor_a)
        response = self.client.delete(
            f"/api/vendor/business-payments/channels/{self.channel_b.id}"
        )
        self.assertEqual(response.status_code, 404)
        self.assertTrue(
            BusinessPaymentChannel.objects.filter(id=self.channel_b.id).exists()
        )

    def test_delete_channel_with_payments_returns_400(self):
        OrderSeeder().run()
        PaymentsSeeder().run()
        customer_status = CustomerStatus.objects.create(
            name="bp-del", title="Active"
        )
        customer = Customer.objects.create_user(
            phone="09120001014", password="password", first_name="T",
            last_name="C", customer_code="CUS-BP-014", status=customer_status,
        )
        order = Order.objects.create(
            customer=customer,
            status=OrderStatus.objects.get(name="payment_pending"),
            address_info={}, subtotal=Decimal("100.00"),
            discount_amount=Decimal("0.00"), shipping_amount=Decimal("0.00"),
            total_amount=Decimal("100.00"),
            reservation_expires_at=timezone.now() + timezone.timedelta(minutes=10),
        )
        BusinessPayment.objects.create(
            business=self.business_a, order=order,
            payment_method=self.method_a, amount=Decimal("100.00"),
            payment_channel=self.channel_a,
            status=self.status_pending,
        )
        self._auth(self.vendor_a)
        response = self.client.delete(
            f"/api/vendor/business-payments/channels/{self.channel_a.id}"
        )
        self.assertEqual(response.status_code, 400)
        self.assertTrue(
            BusinessPaymentChannel.objects.filter(id=self.channel_a.id).exists()
        )

    def _attach_payment(self, channel, method):
        OrderSeeder().run()
        PaymentsSeeder().run()
        customer_status = CustomerStatus.objects.create(
            name="bp-locked-ch", title="Active"
        )
        customer = Customer.objects.create_user(
            phone="09120001020", password="password", first_name="T",
            last_name="C", customer_code="CUS-BP-020", status=customer_status,
        )
        order = Order.objects.create(
            customer=customer,
            status=OrderStatus.objects.get(name="payment_pending"),
            address_info={}, subtotal=Decimal("100.00"),
            discount_amount=Decimal("0.00"), shipping_amount=Decimal("0.00"),
            total_amount=Decimal("100.00"),
            reservation_expires_at=timezone.now() + timezone.timedelta(minutes=10),
        )
        return BusinessPayment.objects.create(
            business=channel.business, order=order,
            payment_method=method, payment_channel=channel,
            amount=Decimal("100.00"), status=self.status_pending,
        )

    def test_update_channel_with_payments_rejects_field_change(self):
        self._attach_payment(self.channel_a, self.method_a)
        self._auth(self.vendor_a)
        response = self.client.patch(
            f"/api/vendor/business-payments/channels/{self.channel_a.id}",
            {"name": "Changed"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.channel_a.refresh_from_db()
        self.assertEqual(self.channel_a.name, "Channel A")

    def test_update_channel_with_payments_allows_is_active(self):
        self._attach_payment(self.channel_a, self.method_a)
        self._auth(self.vendor_a)
        response = self.client.patch(
            f"/api/vendor/business-payments/channels/{self.channel_a.id}",
            {"is_active": False},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.channel_a.refresh_from_db()
        self.assertFalse(self.channel_a.is_active)

    def test_update_channel_methods_with_payments_returns_400(self):
        self._attach_payment(self.channel_a, self.method_a)
        deposit = BusinessPaymentMethod.objects.create(
            code="credit", name="Credit", fa_name="اعتباری"
        )
        self._auth(self.vendor_a)
        response = self.client.post(
            f"/api/vendor/business-payments/channels/{self.channel_a.id}/methods",
            {"payment_method_ids": [deposit.id]},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        support = BusinessPaymentChannelSupportedMethod.objects.get(
            payment_channel=self.channel_a
        )
        self.assertEqual(support.payment_method, self.method_a)

    def test_method_patch_not_allowed(self):
        self._auth(self.vendor_a)
        response = self.client.patch(
            f"/api/vendor/business-payments/methods/{self.method_a.id}",
            {"code": "changed"},
            format="json",
        )
        self.assertEqual(response.status_code, 405)
