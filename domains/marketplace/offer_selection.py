"""Deterministic selection of the offer a storefront read should use.

A variant can be listed by many businesses. Product detail, the cart and
checkout all have to agree on which offer they are talking about, otherwise a
customer can be shown one price, charged another, and have stock reserved from
a third business. Every read therefore attaches the offers in the same order:
in-stock offers first, then the lowest effective price, then stable tie-break
fields.
"""

from django.db.models import Sum

from .models import BusinessOffer
from .services import MarketplacePricingService


def _availability_by_offer(variant_ids):
    """Available units for every ``(variant, business)`` pair in one query."""
    from domains.inventory.models import Inventory

    rows = (
        Inventory.objects.filter(variant_id__in=variant_ids)
        .values("variant_id", "business_id")
        .annotate(sellable=Sum("sellable"), reserved=Sum("reserved"))
    )
    return {
        (row["variant_id"], row["business_id"]): (row["sellable"] or 0)
        - (row["reserved"] or 0)
        for row in rows
    }


def _offer_sort_key(offer, availability):
    available = availability.get((offer.variant_id, offer.business_id), 0)
    return (
        0 if available > 0 else 1,
        MarketplacePricingService.calculate_discounted_price(offer),
        offer.business_id,
        offer.id,
    )


PREVIEW_LIMIT = 5


def public_business_payload(business):
    """The seller fields a storefront may expose.

    The admin business serializer is deliberately not reused here: it carries
    contact, financial and lifecycle data the public catalog has no business
    returning.
    """
    from domains.files.services import FileService

    logo = business.light_logo or business.dark_logo
    logo_url = None
    if logo is not None:
        try:
            logo_url = FileService().url(logo)
        except FileService.Error:
            logo_url = None
    return {
        "id": business.id,
        "name": business.display_name,
        "logo_url": logo_url,
        "availability_status": business.availability_status,
    }


def public_offer_payload(offer):
    """Serializable marketplace offer for storefront reads."""
    available = getattr(offer, "_available", 0)
    return {
        "id": offer.id,
        "business": public_business_payload(offer.business),
        "price": offer.price,
        "effective_price": MarketplacePricingService.calculate_discounted_price(offer),
        "discount_type": offer.discount_type,
        "discount_value": offer.discount_value,
        "available": available,
        "in_stock": available > 0,
    }


def offer_summary(offers):
    """Seller counts for one product or variant."""
    offers = list(offers)
    return {
        "total": len(offers),
        "in_stock": sum(1 for offer in offers if getattr(offer, "_available", 0) > 0),
        "seller_count": len({offer.business_id for offer in offers}),
        "in_stock_seller_count": len({
            offer.business_id
            for offer in offers
            if getattr(offer, "_available", 0) > 0
        }),
    }


def select_offer(variant, offer_id):
    """Make one already-attached offer the selected one for a variant.

    Cart lines can pin the seller the customer chose on the product page.
    The offer must be present in ``_business_offers`` (an active offer for the
    variant); a missing or retired offer clears the selection so validation
    reports the line as unavailable instead of silently switching sellers.
    """
    offers = getattr(variant, "_business_offers", [])
    offer = next((row for row in offers if row.id == offer_id), None)
    variant._business_offer = offer
    variant._business_offer_available = (
        getattr(offer, "_available", 0) if offer is not None else 0
    )
    return offer


def attach_offers(variants, *, business=None):
    """Attach ``_business_offers`` / ``_business_offer`` to each variant.

    ``_business_offers`` is ordered best-first, so ``_business_offer`` is the
    offer the storefront should display and the cart should price. The selected
    offer's available stock is stored on ``_business_offer_available`` so cart
    validation can use the same business's inventory instead of the aggregate
    across every seller.
    """
    variants = list(variants)
    variant_ids = [variant.id for variant in variants]
    queryset = BusinessOffer.objects.filter(
        variant_id__in=variant_ids,
        is_active=True,
    ).select_related(
        "business",
        "business__status",
        "business__light_logo__status",
        "business__dark_logo__status",
    )
    if business is not None:
        queryset = queryset.filter(business=business)

    offer_map = {}
    for offer in queryset:
        offer_map.setdefault(offer.variant_id, []).append(offer)

    availability = _availability_by_offer(variant_ids)
    for variant in variants:
        offers = sorted(
            offer_map.get(variant.id, []),
            key=lambda offer: _offer_sort_key(offer, availability),
        )
        for offer in offers:
            offer._available = availability.get(
                (offer.variant_id, offer.business_id), 0
            )
        selected = offers[0] if offers else None
        variant._business_offers = offers
        variant._business_offer = selected
        variant._business_offer_available = (
            availability.get((variant.id, selected.business_id), 0)
            if selected is not None
            else 0
        )
