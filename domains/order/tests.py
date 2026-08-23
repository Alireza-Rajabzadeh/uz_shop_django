import json
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import Permission, User
from django.db import IntegrityError, transaction
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.utils import timezone

from domains.catalog.models import (
    Category,
    CategoryStatus,
    Product,
    ProductStatus,
    ProductVariants,
    VariantAttribute,
    VariantOption,
)
from domains.cart.models import Cart, CartItem
from domains.customer.models import Customer, CustomerAddress, CustomerStatus
from domains.inventory.models import (
    InventoryStrategy,
    SerializedStock,
    SerializedStockStatus,
    Warehouse,
    WarehouseStatus,
    WarehouseStock,
)
from domains.location.models import City, Country, State
from domains.order.models import (
    Order,
    OrderHistory,
    OrderItem,
    OrderStatus,
    ReturnRequest,
    ReturnRequestEvidence,
    ReturnRequestItem,
)
from domains.payments.models import (
    Payment,
    PaymentChannel,
    PaymentChannelSupportedMethod,
    PaymentMethod,
)
from domains.payments.services import PaymentService
from rest_framework.test import APITestCase

from core.management.seeders.order import (
    ORDER_ACTIONS,
    ORDER_STATUSES,
    ORDER_STATUS_ACTIONS,
    OrderSeeder,
)
from domains.order.models import OrderAction, OrderStatusAction
from core.management.seeders.payments import PaymentsSeeder
from domains.order.services import OrderService


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
            self.assertEqual(
                (status.name, status.fa_name, status.description),
                expected,
            )
        unrelated.refresh_from_db()
        self.assertEqual(unrelated.name, "custom_status")
        self.assertEqual(unrelated.description, "Keep me")

    def test_seeds_actions_and_status_assignments_idempotently(self):
        OrderSeeder().run()
        custom_action = OrderAction.objects.create(
            id=999,
            code="custom_action",
            name="Custom",
            fa_name="سفارشی",
        )
        custom_assignment = OrderStatusAction.objects.create(
            order_status_id=110,
            order_action=custom_action,
        )

        OrderSeeder().run()
        OrderSeeder().run()

        self.assertEqual(
            OrderAction.objects.filter(id__in=ORDER_ACTIONS).count(),
            len(ORDER_ACTIONS),
        )
        for action_id, values in ORDER_ACTIONS.items():
            action = OrderAction.objects.get(id=action_id)
            self.assertEqual(
                (
                    action.code,
                    action.name,
                    action.fa_name,
                    action.admin,
                    action.customer,
                    action.set_status_id,
                ),
                values,
            )
        for status_id, action_id in ORDER_STATUS_ACTIONS:
            self.assertTrue(
                OrderStatusAction.objects.filter(
                    order_status_id=status_id,
                    order_action_id=action_id,
                ).exists()
            )
        self.assertTrue(OrderAction.objects.filter(id=custom_action.id).exists())
        self.assertTrue(OrderStatusAction.objects.filter(id=custom_assignment.id).exists())

    def test_status_action_pair_is_unique(self):
        OrderSeeder().run()
        with self.assertRaises(IntegrityError), transaction.atomic():
            OrderStatusAction.objects.create(
                order_status_id=110,
                order_action_id=1,
            )

    def test_rerun_is_idempotent_and_updates_by_permanent_id(self):
        OrderSeeder().run()
        status = OrderStatus.objects.get(id=310)
        status.name = "wrong_name"
        status.fa_name = "Wrong"
        status.description = "Wrong"
        status.save()

        OrderSeeder().run()
        OrderSeeder().run()

        status.refresh_from_db()
        self.assertEqual(
            (status.name, status.fa_name, status.description),
            ORDER_STATUSES[310],
        )
        self.assertEqual(
            OrderStatus.objects.filter(id__in=ORDER_STATUSES).count(),
            len(ORDER_STATUSES),
        )


