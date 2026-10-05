"""Turn a validated cart into an order — the same sequence for both flows.

Load the lines, check they are still buyable, snapshot each line's price,
hold the stock, total the order, clear the basket. The shop flow and the
marketplace flow differ only in which rows they write and which fields only
one of them has, so every step that does not involve a model choice lives
here. A flow supplies its models and a few small fields; it must not restate
a step.
"""

from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from domains.catalog.models import ProductFile
from domains.files.services import FileService
from domains.inventory.services import InventoryService
from domains.shipment.services import ShipmentCalculationService

from .pricing import attach_offers, line_snapshot, summary_map, validate_item


class CheckoutError(Exception):
    """Carries a field-to-message mapping up to the view layer."""

    def __init__(self, errors):
        self.errors = errors
        super().__init__(str(errors))


class BaseCheckoutService:
    """Creates an order from a cart. A subclass chooses the tables.

    Required on a subclass:

    ``order_model`` / ``item_model`` / ``reservation_model``
        The rows this flow writes.
    ``status_model``
        The status vocabulary the flow's orders point at.
    ``cart_service()``
        Which basket to read.

    Overridable:

    ``_has_payment_channel()``
        When an order may be created at all; each flow checks its own
        registry of channels.
    ``_order_extra_fields(items)``
        Fields only this flow's order carries, plus any rule that only
        applies because of them.
    ``_item_extra_fields(variant)``
        Fields only this flow's line carries.
    ``_reservation_extra_fields(entry)``
        Fields only this flow's hold carries.
    """

    STATUS_PAYMENT_PENDING = "payment_pending"

    ValidationError = CheckoutError

    order_model = None
    item_model = None
    reservation_model = None
    status_model = None

    two_places = Decimal("0.01")
    shipment_service = ShipmentCalculationService()
    # Single source of truth for moving stock; this service only decides when.
    inventory_service = InventoryService()

    # ───────────────────────── hooks ─────────────────────────

    def cart_service(self):
        raise NotImplementedError("A checkout flow must say which basket it reads.")

    def _has_payment_channel(self):
        """May an order be created at all?"""
        return True

    def _order_extra_fields(self, items):
        return {}

    def _item_extra_fields(self, variant):
        return {}

    def _reservation_extra_fields(self, entry):
        return {}

    # ───────────────────────── shared reads ─────────────────────────

    def _status(self, name):
        return self.status_model.objects.filter(name=name).first()

    def _variant_info_snapshot(self, variant):
        """The product detail a line was sold with.

        Snapshotted onto the order so it still describes itself if the
        variant is later edited or removed.
        """
        return {
            "variant_id": variant.id,
            "sku": variant.sku,
            "product_id": variant.product_id,
            "product_name": variant.product.name,
            "product_slug": variant.product.slug,
            "product_image": self._product_thumbnails(
                [variant.product_id]
            ).get(variant.product_id),
            "combination_key": variant.combination_key,
            "selections": [
                {
                    "attribute_id": selection.attribute_id,
                    "attribute": selection.attribute.name,
                    "option_id": selection.option_id,
                    "option": selection.option.name,
                }
                for selection in variant.selections.all()
            ],
        }

    def _product_thumbnails(self, product_ids):
        ids = {pid for pid in product_ids if pid is not None}
        cache = getattr(self, "_thumbnail_urls", {})
        missing = sorted(ids - cache.keys())
        if missing:
            preferred = {}
            fallback = {}
            rows = (
                ProductFile.objects.filter(
                    product_id__in=missing,
                    role__in=[ProductFile.Role.THUMBNAIL, ProductFile.Role.GALLERY],
                )
                .select_related("file")
                .order_by("product_id", "position", "id")
            )
            file_service = FileService()
            for row in rows:
                if row.role == ProductFile.Role.THUMBNAIL:
                    preferred.setdefault(row.product_id, row)
                else:
                    fallback.setdefault(row.product_id, row)
            for product_id in missing:
                row = preferred.get(product_id) or fallback.get(product_id)
                url = None
                if row is not None:
                    try:
                        url = file_service.url(row.file)
                    except FileService.Error:
                        url = None
                cache[product_id] = url
            self._thumbnail_urls = cache
        return cache

    def _load_lines(self, cart):
        return list(
            cart.items.select_related(
                "variant",
                "variant__product",
                "variant__product__status",
            )
            .prefetch_related(
                "variant__selections__attribute", "variant__selections__option"
            )
            .order_by("id")
        )

    def _validate_lines(self, items):
        attach_offers([item.variant for item in items])
        summary = summary_map([item.variant for item in items])
        errors = []
        for item in items:
            ok, message = validate_item(item, summary)
            if not ok:
                errors.append(message)
        if errors:
            raise self.ValidationError({"items": errors})

    def _reserve_line(self, variant, quantity):
        """Hold stock for one order line through the shared inventory service.

        The inventory service owns the reservation algorithm; this only maps
        its failure shape onto the contract this service exposes to views.
        """
        try:
            return self.inventory_service.reserve_variant_stock(variant, quantity)
        except InventoryService.ValidationError as exc:
            raise self.ValidationError(exc.errors) from exc

    # ───────────────────────── the sequence ─────────────────────────

    @transaction.atomic
    def checkout_from_cart(self, customer):
        cart = self.cart_service().get_or_create_cart(customer)
        if not cart.address_info:
            raise self.ValidationError({
                "address": [_("Set a delivery address before checkout.")]
            })
        if not self._has_payment_channel():
            raise self.ValidationError({
                "payment": [_("No active payment channel is available.")]
            })
        items = self._load_lines(cart)
        if not items:
            raise self.ValidationError({"cart": [_("The cart is empty.")]})
        self._validate_lines(items)

        order = self.order_model.objects.create(
            customer=customer,
            status=self._status(self.STATUS_PAYMENT_PENDING),
            address_info=cart.address_info,
            subtotal=Decimal("0.00"),
            discount_amount=Decimal("0.00"),
            shipping_original_amount=Decimal("0.00"),
            shipping_amount=Decimal("0.00"),
            total_amount=Decimal("0.00"),
            **self._order_extra_fields(items),
        )

        subtotal = Decimal("0.00")
        discount_total = Decimal("0.00")
        for item in items:
            variant = item.variant
            line = line_snapshot(variant, item.quantity)
            reservations = self._reserve_line(variant, item.quantity)
            self._write_line(order, variant, line, item, reservations)
            subtotal += line["unit_price"] * item.quantity
            discount_total += line["line_discount"]

        order.subtotal = subtotal.quantize(self.two_places)
        order.discount_amount = discount_total.quantize(self.two_places)
        shipment = self.shipment_service.calculate(order)
        order.shipping_original_amount = shipment.original_price
        order.shipping_amount = shipment.final_price
        order.total_amount = (
            subtotal - discount_total + shipment.final_price
        ).quantize(self.two_places)
        order.reservation_expires_at = timezone.now() + timedelta(
            minutes=settings.ORDER_RESERVATION_MINUTES
        )
        order.save(update_fields=[
            "subtotal",
            "discount_amount",
            "shipping_original_amount",
            "shipping_amount",
            "total_amount",
            "reservation_expires_at",
        ])

        for item in items:
            item.delete()
        return order

    def _write_line(self, order, variant, line, cart_item, reservations):
        order_item = self.item_model.objects.create(
            order=order,
            variant=variant,
            sku=variant.sku,
            quantity=cart_item.quantity,
            unit_price=line["unit_price"],
            discount_type=line["discount_type"],
            discount_value=line["discount_value"],
            discount_amount=line["line_discount"],
            final_price=line["line_total"],
            variant_info=self._variant_info_snapshot(variant),
            **self._item_extra_fields(variant),
        )
        for entry in reservations:
            self.reservation_model.objects.create(
                order_item=order_item,
                quantity=entry.quantity,
                linked_inventory=entry.inventory,
                linked_unit=entry.unit,
                **self._reservation_extra_fields(entry),
            )
        return order_item
