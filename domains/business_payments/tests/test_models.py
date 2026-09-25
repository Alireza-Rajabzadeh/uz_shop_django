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

from ..models import (
    BusinessPayment,
    BusinessPaymentChannel,
    BusinessPaymentChannelSupportedMethod,
    BusinessPaymentDocument,
    BusinessPaymentMethod,
    BusinessPaymentStatus,
)
from ..online_payment_providers import provider_availability, provider_class
from ..services import BusinessPaymentService


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
