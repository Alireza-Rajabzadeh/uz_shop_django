from decimal import Decimal

from django.contrib.auth.models import User

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
    Warehouse,
    WarehouseStatus,
    WarehouseStock,
)
from domains.location.models import City, Country, State
from domains.preorder.models import PreOrder
from domains.wishlist.models import Wishlist
from rest_framework.test import APIClient, APITestCase


class CartAdminAPITests(APITestCase):
    def setUp(self):
        self.active = CustomerStatus.objects.create(name="active", title="Active")
        self.customer = Customer.objects.create_user(
            phone="09120000201",
            password="password",
            first_name="Cart",
            last_name="Admin",
            customer_code="CUS-CART-101",
            status=self.active,
        )
        self.admin = User.objects.create_superuser("cart-admin", password="password")
        self.client.force_authenticate(self.admin)
        self.cart = Cart.objects.create(customer=self.customer)

    def test_admin_list_shows_cart_row(self):
        response = self.client.get("/api/cart/admin/carts")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["count"], 1)
        row = response.data["data"]["results"][0]
        self.assertEqual(row["id"], self.cart.id)
        self.assertEqual(row["customer"]["id"], self.customer.id)
        self.assertEqual(row["items_count"], 0)
        self.assertFalse(row["has_address"])

    def test_admin_list_filters_by_search(self):
        response = self.client.get("/api/cart/admin/carts", {"search": "Admin"})
        self.assertEqual(response.data["data"]["count"], 1)
        response = self.client.get("/api/cart/admin/carts", {"search": "no-match"})
        self.assertEqual(response.data["data"]["count"], 0)

    def test_admin_detail(self):
        response = self.client.get(f"/api/cart/admin/carts/{self.cart.id}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["id"], self.cart.id)
        self.assertEqual(response.data["data"]["customer"]["id"], self.customer.id)
        self.assertEqual(response.data["data"]["items"], [])

    def test_admin_detail_missing_is_404(self):
        response = self.client.get("/api/cart/admin/carts/999999")
        self.assertEqual(response.status_code, 404)

    def test_customer_principal_cannot_use_admin_endpoints(self):
        self.client.force_authenticate(self.customer)
        self.assertEqual(self.client.get("/api/cart/admin/carts").status_code, 403)

    def test_staff_without_permission_is_rejected(self):
        staff = User.objects.create_user(
            username="cart-noperm", password="password", is_staff=True
        )
        self.client.force_authenticate(staff)
        self.assertEqual(self.client.get("/api/cart/admin/carts").status_code, 403)


class CartAPITests(APITestCase):
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
        self.warehouse = Warehouse.objects.create(
            code="WH-CART",
            name="Default Cart Warehouse",
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
            inventory_strategy=self.normal,
            sku=f"CG0-PD{product.id}-CARTBLK",
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

    def add_item(self, variant, quantity=1):
        return self.client.post(
            "/api/cart/items",
            {"variant_id": variant.id, "quantity": quantity},
            format="json",
        )

    # ─────────────── basic cart behavior ───────────────

    def test_get_cart_creates_single_cart(self):
        response = self.client.get("/api/cart/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Cart.objects.filter(customer=self.customer).count(), 1)
        self.assertEqual(response.data["data"]["items"], [])

    def test_add_updates_existing_row_quantity(self):
        product = self.make_product(self.active_status)
        variant = self.make_variant(product)
        first = self.client.post(
            "/api/cart/items",
            {"variant_id": variant.id, "quantity": 2},
            format="json",
        )
        self.assertEqual(first.status_code, 201)
        self.assertEqual(CartItem.objects.count(), 1)

        second = self.client.post(
            "/api/cart/items",
            {"variant_id": variant.id, "quantity": 5},
            format="json",
        )
        self.assertEqual(second.status_code, 201)
        self.assertEqual(second.data["data"]["items"][0]["quantity"], 5)
        self.assertEqual(CartItem.objects.count(), 1)

    def test_add_requires_positive_quantity(self):
        product = self.make_product(self.active_status)
        variant = self.make_variant(product)
        response = self.client.post(
            "/api/cart/items",
            {"variant_id": variant.id, "quantity": 0},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_add_missing_variant_rejected(self):
        response = self.client.post(
            "/api/cart/items", {"variant_id": 999999, "quantity": 1}, format="json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("variant_id", response.data["errors"])

    def test_update_and_remove_quantity(self):
        product = self.make_product(self.active_status)
        variant = self.make_variant(product)
        added = self.add_item(variant, quantity=3)
        item_id = added.data["data"]["items"][0]["id"]

        patch = self.client.patch(
            f"/api/cart/items/{item_id}", {"quantity": 7}, format="json"
        )
        self.assertEqual(patch.status_code, 200)
        self.assertEqual(patch.data["data"]["items"][0]["quantity"], 7)

        zero = self.client.patch(
            f"/api/cart/items/{item_id}", {"quantity": 0}, format="json"
        )
        self.assertEqual(zero.status_code, 400)

        delete = self.client.delete(f"/api/cart/items/{item_id}")
        self.assertEqual(delete.status_code, 200)
        self.assertEqual(delete.data["data"]["items"], [])
        self.assertEqual(CartItem.objects.filter(cart__customer=self.customer).count(), 0)

    def test_remove_missing_item_is_404(self):
        response = self.client.delete("/api/cart/items/999999")
        self.assertEqual(response.status_code, 404)

    # ─────────────── item state / inventory ───────────────

    def test_cart_shows_live_prices_and_discounts(self):
        product = self.make_product(self.active_status)
        variant = self.make_variant(product)
        variant.discount_type = "percentage"
        variant.discount_value = Decimal("10")
        variant.save(update_fields=["discount_type", "discount_value"])

        self.add_item(variant, quantity=2)
        data = self.client.get("/api/cart/").data["data"]
        item = data["items"][0]
        self.assertEqual(item["unit_price"], "100.00")
        self.assertEqual(item["effective_price"], "90.00")
        self.assertEqual(item["line_total"], "180.00")
        self.assertEqual(data["totals"]["total_amount"], "180.00")
        self.assertIn("combination_key", item)

    def test_unavailable_product_is_flagged(self):
        product = self.make_product(self.active_status)
        variant = self.make_variant(product)
        self.add_item(variant)
        product.status = self.inactive_status
        product.save(update_fields=["status"])

        data = self.client.get("/api/cart/").data["data"]
        item = data["items"][0]
        self.assertFalse(item["valid"])
        self.assertEqual(item["status"], "variant_unavailable")
        self.assertEqual(item["suggested_action"], "remove")
        self.assertFalse(data["cart_valid"])

    def test_insufficient_inventory_is_flagged(self):
        product = self.make_product(self.active_status)
        variant = self.make_variant(product)
        self.add_item(variant, quantity=5)
        stock = WarehouseStock.objects.get(variant=variant)
        stock.sellable = 1
        stock.save(update_fields=["sellable"])

        data = self.client.get("/api/cart/").data["data"]
        item = data["items"][0]
        self.assertFalse(item["valid"])
        self.assertEqual(item["status"], "out_of_stock")
        self.assertFalse(data["cart_valid"])

    def test_validate_endpoint(self):
        product = self.make_product(self.active_status)
        variant = self.make_variant(product)
        self.add_item(variant)
        response = self.client.get("/api/cart/validate")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["data"]["valid"])
        self.assertEqual(response.data["data"]["items"][0]["status"], "available")

    def test_empty_cart_is_invalid_for_checkout(self):
        data = self.client.get("/api/cart/validate").data["data"]
        self.assertFalse(data["valid"])

    # ─────────────── moves ───────────────

    def test_moves_item_to_wishlist(self):
        product = self.make_product(self.active_status)
        variant = self.make_variant(product)
        item = self.add_item(variant)
        item_id = item.data["data"]["items"][0]["id"]

        move = self.client.post(f"/api/cart/items/{item_id}/move-to-wishlist")
        self.assertEqual(move.status_code, 200)
        self.assertTrue(Wishlist.objects.filter(customer=self.customer, product=product).exists())
        self.assertFalse(CartItem.objects.filter(id=item_id).exists())

    def test_move_to_wishlist_when_already_saved_still_removes(self):
        product = self.make_product(self.active_status)
        variant = self.make_variant(product)
        Wishlist.objects.create(customer=self.customer, product=product)
        item = self.add_item(variant)
        item_id = item.data["data"]["items"][0]["id"]

        move = self.client.post(f"/api/cart/items/{item_id}/move-to-wishlist")
        self.assertEqual(move.status_code, 200)
        self.assertFalse(CartItem.objects.filter(id=item_id).exists())

    def test_moves_item_to_preorder_when_allowed(self):
        product = self.make_product(self.preorder_status)
        variant = self.make_variant(product)
        item = self.add_item(variant)
        item_id = item.data["data"]["items"][0]["id"]

        move = self.client.post(f"/api/cart/items/{item_id}/move-to-preorder")
        self.assertEqual(move.status_code, 200)
        self.assertTrue(PreOrder.objects.filter(customer=self.customer, product=product).exists())
        self.assertFalse(CartItem.objects.filter(id=item_id).exists())

    def test_move_to_preorder_rejected_when_not_allowed(self):
        product = self.make_product(self.active_status)
        variant = self.make_variant(product)
        item = self.add_item(variant)
        item_id = item.data["data"]["items"][0]["id"]

        move = self.client.post(f"/api/cart/items/{item_id}/move-to-preorder")
        self.assertEqual(move.status_code, 400)
        self.assertIn("product", move.data["errors"])
        self.assertTrue(CartItem.objects.filter(id=item_id).exists())

    # ─────────────── sync ───────────────

    def sync_items(self, items):
        return self.client.post("/api/cart/sync", {"items": items}, format="json")

    def test_add_returns_full_cart(self):
        product = self.make_product(self.active_status)
        variant = self.make_variant(product)
        response = self.client.post(
            "/api/cart/items",
            {"variant_id": variant.id, "quantity": 2},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        data = response.data["data"]
        self.assertIn("items", data)
        self.assertEqual(len(data["items"]), 1)
        self.assertEqual(data["items"][0]["variant_id"], variant.id)
        self.assertEqual(data["items"][0]["quantity"], 2)

    def test_sync_keeps_existing_variants(self):
        product = self.make_product(self.active_status)
        variant = self.make_variant(product)
        response = self.sync_items([{"variant_id": variant.id, "quantity": 3}])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["removed"], [])
        cart = response.data["data"]["cart"]
        self.assertEqual(len(cart["items"]), 1)
        self.assertEqual(cart["items"][0]["quantity"], 3)
        self.assertTrue(CartItem.objects.filter(cart__customer=self.customer).exists())

    def test_sync_merges_quantity(self):
        product = self.make_product(self.active_status)
        variant = self.make_variant(product)
        self.sync_items([{"variant_id": variant.id, "quantity": 2}])
        response = self.sync_items([{"variant_id": variant.id, "quantity": 5}])
        cart = response.data["data"]["cart"]
        self.assertEqual(len(cart["items"]), 1)
        self.assertEqual(cart["items"][0]["quantity"], 5)
        self.assertEqual(CartItem.objects.count(), 1)

    def test_sync_reports_missing_variant(self):
        response = self.sync_items([{"variant_id": 999999, "quantity": 1}])
        removed = response.data["data"]["removed"]
        self.assertEqual(len(removed), 1)
        self.assertEqual(removed[0]["variant_id"], 999999)
        self.assertEqual(removed[0]["suggested_action"], "remove")
        self.assertIsNone(removed[0]["product_id"])
        self.assertEqual(response.data["data"]["cart"]["items"], [])

    def test_sync_reports_preorder_product(self):
        product = self.make_product(self.preorder_status)
        variant = self.make_variant(product)
        response = self.sync_items([{"variant_id": variant.id, "quantity": 1}])
        removed = response.data["data"]["removed"]
        self.assertEqual(len(removed), 1)
        self.assertEqual(removed[0]["product_id"], product.id)
        self.assertEqual(removed[0]["suggested_action"], "preorder")
        self.assertEqual(response.data["data"]["cart"]["items"], [])

    def test_sync_reports_inactive_product(self):
        product = self.make_product(self.active_status)
        variant = self.make_variant(product)
        product.status = self.inactive_status
        product.save(update_fields=["status"])
        response = self.sync_items([{"variant_id": variant.id, "quantity": 1}])
        removed = response.data["data"]["removed"]
        self.assertEqual(len(removed), 1)
        self.assertEqual(removed[0]["product_id"], product.id)
        self.assertEqual(removed[0]["suggested_action"], "wishlist")
        self.assertEqual(response.data["data"]["cart"]["items"], [])

    def test_sync_keeps_out_of_stock_active_product(self):
        product = self.make_product(self.active_status)
        variant = self.make_variant(product, available=0, quantity=0)
        response = self.sync_items([{"variant_id": variant.id, "quantity": 1}])
        self.assertEqual(response.data["data"]["removed"], [])
        cart = response.data["data"]["cart"]
        self.assertEqual(len(cart["items"]), 1)
        self.assertEqual(cart["items"][0]["status"], "out_of_stock")

    def test_sync_empty_items_returns_current_cart(self):
        response = self.sync_items([])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["removed"], [])
        self.assertEqual(response.data["data"]["cart"]["items"], [])

    # ─────────────── clear / merge / guest validation ───────────────

    def test_clear_returns_empty_full_cart(self):
        product = self.make_product(self.active_status)
        variant = self.make_variant(product)
        self.add_item(variant, quantity=2)

        response = self.client.post("/api/cart/clear")
        self.assertEqual(response.status_code, 200)
        data = response.data["data"]
        self.assertEqual(data["items"], [])
        self.assertEqual(data["totals"]["total_amount"], "0.00")
        self.assertFalse(CartItem.objects.filter(cart__customer=self.customer).exists())

    def test_merge_adds_guest_items(self):
        product = self.make_product(self.active_status)
        variant = self.make_variant(product)
        response = self.client.post(
            "/api/cart/merge",
            {"items": [{"variant_id": variant.id, "quantity": 3}]},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        cart = response.data["data"]["cart"]
        self.assertEqual(len(cart["items"]), 1)
        self.assertEqual(cart["items"][0]["quantity"], 3)
        self.assertTrue(CartItem.objects.filter(cart__customer=self.customer).exists())

    def test_merge_reports_unavailable_guest_items(self):
        response = self.client.post(
            "/api/cart/merge",
            {"items": [{"variant_id": 999999, "quantity": 1}]},
            format="json",
        )
        removed = response.data["data"]["removed"]
        self.assertEqual(len(removed), 1)
        self.assertEqual(removed[0]["variant_id"], 999999)
        self.assertEqual(removed[0]["suggested_action"], "remove")

    def test_guest_validate_single_item(self):
        product = self.make_product(self.active_status)
        variant = self.make_variant(product)
        anon = APIClient()
        response = anon.post(
            "/api/cart/validate",
            {"variant_id": variant.id, "quantity": 2},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        data = response.data["data"]
        self.assertTrue(data["valid"])
        self.assertEqual(data["variant_id"], variant.id)
        self.assertEqual(data["quantity"], 2)
        self.assertEqual(data["effective_price"], "100.00")
        self.assertFalse(data["quantity_capped"])

    def test_guest_validate_caps_quantity_to_inventory(self):
        product = self.make_product(self.active_status)
        variant = self.make_variant(product, available=3)
        anon = APIClient()
        response = anon.post(
            "/api/cart/validate",
            {"variant_id": variant.id, "quantity": 5},
            format="json",
        )
        data = response.data["data"]
        self.assertTrue(data["valid"])
        self.assertEqual(data["quantity"], 3)
        self.assertEqual(data["requested_quantity"], 5)
        self.assertTrue(data["quantity_capped"])

    def test_guest_validate_missing_variant_is_invalid(self):
        anon = APIClient()
        response = anon.post(
            "/api/cart/validate",
            {"variant_id": 999999, "quantity": 1},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        data = response.data["data"]
        self.assertFalse(data["valid"])
        self.assertEqual(data["status"], "variant_unavailable")
        self.assertEqual(data["suggested_action"], "remove")

    def test_guest_validate_does_not_persist_cart(self):
        product = self.make_product(self.active_status)
        variant = self.make_variant(product)
        anon = APIClient()
        anon.post(
            "/api/cart/validate",
            {"variant_id": variant.id, "quantity": 1},
            format="json",
        )
        self.assertEqual(Cart.objects.count(), 0)

    def test_guest_bulk_validate_items(self):
        product = self.make_product(self.active_status)
        variant = self.make_variant(product)
        anon = APIClient()
        response = anon.post(
            "/api/cart/validate-items",
            {
                "items": [
                    {"variant_id": variant.id, "quantity": 1},
                    {"variant_id": 999999, "quantity": 2},
                ]
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        items = response.data["data"]["items"]
        self.assertEqual(len(items), 2)
        self.assertTrue(items[0]["valid"])
        self.assertFalse(items[1]["valid"])
        self.assertEqual(Cart.objects.count(), 0)

    def test_anonymous_get_validate_rejected(self):
        anon = APIClient()
        self.assertEqual(anon.get("/api/cart/validate").status_code, 401)

    # ─────────────── address ───────────────

    def test_address_copied_from_saved_address(self):
        address = CustomerAddress.objects.create(
            customer=self.customer,
            title="Home",
            country=Country.objects.get(),
            state=State.objects.get(),
            city=self.city,
            postal_code="1234567890",
            address_line1="Main Street 1",
            is_default=True,
        )
        response = self.client.put(
            "/api/cart/address", {"saved_address_id": address.id}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        info = response.data["data"]
        self.assertEqual(info["country_name"], "Cart Country")
        self.assertEqual(info["address_line1"], "Main Street 1")
        self.assertEqual(info["receiver_name"], "Cart Owner")
        self.assertEqual(info["receiver_phone"], "09120000201")

    def test_address_saved_with_receiver_requires_both(self):
        product = self.make_product(self.preorder_status)
        variant = self.make_variant(product)
        item = self.add_item(variant)
        self.add_item(variant)
        item_id = item.data["data"]["items"][0]["id"]

        response = self.client.put(
            "/api/cart/address",
            {"saved_address_id": 12345, "receiver_name": "Only"}, format="json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("receiver_name", response.data["errors"])

    def test_address_manual_requires_full_address(self):
        response = self.client.put(
            "/api/cart/address",
            {"address_line1": "Only a line"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("address", response.data["errors"])

    def test_address_manual_hierarchy_validated(self):
        country = Country.objects.get(code="CC")
        wrong_state = State.objects.create(name="Other State", country=country)
        wrong_city = City.objects.create(name="Wrong City", state=wrong_state)
        response = self.client.put(
            "/api/cart/address",
            {
                "country_id": country.id,
                "state_id": State.objects.get(country=country, name="Cart State").id,
                "city_id": wrong_city.id,
                "postal_code": "123",
                "address_line1": "Street 2",
                "receiver_name": "Receiver",
                "receiver_phone": "09120000202",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("city_id", response.data["errors"])