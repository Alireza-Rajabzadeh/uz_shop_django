from decimal import Decimal

from django.db import transaction
from django.db.models import Count, Q
from django.utils.translation import gettext as _

from domains.catalog.models import ProductVariants
from domains.catalog.services import VariantService
from domains.inventory.services import InventoryService

from .address import AddressInfoService
from .models import Cart, CartItem


class CartService:
    class ValidationError(Exception):
        def __init__(self, errors):
            self.errors = errors
            super().__init__(str(errors))

    inventory_service = InventoryService()
    variant_service = VariantService()

    @staticmethod
    def get_or_create_cart(customer):
        return Cart.objects.get_or_create(customer=customer)[0]

    def list_admin(self, **filters):
        queryset = Cart.objects.select_related("customer").annotate(
            items_count=Count("items")
        )
        search = (filters.get("search") or "").strip()
        if search:
            queryset = queryset.filter(
                Q(customer__phone__icontains=search)
                | Q(customer__first_name__icontains=search)
                | Q(customer__last_name__icontains=search)
            )
        created_from = filters.get("created_from")
        if created_from:
            queryset = queryset.filter(created_at__date__gte=created_from)
        created_to = filters.get("created_to")
        if created_to:
            queryset = queryset.filter(created_at__date__lte=created_to)
        ordering = (filters.get("ordering") or "").strip()
        if ordering in {"id", "-id", "created_at", "-created_at", "items_count", "-items_count"}:
            queryset = queryset.order_by(ordering, "id")
        else:
            queryset = queryset.order_by("-created_at", "id")
        return queryset

    @staticmethod
    def _admin_cart_row(cart):
        customer = cart.customer
        return {
            "id": cart.id,
            "customer": {
                "id": customer.id,
                "name": f"{customer.first_name} {customer.last_name}".strip(),
                "phone": customer.phone,
                "customer_code": customer.customer_code,
            },
            "items_count": getattr(cart, "items_count", 0),
            "has_address": bool(cart.address_info),
            "created_at": cart.created_at.isoformat(),
            "updated_at": cart.updated_at.isoformat(),
        }

    def cart_payload_admin(self, cart_id):
        try:
            cart = Cart.objects.select_related("customer").get(id=cart_id)
        except Cart.DoesNotExist as exc:
            raise self.ValidationError({"cart": [_("Cart not found.")]}) from exc
        payload = self.describe_existing(cart)
        payload["customer"] = self._admin_cart_row(cart)["customer"]
        return payload

    # ───────────────────────── rendering ─────────────────────────

    def describe_cart(self, customer):
        cart = self.get_or_create_cart(customer)
        return self.describe_existing(cart)

    def describe_existing(self, cart):
        cart_items = list(cart.items.order_by("id"))
        payloads = [
            self._item_payload(item, variant)
            for item, variant in self._attach_variants(cart_items)
        ]
        subtotal = sum(Decimal(p["unit_price"]) * p["quantity"] for p in payloads)
        discount_amount = sum(Decimal(v) for v in (p["line_discount"] for p in payloads))
        shipping = Decimal("0.00")
        return {
            "id": cart.id,
            "address_info": cart.address_info,
            "items": payloads,
            "totals": {
                "subtotal": str(subtotal),
                "discount_amount": str(discount_amount),
                "shipping_amount": str(shipping),
                "total_amount": str(subtotal - discount_amount + shipping),
            },
            "cart_valid": bool(payloads) and all(p["valid"] for p in payloads),
        }

    def _attach_variants(self, items):
        variant_ids = [item.variant_id for item in items]
        queryset = (
            ProductVariants.objects.filter(pk__in=variant_ids)
            .select_related(
                "product", "inventory_strategy", "product__status", "product__brand"
            )
            .prefetch_related("selections__attribute", "selections__option")
        )
        variants = {
            row.id: row
            for row in self.inventory_service.annotate_variant_summaries(queryset)
        }
        return [(item, variants.get(item.variant_id)) for item in items]

    def _item_payload(self, item, variant):
        if variant is None:
            return self._empty_payload(item)
        product = variant.product
        product_status = product.status.name.casefold()
        enough_stock = variant.available_item_count >= item.quantity

        if product_status == "active" and enough_stock:
            status, action, valid, reason = "available", "none", True, ""
        elif product_status == "active":
            status, action, valid = "out_of_stock", "move_to_wishlist", False
            reason = _("Requested quantity exceeds available stock.")
        elif product_status == "preorder":
            status, action, valid, reason = "pre_orderable", "move_to_preorder", False, (
                "This product is now only available for pre-order."
            )
        else:
            status, action, valid = "variant_unavailable", "remove", False
            reason = "This item is no longer available for purchase."

        unit_price = variant.price
        effective_price = self.variant_service.calculate_discounted_price(variant)
        unit_discount = max(unit_price - effective_price, Decimal("0"))
        two_places = Decimal("0.01")
        effective_price = effective_price.quantize(two_places)
        unit_discount = unit_discount.quantize(two_places)
        return {
            "id": item.id,
            "variant_id": item.variant_id,
            "quantity": item.quantity,
            "product_id": product.id,
            "product_name": product.name,
            "product_status": product.status.name,
            "sku": variant.sku,
            "combination_key": variant.combination_key,
            "unit_price": str(unit_price),
            "discount_type": variant.discount_type,
            "discount_value": (
                str(variant.discount_value)
                if variant.discount_value is not None else None
            ),
            "effective_price": str(effective_price),
            "unit_discount_amount": str(unit_discount),
            "line_discount": str((unit_discount * item.quantity).quantize(two_places)),
            "line_total": str((effective_price * item.quantity).quantize(two_places)),
            "inventory_strategy": {
                "id": variant.inventory_strategy_id,
                "code": variant.inventory_strategy.code,
                "name": variant.inventory_strategy.name,
            },
            "available": variant.available_item_count,
            "selections": [
                {
                    "attribute_id": selection.attribute_id,
                    "attribute": selection.attribute.name,
                    "option_id": selection.option_id,
                    "option": selection.option.name,
                }
                for selection in variant.selections.all()
            ],
            "purchasable": product_status == "active",
            "valid": valid,
            "status": status,
            "reason": reason,
            "suggested_action": action,
        }

    @staticmethod
    def _empty_payload(item):
        return {
            "id": item.id,
            "variant_id": item.variant_id,
            "quantity": item.quantity,
            "product_id": None,
            "product_name": "",
            "product_status": "",
            "sku": "",
            "combination_key": "",
            "unit_price": "0.00",
            "discount_type": None,
            "discount_value": None,
            "effective_price": "0.00",
            "unit_discount_amount": "0.00",
            "line_discount": "0.00",
            "line_total": "0.00",
            "inventory_strategy": None,
            "available": 0,
            "selections": [],
            "purchasable": False,
            "valid": False,
            "status": "variant_unavailable",
            "reason": "This item is no longer available.",
            "suggested_action": "remove",
        }

    def _render_item(self, item):
        attached = self._attach_variants([item])
        return self._item_payload(item, dict(attached).get(item))

    # ───────────────────────── mutations ─────────────────────────

    @transaction.atomic
    def add(self, customer, variant_id, quantity=1):
        if quantity < 1:
            raise self.ValidationError({"quantity": [_("Quantity must be greater than zero.")]})
        try:
            variant = ProductVariants.objects.get(id=variant_id)
        except ProductVariants.DoesNotExist as exc:
            raise self.ValidationError({"variant_id": [_("Variant not found.")]}) from exc
        cart = self.get_or_create_cart(customer)
        item, _created = CartItem.objects.get_or_create(
            cart=cart, variant=variant, defaults={"quantity": quantity}
        )
        if not _created:
            item.quantity = quantity
            item.save()
        return self._render_item(item)

    @transaction.atomic
    def update_quantity(self, customer, item_id, quantity):
        if quantity < 1:
            raise self.ValidationError({"quantity": [_("Quantity must be greater than zero.")]})
        item = self._get_item(customer, item_id)
        item.quantity = quantity
        item.save()
        return self._render_item(item)

    @transaction.atomic
    def remove(self, customer, item_id):
        item = self._get_item(customer, item_id)
        item.delete()

    def set_address(self, customer, address_data):
        info = AddressInfoService().build(customer, address_data)
        cart = self.get_or_create_cart(customer)
        cart.address_info = info
        cart.save(update_fields=["address_info", "updated_at"])
        return info

    @transaction.atomic
    def move_to_wishlist(self, customer, item_id):
        item = self._get_item(customer, item_id)
        product_id = item.variant.product_id
        from domains.wishlist.services import WishlistService

        wishlist = WishlistService()
        if not wishlist.exists(customer, product_id):
            wishlist.add(customer, product_id)
        item.delete()
        return {"product_id": product_id, "moved_to": "wishlist"}

    @transaction.atomic
    def move_to_preorder(self, customer, item_id):
        item = self._get_item(customer, item_id)
        product = item.variant.product
        if product.status.name.casefold() != "preorder":
            raise self.ValidationError({
                "product": [_("This product is not available for pre-order.")]
            })
        from domains.preorder.services import PreOrderService

        preorder = PreOrderService()
        if not preorder.exists(customer, product.id):
            preorder.add(customer, product.id)
        item.delete()
        return {"product_id": product.id, "moved_to": "preorder"}

    def get_item(self, customer, item_id):
        return self._get_item(customer, item_id)

    def _get_item(self, customer, item_id):
        try:
            return CartItem.objects.select_related("variant", "variant__product").get(
                id=item_id, cart__customer=customer
            )
        except CartItem.DoesNotExist as exc:
            raise self.ValidationError({
                "item": [_("Cart item not found.")]
            }) from exc