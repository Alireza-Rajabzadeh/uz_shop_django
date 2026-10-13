"""Initial feature rows for ``packages.Feature``.

Pure data: no model imports, so a migration and the ``seed`` command can both
import it safely.

``code`` is the contract. Backend authorization and the panels' feature
availability checks read it, so a code is written once and never renamed;
``name`` and ``description`` stay editable display text.

The set mirrors the capabilities the shop already has a home for: products
and orders are the core, coupons and the custom domain are store dressing,
analytics and warehouses are growth, and ``shop.api`` is the integration
surface. ``content.landingpage`` gates the vendor's landing-page authoring.
"""

FEATURE_SEED = [
    {
        "code": "shop.products",
        "name": "Products",
        "description": "Create and manage product listings, variants, and media.",
    },
    {
        "code": "shop.orders",
        "name": "Orders",
        "description": "Accept, fulfil, and track customer orders.",
    },
    {
        "code": "shop.custom_domain",
        "name": "Custom domain",
        "description": "Serve the storefront from the merchant's own domain.",
    },
    {
        "code": "shop.coupons",
        "name": "Coupons",
        "description": "Issue discount codes against orders.",
    },
    {
        "code": "shop.advanced_analytics",
        "name": "Advanced analytics",
        "description": "Reporting beyond the baseline sales figures.",
    },
    {
        "code": "shop.multiple_warehouses",
        "name": "Multiple warehouses",
        "description": "Hold stock in more than one location.",
    },
    {
        "code": "shop.api",
        "name": "API access",
        "description": "Programmatic access to the merchant's shop data.",
    },
    {
        "code": "content.landingpage",
        "name": "Landing pages",
        "description": "Design and publish storefront landing pages.",
    },
]
