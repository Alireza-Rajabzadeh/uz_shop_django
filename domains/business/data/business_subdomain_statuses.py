"""Initial reference rows for ``business.BusinessSubdomainStatus``.

Pure data: no model imports, so both migrations and seed commands
import it safely.
"""

BUSINESS_SUBDOMAIN_STATUS_SEED = [
    {"id": 1, "code": "active", "name": "Active", "title": "فعال"},
    {"id": 2, "code": "redirect", "name": "Redirect", "title": "هدایت شونده"},
    {"id": 3, "code": "reserved", "name": "Reserved", "title": "رزرو شده"},
]