class OrderAdminAPITests(APITestCase):
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

    def test_admin_list_filters_by_status_and_search(self):
        response = self.client.get("/api/order/admin/orders", {"status": "paid"})
        self.assertEqual(response.data["data"]["count"], 0)
        response = self.client.get(
            "/api/order/admin/orders", {"search": "Admin"}
        )
        self.assertEqual(response.data["data"]["count"], 1)
        response = self.client.get("/api/order/admin/orders", {"search": "no-match"})
        self.assertEqual(response.data["data"]["count"], 0)

    def test_admin_list_filters_in_progress_orders_and_active_returns(self):
        response = self.client.get(
            "/api/order/admin/orders", {"in_progress": "true"}
        )
        self.assertEqual(response.data["data"]["count"], 1)

        response = self.client.get(
            "/api/order/admin/orders", {"has_active_returns": "true"}
        )
        self.assertEqual(response.data["data"]["count"], 0)

        ReturnRequest.objects.create(
            order=self.order,
            customer=self.customer,
            reason="Damaged",
            refund_destination_type="card",
            refund_destination_value="6037991234567890",
        )
        response = self.client.get(
            "/api/order/admin/orders", {"has_active_returns": "true"}
        )
        self.assertEqual(response.data["data"]["count"], 1)

        self.order.status = OrderStatus.objects.get(name="cancelled")
        self.order.save(update_fields=["status"])
        response = self.client.get(
            "/api/order/admin/orders", {"in_progress": "true"}
        )
        self.assertEqual(response.data["data"]["count"], 0)

    def test_admin_list_filters_by_snapshot_state_and_city(self):
        self.order.address_info = {"state_id": 12, "city_id": 34}
        self.order.save(update_fields=["address_info"])

        matched = self.client.get(
            "/api/order/admin/orders", {"state_id": 12, "city_id": 34}
        )
        wrong_city = self.client.get(
            "/api/order/admin/orders", {"state_id": 12, "city_id": 35}
        )

        self.assertEqual(matched.data["data"]["count"], 1)
        self.assertEqual(wrong_city.data["data"]["count"], 0)

    def test_admin_geography_groups_open_orders_and_enriches_city_markers(self):
        country = Country.objects.create(
            name="Iran", fa_title="ایران", code="IR", phone_code="+98"
        )
        state = State.objects.create(
            country=country, name="Tehran", fa_title="تهران"
        )
        city = City.objects.create(
            state=state,
            name="Tehran",
            fa_title="تهران",
            latitude="35.6892000",
            longitude="51.3890000",
        )
        self.order.address_info = {
            "country_id": country.id,
            "state_id": state.id,
            "state_name": state.name,
            "state_fa_title": state.fa_title,
            "city_id": city.id,
            "city_name": city.name,
            "city_fa_title": city.fa_title,
        }
        self.order.save(update_fields=["address_info"])
        Order.objects.create(
            customer=self.customer,
            status=OrderStatus.objects.get(name="cancelled"),
            address_info=self.order.address_info,
            subtotal=Decimal("1.00"),
            total_amount=Decimal("1.00"),
        )
        Order.objects.create(
            customer=self.customer,
            status=self.status,
            address_info={},
            subtotal=Decimal("1.00"),
            total_amount=Decimal("1.00"),
        )
        foreign_country = Country.objects.create(
            name="Turkey", code="TR", phone_code="+90"
        )
        foreign_state = State.objects.create(
            country=foreign_country, name="Istanbul"
        )
        foreign_city = City.objects.create(
            state=foreign_state, name="Istanbul"
        )
        Order.objects.create(
            customer=self.customer,
            status=self.status,
            address_info={
                "country_id": foreign_country.id,
                "state_id": foreign_state.id,
                "city_id": foreign_city.id,
            },
            subtotal=Decimal("1.00"),
            total_amount=Decimal("1.00"),
        )

        response = self.client.get("/api/order/admin/orders/geography")

        self.assertEqual(response.status_code, 200)
        data = response.data["data"]
        self.assertEqual(data["total_open_orders"], 3)
        self.assertEqual(data["mapped_order_count"], 1)
        self.assertEqual(data["unmapped_order_count"], 2)
        self.assertEqual(data["outside_iran_order_count"], 1)
        province = next(row for row in data["provinces"] if row["state_id"] == state.id)
        self.assertEqual(province["order_count"], 1)
        self.assertEqual(province["cities"][0]["city_id"], city.id)
        self.assertEqual(province["cities"][0]["latitude"], 35.6892)
        self.assertEqual(province["cities"][0]["longitude"], 51.389)

    def test_admin_geography_requires_order_view_permission(self):
        staff = User.objects.create_user(
            "order-geography-staff", password="password", is_staff=True
        )
        self.client.force_authenticate(staff)

        response = self.client.get("/api/order/admin/orders/geography")

        self.assertEqual(response.status_code, 403)

    def test_admin_detail_returns_full_payload_with_customer(self):
        response = self.client.get(f"/api/order/admin/orders/{self.order.id}")
        self.assertEqual(response.status_code, 200)
        data = response.data["data"]
        self.assertEqual(data["id"], self.order.id)
        self.assertEqual(data["customer"]["id"], self.customer.id)
        self.assertEqual(data["items"], [])
        self.assertEqual(data["totals"]["total_amount"], "100.00")
        self.assertEqual(data["status"]["name"], "payment_pending")
        self.assertEqual(
            [action["code"] for action in data["available_actions"]],
            ["cancel"],
        )

    def test_admin_return_detail_and_list_summary_require_return_view_permission(self):
        return_request = ReturnRequest.objects.create(
            order=self.order,
            customer=self.customer,
            reason="Damaged",
            refund_destination_type="card",
            refund_destination_value="6037991234567890",
            admin_note="Internal only",
            customer_response="Please send the package.",
        )

        detail = self.client.get(f"/api/order/admin/orders/{self.order.id}")
        listing = self.client.get("/api/order/admin/orders")

        returned = detail.data["data"]["return_requests"][0]
        self.assertEqual(returned["id"], return_request.id)
        self.assertEqual(returned["admin_note"], "Internal only")
        self.assertEqual(returned["customer_response"], "Please send the package.")
        self.assertEqual(returned["refund_destination_masked"], "****7890")
        self.assertEqual(returned["available_actions"], ["approve", "reject"])
        self.assertEqual(
            listing.data["data"]["results"][0]["return_summary"],
            {"count": 1, "open_count": 1, "latest_status": "requested"},
        )

        staff = User.objects.create_user(username="order-viewer", is_staff=True)
        staff.user_permissions.add(Permission.objects.get(codename="view_order"))
        self.client.force_authenticate(staff)
        detail = self.client.get(f"/api/order/admin/orders/{self.order.id}")
        listing = self.client.get("/api/order/admin/orders")
        self.assertNotIn("return_requests", detail.data["data"])
        self.assertNotIn("return_summary", listing.data["data"]["results"][0])

    def test_admin_return_action_requires_change_return_permission(self):
        return_request = ReturnRequest.objects.create(
            order=self.order,
            customer=self.customer,
            reason="Damaged",
            refund_destination_type="card",
            refund_destination_value="6037991234567890",
        )
        staff = User.objects.create_user(username="return-viewer", is_staff=True)
        staff.user_permissions.add(
            Permission.objects.get(codename="view_returnrequest")
        )
        self.client.force_authenticate(staff)

        response = self.client.post(
            f"/api/order/admin/orders/{self.order.id}/returns/{return_request.id}/actions/approve",
            {},
            format="json",
        )

        self.assertEqual(response.status_code, 403)
        return_request.refresh_from_db()
        self.assertEqual(return_request.status, ReturnRequest.Status.REQUESTED)

    def test_admin_detail_missing_is_404(self):
        response = self.client.get("/api/order/admin/orders/999999")
        self.assertEqual(response.status_code, 404)

    def test_admin_status_options(self):
        response = self.client.get("/api/order/admin/statuses")
        self.assertEqual(response.status_code, 200)
        names = {row["name"] for row in response.data["data"]}
        self.assertIn("payment_pending", names)
        self.assertIn("paid", names)
        waiting = next(
            row for row in response.data["data"] if row["name"] == "payment_pending"
        )
        self.assertEqual(waiting["description"], ORDER_STATUSES[110][2])
        self.assertNotIn("next_status", waiting)
        self.assertNotIn("available_actions", waiting)

    def test_customer_principal_cannot_use_admin_endpoints(self):
        self.client.force_authenticate(self.customer)
        self.assertEqual(self.client.get("/api/order/admin/orders").status_code, 403)

    def test_staff_without_permission_is_rejected(self):
        staff = User.objects.create_user(
            username="order-noperm", password="password", is_staff=True
        )
        self.client.force_authenticate(staff)
        self.assertEqual(self.client.get("/api/order/admin/orders").status_code, 403)

    def test_admin_actions_require_view_then_change_order_permissions(self):
        self.order.status = OrderStatus.objects.get(name="paid")
        self.order.save(update_fields=["status"])
        staff = User.objects.create_user(
            username="order-actions-staff", password="password", is_staff=True
        )
        staff.user_permissions.add(Permission.objects.get(codename="view_order"))
        self.client.force_authenticate(staff)

        response = self.client.get(
            f"/api/order/admin/orders/{self.order.id}/actions"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            {action["code"] for action in response.data["data"]["actions"]},
            {"confirm"},
        )
        detail = self.client.get(
            f"/api/order/admin/orders/{self.order.id}"
        ).data["data"]
        self.assertEqual(
            [action["code"] for action in detail["available_actions"]],
            ["confirm"],
        )
        self.assertEqual(
            self.client.post(
                f"/api/order/admin/orders/{self.order.id}/actions/confirm"
            ).status_code,
            403,
        )

        staff.user_permissions.add(Permission.objects.get(codename="change_order"))
        staff = User.objects.get(pk=staff.pk)
        self.client.force_authenticate(staff)
        response = self.client.post(
            f"/api/order/admin/orders/{self.order.id}/actions/confirm"
        )
        self.assertEqual(response.status_code, 200)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status.name, "confirmed")
        history = OrderHistory.objects.get(order=self.order)
        self.assertEqual(history.action.code, "confirm")
        self.assertEqual(history.user_id, staff.pk)
        self.assertEqual(history.user_model, "auth.User")
        self.assertEqual(history.before_values, {"status_id": 100})
        self.assertEqual(history.after_values, {"status_id": 210})
        self.assertEqual(
            history.description,
            "Order action 'Confirm order' executed by admin.",
        )

        detail = self.client.get(
            f"/api/order/admin/orders/{self.order.id}"
        ).data["data"]
        self.assertEqual(detail["history"][0]["id"], history.id)
        self.assertEqual(detail["history"][0]["action"]["code"], "confirm")
        self.assertEqual(detail["history"][0]["user_id"], staff.pk)
        self.assertEqual(detail["history"][0]["user_model"], "auth.User")

    def test_admin_history_is_newest_first(self):
        confirm = OrderAction.objects.get(code="confirm")
        older = OrderHistory.objects.create(
            order=self.order,
            action=confirm,
            before_values={"status_id": 110},
            after_values={"status_id": 100},
            description="Older",
        )
        newer = OrderHistory.objects.create(
            order=self.order,
            action=confirm,
            before_values={"status_id": 100},
            after_values={"status_id": 210},
            description="Newer",
        )

        response = self.client.get(f"/api/order/admin/orders/{self.order.id}")

        self.assertEqual(
            [entry["id"] for entry in response.data["data"]["history"]],
            [newer.id, older.id],
        )

    def test_customer_principal_cannot_use_admin_action_endpoints(self):
        self.client.force_authenticate(self.customer)
        self.assertEqual(
            self.client.get(
                f"/api/order/admin/orders/{self.order.id}/actions"
            ).status_code,
            403,
        )


