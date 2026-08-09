from datetime import timedelta
from decimal import Decimal

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
    OrderItem,
    OrderPayment,
    OrderPaymentChannel,
    OrderPaymentChannelSupportMethod,
    OrderPaymentMethod,
    OrderStatus,
)
from rest_framework.test import APITestCase

from core.management.seeders.order import OrderSeeder
from domains.order.services import OrderService


class OrderAPITests(APITestCase):
    def setUp(self):
        OrderSeeder().run()
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
        self.card_channel = OrderPaymentChannel.objects.get(name="Mellat card-to-card")
        self.card_to_card = OrderPaymentMethod.objects.get(name="card_to_card")
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
        self.assertEqual(data["status"], "payment_waiting")
        self.assertEqual(data["totals"]["subtotal"], "300.00")
        self.assertEqual(data["totals"]["total_amount"], "300.00")
        self.assertTrue(data["reservation_expires_at"])
        self.assertEqual(CartItem.objects.filter(cart__customer=self.customer).count(), 0)

        order = Order.objects.get(id=data["id"])
        self.assertEqual(order.status.name, "payment_waiting")
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
        names = {m["name"] for m in methods}
        self.assertIn("card_to_card", names)
        self.assertIn("deposit_to_account", names)
        card_method = next(m for m in methods if m["name"] == "card_to_card")
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
        self.assertEqual(order.status.name, "success")
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
        self.assertEqual(OrderPayment.objects.filter(order_id=order_id).count(), 1)

    def test_online_method_rejected_for_manual_payment(self):
        product = self.make_product()
        variant = self.make_normal_variant(product)
        self.add_to_cart(variant)
        order_id = self.checkout().data["data"]["id"]
        online_channel = OrderPaymentChannel.objects.get(name="Zarinpal online")

        response = self.client.post(
            f"/api/order/{order_id}/pay",
            {
                "payment_method": "online",
                "payment_channel_id": online_channel.id,
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
        unrelated = OrderPaymentChannel.objects.create(
            name="Alone channel", fa_name="تنها"
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
        self.assertEqual(order.status.name, "failed")
        self.assertEqual(WarehouseStock.objects.get(variant=variant).reserved, 0)

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
        self.assertEqual(order.status.name, "expired")
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
        self.assertEqual(order.status.name, "expired")
