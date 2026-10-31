from decimal import Decimal

from django.db import transaction
from django.db.models import Count, Q
from django.utils.translation import gettext as _

from domains.catalog.models import ProductFile, ProductVariants
from domains.files.services import FileService
from domains.inventory.services import InventoryService
from domains.shipment.services import ShipmentCalculationService

from .address import AddressInfoService
from .models import Cart, CartItem
from .pricing import (
    apply_pinned_offers,
    attach_offers,
    availability,
    load_variants,
    variant_pricing,
)


class BaseCartService:
    """Cart rules shared by the shop cart and the marketplace cart.

    Only the tables differ between the two flows, so the behaviour lives here
    once and each flow supplies its own ``cart_model`` / ``item_model`` plus
    any offer scoping it needs. A subclass must not reimplement a rule; it
    declares which rows it works on.
    """

    class ValidationError(Exception):
        def __init__(self, errors):
            self.errors = errors
            super().__init__(str(errors))

    cart_model = None
    item_model = None
    offer_field = None

    inventory_service = InventoryService()
    shipment_service = ShipmentCalculationService()

    @classmethod
    def get_or_create_cart(cls, customer):
        return cls.cart_model.objects.get_or_create(customer=customer)[0]

    def list_admin(self, **filters):
        queryset = self.cart_model.objects.select_related("customer").annotate(
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
            cart = self.cart_model.objects.select_related("customer").get(id=cart_id)
        except self.cart_model.DoesNotExist as exc:
            raise self.ValidationError({"cart": [_("Cart not found.")]}) from exc
        payload = self.describe_existing(cart)
        payload["customer"] = self._admin_cart_row(cart)["customer"]
        return payload

    # ───────────────────────── rendering ─────────────────────────

    def describe_cart(self, customer, *, include_shipping=False):
        cart = self.get_or_create_cart(customer)
        return self.describe_existing(cart, include_shipping=include_shipping)

    def describe_existing(self, cart, *, include_shipping=False):
        cart_items = list(cart.items.order_by("id"))
        payloads = [
            self._item_payload(item, variant)
            for item, variant in self._attach_variants(cart_items)
        ]
        seller_groups = self._seller_groups(
            payloads, cart, include_shipping=include_shipping
        )
        two_places = Decimal("0.01")
        subtotal = sum(
            (Decimal(group["totals"]["subtotal"]) for group in seller_groups),
            Decimal("0.00"),
        )
        discount_amount = sum(
            (Decimal(group["totals"]["discount_amount"]) for group in seller_groups),
            Decimal("0.00"),
        )
        shipping_amount = sum(
            (
                Decimal(group["totals"]["shipping_amount"])
                for group in seller_groups
                if "shipping_amount" in group["totals"]
            ),
            Decimal("0.00"),
        )
        totals = {
            "subtotal": str(subtotal.quantize(two_places)),
            "discount_amount": str(discount_amount.quantize(two_places)),
            "total_amount": str(
                (subtotal - discount_amount + shipping_amount).quantize(
                    two_places
                )
            ),
        }
        if include_shipping:
            totals["shipping_amount"] = str(shipping_amount.quantize(two_places))
            totals["shipment"] = {
                "original_price": str(
                    sum(
                        (
                            Decimal(
                                group["totals"]["shipment"]["original_price"]
                            )
                            for group in seller_groups
                        ),
                        Decimal("0.00"),
                    ).quantize(two_places)
                ),
                "final_price": str(shipping_amount.quantize(two_places)),
            }
        return {
            "id": cart.id,
            "address_info": cart.address_info,
            "items": payloads,
            "seller_groups": seller_groups,
            "totals": totals,
            "cart_valid": bool(payloads) and all(p["valid"] for p in payloads),
        }

    def _seller_groups(self, payloads, cart, *, include_shipping=False):
        """Split the basket into the independent seller checkouts it implies.

        A cart can hold items from several businesses, but an order belongs to
        exactly one. The group tells the storefront what it may check out now
        and which seller is still missing a payment method.
        """
        grouped = {}
        for payload in payloads:
            business = payload.get("business")
            key = business["id"] if business else "unknown"
            grouped.setdefault(key, {"business": business, "items": []})
            grouped[key]["items"].append(payload)

        groups = []
        for group in grouped.values():
            business = group["business"]
            items = group["items"]
            subtotal = sum(
                Decimal(item["unit_price"]) * item["quantity"] for item in items
            )
            discount_amount = sum(
                Decimal(item["line_discount"]) for item in items
            )
            shipping_amount = Decimal("0.00")
            shipment_payload = None
            if include_shipping:
                shipment = self.shipment_service.calculate(cart)
                shipping_amount = shipment.final_price
                shipment_payload = shipment.payload()
            valid = all(item["valid"] for item in items)
            payment_available = bool(
                business and self._business_payment_available(business["id"])
            )
            if not valid:
                checkout_status = "unavailable"
            elif business is None:
                checkout_status = "unavailable"
            elif not payment_available:
                checkout_status = "awaiting_payment_method"
            else:
                checkout_status = "ready"
            totals = {
                "subtotal": str(subtotal),
                "discount_amount": str(discount_amount),
                "total_amount": str(
                    subtotal - discount_amount + shipping_amount
                ),
            }
            if include_shipping:
                totals["shipping_amount"] = str(shipping_amount)
                totals["shipment"] = shipment_payload
            groups.append({
                "business": business,
                "item_ids": [item["id"] for item in items],
                "valid": valid,
                "payment_available": payment_available,
                "checkout_status": checkout_status,
                "totals": totals,
            })
        return groups

    @staticmethod
    def _business_payment_available(business_id):
        from domains.business_payments.services import BusinessPaymentService

        return BusinessPaymentService.has_available_channel(business_id=business_id)

    def _attach_variants(self, items):
        variant_ids = [item.variant_id for item in items]
        variants = load_variants(variant_ids)
        self._attach_offers(variants.values())
        attached = [(item, variants.get(item.variant_id)) for item in items]
        self._apply_pinned_offers(attached)
        return attached

    def _attach_offers(self, variants):
        """Scope the offers a cart line is priced from.

        A flow that already knows which business it is shopping overrides
        this; the shop flow searches every active offer and selects the best
        in-stock one.
        """
        attach_offers(variants)

    def _resolve_offer(self, variant, offer_id):
        """Return the active offer a shop line may pin, or raise on a bad id."""
        if offer_id is None or not self.offer_field:
            return None
        from domains.marketplace.models import BusinessOffer

        try:
            return BusinessOffer.objects.get(
                id=offer_id,
                variant=variant,
                is_active=True,
            )
        except BusinessOffer.DoesNotExist as exc:
            raise self.ValidationError({
                "offer_id": [_("Selected seller is not available for this variant.")]
            }) from exc

    def _optional_offer(self, variant, offer_id):
        """Best-effort variant of :meth:`_resolve_offer` for cart syncing.

        A guest cart can outlive the seller it pinned. Merging the rest of the
        line is better than rejecting the whole cart at sign-in, so an invalid
        pin falls back to the automatic selection.
        """
        try:
            return self._resolve_offer(variant, offer_id)
        except self.ValidationError:
            return None

    def _apply_pinned_offers(self, attached):
        from domains.marketplace.offer_selection import select_offer

        for item, variant in attached:
            offer_id = getattr(item, "offer_id", None)
            if variant is None or offer_id is None:
                continue
            select_offer(variant, offer_id)

    def _product_thumbnail(self, product):
        media = getattr(product, "storefront_media", None)
        if media is None:
            media = list(
                ProductFile.objects.filter(
                    product=product,
                    file__file_type="image",
                    file__status__name="available",
                    file__deleted_at__isnull=True,
                )
                .select_related("file")
                .order_by("-is_primary", "position", "id")[:1]
            )
        if not media:
            return None
        try:
            return FileService().url(media[0].file)
        except FileService.Error:
            return None

    def _business_payload(self, variant):
        """The seller a cart line is priced from, as public storefront data."""
        offer = getattr(variant, "_business_offer", None)
        if offer is None:
            return None
        from domains.marketplace.offer_selection import public_business_payload

        return public_business_payload(offer.business)

    def _item_payload(self, item, variant):
        if variant is None:
            return self._empty_payload(item)
        product = variant.product
        product_status = product.status.name.casefold()
        available = getattr(
            variant, "_business_offer_available", variant.available_item_count
        )
        enough_stock = available >= item.quantity
        status, action, valid, reason = availability(
            product_status, enough_stock=enough_stock
        )

        two_places = Decimal("0.01")
        pricing = variant_pricing(variant)
        effective_price = Decimal(pricing["effective_price"])
        unit_discount = Decimal(pricing["unit_discount_amount"])
        return {
            "id": item.id,
            "variant_id": item.variant_id,
            "offer_id": getattr(item, "offer_id", None),
            "business": self._business_payload(variant),
            "quantity": item.quantity,
            "product_id": product.id,
            "product_name": product.name,
            "product_thumbnail": self._product_thumbnail(product),
            "product_status": product.status.name,
            "sku": variant.sku,
            "combination_key": variant.combination_key,
            **pricing,
            "line_discount": str((unit_discount * item.quantity).quantize(two_places)),
            "line_total": str((effective_price * item.quantity).quantize(two_places)),
            "available": available,
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
    def _variant_pricing(variant):
        # Kept as a seam for subclasses that render their own payloads.
        return variant_pricing(variant)

    def _variant_payload(self, variant, quantity, *, cap_quantity=False):
        product = variant.product
        product_status = product.status.name.casefold()
        available = getattr(
            variant, "_business_offer_available", variant.available_item_count
        )
        requested_quantity = quantity
        quantity_capped = False

        if cap_quantity and product_status == "active" and 0 < available < quantity:
            quantity = available
            quantity_capped = True
        enough_stock = available >= quantity
        status, action, valid, reason = availability(
            product_status,
            enough_stock=enough_stock,
            quantity_capped=quantity_capped,
            quantity=quantity,
        )

        return {
            "variant_id": variant.id,
            "offer_id": getattr(getattr(variant, "_business_offer", None), "id", None),
            "business": self._business_payload(variant),
            "requested_quantity": requested_quantity,
            "quantity": quantity,
            "quantity_capped": quantity_capped,
            "product_id": product.id,
            "product_name": product.name,
            "product_thumbnail": self._product_thumbnail(product),
            "product_status": product.status.name,
            "sku": variant.sku,
            "combination_key": variant.combination_key,
            **variant_pricing(variant),
            "available": available,
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
    def _unavailable_payload(variant_id, quantity):
        return {
            "variant_id": variant_id,
            "offer_id": None,
            "business": None,
            "requested_quantity": quantity,
            "quantity": 0,
            "quantity_capped": False,
            "product_id": None,
            "product_name": "",
            "product_thumbnail": None,
            "product_status": "",
            "sku": "",
            "combination_key": "",
            "unit_price": "0.00",
            "discount_type": None,
            "discount_value": None,
            "effective_price": "0.00",
            "unit_discount_amount": "0.00",
            "available": 0,
            "selections": [],
            "purchasable": False,
            "valid": False,
            "status": "variant_unavailable",
            "reason": _("This item is no longer available."),
            "suggested_action": "remove",
        }

    @staticmethod
    def _empty_payload(item):
        return {
            "id": item.id,
            "variant_id": item.variant_id,
            "offer_id": getattr(item, "offer_id", None),
            "business": None,
            "quantity": item.quantity,
            "product_id": None,
            "product_name": "",
            "product_thumbnail": None,
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
    def add(self, customer, variant_id, quantity=1, offer_id=None):
        if quantity < 1:
            raise self.ValidationError({"quantity": [_("Quantity must be greater than zero.")]})
        try:
            variant = ProductVariants.objects.get(id=variant_id)
        except ProductVariants.DoesNotExist as exc:
            raise self.ValidationError({"variant_id": [_("Variant not found.")]}) from exc
        offer = self._resolve_offer(variant, offer_id)
        cart = self.get_or_create_cart(customer)
        item, created = self.item_model.objects.get_or_create(
            cart=cart, variant=variant, defaults={"quantity": quantity}
        )
        if not created:
            item.quantity = quantity
        if offer is not None:
            setattr(item, self.offer_field, offer)
        item.save()
        return self._render_item(item)

    @transaction.atomic
    def sync(self, customer, items):
        """Reconcile the client's local cart against the catalog.

        Variants that still exist are kept (added/merged into the server cart).
        Items that no longer exist or can no longer be bought in the cart are
        reported back with a suggested action the client can follow up on.
        """
        cart = self.get_or_create_cart(customer)
        variant_ids = [entry["variant_id"] for entry in items]
        variants = {
            row.id: row
            for row in ProductVariants.objects.filter(pk__in=variant_ids).select_related(
                "product", "product__status"
            )
        }
        removed = []
        for entry in items:
            variant_id = entry["variant_id"]
            quantity = entry.get("quantity", 1)
            variant = variants.get(variant_id)
            if variant is None:
                removed.append({
                    "variant_id": variant_id,
                    "product_id": None,
                    "product_name": "",
                    "reason": _("This item no longer exists."),
                    "suggested_action": "remove",
                })
                continue
            product = variant.product
            product_status = product.status.name.casefold()
            if product_status == "preorder":
                removed.append({
                    "variant_id": variant_id,
                    "product_id": product.id,
                    "product_name": product.name,
                    "reason": _("This product is now only available for pre-order."),
                    "suggested_action": "preorder",
                })
                continue
            if product_status != "active":
                removed.append({
                    "variant_id": variant_id,
                    "product_id": product.id,
                    "product_name": product.name,
                    "reason": _("This item is no longer available for purchase."),
                    "suggested_action": "wishlist",
                })
                continue
            offer = self._optional_offer(variant, entry.get("offer_id"))
            item, _created = self.item_model.objects.get_or_create(
                cart=cart, variant=variant, defaults={"quantity": quantity}
            )
            if not _created:
                item.quantity = quantity
            if offer is not None:
                setattr(item, self.offer_field, offer)
            item.save()
        return {
            "cart": self.describe_existing(cart),
            "removed": removed,
        }

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

    def validate_variant(self, variant_id, quantity=1, offer_id=None):
        """Validate a variant and requested quantity without a cart.

        Used by the guest flow; nothing is persisted.
        """
        if quantity < 1:
            raise self.ValidationError({"quantity": [_("Quantity must be greater than zero.")]})
        try:
            variant = ProductVariants.objects.select_related(
                "product", "product__status"
            ).prefetch_related("selections__attribute", "selections__option").get(id=variant_id)
        except ProductVariants.DoesNotExist:
            return self._unavailable_payload(variant_id, quantity)
        queryset = ProductVariants.objects.filter(pk=variant.id).select_related(
            "product", "product__status"
        ).prefetch_related("selections__attribute", "selections__option")
        variant = self.inventory_service.annotate_variant_summaries(queryset)[0]
        self._attach_offers([variant])
        if offer_id is not None and self.offer_field:
            from domains.marketplace.offer_selection import select_offer

            if select_offer(variant, offer_id) is None:
                return self._unavailable_payload(variant_id, quantity)
        return self._variant_payload(variant, quantity, cap_quantity=True)

    def validate_items(self, items):
        return [
            self.validate_variant(
                entry["variant_id"],
                entry.get("quantity", 1),
                entry.get("offer_id"),
            )
            for entry in items
        ]

    @transaction.atomic
    def clear(self, customer):
        self.item_model.objects.filter(cart__customer=customer).delete()

    def merge(self, customer, items):
        """Merge a guest cart into the customer's persisted cart.

        Delegates to the same reconciling rules used by sync: valid purchasable
        variants are added/merged, and items that can no longer be bought are
        reported back so the client can follow up.
        """
        return self.sync(customer, items)

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
            return self.item_model.objects.select_related(
                "variant", "variant__product"
            ).get(id=item_id, cart__customer=customer)
        except self.item_model.DoesNotExist as exc:
            raise self.ValidationError({
                "item": [_("Cart item not found.")]
            }) from exc


class CartService(BaseCartService):
    """The shop cart: one basket per customer, priced by the selected offer."""

    cart_model = Cart
    item_model = CartItem
    offer_field = "offer"
