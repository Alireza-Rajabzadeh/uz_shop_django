from decimal import Decimal

from django.db import transaction

from domains.business.models import (
    BusinessProfileServiceMode,
    BusinessServiceMode,
    BusinessShipment,
)
from domains.shipment.models import ShipmentMethod
from domains.shipment.services import ShipmentPricingService

from .business_shipment_service import BusinessShipmentService


class BusinessOnboardingService:
    """Initial fulfilment selections for a newly registered business.

    A vendor's first store setup fills the two reference vocabularies so the
    onboarding wizard opens with a usable baseline instead of empty screens:

    - the ``online`` service mode is enabled;
    - a draft ``vendor_delivery`` / ``fixed`` shipment is created so the
      vendor only has to set a cost and switch it on. It is deliberately
      inactive and not the default: a zero-cost active row would publish free
      shipping before anyone priced it.

    The initializer is create-only and tolerant of an unseeded environment: a
    missing reference row means the vocabulary was not provisioned, so that
    half is skipped rather than making store creation fail. It never raises
    ``ValidationError`` for reference data; the wizard steps are the place
    where the vendor makes the real choice.

    Called from the vendor profile-creation view, not from ``save()``, so
    fixtures, admin paths, and tests keep creating bare profiles.
    """

    DEFAULT_SERVICE_MODE_CODE = "online"
    DEFAULT_SHIPMENT_METHOD_CODE = "vendor_delivery"
    DEFAULT_PRICING_METHOD_CODE = ShipmentPricingService.FIXED_CODE
    DRAFT_SHIPMENT_COST = Decimal("0.00")

    @classmethod
    @transaction.atomic
    def initialize(cls, business):
        cls._enable_default_service_mode(business)
        cls._create_draft_shipment(business)
        cls._ensure_subdomain(business)
        return business

    @staticmethod
    def _ensure_subdomain(business):
        from .business_subdomain_service import BusinessSubdomainService

        try:
            BusinessSubdomainService.ensure_initial_subdomain(business)
        except Exception:
            pass

    @staticmethod
    def _enable_default_service_mode(business):
        mode = BusinessServiceMode.objects.filter(
            code=BusinessOnboardingService.DEFAULT_SERVICE_MODE_CODE,
            is_active=True,
        ).first()
        if mode is None:
            return None
        configuration, _ = BusinessProfileServiceMode.objects.get_or_create(
            business_profile=business,
            service_mode=mode,
            defaults={"is_active": True},
        )
        return configuration

    @classmethod
    def _create_draft_shipment(cls, business):
        method = ShipmentMethod.objects.filter(
            code=cls.DEFAULT_SHIPMENT_METHOD_CODE, is_active=True
        ).first()
        if method is None:
            return None
        try:
            pricing_method = ShipmentPricingService.resolve_method(
                cls.DEFAULT_PRICING_METHOD_CODE
            )
        except ShipmentPricingService.ValidationError:
            return None
        # Create-only: a business that already configured shipping keeps it.
        if BusinessShipment.objects.filter(business=business).exists():
            return None
        return BusinessShipmentService.create_shipment(
            business,
            shipment_method=method,
            pricing_method=pricing_method,
            cost=cls.DRAFT_SHIPMENT_COST,
            is_default=False,
            is_active=False,
        )
