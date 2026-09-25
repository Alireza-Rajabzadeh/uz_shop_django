from decimal import Decimal

from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.test import TestCase
from rest_framework.test import APITestCase

from core.management.seeders.order import ORDER_ACTIONS, ORDER_STATUSES, ORDER_STATUS_ACTIONS, OrderSeeder
from core.management.seeders.payments import PaymentsSeeder
from domains.customer.models import Customer, CustomerStatus
from domains.order.models import Order, OrderAction, OrderStatus, OrderStatusAction


class OrderSeederTests(TestCase):
    def test_seeds_exact_statuses_and_preserves_unrelated_rows(self):
        unrelated = OrderStatus.objects.create(
            id=999,
            name="custom_status",
            fa_name="سفارشی",
            description="Keep me",
        )
        OrderStatus.objects.update_or_create(
            id=100,
            defaults={
                "name": "payment_waiting",
                "fa_name": "Old waiting",
                "description": "Old description",
            },
        )
        OrderStatus.objects.update_or_create(
            id=200,
            defaults={
                "name": "paid",
                "fa_name": "Old paid",
                "description": "Old description",
            },
        )

        OrderSeeder().run()

        self.assertEqual(
            OrderStatus.objects.filter(id__in=ORDER_STATUSES).count(),
            len(ORDER_STATUSES),
        )
        for status_id, expected in ORDER_STATUSES.items():
            status = OrderStatus.objects.get(id=status_id)
            self.assertEqual((status.name, status.fa_name, status.description), expected)
        unrelated.refresh_from_db()
        self.assertEqual(unrelated.name, "custom_status")
        self.assertEqual(unrelated.description, "Keep me")

    def test_status_action_pair_is_unique(self):
        OrderSeeder().run()
        with self.assertRaises(IntegrityError), transaction.atomic():
            OrderStatusAction.objects.create(
                order_status_id=110,
                order_action_id=1,
            )


class OrderAdminListTests(APITestCase):
    def setUp(self):
        OrderSeeder().run()
        PaymentsSeeder().run()
        self.active = CustomerStatus.objects.create(name="active", title="Active")
        self.customer = Customer.objects.create_user(
            phone="09120000301",
            password="password",
            first_name="Order",
            last_name="Admin",
            customer_code="CUS-ORDER-101",
            status=self.active,
        )
        self.admin = User.objects.create_superuser("order-admin", password="password")
        self.client.force_authenticate(self.admin)
        self.status = OrderStatus.objects.get(name="payment_pending")
        self.order = Order.objects.create(
            customer=self.customer,
            status=self.status,
            address_info={},
            subtotal=Decimal("100.00"),
            discount_amount=Decimal("0.00"),
            shipping_amount=Decimal("0.00"),
            total_amount=Decimal("100.00"),
        )

    def test_admin_list_is_paginated_and_shows_customer(self):
        response = self.client.get("/api/order/admin/orders")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["count"], 1)
        row = response.data["data"]["results"][0]
        self.assertEqual(row["id"], self.order.id)
        self.assertEqual(row["customer"]["id"], self.customer.id)
        self.assertEqual(
            row["status"],
            {"id": 110, "name": "payment_pending", "fa_name": "در انتظار پرداخت"},
        )
        self.assertEqual(row["available_actions"][0]["code"], "cancel")
        self.assertEqual(row["totals"]["total_amount"], "100.00")

    def test_admin_list_filters_status_and_search(self):
        response = self.client.get("/api/order/admin/orders", {"status": "paid"})
        self.assertEqual(response.data["data"]["count"], 0)

        response = self.client.get("/api/order/admin/orders", {"search": "Admin"})
        self.assertEqual(response.data["data"]["count"], 1)

        response = self.client.get("/api/order/admin/orders", {"search": "no-match"})
        self.assertEqual(response.data["data"]["count"], 0)
