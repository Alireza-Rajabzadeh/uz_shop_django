from django.db.models import Prefetch

from domains.catalog.models import Product, ProductDetails, ProductVariants
from domains.catalog.services.variant_service import VariantService
from domains.files.services import FileService
from domains.inventory.services import InventoryService
from domains.marketplace.models import BusinessOffer
from domains.marketplace.offer_selection import (
    PREVIEW_LIMIT,
    offer_summary,
    public_offer_payload,
)


class StorefrontProductService:
    inventory_service = InventoryService()
    variant_service = VariantService()

    def get_quick_view(self, slug):
        product = self._get_product(slug)
        payload = self._base_payload(product)
        payload.update({
            "description": product.description or "",
            "json_description": self._resolve_json_description(product.json_description),
            "details": self._detail_payload(product.storefront_details),
        })
        return payload

    def get_detail(self, slug):
        product = self._get_product(slug)
        payload = self._base_payload(product)
        payload.update({
            "description": product.description or "",
            "json_description": self._resolve_json_description(product.json_description),
            "details": self._detail_payload(product.storefront_details),
            "variants": [self._variant_payload(variant) for variant in product.storefront_variants],
            "similar_products": self._similar_products(product),
            "suggested_products": self._suggestion_products(product),
            "seo": self._seo_payload(product),
        })
        return payload

    def get_variant_offers(self, slug, variant_id, *, page=1, page_size=20):
        """Paginated seller offers for one variant.

        Product detail only carries a short preview so a product with many
        sellers does not inflate every response. This is the full list, using
        the same deterministic ordering as ``attach_offers``.
        """
        product = self._get_product(slug)
        variant = next(
            (row for row in product.storefront_variants if row.id == variant_id),
            None,
        )
        if variant is None:
            raise Product.DoesNotExist
        self._attach_offers([variant])
        offers = list(getattr(variant, "_business_offers", []))
        start = (page - 1) * page_size
        return {
            "count": len(offers),
            "page": page,
            "page_size": page_size,
            "results": [
                public_offer_payload(offer)
                for offer in offers[start:start + page_size]
            ],
        }

    def _seo_payload(self, product):
        from domains.content.services import SEOService
        return SEOService.get_for("product", product.id)

    def _resolve_json_description(self, json_description):
        if not json_description or not json_description.get("components"):
            return json_description or {}
        from domains.content.services import LandingPageContentResolver
        return LandingPageContentResolver().resolve(json_description)

    def get_content_items(self, ids, *, include_unlisted=False):
        if not ids:
            return []

        products = self._content_queryset().filter(
            id__in=set(ids),
            status__name__iexact="active",
        )
        items = self._content_items(products, include_unlisted=include_unlisted)
        return [items[item_id] for item_id in ids if item_id in items]

    def _content_queryset(self):
        from domains.catalog.models import ProductFile
        media = ProductFile.objects.filter(
            file__file_type="image",
            file__status__name="available",
            file__deleted_at__isnull=True,
        ).select_related("file").order_by("-is_primary", "position", "id")
        variants = self.inventory_service.annotate_variant_summaries(
            ProductVariants.objects
            .filter(status__name__iexact="active")
        ).prefetch_related("selections__attribute", "selections__option").order_by("id")
        return (
            Product.objects.select_related("brand")
            .prefetch_related(
                "categories__status",
                Prefetch("product_files", queryset=media, to_attr="storefront_media"),
                Prefetch("variants", queryset=variants, to_attr="storefront_variants"),
            )
        )

    def _content_items(self, queryset, *, include_unlisted=False):
        items = {}
        for product in queryset:
            category = self._primary_category(product)
            if category is None or category.status.name.casefold() != "active":
                continue
            try:
                self._validate_category_ancestors(category)
            except Product.DoesNotExist:
                continue
            payload = self._base_payload(product)
            if (
                not include_unlisted
                and payload["pricing"]["minimum_effective_price"] is None
            ):
                continue
            items[product.id] = {
                "id": payload["id"],
                "slug": payload["slug"],
                "name": payload["name"],
                "category": payload["category"],
                "brand": payload["brand"],
                "thumbnail_url": payload["thumbnail_url"],
                "pricing": payload["pricing"],
                "availability": payload["availability"],
            }
        return items

    def _similar_products(self, product, limit=15):
        category_ids = list(product.categories.values_list("id", flat=True))
        if not category_ids:
            return []
        queryset = (
            self._content_queryset()
            .filter(
                categories__in=category_ids,
                status__name__iexact="active",
            )
            .exclude(pk=product.pk)
            .distinct()
            .order_by("id")
        )[:limit]
        return list(self._content_items(queryset).values())

    def _suggestion_products(self, product, limit=15):
        from django.db.models import Q
        offer_ids = BusinessOffer.objects.filter(
            is_active=True,
            discount_type__isnull=False,
            discount_value__gt=0,
        ).values_list("variant_id", flat=True)
        queryset = (
            self._content_queryset()
            .filter(
                status__name__iexact="active",
                variants__id__in=offer_ids,
            )
            .exclude(pk=product.pk)
            .distinct()
            .order_by("id")
        )[:limit]
        return list(self._content_items(queryset).values())

    def _get_product(self, slug):
        from domains.catalog.models import ProductFile
        media = ProductFile.objects.filter(
            file__file_type="image",
            file__status__name="available",
            file__deleted_at__isnull=True,
        ).select_related("file").order_by("-is_primary", "position", "id")
        details = ProductDetails.objects.select_related("detail", "option").order_by(
            "detail__name", "id"
        )
        variants = self.inventory_service.annotate_variant_summaries(
            ProductVariants.objects
            .filter(status__name__iexact="active")
        ).prefetch_related("selections__attribute", "selections__option").order_by("id")
        product = (
            Product.objects.select_related("brand")
            .prefetch_related(
                "categories",
                Prefetch("product_files", queryset=media, to_attr="storefront_media"),
                Prefetch("details", queryset=details, to_attr="storefront_details"),
                Prefetch("variants", queryset=variants, to_attr="storefront_variants"),
            )
            .filter(
                slug=slug,
                status__name__iexact="active",
            )
            .first()
        )
        if product is None:
            raise Product.DoesNotExist
        primary_category = self._primary_category(product)
        if primary_category is None or primary_category.status.name.casefold() != "active":
            raise Product.DoesNotExist
        self._validate_category_ancestors(primary_category)
        return product

    @staticmethod
    def _primary_category(product):
        return product.categories.order_by("id").first()

    @staticmethod
    def _validate_category_ancestors(category):
        seen = set()
        current = category
        while current.parent_id and current.parent_id not in seen:
            seen.add(current.id)
            current = current.parent
            if current is None or current.status.name.casefold() != "active":
                raise Product.DoesNotExist

    def _attach_offers(self, variants):
        from domains.marketplace.offer_selection import attach_offers

        attach_offers(variants)

    @staticmethod
    def _available(variant):
        return getattr(
            variant, "_business_offer_available", variant.available_item_count
        )

    def _base_payload(self, product):
        variants = product.storefront_variants
        self._attach_offers(variants)
        listed_variants = [
            row for row in variants if getattr(row, "_business_offer", None) is not None
        ]
        default_variant = next(
            (row for row in listed_variants if self._available(row) > 0),
            listed_variants[0] if listed_variants else (variants[0] if variants else None),
        )
        effective_prices = [
            self.variant_service.calculate_discounted_price(row)
            for row in listed_variants
        ]
        prices = [row._business_offer.price for row in listed_variants]
        listed_offers = [
            offer
            for row in listed_variants
            for offer in getattr(row, "_business_offers", [])
        ]
        media = self._media_payload(product.storefront_media)
        primary_category = self._primary_category(product)
        default_offer = getattr(default_variant, "_business_offer", None)
        return {
            "id": product.id,
            "slug": product.slug,
            "name": product.name,
            "category": (
                {
                    "id": primary_category.id,
                    "slug": primary_category.slug,
                    "name": primary_category.name,
                }
                if primary_category else None
            ),
            "brand": (
                {"id": product.brand_id, "slug": product.brand.slug, "name": product.brand.name}
                if product.brand_id else None
            ),
            "media": media,
            "thumbnail_url": media[0]["url"] if media else None,
            "pricing": {
                "minimum_price": min(prices, default=None),
                "minimum_effective_price": min(effective_prices, default=None),
                "maximum_effective_price": max(effective_prices, default=None),
            },
            "availability": {
                "in_stock": any(self._available(row) > 0 for row in listed_variants),
            },
            "offers": offer_summary(listed_offers),
            "variant_options": self._variant_options(variants),
            "default_variant": (
                {
                    "id": default_variant.id,
                    "price": getattr(default_variant._business_offer, "price", None),
                    "effective_price": self.variant_service.calculate_discounted_price(
                        default_variant
                    ),
                    "in_stock": self._available(default_variant) > 0,
                    "selected_offer": (
                        public_offer_payload(default_offer)
                        if default_offer is not None else None
                    ),
                }
                if default_variant else None
            ),
        }

    @staticmethod
    def _detail_payload(details):
        return [
            {
                "id": row.detail_id,
                "label": row.detail.name,
                "type": row.detail.type,
                "value": row.option.name if row.option_id else row.value,
                "option_id": row.option_id,
            }
            for row in details
        ]

    @staticmethod
    def _media_payload(relations):
        result = []
        for relation in relations:
            try:
                url = FileService().url(relation.file)
            except FileService.Error:
                continue
            result.append({
                "id": relation.id,
                "url": url,
                "role": relation.role,
                "alt_text": relation.alt_text,
            })
        return result

    @staticmethod
    def _variant_options(variants):
        attributes = {}
        for variant in variants:
            for selection in variant.selections.all():
                attribute = attributes.setdefault(selection.attribute_id, {
                    "attribute_id": selection.attribute_id,
                    "label": selection.attribute.name,
                    "fa_name": selection.attribute.fa_name or "",
                    "values": {},
                })
                attribute["values"][selection.option_id] = {
                    "option_id": selection.option_id,
                    "label": selection.option.name,
                    "fa_name": selection.option.fa_name or "",
                    "extra": selection.option.info or None,
                }
        return [
            {**attribute, "values": list(attribute["values"].values())}
            for attribute in attributes.values()
        ]

    def _variant_payload(self, variant):
        offer = getattr(variant, "_business_offer", None)
        offers = list(getattr(variant, "_business_offers", []))
        return {
            "id": variant.id,
            "price": getattr(offer, "price", None),
            "effective_price": self.variant_service.calculate_discounted_price(variant),
            "discount_type": getattr(offer, "discount_type", None),
            "discount_value": getattr(offer, "discount_value", None),
            "in_stock": self._available(variant) > 0,
            "selected_offer": (
                public_offer_payload(offer) if offer is not None else None
            ),
            "offer_summary": offer_summary(offers),
            "offers": [
                public_offer_payload(row)
                for row in offers[:PREVIEW_LIMIT]
            ],
            "selections": [
                {
                    "attribute_id": row.attribute_id,
                    "attribute": row.attribute.name,
                    "option_id": row.option_id,
                    "option": row.option.name,
                }
                for row in variant.selections.all()
            ],
        }
