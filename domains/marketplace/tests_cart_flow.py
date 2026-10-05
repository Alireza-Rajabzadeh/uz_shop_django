from decimal import Decimal

from django.test import TestCase

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
from domains.cart.services import CartService
from domains.customer.models import Customer, CustomerStatus
from domains.inventory.models import Inventory, Warehouse, WarehouseStatus
from domains.location.models import City, Country, State
from domains.marketplace.models import (
    BusinessOffer,
    MarketplaceCart,
    MarketplaceCartItem,
)
from domains.marketplace.services.cart_service import MarketplaceCartService
from domains.business.models import BusinessProfile
from domains.vendor.models import Vendor, VendorStatus


class MarketplaceCartServiceTests(TestCase):
    """The marketplace basket behaves exactly like the shop basket.

    The two flows are meant to be interchangeable from a customer's point of
    view, so these tests pin both the table separation and the payload
    equivalence. Any divergence in behaviour should show up here as a failed
    assertion rather than as a difference a client has to work around.
    """

    def setUp(self):
        self.customer = Customer.objects.create_user(
            phone="09120000601",
            password="password",
            first_name="Marketplace",
            last_name="Cart",
            customer_code="CUS-MKTCART-001",
            status=CustomerStatus.objects.create(name="mkt-cart-active", title="Active"),
        )

        country = Country.objects.create(name="Mkt Country", code="MC", phone_code="+98")
        state = State.objects.create(name="Mkt State", country=country)
        city = City.objects.create(name="Mkt City", state=state)
        self.warehouse = Warehouse.objects.create(
            code="WH-MKTCART",
            name="Mkt Warehouse",
            city=city,
            address="Mkt address",
            lat="0",
            lng="0",
            is_default=True,
            status=WarehouseStatus.objects.create(name="available-mkt-cart"),
        )
        self.category = Category.objects.create(
            name="Mkt Cart Category",
            status=CategoryStatus.objects.create(name="mkt-cart-active"),
        )
        self.active_status = ProductStatus.objects.create(name="active")
        self.attribute = VariantAttribute.objects.create(name="Mkt Color")
        self.option = VariantOption.objects.create(
            attribute=self.attribute, name="White", sku_code="MKTWH"
        )
        vendor_status = VendorStatus.objects.create(name="active", title="Active")
        vendor = Vendor.objects.create(
            phone="+9990000014",
            first_name="Mkt",
            last_name="Vendor",
            national_id="0000000014",
            vendor_code="VEN-MKTCART-001",
            status=vendor_status,
        )
        self.business, _ = BusinessProfile.objects.get_or_create(
            id=1,
            defaults={
                "vendor": vendor,
                "business_name": "Mkt Cart Business",
                "display_name": "Mkt Cart Business",
            },
        )

    def make_variant(self, price="100.00", discount_value=None, available=8):
        product = Product.objects.create(name="Mkt Cart Product", status=self.active_status)
        product.categories.add(self.category)
        variant = ProductVariants.objects.create(
            product=product,
            sku=f"MKT-PD{product.id}-MKTWH",
            combination_key=f"opt:{self.option.id}",
        )
        offer = BusinessOffer.objects.create(
            business=self.business,
            variant=variant,
            price=Decimal(price),
            discount_type="percentage" if discount_value else None,
            discount_value=discount_value,
        )
        Inventory.objects.create(
            business=self.business,
            variant=variant,
            warehouse=self.warehouse,
            quantity=10,
            sellable=available,
            reserved=0,
            min_stock=0,
        )
        return variant, offer

    def test_adding_writes_the_marketplace_tables_only(self):
        variant, _offer = self.make_variant()

        MarketplaceCartService().add(self.customer, variant.id, quantity=2)

        self.assertEqual(MarketplaceCart.objects.filter(customer=self.customer).count(), 1)
        item = MarketplaceCartItem.objects.get()
        self.assertEqual(item.variant_id, variant.id)
        self.assertEqual(item.quantity, 2)
        self.assertEqual(Cart.objects.filter(customer=self.customer).count(), 0)
        self.assertEqual(CartItem.objects.count(), 0)

    def test_shop_and_marketplace_baskets_are_independent(self):
        variant, _offer = self.make_variant()

        CartService().add(self.customer, variant.id, quantity=1)
        MarketplaceCartService().add(self.customer, variant.id, quantity=3)

        self.assertEqual(CartItem.objects.get().quantity, 1)
        self.assertEqual(MarketplaceCartItem.objects.get().quantity, 3)

    def test_pricing_comes_from_the_active_offer(self):
        variant, _offer = self.make_variant(price="500.00", discount_value=Decimal("10.00"))
        MarketplaceCartService().add(self.customer, variant.id)

        payload = MarketplaceCartService().describe_cart(self.customer)

        item = payload["items"][0]
        self.assertEqual(item["unit_price"], "500.00")
        self.assertEqual(item["effective_price"], "450.00")
        self.assertEqual(item["unit_discount_amount"], "50.00")
        self.assertEqual(item["quantity"], 1)

    def test_payload_is_indistinguishable_from_the_shop_cart(self):
        variant, _offer = self.make_variant(price="500.00", discount_value=Decimal("10.00"))
        CartService().add(self.customer, variant.id, quantity=1)
        MarketplaceCartService().add(self.customer, variant.id, quantity=1)

        shop_payload = CartService().describe_cart(self.customer)
        marketplace_payload = MarketplaceCartService().describe_cart(self.customer)

        self.assertEqual(set(shop_payload), set(marketplace_payload))
        self.assertEqual(
            [set(item) for item in shop_payload["items"]],
            [set(item) for item in marketplace_payload["items"]],
        )
        self.assertEqual(shop_payload["totals"], marketplace_payload["totals"])
        self.assertEqual(shop_payload["cart_valid"], marketplace_payload["cart_valid"])
        # Only the row identity may differ.
        self.assertNotEqual(shop_payload["id"], marketplace_payload["id"])
        self.assertNotEqual(
            shop_payload["items"][0]["id"], marketplace_payload["items"][0]["id"]
        )

    def test_a_deactivated_offer_is_not_read_for_pricing(self):
        variant, offer = self.make_variant()
        offer.is_active = False
        offer.save(update_fields=["is_active"])
        MarketplaceCartService().add(self.customer, variant.id)

        payload = MarketplaceCartService().describe_cart(self.customer)

        # Only published offers are attached, so the line falls back to zero
        # rather than to the offer that stopped being published.
        self.assertEqual(Decimal(payload["items"][0]["unit_price"]), Decimal("0"))
        self.assertEqual(Decimal(payload["items"][0]["effective_price"]), Decimal("0"))
        self.assertEqual(payload["cart_valid"], True)
