"""Predefined rows for ``business.BusinessServiceMode``.

Pure data: no model imports, so the ``seed`` command can import it safely.

``code`` is the stable contract callers key off, so it is written once and
never renamed; ``name``, ``description``, and ``is_active`` stay editable.
The seeder creates missing rows only, so administrator edits are preserved.
A mode is retired with ``is_active=False``, not deleted.
"""

BUSINESS_SERVICE_MODE_SEED = [
    {
        "code": "online",
        "name": "Online",
        "description": "The business serves its customers online.",
        "is_active": True,
    },
    {
        "code": "in_person",
        "name": "In Person",
        "description": "The business serves its customers in person.",
        "is_active": True,
    },
]
