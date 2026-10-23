"""Realistic vendor/business/marketplace fixtures for development.

Creates a large, deterministic marketplace sample:

* complete vendors (profile, status, verified contact data),
* one complete business profile per vendor (address, phones, social links,
  working days, categories),
* a default warehouse per business,
* inventory supplies and sellable stock for products in the business's
  root categories, and
* an active ``BusinessOffer`` for every stocked variant.

The generator reuses the imported catalog where a root already has products
and adds a small curated catalog for roots the import does not cover.  It is
idempotent: re-running converges the fixture set instead of duplicating it.

Development-only.  It creates accounts with a known shared password and
writes no files, so do not run it against shared environments.
"""

from __future__ import annotations

import random
from datetime import date, time, timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.contrib.auth.hashers import make_password
from django.db import transaction
from django.utils import timezone

from core.management.data.vendor_marketplace_fixtures import (
    BUSINESS_CORES,
    BUSINESS_PREFIXES,
    BUSINESS_TYPES,
    CATEGORY_PRICE_BANDS,
    CITY_PROFILES,
    CURATED_PRODUCTS,
    FEMALE_FIRST_NAMES,
    LAST_NAMES,
    MALE_FIRST_NAMES,
    ROOT_PRICE_BANDS,
    SEED_MARKER,
    SHARED_PASSWORD,
    STREETS,
)
from core.management.seeders.base import BaseSeeder
from domains.business.models import (
    BusinessPhone,
    BusinessProfile,
    BusinessSocialLink,
    BusinessStatus,
    BusinessWorkingDay,
    SocialMedia,
)
from domains.business.services import BusinessService
from domains.catalog.models import (
    Brand,
    Category,
    Product,
    ProductStatus,
    ProductVariantStatus,
    ProductVariants,
    VariantAttribute,
    VariantOption,
)
from domains.catalog.services import ProductService
from domains.inventory.models import (
    Inventory,
    InventoryType,
    Warehouse,
    WarehouseStatus,
)
from domains.inventory.services import InventoryService, InventorySupplyService
from domains.location.models import City
from domains.marketplace.models import BusinessOffer, PricingStrategy
from domains.marketplace.services import MarketplacePricingService
from domains.packages.models import Package
from domains.vendor.models import Vendor, VendorStatus

SUPPORTED_ROOTS = frozenset(
    root for business_type in BUSINESS_TYPES for root in business_type["roots"]
)


