from decimal import Decimal

from rest_framework import status
from rest_framework.test import APITestCase

from domains.business.models import BusinessProfile
from domains.business_payments.models import (
    BusinessPaymentChannel,
    BusinessPaymentChannelSupportedMethod,
    BusinessPaymentMethod,
)
from domains.catalog.models import ProductVariants
from domains.inventory.models import Inventory, Warehouse, WarehouseStatus
from domains.marketplace.models import (
    BusinessOffer,
    MarketplaceCart,
    MarketplaceCartItem,
    MarketplaceOrder,
)
from domains.marketplace.services.cart_service import MarketplaceCartService
from domains.marketplace.services.order_service import MarketplaceOrderService
from domains.vendor.models import Vendor, VendorStatus

from .tests_checkout import MarketplaceCheckoutFixture


class SellerCheckoutTests(MarketplaceCheckoutFixture):
    """Seller isolation through the marketplace cart, checkout and payment."""

    def setUp(self):
        super().setUp()
        self.client.force_authenticate(self.customer)
        self.vendor2 = Vendor.objects.create(
            phone="+9990000006",
            first_name="Second",
            last_name="Vendor",
            national_id="0000000006",
            vendor_code="VEN-MKCO-002",
            status=VendorStatus.objects.create(
                name="active-second", title="Active"
            ),
        )
        self.business2 = BusinessProfile.objects.create(
            vendor=self.vendor2,
            business_name="Second Business",
            display_name="Second Business",
        )
        self.warehouse2 = Warehouse.objects.create(
            code="WH-MKCO-2",
            name="Second Warehouse",
            business=self.business2,
            city=self.city,
            address="Second address",
            lat="0",
            lng="0",
            is_default=True,
            status=WarehouseStatus.objects.create(name="available-second"),
        )
        self.cart = MarketplaceCart.objects.create(
            customer=self.customer, address_info={"city_name": "MkCi"}
        )

    def make_offer(self, business, warehouse, price="100.00"):
        product = self.make_product()
        variant = ProductVariants.objects.create(
            product=product,
            sku=f"MKCO2-{ProductVariants.objects.count() + 1}",
            combination_key=f"opt:{self.option.id}",
        )
        offer = BusinessOffer.objects.create(
            business=business,
            variant=variant,
            price=Decimal(price),
        )
        inventory = Inventory.objects.create(
            business=business,
            variant=variant,
            warehouse=warehouse,
            quantity=10,
            sellable=8,
            reserved=0,
            min_stock=0,
        )
        return variant, offer, inventory

    def add(self, variant, offer, quantity=1):
        MarketplaceCartService().add(
            self.customer,
            variant.id,
            quantity=quantity,
            offer_id=offer.id,
        )

    def make_channel(self, business, code):
        channel = BusinessPaymentChannel.objects.create(
            business=business,
            code=code,
            name=code,
            fa_name=code,
            card_number="6104337890123456",
        )
        BusinessPaymentChannelSupportedMethod.objects.create(
            payment_channel=channel,
            payment_method=BusinessPaymentMethod.objects.get(code="card_to_card"),
        )
        return channel

    def test_cart_groups_and_checkout_are_independent_per_seller(self):
        variant1, offer1, inventory1 = self.make_offer(
            self.business, self.warehouse
        )
        variant2, offer2, inventory2 = self.make_offer(
            self.business2, self.warehouse2
        )
        self.add(variant1, offer1, quantity=2)
        self.add(variant2, offer2, quantity=1)

        payload = MarketplaceCartService().describe_cart(self.customer)
        groups = {group["business"]["id"]: group for group in payload["seller_groups"]}

        self.assertEqual(len(groups), 2)
        self.assertTrue(groups[self.business.id]["payment_available"])
        self.assertFalse(groups[self.business2.id]["payment_available"])
        self.assertEqual(groups[self.business.id]["checkout_status"], "ready")
        self.assertEqual(
            groups[self.business2.id]["checkout_status"],
            "awaiting_payment_method",
        )

        order1 = MarketplaceOrderService().checkout_business_from_cart(
            self.customer, self.business.id
        )

        self.assertEqual(order1.business, self.business)
        self.assertEqual(order1.items.count(), 1)
        self.assertEqual(
            MarketplaceCartItem.objects.filter(cart=self.cart).count(), 1
        )
        self.assertEqual(
            MarketplaceCartItem.objects.get().variant_id, variant2.id
        )
        inventory1.refresh_from_db()
        inventory2.refresh_from_db()
        self.assertEqual(inventory1.reserved, 2)
        self.assertEqual(inventory2.reserved, 0)

        self.make_channel(self.business2, "second-manual")
        refreshed = MarketplaceCartService().describe_cart(self.customer)
        refreshed_groups = {
            group["business"]["id"]: group
            for group in refreshed["seller_groups"]
        }
        self.assertEqual(
            refreshed_groups[self.business2.id]["checkout_status"], "ready"
        )
        order2 = MarketplaceOrderService().checkout_business_from_cart(
            self.customer, self.business2.id
        )

        self.assertEqual(order2.business, self.business2)
        self.assertEqual(MarketplaceCartItem.objects.filter(cart=self.cart).count(), 0)
        inventory2.refresh_from_db()
        self.assertEqual(inventory2.reserved, 1)
        self.assertEqual(MarketplaceOrder.objects.count(), 2)

    def test_waiting_seller_does_not_block_a_ready_seller(self):
        variant1, offer1, _inventory1 = self.make_offer(
            self.business, self.warehouse
        )
        variant2, offer2, inventory2 = self.make_offer(
            self.business2, self.warehouse2
        )
        self.add(variant1, offer1)
        self.add(variant2, offer2)

        with self.assertRaises(
            MarketplaceOrderService.PaymentMethodUnavailable
        ):
            MarketplaceOrderService().checkout_business_from_cart(
                self.customer, self.business2.id
            )

        self.assertEqual(MarketplaceOrder.objects.count(), 0)
        self.assertEqual(
            MarketplaceCartItem.objects.filter(cart=self.cart).count(), 2
        )
        inventory2.refresh_from_db()
        self.assertEqual(inventory2.reserved, 0)

        order = MarketplaceOrderService().checkout_business_from_cart(
            self.customer, self.business.id
        )

        self.assertEqual(order.business, self.business)
        self.assertEqual(
            MarketplaceCartItem.objects.filter(cart=self.cart).count(), 1
        )
        self.assertEqual(
            MarketplaceCartItem.objects.get().variant_id, variant2.id
        )

        self.make_channel(self.business2, "second-manual")
        later = MarketplaceOrderService().checkout_business_from_cart(
            self.customer, self.business2.id
        )
        self.assertEqual(later.business, self.business2)

    def test_payment_methods_are_scoped_to_the_orders_business(self):
        variant1, offer1, _inventory1 = self.make_offer(
            self.business, self.warehouse
        )
        self.add(variant1, offer1)
        order = MarketplaceOrderService().checkout_business_from_cart(
            self.customer, self.business.id
        )
        other_channel = self.make_channel(self.business2, "other-manual")

        response = self.client.get(
            f"/api/marketplace/orders/{order.id}/payment-methods"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        methods = response.data["data"]["methods"]
        method = next(method for method in methods if method["code"] == "card_to_card")
        self.assertEqual(
            [channel["id"] for channel in method["channels"]],
            [self.channel.id],
        )

        rejected = self.client.post(
            f"/api/marketplace/orders/{order.id}/pay",
            {
                "payment_method": "card_to_card",
                "payment_channel_id": other_channel.id,
                "ref_number": "123456",
            },
            format="json",
        )
        self.assertEqual(rejected.status_code, status.HTTP_400_BAD_REQUEST)

    def test_customer_checkout_api_creates_only_the_selected_seller_order(self):
        variant1, offer1, _inventory1 = self.make_offer(
            self.business, self.warehouse
        )
        variant2, offer2, _inventory2 = self.make_offer(
            self.business2, self.warehouse2
        )
        self.add(variant1, offer1)
        self.add(variant2, offer2)

        response = self.client.post(
            "/api/marketplace/orders/",
            {"business_id": self.business.id},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["data"]["business"]["id"], self.business.id)
        self.assertEqual(MarketplaceOrder.objects.count(), 1)
        self.assertEqual(
            MarketplaceOrder.objects.get().business_id, self.business.id
        )
        self.assertEqual(
            MarketplaceCartItem.objects.filter(cart=self.cart).count(), 1
        )

        waiting = self.client.post(
            "/api/marketplace/orders/",
            {"business_id": self.business2.id},
            format="json",
        )
        self.assertEqual(waiting.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(
            waiting.data["data"]["code"], "payment_method_unavailable"
        )
        self.assertEqual(MarketplaceOrder.objects.count(), 1)
