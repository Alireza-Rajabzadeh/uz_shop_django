from .business_payment_channels import BusinessPaymentChannelsSeeder
from .customers import CustomerSeeder, FakeCustomerSeeder
from .inventory_stock import InventoryStockSeeder
from .vendor_marketplace_fixtures import VendorMarketplaceSeeder

DEVELOPING_SEEDERS = [
    CustomerSeeder,
    VendorMarketplaceSeeder,
    InventoryStockSeeder,
    BusinessPaymentChannelsSeeder,
]

DEVELOPING_SEEDERS_MAP = {
    "customers": CustomerSeeder,
    "vendor_marketplace": VendorMarketplaceSeeder,
    "inventory_stock": InventoryStockSeeder,
    "business_payment_channels": BusinessPaymentChannelsSeeder,
}

DEVELOPING_ALIASES = {
    "customer": "customers",
    "fake_customers": "customers",
    "fake_customer": "customers",
    "vendor_market_place": "vendor_marketplace",
    "vendormarketplace": "vendor_marketplace",
    "vendors": "vendor_marketplace",
    "vendor": "vendor_marketplace",
    "marketplace": "vendor_marketplace",
    "fixtures": "vendor_marketplace",
    "vendor_marketplace_fixtures": "vendor_marketplace",
    "stock": "inventory_stock",
    "inventory": "inventory_stock",
    "inventorystock": "inventory_stock",
    "payment_channels": "business_payment_channels",
    "payment_channel": "business_payment_channels",
    "business_payment_channel": "business_payment_channels",
    "channels": "business_payment_channels",
    "channel": "business_payment_channels",
}


def get_developing_seeder(name: str):
    if not name:
        return None
    key = name.strip().lower().replace("-", "_")
    if key.endswith("seeder"):
        key = key[:-6].rstrip("_")
    if key in DEVELOPING_SEEDERS_MAP:
        return DEVELOPING_SEEDERS_MAP[key]
    if key in DEVELOPING_ALIASES:
        return DEVELOPING_SEEDERS_MAP[DEVELOPING_ALIASES[key]]
    return None


__all__ = [
    "BusinessPaymentChannelsSeeder",
    "CustomerSeeder",
    "FakeCustomerSeeder",
    "InventoryStockSeeder",
    "VendorMarketplaceSeeder",
    "DEVELOPING_SEEDERS",
    "DEVELOPING_SEEDERS_MAP",
    "get_developing_seeder",
]
