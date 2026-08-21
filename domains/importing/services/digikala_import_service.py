import hashlib
import json
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import urlsplit

from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction

from core.management.seeders.categories import CategorySeeder
from domains.importing.integrations.digikala.client import DigikalaClient
from domains.catalog.models import (
    Brand,
    Category,
    CategoryDetail,
    CategoryDetailRelation,
    CategoryStatus,
    CategoryVariantAttribute,
    Product,
    ProductVariants,
    VariantAttribute,
    VariantOption,
)
from domains.catalog.services.brand_service import BrandService
from domains.catalog.services.detail_service import DetailService
from domains.catalog.services.product_file_service import ProductFileService
from domains.catalog.services.product_service import ProductService
from domains.catalog.services.variant_attribute_service import VariantAttributeService
from domains.files.models import File
from domains.files.services import FileService
from domains.importing.models import ExternalProductIdentity


class DigikalaImportService:
    """Reconcile one normalized Digikala detail document into Catalog."""

    SOURCE_PREFIX = "digikala"
    DEFAULT_ATTRIBUTE = "Variant"
    DEFAULT_OPTION = "Default"
    SOURCE_LABEL_PATTERNS = (
        re.compile(r"(?<![A-Za-z0-9])digi[\s_-]*kala(?![A-Za-z0-9])", re.IGNORECASE),
        re.compile(r"(?<![A-Za-z0-9])dk(?![A-Za-z0-9])", re.IGNORECASE),
        re.compile(r"دیجی[\s‌_-]*کالا"),
    )

    class Error(Exception):
        pass

    def __init__(self, category_manifest=None):
        self.category_manifest = Path(
            category_manifest or CategorySeeder.MANIFEST_PATH
        )
        self.brand_service = BrandService()
        self.detail_service = DetailService()
        self.product_service = ProductService()
        self.variant_service = VariantAttributeService()
        self.file_service = FileService()
        self.product_file_service = ProductFileService()

    @staticmethod
    def _normalize(value):
        return " ".join(str(value or "").split())

    @classmethod
    def _sanitize_display_text(cls, value):
        value = cls._normalize(value)
        for pattern in cls.SOURCE_LABEL_PATTERNS:
            value = pattern.sub(" ", value)
        value = cls._normalize(value)
        return value.strip(" -–—_|,:;،؛/\\()[]{}")

    @staticmethod
    def _limited(value, limit):
        value = DigikalaImportService._sanitize_display_text(value)
        if len(value) <= limit:
            return value
        digest = hashlib.sha256(value.encode()).hexdigest()[:8]
        return f"{value[: limit - 9]}-{digest}"

    @staticmethod
    def _source_id(detail):
        try:
            return int(detail["source"]["id"])
        except (KeyError, TypeError, ValueError) as exc:
            raise DigikalaImportService.Error(
                "Normalized detail has no valid source product ID."
            ) from exc

    @classmethod
    def source_slug(cls, source_id):
        return f"{cls.SOURCE_PREFIX}-{int(source_id)}"

    def _manifest_categories(self):
        with self.category_manifest.open(encoding="utf-8") as manifest_file:
            manifest = json.load(manifest_file)
        records = {}

        def visit(items, parent_id=None):
            for item in items:
                records[int(item["id"])] = {
                    "id": int(item["id"]),
                    "name": item["name"],
                    "parent_id": parent_id,
                }
                visit(item.get("children", []), int(item["id"]))

        visit(manifest.get("categories", []))
        return records

    def _ensure_categories(self, category_ids):
        records = self._manifest_categories()
        active_status = CategoryStatus.objects.filter(name__iexact="active").first()
        if active_status is None:
            raise self.Error("The active category status is not configured.")
        resolved = {}

        def ensure(category_id):
            if category_id in resolved:
                return resolved[category_id]
            existing = Category.objects.filter(pk=category_id).first()
            if existing:
                resolved[category_id] = existing
                return existing
            record = records.get(category_id)
            if record is None:
                raise self.Error(
                    f"Category {category_id} is not in the canonical category manifest."
                )
            parent = ensure(record["parent_id"]) if record["parent_id"] else None
            try:
                category = Category.objects.create(
                    id=record["id"],
                    name=record["name"],
                    fa_name=record["name"],
                    status=active_status,
                    parent=parent,
                )
            except IntegrityError:
                category = Category.objects.get(pk=record["id"])
            resolved[category_id] = category
            return category

        return [ensure(int(category_id)) for category_id in sorted(set(category_ids))]

    def _resolve_brand(self, payload, warnings):
        if not isinstance(payload, dict):
            return None
        title_fa = self._limited(payload.get("title_fa"), 150)
        title_en = self._limited(payload.get("title_en"), 150)
        code = self._limited(payload.get("code"), 150)
        name = title_en or code or title_fa
        if not name:
            return None
        normalized = self.brand_service.normalize_name(name).casefold()
        brand = next(
            (
                item
                for item in Brand.objects.all()
                if self.brand_service.normalize_name(item.name).casefold() == normalized
            ),
            None,
        )
        if brand is None and title_fa:
            matches = [
                item
                for item in Brand.objects.all()
                if item.fa_name
                and self.brand_service.normalize_name(item.fa_name).casefold()
                == self.brand_service.normalize_name(title_fa).casefold()
            ]
            if len(matches) == 1:
                brand = matches[0]
            elif len(matches) > 1:
                warnings.append(f"Brand '{title_fa}' matched multiple Persian names.")
                return None
        if brand is None:
            try:
                return self.brand_service.create_brand(
                    name=name, fa_name=title_fa or None
                )
            except BrandService.ValidationError:
                brand = Brand.objects.filter(name__iexact=name).first()
                if brand is None:
                    raise
                return brand
        if title_fa and not brand.fa_name:
            brand = self.brand_service.update_brand(
                brand, name=brand.name, fa_name=title_fa
            )
        return brand

    @staticmethod
    def _display_value(value):
        if isinstance(value, dict):
            value = (
                value.get("title_fa")
                or value.get("title")
                or value.get("name")
                or value.get("value")
            )
        if isinstance(value, list):
            parts = [DigikalaImportService._display_value(item) for item in value]
            return "، ".join(part for part in parts if part)
        return DigikalaImportService._sanitize_display_text(value)

    def _detail_items(self, detail, categories, warnings):
        items = []
        seen = set()
        for group in detail.get("specifications", []):
            for attribute in group.get("attributes", []):
                name = self._limited(
                    attribute.get("title") or attribute.get("name"), 100
                )
                value = self._display_value(attribute.get("values", []))
                if not name or not value or name.casefold() in seen:
                    continue
                seen.add(name.casefold())
                definition = next(
                    (
                        candidate
                        for candidate in CategoryDetail.objects.all()
                        if self.detail_service.normalize_name(candidate.name).casefold()
                        == self.detail_service.normalize_name(name).casefold()
                    ),
                    None,
                )
                if definition is None:
                    try:
                        definition = self.detail_service.create_category_detail(
                            name=name,
                            type="text",
                            required=False,
                            options="",
                            filterable=False,
                        )
                    except DetailService.ValidationError:
                        definition = CategoryDetail.objects.filter(
                            name__iexact=name
                        ).first()
                if definition is None:
                    warnings.append(f"Could not resolve detail '{name}'.")
                    continue
                if definition.type != "text":
                    warnings.append(
                        f"Skipped detail '{name}' because its existing type is {definition.type}."
                    )
                    continue
                for category in categories:
                    CategoryDetailRelation.objects.get_or_create(
                        category=category, detail=definition, defaults={"value": ""}
                    )
                if len(value) > 250:
                    warnings.append(f"Detail '{name}' was truncated to 250 characters.")
                    value = value[:250]
                items.append({"detail_id": definition.id, "value": value})
        return items

    @staticmethod
    def _named(value):
        if not isinstance(value, dict):
            return None
        title_fa = DigikalaImportService._sanitize_display_text(
            value.get("title_fa") or value.get("title") or value.get("name")
        )
        title_en = DigikalaImportService._sanitize_display_text(value.get("title_en"))
        if not title_fa and not title_en:
            return None
        info = DigikalaImportService._normalize(
            value.get("hex") or value.get("hex_code") or value.get("color")
        )
        return {
            "id": value.get("id"),
            "code": value.get("code"),
            "title_fa": title_fa,
            "title_en": title_en,
            "info": info,
        }

    def _source_selections(self, variant):
        selections = []
        for theme in variant.get("themes", []):
            if not isinstance(theme, dict):
                continue
            attribute_name = self._sanitize_display_text(
                theme.get("title")
                or theme.get("name")
                or theme.get("label")
                or theme.get("type")
            )
            raw_option = theme.get("value") or theme.get("option") or theme
            nature = raw_option.get("nature") if isinstance(raw_option, dict) else None
            if (
                nature == "color"
                or theme.get("type") == "colored"
                or attribute_name.casefold() in {"رنگ", "color"}
            ):
                attribute_name = "Color"
            option = self._named(raw_option)
            if not option and isinstance(raw_option, str):
                option = {
                    "id": None,
                    "code": None,
                    "title_fa": self._sanitize_display_text(raw_option),
                    "title_en": "",
                }
            if attribute_name and option:
                selections.append({"attribute": attribute_name, "option": option})
        unique = {}
        for selection in selections:
            unique.setdefault(selection["attribute"].casefold(), selection)
        color = self._named(variant.get("color"))
        if color:
            unique.setdefault(
                "color", {"attribute": "Color", "option": color}
            )
        if unique:
            return list(unique.values())
        return [
            {
                "attribute": self.DEFAULT_ATTRIBUTE,
                "option": {
                    "id": "default",
                    "code": "default",
                    "title_fa": self.DEFAULT_OPTION,
                    "title_en": self.DEFAULT_OPTION,
                },
            }
        ]

    def _source_combination(self, variant):
        selections = self._source_selections(variant)
        return tuple(
            sorted(
                (
                    item["attribute"].casefold(),
                    str(
                        item["option"].get("id")
                        or item["option"].get("code")
                        or item["option"].get("title_en")
                        or item["option"].get("title_fa")
                    ).casefold(),
                )
                for item in selections
            )
        )

    @staticmethod
    def _decimal(value):
        if value is None or isinstance(value, bool):
            return None
        try:
            number = Decimal(str(value))
        except (InvalidOperation, ValueError):
            return None
        return number if number.is_finite() and number >= 0 else None

    def _pricing(self, variant):
        price = variant.get("price") if isinstance(variant.get("price"), dict) else {}
        selling = self._decimal(price.get("selling_price"))
        rrp = self._decimal(price.get("rrp_price"))
        if selling is None and rrp is None:
            return None
        if selling is not None and rrp is not None and rrp >= selling:
            discount = rrp - selling
            return {
                "price": rrp,
                "discount_type": "fixed" if discount > 0 else None,
                "discount_value": discount if discount > 0 else None,
            }
        return {
            "price": selling if selling is not None else rrp,
            "discount_type": None,
            "discount_value": None,
        }

    def _preferred_variants(self, detail):
        grouped = {}
        for variant in detail.get("variants", []):
            pricing = self._pricing(variant)
            if pricing is None:
                continue
            key = self._source_combination(variant)
            marketable = str(variant.get("status") or "").casefold() in {
                "marketable",
                "active",
                "available",
            }
            candidate = (not marketable, pricing["price"], int(variant.get("id") or 0))
            if key not in grouped or candidate < grouped[key][0]:
                grouped[key] = (candidate, variant, pricing)
        return [(variant, pricing) for _rank, variant, pricing in grouped.values()]

    @staticmethod
    def _sku_code(attribute_name, option):
        identity = "|".join(
            str(value or "")
            for value in (
                attribute_name,
                option.get("id"),
                option.get("code"),
                option.get("title_en"),
                option.get("title_fa"),
            )
        )
        return "DK" + hashlib.sha256(identity.encode()).hexdigest()[:14].upper()

    def _resolve_attribute(self, name):
        name = self._limited(name, 100)
        normalized = self.variant_service.normalize_name(name).casefold()
        attribute = next(
            (
                item
                for item in VariantAttribute.objects.all()
                if self.variant_service.normalize_name(item.name).casefold() == normalized
            ),
            None,
        )
        if attribute:
            return attribute
        try:
            return self.variant_service.create_attribute(name=name)
        except VariantAttributeService.ValidationError:
            return VariantAttribute.objects.get(name__iexact=name)

    def _resolve_option(self, attribute, source):
        title_fa = self._limited(source.get("title_fa"), 100)
        title_en = self._limited(source.get("title_en"), 100)
        name = title_en or title_fa
        if not name:
            raise self.Error(f"Variant attribute '{attribute.name}' has an empty option.")
        code = self._sku_code(attribute.name, source)
        option = VariantOption.objects.filter(sku_code__iexact=code).first()
        if option:
            if option.attribute_id != attribute.id:
                raise self.Error(f"Variant option SKU code collision for {code}.")
            return option
        normalized = self.variant_service.normalize_name(name).casefold()
        option = next(
            (
                item
                for item in attribute.options.all()
                if self.variant_service.normalize_name(item.name).casefold() == normalized
            ),
            None,
        )
        if option:
            return option
        try:
            return self.variant_service.create_option(
                attribute=attribute,
                name=name,
                fa_name=title_fa or None,
                info=source.get("info"),
                sku_code=code,
            )
        except VariantAttributeService.ValidationError:
            option = VariantOption.objects.filter(sku_code__iexact=code).first()
            if option is None:
                raise
            return option

    def _variant_selections(self, variant, categories):
        result = []
        for source in self._source_selections(variant):
            attribute = self._resolve_attribute(source["attribute"])
            option = self._resolve_option(attribute, source["option"])
            for category in categories:
                CategoryVariantAttribute.objects.get_or_create(
                    category=category, attribute=attribute
                )
            result.append({"attribute": attribute, "option": option})
        return result

    def _media_sources(self, detail, max_images=12):
        images = detail.get("images") if isinstance(detail.get("images"), dict) else {}
        by_identity = {}
        for value in [*images.get("main", []), *images.get("gallery", [])]:
            if not isinstance(value, str) or not value.strip():
                continue
            parts = urlsplit(value)
            identity = (parts.scheme.lower(), parts.netloc.lower(), parts.path)
            is_webp = (
                "format,webp" in parts.query.casefold()
                or parts.path.casefold().endswith(".webp")
            )
            existing = by_identity.get(identity)
            if existing is None or (not is_webp and existing[1]):
                by_identity[identity] = (value, is_webp)
            if len(by_identity) >= max_images:
                break
        return [value for value, _is_webp in by_identity.values()]

    @staticmethod
    def _media_source_url(metadata):
        return metadata.get("source_url") if isinstance(metadata, dict) else None

    def _existing_media_file(self, source_url):
        return (
            File.objects.filter(
                metadata__source_url=source_url,
                status__name="available",
                deleted_at__isnull=True,
            )
            .order_by("created_at")
            .first()
        )

    def import_media(self, product, detail, *, client, warnings):
        source_id = self._source_id(detail)
        sources = self._media_sources(detail)
        if not sources:
            return 0
        existing = {
            self._media_source_url(relation.file.metadata)
            for relation in product.product_files.select_related("file").all()
        }
        attached = 0
        for index, source_url in enumerate(sources):
            if source_url in existing:
                continue
            try:
                file_row = self._existing_media_file(source_url)
                if file_row is None:
                    payload, content_type = client.get_image_bytes(source_url)
                    extension = Path(urlsplit(source_url).path).suffix.lower()
                    file_row = self.file_service.upload(
                        SimpleUploadedFile(
                            f"digikala_{source_id}_{index}{extension}",
                            payload,
                            content_type=content_type,
                        ),
                        metadata={
                            "source": self.SOURCE_PREFIX,
                            "source_url": source_url,
                            "source_product_id": source_id,
                        },
                    )
                self.product_file_service.attach(
                    product,
                    file_row,
                    role="gallery",
                    position=index,
                    is_primary=index == 0,
                    alt_text=self._limited(product.name, 255),
                )
                attached += 1
            except Exception as exc:
                warnings.append(
                    f"Image '{source_url}' could not be imported: {exc}"
                )
        return attached

    @transaction.atomic
    def import_product(
        self, detail, category_ids, *, download_media=False, media_client=None
    ):
        warnings = []
        source_id = self._source_id(detail)
        categories = self._ensure_categories(category_ids)
        if not categories:
            raise self.Error("At least one local category is required.")
        brand = self._resolve_brand(detail.get("brand"), warnings)
        name = self._limited(detail.get("title_fa"), 250) or self._limited(
            detail.get("title_en"), 250
        )
        if not name:
            raise self.Error("The product has no usable title.")
        identity = (
            ExternalProductIdentity.objects.select_for_update()
            .select_related("product")
            .filter(provider=self.SOURCE_PREFIX, external_id=str(source_id))
            .first()
        )
        product = identity.product if identity else None
        if product is None:
            product = Product.objects.select_for_update().filter(
                slug=self.source_slug(source_id)
            ).first()
            if product is not None:
                ExternalProductIdentity.objects.create(
                    provider=self.SOURCE_PREFIX,
                    external_id=str(source_id),
                    product=product,
                )
        created = product is None
        if created:
            product = self.product_service.create_product(
                name=name,
                brand=brand,
                description="",
            )
            ExternalProductIdentity.objects.create(
                provider=self.SOURCE_PREFIX,
                external_id=str(source_id),
                product=product,
            )
        else:
            self.product_service.update_product(
                product,
                name=name,
                brand=brand,
            )
        previous_primary_id = self.product_service._primary_category_id(product)
        current_categories = list(product.categories.all())
        by_id = {category.id: category for category in current_categories + categories}
        product.categories.set(by_id.values())
        if (
            not created
            and self.product_service._primary_category_id(product) != previous_primary_id
        ):
            self.product_service.regenerate_product_variant_skus(product)

        detail_items = self._detail_items(detail, list(by_id.values()), warnings)
        if detail_items:
            self.product_service.add_detail_to_product(product, detail_items)

        variant_created = 0
        variant_updated = 0
        for variant, pricing in self._preferred_variants(detail):
            selections = self._variant_selections(variant, list(by_id.values()))
            combination_key = self.product_service._build_combination_key(
                sorted(selections, key=lambda item: item["attribute"].id)
            )
            existing = ProductVariants.objects.filter(
                product=product, combination_key=combination_key
            ).first()
            if existing:
                self.product_service.update_variant(
                    existing,
                    selections=selections,
                    inventory_submitted=False,
                    **pricing,
                )
                variant_updated += 1
            else:
                self.product_service.add_variant_to_product(
                    product,
                    selections=selections,
                    inventory_strategy_code="normal",
                    inventory_submitted=False,
                    **pricing,
                )
                variant_created += 1

        media_attached = 0
        if download_media:
            media_attached = self.import_media(
                product,
                detail,
                client=media_client or DigikalaClient(),
                warnings=warnings,
            )

        return {
            "status": "created" if created else "updated",
            "source_product_id": source_id,
            "local_product_id": product.id,
            "variants_created": variant_created,
            "variants_updated": variant_updated,
            "media_attached": media_attached,
            "warnings": warnings,
        }
