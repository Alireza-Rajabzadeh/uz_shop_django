from django.db.models import Prefetch

from domains.catalog.models import Product, ProductDetails, ProductFile, ProductVariants
from domains.catalog.services.variant_service import VariantService
from domains.files.services import FileService
from domains.inventory.services import InventoryService


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

    def _seo_payload(self, product):
        from domains.content.services import SEOService
        return SEOService.get_for("product", product.id)

    def _resolve_json_description(self, json_description):
        if not json_description or not json_description.get("components"):
            return json_description or {}
        from domains.content.services import LandingPageContentResolver
        return LandingPageContentResolver().resolve(json_description)

    def get_content_items(self, ids):
        if not ids:
            return []

        products = self._content_queryset().filter(
            id__in=set(ids),
            status__name__iexact="active",
        )
        items = self._content_items(products)
        return [items[item_id] for item_id in ids if item_id in items]

    def _content_queryset(self):
        media = ProductFile.objects.filter(
            file__file_type="image",
            file__status__name="available",
            file__deleted_at__isnull=True,
        ).select_related("file").order_by("-is_primary", "position", "id")
        variants = self.inventory_service.annotate_variant_summaries(
            ProductVariants.objects.select_related("inventory_strategy")
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

    def _content_items(self, queryset):
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
        queryset = (
            self._content_queryset()
            .filter(
                status__name__iexact="active",
                variants__discount_type__isnull=False,
                variants__discount_value__gt=0,
            )
            .exclude(pk=product.pk)
            .distinct()
            .order_by("id")
        )[:limit]
        return list(self._content_items(queryset).values())

    def _get_product(self, slug):
        media = ProductFile.objects.filter(
            file__file_type="image",
            file__status__name="available",
            file__deleted_at__isnull=True,
        ).select_related("file").order_by("-is_primary", "position", "id")
        details = ProductDetails.objects.select_related("detail", "option").order_by(
            "detail__name", "id"
        )
        variants = self.inventory_service.annotate_variant_summaries(
            ProductVariants.objects.select_related("inventory_strategy")
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

    def _base_payload(self, product):
        variants = product.storefront_variants
        default_variant = next(
            (row for row in variants if row.available_item_count > 0),
            variants[0] if variants else None,
        )
        effective_prices = [self.variant_service.calculate_discounted_price(row) for row in variants]
        media = self._media_payload(product.storefront_media)
        primary_category = self._primary_category(product)
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
                "minimum_price": min((row.price for row in variants), default=None),
                "minimum_effective_price": min(effective_prices, default=None),
                "maximum_effective_price": max(effective_prices, default=None),
            },
            "availability": {
                "in_stock": any(row.available_item_count > 0 for row in variants),
            },
            "variant_options": self._variant_options(variants),
            "default_variant": (
                {
                    "id": default_variant.id,
                    "price": default_variant.price,
                    "effective_price": self.variant_service.calculate_discounted_price(
                        default_variant
                    ),
                    "in_stock": default_variant.available_item_count > 0,
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
                    "values": {},
                })
                attribute["values"][selection.option_id] = {
                    "option_id": selection.option_id,
                    "label": selection.option.name,
                    "extra": selection.option.info or None,
                }
        return [
            {**attribute, "values": list(attribute["values"].values())}
            for attribute in attributes.values()
        ]

    def _variant_payload(self, variant):
        return {
            "id": variant.id,
            "price": variant.price,
            "effective_price": self.variant_service.calculate_discounted_price(variant),
            "discount_type": variant.discount_type,
            "discount_value": variant.discount_value,
            "in_stock": variant.available_item_count > 0,
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
