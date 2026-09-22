from django.db import connection
from django.test import TransactionTestCase


class BusinessPaymentMigrationTests(TransactionTestCase):
    def test_migrations_apply_cleanly(self):
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_name LIKE 'business_payment%'"
            )
            tables = {row[0] for row in cursor.fetchall()}
        expected = {
            "business_payment_status",
            "business_payment_method",
            "business_payment_channel",
            "business_payment_channel_support",
            "business_payment",
            "business_payment_document",
        }
        self.assertTrue(expected.issubset(tables), f"Missing tables: {expected - tables}")
        cursor.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'business_payment_channel' "
            "AND column_name = 'business_id'"
        )
        self.assertEqual(cursor.fetchone()[0], "business_id")
