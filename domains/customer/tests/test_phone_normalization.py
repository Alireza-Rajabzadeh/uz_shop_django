from django.db import IntegrityError, transaction
from django.test import TestCase

from core.utils import normalize_phone
from domains.customer.models import Customer, CustomerStatus


class CustomerPhoneNormalizationTests(TestCase):
    def test_persian_and_arabic_digits_are_stored_as_ascii(self):
        status = CustomerStatus.objects.create(name="active", title="Active")
        customer = Customer.objects.create_user(
            phone="۰۹۱۲-۳۴۵-۶۷۸۹",
            password="password",
            first_name="Phone",
            last_name="Test",
            customer_code="CUS-PHONE",
            status=status,
        )

        self.assertEqual(customer.phone, "09123456789")
        self.assertEqual(normalize_phone("٠٩١٢ ٣٤٥ ٦٧٨٩"), "09123456789")

        with self.assertRaises(IntegrityError), transaction.atomic():
            Customer.objects.create_user(
                phone="0912 345 6789",
                password="password",
                first_name="Duplicate",
                last_name="Phone",
                customer_code="CUS-PHONE-DUPLICATE",
                status=status,
            )

    def test_database_rejects_noncanonical_bulk_update(self):
        status = CustomerStatus.objects.create(name="active", title="Active")
        customer = Customer.objects.create_user(
            phone="09123456789",
            password="password",
            first_name="Phone",
            last_name="Constraint",
            customer_code="CUS-PHONE-CONSTRAINT",
            status=status,
        )

        with self.assertRaises(IntegrityError), transaction.atomic():
            Customer.objects.filter(pk=customer.pk).update(phone="invalid")
