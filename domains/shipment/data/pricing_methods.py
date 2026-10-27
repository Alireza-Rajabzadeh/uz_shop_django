"""Predefined rows for ``shipment.ShipmentPricingMethod``.

Pure data: no model imports, so the ``seed`` command can import it safely.

A row only declares that the pricing method exists. Its calculation lives in
``ShipmentPricingService``; adding a row for a future method here does not
give it an implementation.

``code`` is the stable contract and is written once. ``name``,
``description``, and ``is_active`` stay editable.
"""

SHIPMENT_PRICING_METHOD_SEED = [
    {
        "code": "fixed",
        "name": "Fixed Price",
        "description": "A fixed shipping cost configured by the business.",
        "is_active": True,
    },
]
