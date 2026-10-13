"""Initial package rows for ``packages.Package`` and their feature grants.

Pure data: no model imports, so the ``seed`` command can import it safely.

Three tiers for now. Prices below are **development placeholders**, not a
commercial decision — they exist so a fresh database has a non-empty package
table to exercise the API and the panels against. Repricing a tier is an
operator decision, done through ``PATCH /api/packages/admin/packages/<id>``;
the seeder will not overwrite an edited price on a later run.

``code`` is the identity: rows are looked up by it, never by ``id``, because
ids are not portable between environments.
"""

# (package code, feature code, config)
#
# Grants are expressed as codes for the same reason: an assignment must not
# depend on which rows happen to exist or in what order they were created.
PACKAGE_FEATURE_SEED = [
    # Free: enough to run a small shop, with the product ceiling that makes
    # upgrading the natural next step.
    ("free", "shop.products", {"enabled": True, "limit": 50}),
    ("free", "shop.orders", {"enabled": True}),
    # Plus: the storefront starts looking like a brand.
    ("plus", "shop.products", {"enabled": True, "limit": 2000}),
    ("plus", "shop.orders", {"enabled": True}),
    ("plus", "shop.coupons", {"enabled": True}),
    ("plus", "shop.custom_domain", {"enabled": True}),
    ("plus", "shop.advanced_analytics", {"enabled": True}),
    # Pro: everything, and the limits stop being the constraint.
    ("pro", "shop.products", {"enabled": True, "limit": 100000}),
    ("pro", "shop.orders", {"enabled": True}),
    ("pro", "shop.coupons", {"enabled": True}),
    ("pro", "shop.custom_domain", {"enabled": True}),
    ("pro", "shop.advanced_analytics", {"enabled": True}),
    ("pro", "shop.multiple_warehouses", {"enabled": True, "limit": 20}),
    ("pro", "shop.api", {"enabled": True}),
    ("pro", "content.landingpage", {"enabled": True}),
]

PACKAGE_SEED = [
    {
        "code": "free",
        "name": "Free",
        # Placeholder pricing; see the module docstring.
        "price": "0.00",
        "off_discount": "0.00",
        "is_active": True,
    },
    {
        "code": "plus",
        "name": "Plus",
        "price": "500000.00",
        "off_discount": "0.00",
        "is_active": True,
    },
    {
        "code": "pro",
        "name": "Pro",
        "price": "1500000.00",
        "off_discount": "0.00",
        "is_active": True,
    },
]
