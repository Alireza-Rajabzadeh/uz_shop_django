from decimal import Decimal

from domains.business.models import BusinessProfile
from domains.catalog.models import (
    Category,
    CategoryStatus,
    Product,
    ProductStatus,
    ProductVariants,
    VariantAttribute,
    VariantOption,
)
from domains.customer.models import Customer, CustomerStatus
from domains.inventory.models import Inventory, Warehouse, WarehouseStatus
from domains.location.models import City, Country, State
from domains.marketplace.models import BusinessOffer
from domains.vendor.models import Vendor, VendorStatus
from rest_framework.test import APITestCase


class CartBaseAPITestCase(APITestCase):
    def setUp(self):
        self.active = CustomerStatus.objects.create(name="active", title="Active")
        self.customer = Customer.objects.create_user(
            phone="09120000201",
            password="password",
            first_name="Cart",
            last_name="Owner",
            customer_code="CUS-CART-001",
            status=self.active,
        )
        self.client.force_authenticate(self.customer)

        country = Country.objects.create(name="Cart Country", code="CC", phone_code="+98")
        state = State.objects.create(name="Cart State", country=country)
        self.city = City.objects.create(name="Cart City", state=state)
        self.warehouse_status = WarehouseStatus.objects.create(name="available-for-tests")
        # inventory.0022 seeds the singleton profile with id=1 in every test
        # database, so this must attach to it rather than insert a new row.
        vendor_status = VendorStatus.objects.create(name="active", title="Active")
        vendor = Vendor.objects.create(
            phone="+9990000002",
            first_name="Cart",
            last_name="Vendor",
            national_id="0000000002",
            vendor_code="VEN-CART-001",
            status=vendor_status,
        )
        self.business, _ = BusinessProfile.objects.get_or_create(
            id=1,
            defaults={
                "vendor": vendor,
                "business_name": "Cart Business",
                "display_name": "Cart Business",
            },
        )
        self.warehouse = Warehouse.objects.create(
            code="WH-CART",
            name="Default Cart Warehouse",
            business=self.business,
            city=self.city,
            address="Test address",
            lat="0",
            lng="0",
            is_default=True,
            status=self.warehouse_status,
        )
        category_status = CategoryStatus.objects.create(name="cart-active")
        self.category = Category.objects.create(
            name="Cart Category", status=category_status
        )
        self.active_status = ProductStatus.objects.create(name="active")
        self.inactive_status = ProductStatus.objects.create(name="inactive")
        self.preorder_status = ProductStatus.objects.create(name="preorder")
        self.attribute = VariantAttribute.objects.create(name="Cart Color")
        self.option = VariantOption.objects.create(
            attribute=self.attribute, name="Black", sku_code="CARTBLK"
        )

    def make_product(self, status):
        product = Product.objects.create(name="Cart Product", status=status)
        product.categories.add(self.category)
        return product

    def make_variant(self, product, price="100.00", available=8, quantity=10):
        variant = ProductVariants.objects.create(
            product=product,
            sku=f"CG0-PD{product.id}-CARTBLK",
            combination_key=f"opt:{self.option.id}",
        )
        BusinessOffer.objects.get_or_create(
            business=self.business,
            variant=variant,
            defaults={"price": Decimal(price)},
        )
        Inventory.objects.create(
            business=self.business,
            variant=variant,
            warehouse=self.warehouse,
            quantity=quantity,
            sellable=available,
            reserved=0,
            min_stock=0,
        )
        return variant

    def add_item(self, variant, quantity=1):
        return self.client.post(
            "/api/cart/items",
            {"variant_id": variant.id, "quantity": quantity},
            format="json",
        )

    def sync_items(self, items):
        return self.client.post("/api/cart/sync", {"items": items}, format="json")