class OrderAPITests(APITestCase):
    def setUp(self):
        OrderSeeder().run()
        PaymentsSeeder().run()
        self.active = CustomerStatus.objects.create(name="active", title="Active")
        self.customer = Customer.objects.create_user(
            phone="09120000301",
            password="password",
            first_name="Order",
            last_name="Owner",
            customer_code="CUS-ORDER-001",
            status=self.active,
        )
        self.client.force_authenticate(self.customer)

        country = Country.objects.create(name="Order Country", code="OC", phone_code="+98")
        state = State.objects.create(name="Order State", country=country)
        self.city = City.objects.create(name="Order City", state=state)
        self.warehouse_status = WarehouseStatus.objects.create(name="available-order-tests")
        self.warehouse = Warehouse.objects.create(
            code="WH-ORDER",
            name="Default Order Warehouse",
            city=self.city,
            address="Test address",
            lat="0",
            lng="0",
            is_default=True,
            status=self.warehouse_status,
        )
        self.normal, _ = InventoryStrategy.objects.update_or_create(
            code="normal", defaults={"name": "Normal"}
        )
        self.serialized = InventoryStrategy.objects.get(code="serialized")
        category_status = CategoryStatus.objects.create(name="order-active")
        self.category = Category.objects.create(
            name="Order Category", status=category_status
        )
        self.active_status, _ = ProductStatus.objects.get_or_create(name="active")
        self.inactive, _ = ProductStatus.objects.get_or_create(name="inactive")
        for name in ("pending", "preorder"):
            ProductStatus.objects.get_or_create(name=name)
        self.attribute = VariantAttribute.objects.create(name="Order Color")
        self.option = VariantOption.objects.create(
            attribute=self.attribute, name="Black", sku_code="ORD-BLK"
        )
        self.card_channel = PaymentChannel.objects.create(
            code="manual_card", name="Manual card", fa_name="کارت دستی",
            card_number="6104337890123456", is_active=True,
        )
        self.card_to_card = PaymentMethod.objects.get(code="card_to_card")
        PaymentChannelSupportedMethod.objects.create(
            payment_channel=self.card_channel, payment_method=self.card_to_card
        )
        self.set_address()

    def set_address(self):
        state = State.objects.get(name="Order State")
        address = CustomerAddress.objects.create(
            customer=self.customer,
            title="Home",
            country=state.country,
            state=state,
            city=state.cities.get(),
            postal_code="1234567890",
            address_line1="Main Street 1",
            is_default=True,
        )
        return self.client.put(
            "/api/cart/address", {"saved_address_id": address.id}, format="json"
        )

    def make_product(self, status=None):
        product = Product.objects.create(
            name="Order Product", status=status or self.active_status
        )
        product.categories.add(self.category)
        return product

    def make_normal_variant(self, product, price="100.00", available=8, quantity=10):
        variant = ProductVariants.objects.create(
            product=product,
            inventory_strategy=self.normal,
            sku=f"ORD-PD{product.id}-BLK",
            combination_key=f"opt:{self.option.id}",
            price=price,
        )
        WarehouseStock.objects.create(
            variant=variant,
            warehouse=self.warehouse,
            quantity=quantity,
            sellable=available,
            reserved=0,
            min_stock=0,
        )
        return variant

    def add_to_cart(self, variant, quantity=1):
        return self.client.post(
            "/api/cart/items",
            {"variant_id": variant.id, "quantity": quantity},
            format="json",
        )

    def checkout(self):
        return self.client.post("/api/order/", {}, format="json")

    # ───────────────────────────── checkout ─────────────────────────────

    def test_checkout_creates_order_and_reserves_stock(self):
        product = self.make_product()
        variant = self.make_normal_variant(product)
        self.add_to_cart(variant, quantity=3)

        response = self.checkout()
        self.assertEqual(response.status_code, 201)
        data = response.data["data"]
        self.assertEqual(
            data["status"],
            {
                "id": 110,
                "name": "payment_pending",
                "fa_name": "در انتظار پرداخت",
                "description": (
                    "سفارش ایجاد شده اما پرداخت آن هنوز توسط مشتری انجام نشده است."
                ),
            },
        )
        self.assertEqual(
            data["available_actions"],
            [
                {
                    "id": 1,
                    "code": "cancel",
                    "name": "Cancel order",
                    "fa_name": "لغو سفارش",
                }
            ],
        )
        self.assertEqual(data["totals"]["subtotal"], "300.00")
        self.assertEqual(
            data["totals"]["shipment"],
            {"original_price": "200000.00", "final_price": "0.00"},
        )
        self.assertEqual(data["totals"]["shipping_amount"], "0.00")
        self.assertEqual(data["totals"]["total_amount"], "300.00")
        self.assertTrue(data["reservation_expires_at"])
        self.assertEqual(CartItem.objects.filter(cart__customer=self.customer).count(), 0)

        order = Order.objects.get(id=data["id"])
        self.assertEqual(order.status.name, "payment_pending")
        self.assertEqual(order.shipping_original_amount, Decimal("200000.00"))
        self.assertEqual(order.shipping_amount, Decimal("0.00"))
        stock = WarehouseStock.objects.get(variant=variant)
        self.assertEqual(stock.reserved, 3)
        self.assertEqual(order.items.count(), 1)
        item = order.items.get()
        self.assertEqual(item.final_price, Decimal("300.00"))

    def test_checkout_requires_address(self):
        CartItem.objects.all().delete()
        product = self.make_product()
        variant = self.make_normal_variant(product)
        self.add_to_cart(variant)
        Cart.objects.filter(customer=self.customer).update(address_info={})

        response = self.checkout()
        self.assertEqual(response.status_code, 400)
        self.assertIn("address", response.data["errors"])

    def test_checkout_requires_non_empty_cart(self):
        response = self.checkout()
        self.assertEqual(response.status_code, 400)
        self.assertIn("cart", response.data["errors"])

    def test_checkout_rejects_insufficient_stock(self):
        product = self.make_product()
        variant = self.make_normal_variant(product, available=1)
        self.add_to_cart(variant, quantity=3)

        response = self.checkout()
        self.assertEqual(response.status_code, 400)
        self.assertIn("items", response.data["errors"])

    def test_checkout_rejects_inactive_product(self):
        product = self.make_product(self.inactive)
        variant = self.make_normal_variant(product)
        self.add_to_cart(variant)

        response = self.checkout()
        self.assertEqual(response.status_code, 400)
        self.assertIn("items", response.data["errors"])

    def test_checkout_rejects_when_no_active_payment_channel(self):
        product = self.make_product()
        variant = self.make_normal_variant(product)
        self.add_to_cart(variant)
        self.card_channel.is_active = False
        self.card_channel.save()

        response = self.checkout()
        self.assertEqual(response.status_code, 400)
        self.assertIn("payment", response.data["errors"])
        self.assertFalse(Order.objects.exists())
        stock = WarehouseStock.objects.get(variant=variant)
        self.assertEqual(stock.reserved, 0)

    def test_checkout_for_serialized_reserves_rows(self):
        in_stock = SerializedStockStatus.objects.get(code="in_stock")
        product = self.make_product()
        variant = ProductVariants.objects.create(
            product=product,
            inventory_strategy=self.serialized,
            sku=f"SER-PD{product.pk}-BLK",
            combination_key=f"ser:{self.option.id}",
            price="500.00",
        )
        for index in range(3):
            SerializedStock.objects.create(
                variant=variant,
                warehouse=self.warehouse,
                status=in_stock,
                serial_number=f"ORD-SN-{index}",
                sellable=True,
                reserved=False,
            )
        self.add_to_cart(variant, quantity=2)

        response = self.checkout()
        self.assertEqual(response.status_code, 201)
        order = Order.objects.get(id=response.data["data"]["id"])
        item = order.items.get()
        self.assertEqual(item.reservations.count(), 2)
        reserved = list(
            SerializedStock.objects.filter(variant=variant, reserved=True).values_list(
                "serial_number", flat=True
            )
        )
        self.assertEqual(len(set(reserved) & set("ORD-SN-0 ORD-SN-1 ORD-SN-2".split())), 2)

    # ───────────────────── payment consumes or releases ─────────────────────

    def _submit_payment(self, order_id):
        return self.client.post(
            f"/api/order/{order_id}/pay",
            {
                "payment_method": "card_to_card",
                "payment_channel_id": self.card_channel.id,
                "ref_number": "ORD-TRX-REV",
            },
            format="json",
        )

    def test_paid_order_consumes_normal_reservation(self):
        product = self.make_product()
        variant = self.make_normal_variant(product, available=8)
        self.add_to_cart(variant, quantity=3)
        order_id = self.checkout().data["data"]["id"]

        stock = WarehouseStock.objects.get(variant=variant)
        self.assertEqual(stock.sellable, 8)
        self.assertEqual(stock.reserved, 3)

        payment_response = self._submit_payment(order_id)
        self.assertEqual(payment_response.status_code, 202)
        payment = Payment.objects.get(order_id=order_id)

        admin = User.objects.create_superuser("payment-approver", password="password")
        PaymentService().review_payment(payment.id, approve=True, admin=admin)

        stock.refresh_from_db()
        self.assertEqual(stock.sellable, 5)
        self.assertEqual(stock.reserved, 0)

    def test_paid_order_consumes_serialized_reservation(self):
        in_stock = SerializedStockStatus.objects.get(code="in_stock")
        product = self.make_product()
        variant = ProductVariants.objects.create(
            product=product,
            inventory_strategy=self.serialized,
            sku=f"SER-PD{product.pk}-BLK",
            combination_key=f"ser:{self.option.id}",
            price="500.00",
        )
        for index in range(3):
            SerializedStock.objects.create(
                variant=variant,
                warehouse=self.warehouse,
                status=in_stock,
                serial_number=f"ORD-SN-SALE-{index}",
                sellable=True,
                reserved=False,
            )
        self.add_to_cart(variant, quantity=2)
        order_id = self.checkout().data["data"]["id"]

        payment_response = self._submit_payment(order_id)
        self.assertEqual(payment_response.status_code, 202)
        payment = Payment.objects.get(order_id=order_id)

        admin = User.objects.create_superuser("payment-approver", password="password")
        PaymentService().review_payment(payment.id, approve=True, admin=admin)

        sold = SerializedStockStatus.objects.get(code="sold")
        sold_rows = SerializedStock.objects.filter(variant=variant, status=sold)
        self.assertEqual(sold_rows.count(), 2)
        self.assertFalse(sold_rows.filter(reserved=True).exists())
        self.assertFalse(sold_rows.filter(sellable=True).exists())
        self.assertEqual(
            SerializedStock.objects.filter(
                variant=variant, status=in_stock, sellable=True, reserved=False
            ).count(),
            1,
        )

    def test_rejected_payment_releases_normal_reservation(self):
        product = self.make_product()
        variant = self.make_normal_variant(product, available=8)
        self.add_to_cart(variant, quantity=3)
        order_id = self.checkout().data["data"]["id"]

        payment_response = self._submit_payment(order_id)
        self.assertEqual(payment_response.status_code, 202)
        payment = Payment.objects.get(order_id=order_id)

        admin = User.objects.create_superuser("payment-rejector", password="password")
        PaymentService().review_payment(payment.id, approve=False, admin=admin)

        order = Order.objects.get(id=order_id)
        self.assertEqual(order.status.name, "payment_failed")
        stock = WarehouseStock.objects.get(variant=variant)
        self.assertEqual(stock.sellable, 8)
        self.assertEqual(stock.reserved, 0)

    # ───────────────────────────── reads ─────────────────────────────

    def test_list_and_detail(self):
        product = self.make_product()
        variant = self.make_normal_variant(product)
        self.add_to_cart(variant)
        order_id = self.checkout().data["data"]["id"]

        listing = self.client.get("/api/order/")
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.data["data"]["count"], 1)
        self.assertEqual(listing.data["data"]["results"][0]["id"], order_id)

        detail = self.client.get(f"/api/order/{order_id}")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.data["data"]["items"][0]["sku"], variant.sku)

    def test_cannot_access_another_customers_order(self):
        other = Customer.objects.create_user(
            phone="09120000302",
            password="password",
            first_name="Other",
            last_name="User",
            customer_code="CUS-ORDER-002",
            status=self.active,
        )
        product = self.make_product()
        variant = self.make_normal_variant(product)
        self.add_to_cart(variant)
        order_id = self.checkout().data["data"]["id"]
        order = Order.objects.get(id=order_id)
        order.customer = other
        order.save(update_fields=["customer"])

        response = self.client.get(f"/api/order/{order_id}")
        self.assertEqual(response.status_code, 404)

    # ───────────────────────────── payment ─────────────────────────────

    def test_payment_methods_endpoint(self):
        response = self.client.get("/api/order/payment-methods")
        self.assertEqual(response.status_code, 200)
        methods = response.data["data"]["methods"]
        names = {m["code"] for m in methods}
        self.assertIn("card_to_card", names)
        self.assertIn("deposit_to_account", names)
        card_method = next(m for m in methods if m["code"] == "card_to_card")
        self.assertTrue(card_method["channels"])

    def test_manual_payment_finalizes_order(self):
        product = self.make_product()
        variant = self.make_normal_variant(product)
        self.add_to_cart(variant)
        order_id = self.checkout().data["data"]["id"]

        response = self.client.post(
            f"/api/order/{order_id}/pay",
            {
                "payment_method": "card_to_card",
                "payment_channel_id": self.card_channel.id,
                "ref_number": "ORD-TRX-001",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        order = Order.objects.select_related("status").get(id=order_id)
        self.assertEqual(order.status.name, "paid")
        self.assertEqual(response.data["data"]["available_actions"], [])
        self.assertIsNotNone(order.successful_payment)
        self.assertEqual(order.successful_payment.payment_method, self.card_to_card)
        self.assertEqual(order.successful_payment.ref_number, "ORD-TRX-001")

    def test_payment_is_idempotent(self):
        product = self.make_product()
        variant = self.make_normal_variant(product)
        self.add_to_cart(variant)
        order_id = self.checkout().data["data"]["id"]
        payload = {
            "payment_method": "card_to_card",
            "payment_channel_id": self.card_channel.id,
            "ref_number": "ORD-TRX-DUP",
        }

        first = self.client.post(f"/api/order/{order_id}/pay", payload, format="json")
        second = self.client.post(f"/api/order/{order_id}/pay", payload, format="json")
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(Payment.objects.filter(order_id=order_id).count(), 1)

    def test_online_method_rejected_for_manual_payment(self):
        product = self.make_product()
        variant = self.make_normal_variant(product)
        self.add_to_cart(variant)
        order_id = self.checkout().data["data"]["id"]
        response = self.client.post(
            f"/api/order/{order_id}/pay",
            {
                "payment_method": "online",
                "payment_channel_id": self.card_channel.id,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("payment_method", response.data["errors"])

    def test_pay_rejects_unsupported_channel(self):
        product = self.make_product()
        variant = self.make_normal_variant(product)
        self.add_to_cart(variant)
        order_id = self.checkout().data["data"]["id"]
        unrelated = PaymentChannel.objects.create(
            code="alone", name="Alone channel", fa_name="تنها"
        )

        response = self.client.post(
            f"/api/order/{order_id}/pay",
            {
                "payment_method": "card_to_card",
                "payment_channel_id": unrelated.id,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("payment_channel", response.data["errors"])

    # ───────────────────────────── cancel / expiry ─────────────────────────────

    def test_cancel_releases_reservation(self):
        product = self.make_product()
        variant = self.make_normal_variant(product)
        self.add_to_cart(variant)
        order_id = self.checkout().data["data"]["id"]

        response = self.client.post(f"/api/order/{order_id}/cancel")
        self.assertEqual(response.status_code, 200)
        order = Order.objects.get(id=order_id)
        self.assertEqual(order.status.name, "cancelled")
        self.assertEqual(WarehouseStock.objects.get(variant=variant).reserved, 0)

    def test_customer_actions_are_relation_and_actor_driven(self):
        product = self.make_product()
        variant = self.make_normal_variant(product)
        self.add_to_cart(variant)
        order_id = self.checkout().data["data"]["id"]

        response = self.client.get(f"/api/order/{order_id}/actions")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [action["code"] for action in response.data["data"]["actions"]],
            ["cancel"],
        )
        response = self.client.post(f"/api/order/{order_id}/actions/confirm")
        self.assertEqual(response.status_code, 400)
        response = self.client.post(f"/api/order/{order_id}/actions/cancel")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["status"]["name"], "cancelled")
        self.assertEqual(response.data["data"]["available_actions"], [])
        self.assertEqual(WarehouseStock.objects.get(variant=variant).reserved, 0)
        history = OrderHistory.objects.get(order_id=order_id)
        self.assertEqual(history.action.code, "cancel")
        self.assertEqual(
            set(history.before_values),
            {"status_id", "reservation_expires_at"},
        )
        self.assertEqual(history.before_values["status_id"], 110)
        self.assertIsNotNone(history.before_values["reservation_expires_at"])
        self.assertEqual(
            history.after_values,
            {"status_id": 500, "reservation_expires_at": None},
        )
        self.assertEqual(
            history.description,
            "Order action 'Cancel order' executed by customer.",
        )

    def test_unavailable_action_does_not_create_history(self):
        product = self.make_product()
        variant = self.make_normal_variant(product)
        self.add_to_cart(variant)
        order_id = self.checkout().data["data"]["id"]

        response = self.client.post(f"/api/order/{order_id}/actions/confirm")

        self.assertEqual(response.status_code, 400)
        self.assertFalse(OrderHistory.objects.filter(order_id=order_id).exists())

    def test_history_failure_rolls_back_action_and_reservation_release(self):
        product = self.make_product()
        variant = self.make_normal_variant(product)
        self.add_to_cart(variant)
        order_id = self.checkout().data["data"]["id"]

        with patch.object(OrderHistory.objects, "create", side_effect=RuntimeError):
            with self.assertRaises(RuntimeError):
                OrderService().execute_action(
                    order_id,
                    "cancel",
                    actor="customer",
                    customer=self.customer,
                )

        order = Order.objects.get(id=order_id)
        self.assertEqual(order.status.name, "payment_pending")
        self.assertIsNotNone(order.reservation_expires_at)
        self.assertEqual(WarehouseStock.objects.get(variant=variant).reserved, 1)
        self.assertFalse(OrderHistory.objects.filter(order_id=order_id).exists())

    def test_customer_cannot_access_another_orders_actions(self):
        product = self.make_product()
        variant = self.make_normal_variant(product)
        self.add_to_cart(variant)
        order_id = self.checkout().data["data"]["id"]
        other = Customer.objects.create_user(
            phone="09120000303",
            password="password",
            first_name="Other",
            last_name="Actions",
            customer_code="CUS-ORDER-003",
            status=self.active,
        )
        self.client.force_authenticate(other)

        self.assertEqual(
            self.client.get(f"/api/order/{order_id}/actions").status_code, 404
        )
        self.assertEqual(
            self.client.post(f"/api/order/{order_id}/actions/cancel").status_code,
            404,
        )

    def test_cancel_finalized_order_rejected(self):
        product = self.make_product()
        variant = self.make_normal_variant(product)
        self.add_to_cart(variant)
        order_id = self.checkout().data["data"]["id"]
        self.client.post(
            f"/api/order/{order_id}/pay",
            {
                "payment_method": "card_to_card",
                "payment_channel_id": self.card_channel.id,
            },
            format="json",
        )

        response = self.client.post(f"/api/order/{order_id}/cancel")
        self.assertEqual(response.status_code, 400)

    def test_expire_releases_reservation(self):
        product = self.make_product()
        variant = self.make_normal_variant(product)
        self.add_to_cart(variant)
        order_id = self.checkout().data["data"]["id"]
        order = Order.objects.get(id=order_id)
        order.reservation_expires_at = timezone.now() - timedelta(minutes=1)
        order.save(update_fields=["reservation_expires_at"])


        OrderService().expire_orders([Order.objects.get(id=order_id)])
        order.refresh_from_db()
        self.assertEqual(order.status.name, "payment_expired")
        self.assertEqual(WarehouseStock.objects.get(variant=variant).reserved, 0)

    def test_expire_orders_without_arg_uses_query(self):
        product = self.make_product()
        variant = self.make_normal_variant(product)
        self.add_to_cart(variant)
        order_id = self.checkout().data["data"]["id"]
        order = Order.objects.get(id=order_id)
        order.reservation_expires_at = timezone.now() - timedelta(minutes=1)
        order.save(update_fields=["reservation_expires_at"])

        expired = OrderService().expire_orders()
        self.assertEqual([o.id for o in expired], [order_id])
        order.refresh_from_db()
        self.assertEqual(order.status.name, "payment_expired")

    def create_delivered_order(self, quantity=3):
        product = self.make_product()
        variant = self.make_normal_variant(product)
        self.add_to_cart(variant, quantity=quantity)
        order_id = self.checkout().data["data"]["id"]
        order = Order.objects.get(id=order_id)
        order.status = OrderStatus.objects.get(name="delivered")
        order.save(update_fields=["status"])
        OrderHistory.objects.create(
            order=order,
            action=OrderAction.objects.get(code="deliver"),
            before_values={"status_id": OrderStatus.objects.get(name="shipped").id},
            after_values={"status_id": order.status_id},
        )
        return order, order.items.get()

    def return_payload(self, order, order_item, quantity=1):
        return {
            "order_id": order.id,
            "reason": "Damaged product",
            "customer_note": "The box was crushed.",
            "refund_destination_type": "card",
            "refund_destination_value": "6037991234567890",
            "items": [{
                "order_item_id": order_item.id,
                "quantity": quantity,
                "reason": "Visible damage",
            }],
        }

    def test_customer_can_create_return_without_changing_order(self):
        order, order_item = self.create_delivered_order(quantity=3)
        detail = self.client.get(f"/api/order/{order.id}")

        self.assertIn(
            "request_return",
            [action["code"] for action in detail.data["data"]["available_actions"]],
        )

        response = self.client.post(
            "/api/order/returns",
            self.return_payload(order, order_item, quantity=2),
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["data"]["status"], "requested")
        self.assertEqual(response.data["data"]["items"][0]["quantity"], 2)
        self.assertEqual(response.data["data"]["refund_destination_type"], "card")
        self.assertEqual(response.data["data"]["refund_destination_masked"], "****7890")
        self.assertNotIn("refund_destination_value", response.data["data"])
        self.assertNotIn("admin_note", response.data["data"])
        self.assertIn("customer_response", response.data["data"])
        order.refresh_from_db()
        order_item.refresh_from_db()
        self.assertEqual(order.status.name, "delivered")
        self.assertEqual(order_item.quantity, 3)

    @patch("domains.files.services.file_service.FileService._storage")
    def test_customer_can_create_multipart_return_with_ordered_evidence(self, storage):
        storage.return_value.save.side_effect = lambda key, uploaded: key
        storage.return_value.url.side_effect = lambda key: f"https://files.example/{key}"
        order, order_item = self.create_delivered_order()
        payload = self.return_payload(order, order_item)
        payload["items"] = json.dumps(payload["items"])
        payload["images"] = [
            SimpleUploadedFile("first.jpg", b"first", content_type="image/jpeg"),
            SimpleUploadedFile("second.webp", b"second", content_type="image/webp"),
        ]

        response = self.client.post("/api/order/returns", payload, format="multipart")

        self.assertEqual(response.status_code, 201, response.data)
        evidence = response.data["data"]["evidence"]
        self.assertEqual([item["position"] for item in evidence], [0, 1])
        self.assertEqual([item["original_name"] for item in evidence], ["first.jpg", "second.webp"])
        self.assertTrue(evidence[0]["url"].startswith("https://files.example/orders/"))
        self.assertEqual(ReturnRequestEvidence.objects.count(), 2)

    def test_return_rejects_too_many_or_invalid_images(self):
        order, order_item = self.create_delivered_order()
        payload = self.return_payload(order, order_item)
        payload["items"] = json.dumps(payload["items"])
        payload["images"] = [
            SimpleUploadedFile(f"{index}.gif", b"image", content_type="image/gif")
            for index in range(6)
        ]

        response = self.client.post("/api/order/returns", payload, format="multipart")

        self.assertEqual(response.status_code, 400)
        self.assertFalse(ReturnRequest.objects.exists())

    def test_customer_order_suggests_successful_payment_source_not_channel(self):
        order, _ = self.create_delivered_order()
        payment = Payment.objects.create(
            order=order,
            payment_method=self.card_to_card,
            payment_channel=self.card_channel,
            amount=order.total_amount,
            status=Payment.Status.SUCCESSFUL,
            resource_account_number="6037991234567890",
        )
        order.successful_payment = payment
        order.save(update_fields=["successful_payment"])

        response = self.client.get(f"/api/order/{order.id}")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.data["data"]["refund_destination_suggestion"],
            {"type": "card", "value": "6037991234567890"},
        )
        self.assertNotEqual(
            response.data["data"]["refund_destination_suggestion"]["value"],
            self.card_channel.card_number,
        )

    def test_return_requires_delivered_order(self):
        product = self.make_product()
        variant = self.make_normal_variant(product)
        self.add_to_cart(variant)
        order = Order.objects.get(id=self.checkout().data["data"]["id"])

        response = self.client.post(
            "/api/order/returns",
            self.return_payload(order, order.items.get()),
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(ReturnRequest.objects.exists())

    def test_expired_return_window_hides_action_and_rejects_create(self):
        order, order_item = self.create_delivered_order()
        delivered = order.history.get(action__code="deliver")
        OrderHistory.objects.filter(id=delivered.id).update(
            created_at=timezone.now() - timedelta(days=3, seconds=1)
        )

        detail = self.client.get(f"/api/order/{order.id}")
        create = self.client.post(
            "/api/order/returns",
            self.return_payload(order, order_item),
            format="json",
        )

        self.assertNotIn(
            "request_return",
            [action["code"] for action in detail.data["data"]["available_actions"]],
        )
        self.assertEqual(create.status_code, 400)

    def test_order_detail_includes_return_request_state(self):
        order, order_item = self.create_delivered_order()
        created = self.client.post(
            "/api/order/returns",
            self.return_payload(order, order_item),
            format="json",
        ).data["data"]

        detail = self.client.get(f"/api/order/{order.id}")

        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.data["data"]["return_requests"][0]["id"], created["id"])
        self.assertEqual(detail.data["data"]["return_requests"][0]["status"], "requested")

    def test_admin_processes_return_without_mutating_order_or_item(self):
        order, order_item = self.create_delivered_order(quantity=3)
        created = self.client.post(
            "/api/order/returns",
            self.return_payload(order, order_item, quantity=2),
            format="json",
        ).data["data"]
        return_request = ReturnRequest.objects.get(id=created["id"])
        ReturnRequest.objects.filter(id=return_request.id).update(
            admin_note="Preserve me"
        )
        original_order_status = order.status_id
        original_item_quantity = order_item.quantity
        admin = User.objects.create_superuser("return-admin", password="password")
        self.client.force_authenticate(admin)
        url = (
            f"/api/order/admin/orders/{order.id}/returns/{return_request.id}/actions"
        )

        approve = self.client.post(
            f"{url}/approve", {"customer_response": "Return accepted."}, format="json"
        )
        invalid_status = self.client.post(f"{url}/complete", {}, format="json")
        invalid_action = self.client.post(f"{url}/unknown", {}, format="json")
        received = self.client.post(
            f"{url}/received", {"admin_note": None}, format="json"
        )
        completed = self.client.post(f"{url}/complete", {}, format="json")

        self.assertEqual(approve.status_code, 200, approve.data)
        self.assertEqual(invalid_status.status_code, 400)
        self.assertEqual(invalid_action.status_code, 400)
        self.assertEqual(received.status_code, 200, received.data)
        self.assertEqual(completed.status_code, 200, completed.data)
        return_request.refresh_from_db()
        order.refresh_from_db()
        order_item.refresh_from_db()
        self.assertEqual(return_request.status, ReturnRequest.Status.COMPLETED)
        self.assertIsNotNone(return_request.approved_at)
        self.assertIsNotNone(return_request.received_at)
        self.assertIsNotNone(return_request.completed_at)
        self.assertIsNone(return_request.admin_note)
        self.assertEqual(return_request.customer_response, "Return accepted.")
        self.assertEqual(order.status_id, original_order_status)
        self.assertEqual(order_item.quantity, original_item_quantity)
        self.assertFalse(
            OrderHistory.objects.filter(order=order).exclude(action__code="deliver").exists()
        )

        self.client.force_authenticate(self.customer)
        customer_detail = self.client.get(f"/api/order/{order.id}").data["data"]
        customer_return = customer_detail["return_requests"][0]
        self.assertNotIn("admin_note", customer_return)
        self.assertEqual(customer_return["customer_response"], "Return accepted.")

    def test_active_return_blocks_another_request_until_processed(self):
        order, order_item = self.create_delivered_order(quantity=3)
        first = self.client.post(
            "/api/order/returns",
            self.return_payload(order, order_item),
            format="json",
        )

        detail_while_active = self.client.get(f"/api/order/{order.id}")
        second = self.client.post(
            "/api/order/returns",
            self.return_payload(order, order_item),
            format="json",
        )

        self.assertEqual(first.status_code, 201)
        self.assertNotIn(
            "request_return",
            [
                action["code"]
                for action in detail_while_active.data["data"]["available_actions"]
            ],
        )
        self.assertEqual(second.status_code, 400)

        ReturnRequest.objects.filter(id=first.data["data"]["id"]).update(
            status=ReturnRequest.Status.COMPLETED,
            completed_at=timezone.now(),
        )
        detail_after_completion = self.client.get(f"/api/order/{order.id}")

        self.assertIn(
            "request_return",
            [
                action["code"]
                for action in detail_after_completion.data["data"]["available_actions"]
            ],
        )

    def test_generic_return_action_does_not_change_order_status(self):
        order, _ = self.create_delivered_order()

        response = self.client.post(f"/api/order/{order.id}/actions/request_return")

        self.assertEqual(response.status_code, 400)
        order.refresh_from_db()
        self.assertEqual(order.status.name, "delivered")

    def test_return_rejects_item_from_another_order_atomically(self):
        order, order_item = self.create_delivered_order()
        other_order, other_item = self.create_delivered_order()
        payload = self.return_payload(order, order_item)
        payload["items"].append({"order_item_id": other_item.id, "quantity": 1})

        response = self.client.post("/api/order/returns", payload, format="json")

        self.assertEqual(response.status_code, 400)
        self.assertFalse(ReturnRequest.objects.exists())
        self.assertNotEqual(order.id, other_order.id)

    def test_return_rejects_duplicate_items(self):
        order, order_item = self.create_delivered_order()
        payload = self.return_payload(order, order_item)
        payload["items"].append({"order_item_id": order_item.id, "quantity": 1})

        response = self.client.post("/api/order/returns", payload, format="json")

        self.assertEqual(response.status_code, 400)
        self.assertFalse(ReturnRequest.objects.exists())

    def test_active_and_completed_returns_reduce_available_quantity(self):
        order, order_item = self.create_delivered_order(quantity=5)
        for status, quantity in (("approved", 2), ("completed", 2)):
            existing = ReturnRequest.objects.create(
                order=order,
                customer=self.customer,
                status=status,
                reason="Existing return",
            )
            ReturnRequestItem.objects.create(
                return_request=existing,
                order_item=order_item,
                quantity=quantity,
            )

        rejected = self.client.post(
            "/api/order/returns",
            self.return_payload(order, order_item, quantity=2),
            format="json",
        )
        ReturnRequest.objects.filter(status="approved").update(
            status="completed",
            completed_at=timezone.now(),
        )
        accepted = self.client.post(
            "/api/order/returns",
            self.return_payload(order, order_item, quantity=1),
            format="json",
        )

        self.assertEqual(rejected.status_code, 400)
        self.assertEqual(accepted.status_code, 201)

    def test_rejected_and_cancelled_returns_do_not_reduce_quantity(self):
        order, order_item = self.create_delivered_order(quantity=2)
        for status in ("rejected", "cancelled"):
            existing = ReturnRequest.objects.create(
                order=order,
                customer=self.customer,
                status=status,
                reason="Inactive return",
            )
            ReturnRequestItem.objects.create(
                return_request=existing,
                order_item=order_item,
                quantity=2,
            )

        response = self.client.post(
            "/api/order/returns",
            self.return_payload(order, order_item, quantity=2),
            format="json",
        )

        self.assertEqual(response.status_code, 201)

    def test_return_list_and_detail_are_customer_scoped(self):
        order, order_item = self.create_delivered_order()
        created = self.client.post(
            "/api/order/returns",
            self.return_payload(order, order_item),
            format="json",
        ).data["data"]
        other_customer = Customer.objects.create_user(
            phone="09120000302",
            password="password",
            customer_code="CUS-ORDER-002",
            status=self.active,
        )
        self.client.force_authenticate(other_customer)

        listing = self.client.get("/api/order/returns")
        detail = self.client.get(f"/api/order/returns/{created['id']}")
        foreign_create = self.client.post(
            "/api/order/returns",
            self.return_payload(order, order_item),
            format="json",
        )

        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.data["data"]["count"], 0)
        self.assertEqual(detail.status_code, 404)
        self.assertEqual(foreign_create.status_code, 404)