class VendorMarketplaceSeeder(BaseSeeder):
    def __init__(self, *, vendor_count=100, seed=20261022):
        self.vendor_count = max(0, int(vendor_count))
        self.seed = int(seed)
        self.product_service = ProductService()
        self.inventory_service = InventoryService()
        self.supply_service = InventorySupplyService()
        self.counts = {
            "vendors_created": 0,
            "businesses_created": 0,
            "products_created": 0,
            "variants_created": 0,
            "warehouses_created": 0,
            "supplies_created": 0,
            "offers_created": 0,
        }
        self._password_hash = make_password(SHARED_PASSWORD)
        self._used_business_names = set()
        self._unit_cost_cache = {}
        self._root_by_category = {}
        self._variant_pools = {}
        self._reference = {}

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------
    def run(self):
        self._ensure_reference_data()
        self._load_category_roots()
        self._seed_catalog()
        self._build_variant_pools()
        self._seed_marketplace()
        return self.counts

    # ------------------------------------------------------------------
    # Reference data
    # ------------------------------------------------------------------
    def _ensure_reference_data(self):
        from core.management.seeders.business_statuses import BusinessStatusSeeder
        from core.management.seeders.categories import CategorySeeder
        from core.management.seeders.inventory import InventorySeeder
        from core.management.seeders.marketplace import MarketplaceSeeder
        from core.management.seeders.packages import PackagesSeeder
        from core.management.seeders.product_statuses import ProductStatusSeeder
        from core.management.seeders.product_variant_statuses import (
            ProductVariantStatusSeeder,
        )
        from core.management.seeders.social_media import SocialMediaSeeder
        from core.management.seeders.vendor_statuses import VendorStatusSeeder

        if not Category.objects.filter(parent__isnull=True).exists():
            CategorySeeder().run()
        if not VendorStatus.objects.filter(name="active").exists():
            VendorStatusSeeder().run()
        if not BusinessStatus.objects.filter(code="active").exists():
            BusinessStatusSeeder().run()
        if not ProductStatus.objects.filter(name="active").exists():
            ProductStatusSeeder().run()
        if not ProductVariantStatus.objects.filter(name="active").exists():
            ProductVariantStatusSeeder().run()
        if not SocialMedia.objects.filter(slug="instagram").exists():
            SocialMediaSeeder().run()
        if not Package.objects.filter(code="free").exists():
            PackagesSeeder().run()
        if not InventoryType.objects.filter(id=1).exists() or not (
            WarehouseStatus.objects.filter(id=1).exists()
        ):
            if not City.objects.exists():
                raise RuntimeError(
                    "Seed location data before running vendor marketplace fixtures."
                )
            InventorySeeder().run()
        if not City.objects.exists():
            raise RuntimeError(
                "Seed location data before running vendor marketplace fixtures."
            )
        if not PricingStrategy.objects.exists():
            MarketplaceSeeder().run()

        self._reference = {
            "vendor_status": VendorStatus.objects.get(name="active"),
            "business_status": BusinessStatus.objects.get(code="active"),
            "product_status": ProductStatus.objects.get(name="active"),
            "variant_status": ProductVariantStatus.objects.get(name="active"),
            "warehouse_status": WarehouseStatus.objects.get(id=1),
            "packages": {
                package.code: package for package in Package.objects.all()
            },
            "social_media": {
                media.slug: media for media in SocialMedia.objects.all()
            },
        }

    # ------------------------------------------------------------------
    # Categories
    # ------------------------------------------------------------------
    def _load_category_roots(self):
        parents = dict(Category.objects.values_list("id", "parent_id"))

        def root_of(category_id):
            seen = set()
            current = category_id
            while True:
                if current in seen:
                    return current
                seen.add(current)
                parent = parents.get(current)
                if parent is None:
                    return current
                current = parent

        self._root_by_category = {
            category_id: root_of(category_id) for category_id in parents
        }

    # ------------------------------------------------------------------
    # Curated catalog for roots the imported catalog does not cover
    # ------------------------------------------------------------------
    def _seed_catalog(self):
        categories = {
            category.id: category
            for category in Category.objects.filter(
                id__in={entry["category"] for entry in CURATED_PRODUCTS}
            )
        }
        brands = {brand.name.casefold(): brand for brand in Brand.objects.all()}
        attributes = {
            attribute.name: attribute for attribute in VariantAttribute.objects.all()
        }
        options = {
            (option.attribute_id, option.name): option
            for option in VariantOption.objects.all()
        }
        product_status = self._reference["product_status"]
        variant_status = self._reference["variant_status"]

        for entry in CURATED_PRODUCTS:
            category = categories.get(entry["category"])
            if category is None:
                raise RuntimeError(
                    f"Curated product category {entry['category']} is missing. "
                    "Run `python manage.py seed_categories` first."
                )
            brand = brands.get((entry.get("brand") or "").casefold())
            product = Product.objects.filter(
                name=entry["name"], creator_model=SEED_MARKER
            ).first()
            if product is None:
                product = self.product_service.create_complete_product(
                    name=entry["name"],
                    category_ids=[category],
                    description=(
                        entry.get("description")
                        or f"{entry['name']}، محصولی با کیفیت مناسب برای فروش آنلاین."
                    ),
                    brand=brand,
                )
                product.status = product_status
                product.creator_model = SEED_MARKER
                product.save(update_fields=["status", "creator_model"])
                self.counts["products_created"] += 1
            else:
                if product.status_id != product_status.id:
                    product.status = product_status
                    product.save(update_fields=["status"])
                if not product.categories.filter(id=category.id).exists():
                    product.categories.add(category)

            existing_combinations = set(
                product.variants.values_list("combination_key", flat=True)
            )
            for variant_row in entry["variants"]:
                selections = []
                for attribute_name, option_name in variant_row.items():
                    attribute = attributes.get(attribute_name)
                    option = options.get(
                        (attribute.id, option_name) if attribute else (None, None)
                    )
                    if attribute is None or option is None:
                        raise RuntimeError(
                            "Variant attribute/option missing for curated product "
                            f"{entry['name']!r}: {attribute_name}={option_name!r}"
                        )
                    selections.append({"attribute": attribute, "option": option})
                combination_key = "|".join(
                    f"{item['attribute'].id}:{item['option'].id}"
                    for item in sorted(selections, key=lambda item: item["attribute"].id)
                )
                if combination_key in existing_combinations:
                    continue
                self.product_service.add_variant_to_product(
                    product,
                    selections=selections,
                    status_id=variant_status.id,
                )
                existing_combinations.add(combination_key)
                self.counts["variants_created"] += 1

    # ------------------------------------------------------------------
    # Candidate variants per root category
    # ------------------------------------------------------------------
    def _build_variant_pools(self):
        pools = {root: {} for root in SUPPORTED_ROOTS}
        variants = (
            ProductVariants.objects.filter(
                status__name="active",
                product__status__name="active",
            )
            .select_related("product")
            .prefetch_related("product__categories")
        )
        for variant in variants:
            roots = {
                self._root_by_category.get(category.id)
                for category in variant.product.categories.all()
            }
            for root in roots & SUPPORTED_ROOTS:
                pools[root][variant.id] = variant
        self._variant_pools = {
            root: sorted(values.values(), key=lambda variant: variant.id)
            for root, values in pools.items()
        }

    # ------------------------------------------------------------------
    # Vendors and businesses
    # ------------------------------------------------------------------
    def _seed_marketplace(self):
        for index in range(1, self.vendor_count + 1):
            with transaction.atomic():
                business_type = BUSINESS_TYPES[(index - 1) % len(BUSINESS_TYPES)]
                vendor, vendor_created = self._ensure_vendor(index)
                if vendor_created:
                    self.counts["vendors_created"] += 1
                business, business_created = self._ensure_business(
                    vendor, index, business_type
                )
                if business_created:
                    self.counts["businesses_created"] += 1
                self._ensure_contacts(vendor, business, index, business_type)
                self._ensure_categories(business, business_type)
                warehouse = self._ensure_warehouse(vendor, business)
                self._stock_and_offer_business(
                    business, warehouse, index, business_type
                )

    def _ensure_vendor(self, index):
        phone = f"0990{index:07d}"
        vendor = Vendor.objects.filter(phone=phone).first()
        if vendor is not None:
            return vendor, False

        rng = random.Random(self.seed * 17 + index)
        gender = rng.choice(("male", "female"))
        first_name = rng.choice(
            MALE_FIRST_NAMES if gender == "male" else FEMALE_FIRST_NAMES
        )
        last_name = rng.choice(LAST_NAMES)
        date_of_birth = date(1980, 1, 1) + timedelta(days=rng.randint(0, 7300))
        now = timezone.now()
        vendor = Vendor(
            phone=phone,
            first_name=first_name,
            last_name=last_name,
            email=f"vendor{index:03d}@uzshop.test",
            national_id=f"00{index:08d}",
            status=self._reference["vendor_status"],
            date_of_birth=date_of_birth,
            gender=gender,
            email_verified_at=now,
            phone_verified_at=now,
            password=self._password_hash,
        )
        vendor.save()
        return vendor, True

    def _ensure_business(self, vendor, index, business_type):
        business = BusinessProfile.objects.filter(vendor=vendor).first()
        if business is not None:
            return business, False

        rng = random.Random(self.seed * 31 + index)
        city_profile = CITY_PROFILES[(index - 1) % len(CITY_PROFILES)]
        city = (
            City.objects.select_related("state")
            .filter(name=city_profile["name"])
            .first()
        )
        if city is None:
            city = City.objects.select_related("state").order_by("id").first()
            if city is None:
                raise RuntimeError(
                    "No cities are available; seed location data first."
                )
            city_profile = next(
                (
                    profile
                    for profile in CITY_PROFILES
                    if profile["name"] == city.name
                ),
                {
                    "label": city.name,
                    "latitude": str(city.latitude or "35.689200"),
                    "longitude": str(city.longitude or "51.389000"),
                    "postal_prefix": "11",
                },
            )

        core = BUSINESS_CORES[(index * 7) % len(BUSINESS_CORES)]
        suffix = business_type["suffixes"][index % len(business_type["suffixes"])]
        prefix = BUSINESS_PREFIXES[(index * 3) % len(BUSINESS_PREFIXES)]
        display_name = f"{core} {suffix}"
        business_name = f"{prefix} {display_name}"
        if business_name in self._used_business_names:
            business_name = f"{business_name} {index}"
        self._used_business_names.add(business_name)

        package_code = rng.choices(
            ("free", "plus", "pro"), weights=(70, 20, 10), k=1
        )[0]
        package = self._reference["packages"].get(package_code)
        street = STREETS[(index * 5) % len(STREETS)]
        address = (
            f"{city_profile['label']}، {street}، پلاک "
            f"{rng.randint(1, 250)}، واحد {rng.randint(1, 20)}"
        )
        latitude = Decimal(city_profile["latitude"]) + Decimal(
            str(round(rng.uniform(-0.04, 0.04), 6))
        )
        longitude = Decimal(city_profile["longitude"]) + Decimal(
            str(round(rng.uniform(-0.04, 0.04), 6))
        )
        availability_status = rng.choices(
            ("open", "temporarily_unavailable", "maintenance"),
            weights=(92, 5, 3),
            k=1,
        )[0]
        availability_message = {
            "open": "",
            "temporarily_unavailable": "سفارش‌ها با تاخیر ارسال می‌شوند.",
            "maintenance": "فروشگاه در حال به‌روزرسانی است.",
        }[availability_status]

        business = BusinessProfile.objects.create(
            vendor=vendor,
            package=package,
            status=self._reference["business_status"],
            business_name=business_name,
            display_name=display_name,
            legal_name=f"شرکت {business_name}",
            email=f"info{index:03d}@uzshop.test",
            address=address,
            province=city.state,
            city=city,
            postal_code=(
                f"{city_profile['postal_prefix']}{10_000_000 + index * 137:08d}"
            ),
            latitude=latitude,
            longitude=longitude,
            availability_status=availability_status,
            availability_message=availability_message,
            cache_ttl=3600,
        )
        return business, True

    def _ensure_contacts(self, vendor, business, index, business_type):
        BusinessPhone.objects.get_or_create(
            business=business,
            key="main",
            defaults={
                "title": "تلفن همراه مدیر",
                "number": vendor.phone,
                "visibility": "public",
                "status": "active",
                "position": 0,
            },
        )
        BusinessPhone.objects.get_or_create(
            business=business,
            key="support",
            defaults={
                "title": "پشتیبانی فروش",
                "number": f"021-{70_000_000 + index * 137:08d}",
                "visibility": "public",
                "status": "active",
                "position": 1,
            },
        )

        social_media = self._reference["social_media"]
        social_rows = (
            ("instagram", "اینستاگرام", f"https://instagram.com/uzshop_{business_type['key']}_{index:03d}"),
            ("telegram", "تلگرام", f"https://t.me/uzshop_{business_type['key']}_{index:03d}"),
            ("whatsapp", "واتس‌اپ", f"https://wa.me/98{vendor.phone[1:]}"),
        )
        for position, (slug, title, url) in enumerate(social_rows):
            media = social_media.get(slug)
            if media is None:
                continue
            BusinessSocialLink.objects.get_or_create(
                business=business,
                key=slug,
                defaults={
                    "title": title,
                    "social_media": media,
                    "url": url,
                    "visibility": "public",
                    "status": "active",
                    "position": position,
                },
            )

        rng = random.Random(self.seed * 43 + index)
        for weekday in range(7):
            is_open = business_type["key"] == "market" or weekday != 6
            if not is_open:
                opens_at = closes_at = second_opens_at = second_closes_at = None
            elif business_type["key"] == "market":
                opens_at, closes_at = time(8, 0), time(23, 0)
                second_opens_at = second_closes_at = None
            elif rng.random() < 0.3:
                opens_at, closes_at = time(9, 0), time(13, 0)
                second_opens_at, second_closes_at = time(17, 0), time(21, 0)
            else:
                opens_at, closes_at = time(9, 0), time(21, 0)
                second_opens_at = second_closes_at = None
            BusinessWorkingDay.objects.get_or_create(
                vendor=vendor,
                weekday=weekday,
                defaults={
                    "is_open": is_open,
                    "opens_at": opens_at,
                    "closes_at": closes_at,
                    "second_opens_at": second_opens_at,
                    "second_closes_at": second_closes_at,
                },
            )

    def _ensure_categories(self, business, business_type):
        BusinessService.replace_profile_categories(
            business, list(business_type["roots"])
        )

    def _ensure_warehouse(self, vendor, business):
        warehouse = Warehouse.objects.filter(
            business=business, is_default=True
        ).first()
        if warehouse is not None:
            return warehouse
        warehouse = Warehouse.objects.create(
            business=business,
            name=f"انبار {business.display_name}",
            city=business.city,
            address=business.address,
            lat=business.latitude,
            lng=business.longitude,
            phone_numbers=[vendor.phone],
            postal_code=business.postal_code,
            is_default=True,
            status=self._reference["warehouse_status"],
        )
        self.counts["warehouses_created"] += 1
        return warehouse

    # ------------------------------------------------------------------
    # Stock and offers
    # ------------------------------------------------------------------
    def _stock_and_offer_business(self, business, warehouse, index, business_type):
        variants = self._choose_variants(index, business_type)
        for variant in variants:
            self._stock_and_offer(business, warehouse, variant)
        self._ensure_root_coverage(business, warehouse, business_type)

    def _choose_variants(self, index, business_type):
        rng = random.Random(self.seed * 101 + index)
        target = rng.randint(6, 10)
        roots = list(business_type["roots"])
        base, remainder = divmod(target, len(roots))
        allocations = {
            root: base + (1 if position < remainder else 0)
            for position, root in enumerate(roots)
        }

        chosen = []
        seen = set()
        carry = 0
        for root in roots:
            pool = self._variant_pools.get(root) or []
            quota = allocations[root] + carry
            if not pool:
                carry = quota
                continue
            picks = []
            # One deterministic featured variant per root keeps a shared
            # product across every business of this type, which is what makes
            # offer comparison testable.
            for variant in pool[:1]:
                if variant.id not in seen:
                    picks.append(variant)
            remaining = [
                variant
                for variant in pool
                if variant.id not in seen and variant not in picks
            ]
            need = max(0, quota - len(picks))
            if need and remaining:
                picks.extend(rng.sample(remaining, min(len(remaining), need)))
            for variant in picks[:quota]:
                if variant.id in seen:
                    continue
                seen.add(variant.id)
                chosen.append(variant)
            carry = max(0, quota - len(picks))

        minimum = max(6, target)
        if len(chosen) < minimum:
            fallback = [
                variant
                for root in roots
                for variant in (self._variant_pools.get(root) or [])
            ]
            rng.shuffle(fallback)
            for variant in fallback:
                if variant.id in seen:
                    continue
                seen.add(variant.id)
                chosen.append(variant)
                if len(chosen) >= minimum:
                    break

        return chosen

    def _ensure_root_coverage(self, business, warehouse, business_type):
        """Converge older fixture runs that trimmed a category's variants.

        The selector allocates one slot per root, but data created by an
        earlier version (or a run interrupted mid-business) can leave a root
        without an offer.  Add one variant from that root instead of deleting
        and rebuilding the business's working data.
        """
        existing = list(
            BusinessOffer.objects.filter(business=business)
            .select_related("variant__product")
            .prefetch_related("variant__product__categories")
        )
        offered_variant_ids = {offer.variant_id for offer in existing}
        covered_roots = set()
        for offer in existing:
            covered_roots |= {
                self._root_by_category.get(category.id)
                for category in offer.variant.product.categories.all()
            }
        for root in business_type["roots"]:
            if root in covered_roots:
                continue
            pool = self._variant_pools.get(root) or []
            candidate = next(
                (
                    variant
                    for variant in pool
                    if variant.id not in offered_variant_ids
                ),
                None,
            )
            if candidate is None:
                continue
            self._stock_and_offer(business, warehouse, candidate)
            offered_variant_ids.add(candidate.id)
            covered_roots.add(root)

    def _stock_and_offer(self, business, warehouse, variant):
        inventory = Inventory.objects.filter(
            business=business, warehouse=warehouse, variant=variant
        ).first()
        if inventory is None:
            rng = random.Random(
                self.seed * 47 + business.id * 104_729 + variant.id
            )
            quantity = self._quantity(rng)
            if quantity > 0:
                unit_cost = self._unit_cost(variant)
                batches = [(quantity, unit_cost)]
                if rng.random() < 0.2:
                    batches.append(
                        (
                            max(1, quantity // 3),
                            (unit_cost * Decimal("1.05")).quantize(
                                Decimal("0.01")
                            ),
                        )
                    )
                for sequence, (batch_quantity, batch_cost) in enumerate(batches):
                    supply = self.supply_service.create_supply(
                        variant=variant,
                        warehouse=warehouse,
                        quantity=batch_quantity,
                        unit_buy_price=batch_cost,
                        supplied_at=timezone.now()
                        - timedelta(
                            days=rng.randint(2, 120), hours=rng.randint(0, 23)
                        ),
                        reference_number=(
                            f"SEED-{business.id:04d}-{variant.id:05d}-{sequence}"
                        ),
                        invoice_number=f"INV-{business.id:04d}-{variant.id:05d}",
                        notes="داده آزمایشی بازارگاه",
                        costs=self._supply_costs(
                            rng, batch_quantity, batch_cost
                        ),
                    )
                    self.supply_service.receive_supply(supply)
                    self.counts["supplies_created"] += 1
                total = sum(batch[0] for batch in batches)
                self.inventory_service.adjust_variant_stock(
                    variant,
                    business=business,
                    inventory={
                        "quantity": total,
                        "sellable": total,
                        "reserved": 0,
                        "min_stock": min(total, rng.randint(2, 8)),
                    },
                )
            inventory = Inventory.objects.filter(
                business=business, warehouse=warehouse, variant=variant
            ).first()

        if BusinessOffer.objects.filter(
            business=business, variant=variant
        ).exists():
            return

        rng = random.Random(
            self.seed * 53 + business.id * 104_729 + variant.id
        )
        unit_cost = self._unit_cost(variant)
        margin = Decimal(str(round(rng.uniform(0.08, 0.40), 2)))
        price = (unit_cost * (Decimal("1") + margin)).quantize(
            Decimal("1000"), rounding=ROUND_HALF_UP
        )
        if price <= 0:
            price = unit_cost

        discount_type = None
        discount_value = None
        roll = rng.random()
        if roll < 0.18:
            discount_type = "percentage"
            discount_value = Decimal(rng.choice((5, 10, 15, 20, 25)))
        elif roll < 0.30:
            candidate = (
                price * Decimal(str(round(rng.uniform(0.05, 0.15), 2)))
            ).quantize(Decimal("1000"), rounding=ROUND_HALF_UP)
            if 0 < candidate < price:
                discount_type = "fixed"
                discount_value = candidate

        sellable = inventory.sellable if inventory is not None else 0
        MarketplacePricingService.create_offer(
            business=business,
            variant=variant,
            price=price,
            discount_type=discount_type,
            discount_value=discount_value,
            expected_profit_percentage=(margin * 100).quantize(
                Decimal("0.01")
            ),
            cost_strategy=rng.choice(
                ("latest", "weighted_average", "fifo_next")
            ),
            is_active=bool(sellable > 0 and rng.random() >= 0.05),
        )
        self.counts["offers_created"] += 1

    def _unit_cost(self, variant):
        cached = self._unit_cost_cache.get(variant.id)
        if cached is not None:
            return cached
        category = variant.product.categories.order_by("id").first()
        band = None
        if category is not None:
            band = CATEGORY_PRICE_BANDS.get(category.id)
            if band is None:
                band = ROOT_PRICE_BANDS.get(
                    self._root_by_category.get(category.id)
                )
        if band is None:
            band = (200_000, 5_000_000)
        low, high = int(band[0]), int(band[1])
        rng = random.Random(variant.id * 7919 + 17)
        cost = Decimal(rng.randrange(low, max(low + 1000, high), 1000))
        self._unit_cost_cache[variant.id] = cost
        return cost

    @staticmethod
    def _quantity(rng):
        roll = rng.random()
        if roll < 0.05:
            return 0
        if roll < 0.15:
            return rng.randint(2, 5)
        if roll < 0.45:
            return rng.randint(6, 15)
        if roll < 0.8:
            return rng.randint(16, 40)
        return rng.randint(41, 100)

    @staticmethod
    def _supply_costs(rng, quantity, unit_cost):
        if rng.random() >= 0.2:
            return []
        return [
            {
                "type": "shipment",
                "amount": (
                    unit_cost * Decimal(quantity) * Decimal("0.02")
                ).quantize(Decimal("0.01")),
                "description": "هزینه ارسال محموله",
            }
        ]
