from .banks import BankSeeder
from .brands import BrandSeeder
from .business_payment_statuses import BusinessPaymentStatusSeeder
from .business_payments import BusinessPaymentMethodsSeeder
from .business_service_modes import BusinessServiceModeSeeder
from .business_statuses import BusinessStatusSeeder
from .business_subdomain_statuses import BusinessSubdomainStatusSeeder
from .categories import CategorySeeder
from .category_details import CategoryDetailSeeder
from .customer_statuses import CustomerStatusSeeder
from .inventory import InventorySeeder
from .inventory_attribute_definitions import InventoryAttributeDefinitionSeeder
from .location import LocationSeeder
from .marketplace import MarketplaceSeeder
from .marketplace_order import MarketplaceOrderSeeder
from .order import OrderSeeder
from .packages import PackagesSeeder
from .payments import PaymentsSeeder
from .product_statuses import ProductStatusSeeder
from .product_variant_statuses import ProductVariantStatusSeeder
from .shipment import ShipmentSeeder
from .social_media import SocialMediaSeeder
from .variant_attributes import VariantAttributeSeeder
from .vendor_product_statuses import VendorProductStatusSeeder
from .vendor_statuses import VendorStatusSeeder
from .vendors_club import VendorsClubSeeder

CONFIG_SEEDERS = [
    LocationSeeder,
    CategorySeeder,
    BrandSeeder,
    VariantAttributeSeeder,
    VendorStatusSeeder,
    BusinessStatusSeeder,
    BusinessSubdomainStatusSeeder,
    BusinessServiceModeSeeder,
    BusinessPaymentStatusSeeder,
    BusinessPaymentMethodsSeeder,
    BankSeeder,
    CategoryDetailSeeder,
    ProductStatusSeeder,
    ProductVariantStatusSeeder,
    VendorProductStatusSeeder,
    CustomerStatusSeeder,
    InventorySeeder,
    InventoryAttributeDefinitionSeeder,
    MarketplaceSeeder,
    OrderSeeder,
    MarketplaceOrderSeeder,
    PaymentsSeeder,
    SocialMediaSeeder,
    PackagesSeeder,
    ShipmentSeeder,
    VendorsClubSeeder,
]

CONFIG_SEEDERS_MAP = {
    "location": LocationSeeder,
    "categories": CategorySeeder,
    "brands": BrandSeeder,
    "variant_attributes": VariantAttributeSeeder,
    "vendor_statuses": VendorStatusSeeder,
    "business_statuses": BusinessStatusSeeder,
    "business_subdomain_statuses": BusinessSubdomainStatusSeeder,
    "business_service_modes": BusinessServiceModeSeeder,
    "business_payment_statuses": BusinessPaymentStatusSeeder,
    "business_payments": BusinessPaymentMethodsSeeder,
    "banks": BankSeeder,
    "category_details": CategoryDetailSeeder,
    "product_statuses": ProductStatusSeeder,
    "product_variant_statuses": ProductVariantStatusSeeder,
    "vendor_product_statuses": VendorProductStatusSeeder,
    "customer_statuses": CustomerStatusSeeder,
    "inventory": InventorySeeder,
    "inventory_attribute_definitions": InventoryAttributeDefinitionSeeder,
    "marketplace": MarketplaceSeeder,
    "order": OrderSeeder,
    "marketplace_order": MarketplaceOrderSeeder,
    "payments": PaymentsSeeder,
    "social_media": SocialMediaSeeder,
    "packages": PackagesSeeder,
    "shipment": ShipmentSeeder,
    "vendors_club": VendorsClubSeeder,
}

CONFIG_ALIASES = {
    "locations": "location",
    "category": "categories",
    "brand": "brands",
    "bank": "banks",
    "orders": "order",
    "marketplace_orders": "marketplace_order",
    "package": "packages",
    "shipments": "shipment",
    "social": "social_media",
    "vendor_club": "vendors_club",
    "customer_status": "customer_statuses",
    "vendor_status": "vendor_statuses",
    "business_status": "business_statuses",
    "business_payment_status": "business_payment_statuses",
    "business_payment_method": "business_payments",
    "business_payment_methods": "business_payments",
    "variant_attribute": "variant_attributes",
    "category_detail": "category_details",
    "product_status": "product_statuses",
    "product_variant_status": "product_variant_statuses",
    "vendor_product_status": "vendor_product_statuses",
    "inventory_attribute_definition": "inventory_attribute_definitions",
    "inventory_attributes": "inventory_attribute_definitions",
}


def get_config_seeder(name: str):
    if not name:
        return None
    key = name.strip().lower().replace("-", "_")
    if key.endswith("seeder"):
        key = key[:-6].rstrip("_")
    if key in CONFIG_SEEDERS_MAP:
        return CONFIG_SEEDERS_MAP[key]
    if key in CONFIG_ALIASES:
        return CONFIG_SEEDERS_MAP[CONFIG_ALIASES[key]]
    return None


__all__ = [
    "BankSeeder",
    "BrandSeeder",
    "BusinessPaymentMethodsSeeder",
    "BusinessPaymentStatusSeeder",
    "BusinessServiceModeSeeder",
    "BusinessStatusSeeder",
    "BusinessSubdomainStatusSeeder",
    "CategoryDetailSeeder",
    "CategorySeeder",
    "CustomerStatusSeeder",
    "InventoryAttributeDefinitionSeeder",
    "InventorySeeder",
    "LocationSeeder",
    "MarketplaceOrderSeeder",
    "MarketplaceSeeder",
    "OrderSeeder",
    "PackagesSeeder",
    "PaymentsSeeder",
    "ProductStatusSeeder",
    "ProductVariantStatusSeeder",
    "ShipmentSeeder",
    "SocialMediaSeeder",
    "VariantAttributeSeeder",
    "VendorProductStatusSeeder",
    "VendorStatusSeeder",
    "VendorsClubSeeder",
    "CONFIG_SEEDERS",
    "CONFIG_SEEDERS_MAP",
    "get_config_seeder",
]
