"""Predefined rows for ``vendors_club.VendorClubActivity``.

Pure data: no model imports, so the ``seed`` command can import it safely.

``code`` is the contract. Another domain awards points by passing the code to
``PointsService.award_points``, so a code is written once and never renamed;
``name``, ``description``, and ``points`` stay editable display/business text.
An activity is retired by clearing ``is_active``, never by deleting it, because
ledger rows point at it for the life of the program.

The set is deliberately small: it covers the lifecycle a vendor already walks
(join, verify, list, sell) and gives each step a stable code to award against.
New earning rules are added here, not hard-coded in the service.
"""

VENDOR_CLUB_ACTIVITY_SEED = [
    {
        "code": "profile.completed",
        "name": "Complete profile",
        "description": "Vendor completed the required business profile information.",
        "points": 100,
        "is_active": True,
    },
    {
        "code": "business.verified",
        "name": "Verified business",
        "description": "The business profile passed verification.",
        "points": 150,
        "is_active": True,
    },
    {
        "code": "product.published",
        "name": "Publish a product",
        "description": "Vendor published a product to the catalog.",
        "points": 50,
        "is_active": True,
    },
    {
        "code": "first.order",
        "name": "First order",
        "description": "Vendor received their first order.",
        "points": 200,
        "is_active": True,
    },
    {
        "code": "order.delivered",
        "name": "Deliver an order",
        "description": "Vendor delivered an order to the customer.",
        "points": 25,
        "is_active": True,
    },
]
