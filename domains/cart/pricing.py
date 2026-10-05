"""Price, stock and availability reads shared by every checkout path.

A shop cart, a shop order, a marketplace cart and a marketplace order all ask
the same questions about a variant: which offer applies, what does it cost
after discount, how much stock is left, and may it still be bought. Each
answer lives here once. A flow decides only which rows to load and what to do
with the result, so a change to pricing or availability rules cannot drift
between the two flows.
"""

from decimal import Decimal

from django.db.models import Prefetch
from django.utils.translation import gettext as _

from domains.catalog.models import ProductFile, ProductVariants
from domains.catalog.services import VariantService
from domains.inventory.services import InventoryService

TWO_PLACES = Decimal("0.01")
ZERO = Decimal("0")

_inventory_service = InventoryService()
_variant_service = VariantService()


def storefront_media():
    """Product images that are eligible for a cart or order thumbnail."""
    return ProductFile.objects.filter(
        file__file_type="image",
        file__status__name="available",
        file__deleted_at__isnull=True,
    ).select_related("file").order_by("-is_primary", "position", "id")


def attach_offers(variants, *, business=None):
    """Attach ``_business_offers`` / ``_business_offer`` to each variant.

    Pricing is read from ``_business_offer``, so every flow that touches a
    price must attach first. ``variants`` must be re-iterable. ``business``
    scopes the lookup for the marketplace flow; leaving it unset reads the
    singleton business's offers, which is what the shop flow means.
    """
    from domains.marketplace.models import BusinessOffer

    variant_ids = [variant.id for variant in variants]
    queryset = BusinessOffer.objects.filter(
        variant_id__in=variant_ids, is_active=True
    ).select_related("business")
    if business is not None:
        queryset = queryset.filter(business=business)
    offer_map = {}
    for offer in queryset:
        offer_map.setdefault(offer.variant_id, []).append(offer)
    for variant in variants:
        attached = offer_map.get(variant.id, [])
        variant._business_offers = attached
        variant._business_offer = attached[0] if attached else None


def annotated_variants(variant_ids):
    """Stock-annotated variant rows keyed by variant id."""
    rows = ProductVariants.objects.filter(id__in=list(variant_ids))
    return {
        row.id: row
        for row in _inventory_service.annotate_variant_summaries(rows)
    }


def load_variants(variant_ids):
    """Variant rows loaded for rendering: product, selections and media."""
    queryset = (
        ProductVariants.objects.filter(pk__in=list(variant_ids))
        .select_related("product", "product__status", "product__brand")
        .prefetch_related(
            "selections__attribute",
            "selections__option",
            Prefetch(
                "product__product_files",
                queryset=storefront_media(),
                to_attr="storefront_media",
            ),
        )
    )
    return {
        row.id: row
        for row in _inventory_service.annotate_variant_summaries(queryset)
    }


def summary_map(variants):
    """Stock summaries for already-loaded variants, keyed by variant id."""
    return annotated_variants([variant.id for variant in variants if variant is not None])


def _read_offer_price(variant):
    """Return ``(offer, unit_price, effective_price)`` before any rounding.

    The order flow rounds first and then differences, while the cart flow
    differences and then rounds, so the two renderings below each keep their
    own arithmetic. They still agree on where the number comes from.
    """
    offer = getattr(variant, "_business_offer", None)
    unit_price = getattr(offer, "price", None) or ZERO
    effective_price = _variant_service.calculate_discounted_price(variant, offer)
    return offer, unit_price, effective_price


def variant_pricing(variant):
    """Price payload for one variant after its discount, as decimal strings."""
    offer, unit_price, effective_price = _read_offer_price(variant)
    unit_discount = max(unit_price - effective_price, ZERO)
    return {
        "unit_price": str(unit_price),
        "discount_type": getattr(offer, "discount_type", None),
        "discount_value": (
            str(offer.discount_value)
            if offer and offer.discount_value is not None else None
        ),
        "effective_price": str(effective_price.quantize(TWO_PLACES)),
        "unit_discount_amount": str(unit_discount.quantize(TWO_PLACES)),
    }


def line_snapshot(variant, quantity):
    """Order-item price snapshot taken when the order line is created.

    This is historical truth: totals are always read back from the order row,
    never recomputed from the offer as it stands later.
    """
    offer, unit_price, effective_price = _read_offer_price(variant)
    price = unit_price.quantize(TWO_PLACES)
    effective = effective_price.quantize(TWO_PLACES)
    unit_discount = max(price - effective, ZERO).quantize(TWO_PLACES)
    return {
        "unit_price": price,
        "discount_type": getattr(offer, "discount_type", None),
        "discount_value": getattr(offer, "discount_value", None),
        "unit_discount": unit_discount,
        "line_discount": (unit_discount * quantity).quantize(TWO_PLACES),
        "line_total": (effective * quantity).quantize(TWO_PLACES),
    }


def validate_item(item, summary):
    """Is this cart line still buyable at the requested quantity?

    ``item`` is any row with ``variant`` and ``quantity``; ``summary`` comes
    from :func:`summary_map`. Returns ``(ok, message)``.
    """
    variant = item.variant
    if variant is None:
        return False, _("Item is no longer available.")
    product_status = variant.product.status.name.casefold()
    if product_status != "active":
        return False, _("Item %(sku)s is not available for purchase.") % {
            "sku": variant.sku
        }
    summary_row = summary.get(variant.id)
    available = summary_row.available_item_count if summary_row else 0
    if available < item.quantity:
        return False, _("Item %(sku)s does not have enough stock.") % {
            "sku": variant.sku
        }
    return True, ""


def availability(product_status, *, enough_stock, quantity_capped=False, quantity=None):
    """Map a product status plus stock to the cart item state machine.

    Returns ``(status, action, valid, reason)`` — the four fields every cart
    payload exposes so a client knows whether to keep a line, trim it, move it
    to the wishlist or drop it.
    """
    status_name = (product_status or "").casefold()
    if status_name == "active" and enough_stock:
        reason = (
            _("Requested quantity exceeds available stock; reduced to {count}.").format(
                count=quantity
            )
            if quantity_capped else ""
        )
        return "available", "none", True, reason
    if status_name == "active":
        return (
            "out_of_stock",
            "move_to_wishlist",
            False,
            _("Requested quantity exceeds available stock."),
        )
    if status_name == "preorder":
        return (
            "pre_orderable",
            "move_to_preorder",
            False,
            _("This product is now only available for pre-order."),
        )
    return (
        "variant_unavailable",
        "remove",
        False,
        _("This item is no longer available for purchase."),
    )
