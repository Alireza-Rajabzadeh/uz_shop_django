from enum import Enum


class PackageFeatureEnum(Enum):
    SHOP_PRODUCTS = 1
    SHOP_ORDERS = 2
    SHOP_CUSTOM_DOMAIN = 3
    SHOP_COUPONS = 4
    SHOP_ADVANCED_ANALYTICS = 5
    SHOP_MULTIPLE_WAREHOUSES = 6
    SHOP_API = 7
    CONTENT_LANDINGPAGE = 8

    @property
    def code(self) -> str:
        return {
            PackageFeatureEnum.SHOP_PRODUCTS: "shop.products",
            PackageFeatureEnum.SHOP_ORDERS: "shop.orders",
            PackageFeatureEnum.SHOP_CUSTOM_DOMAIN: "shop.custom_domain",
            PackageFeatureEnum.SHOP_COUPONS: "shop.coupons",
            PackageFeatureEnum.SHOP_ADVANCED_ANALYTICS: "shop.advanced_analytics",
            PackageFeatureEnum.SHOP_MULTIPLE_WAREHOUSES: "shop.multiple_warehouses",
            PackageFeatureEnum.SHOP_API: "shop.api",
            PackageFeatureEnum.CONTENT_LANDINGPAGE: "content.landingpage",
        }[self]
