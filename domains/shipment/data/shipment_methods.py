"""Predefined rows for ``shipment.ShipmentMethod``.

Pure data: no model imports, so the ``seed`` command can import it safely.

``code`` is the stable contract. A code is written once and never renamed;
``name``, ``description``, and ``is_active`` stay editable. The list is a
platform catalogue only — it does not claim that every business supports
every method.
"""

SHIPMENT_METHOD_SEED = [
    {
        "code": "vendor_delivery",
        "name": "Vendor Delivery",
        "description": "The vendor delivers the order directly to the customer.",
        "is_active": True,
    },
    {
        "code": "post",
        "name": "Post",
        "description": "Delivery through the postal service.",
        "is_active": True,
    },
    {
        "code": "courier",
        "name": "Courier",
        "description": "Delivery through a courier service.",
        "is_active": True,
    },
    {
        "code": "customer_pickup",
        "name": "Customer Pickup",
        "description": "The customer collects the order from the vendor.",
        "is_active": True,
    },
]
