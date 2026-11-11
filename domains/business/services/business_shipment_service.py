from django.db import transaction
from django.utils.translation import gettext as _

from domains.business.models import BusinessProfile, BusinessShipment
from domains.shipment.services import ShipmentPricingService


class BusinessShipmentService:
    """Reads and writes one business's shipment configurations.

    Business ownership is always a parameter: every lookup is scoped to the
    caller's business, and the caller (the vendor view) resolves that business
    from the authenticated vendor. Pricing rules stay in the shipping domain;
    this service only passes the configured cost and method through
    ``ShipmentPricingService``.
    """

    class ValidationError(Exception):
        def __init__(self, errors):
            self.errors = errors
            super().__init__(str(errors))

    @staticmethod
    def list_shipments(business):
        return (
            BusinessShipment.objects.filter(business=business)
            .select_related("shipment_method", "pricing_method")
            .order_by("-is_default", "id")
        )

    @staticmethod
    def get_shipment(business, shipment_id, *, lock=False):
        queryset = BusinessShipment.objects.select_related(
            "shipment_method", "pricing_method"
        )
        if lock:
            queryset = queryset.select_for_update()
        return queryset.filter(pk=shipment_id, business=business).first()

    @classmethod
    def default_shipment(cls, business):
        """The business's usable default, or ``None``.

        Inactive configurations, globally retired methods, and inactive
        pricing methods are excluded, so a future order flow cannot select a
        configuration the business can no longer offer.
        """
        return cls.available_shipments(business).filter(is_default=True).first()

    @classmethod
    def resolve_for_checkout(cls, business, shipment_id=None):
        """The shipment a checkout should use.

        Without an explicit id the business's default is used, falling back
        to its first usable configuration (most businesses configure one
        method, so a default row is not guaranteed). An explicit id must name
        a configuration this business can still offer.
        """
        queryset = cls.available_shipments(business)
        if shipment_id is None:
            return queryset.filter(is_default=True).first() or queryset.first()
        shipment = queryset.filter(pk=shipment_id).first()
        if shipment is None:
            raise cls.ValidationError({
                "shipment": [_("The selected shipment method is not available.")]
            })
        return shipment

    @staticmethod
    def available_shipments(business):
        return (
            BusinessShipment.objects.filter(
                business=business,
                is_active=True,
                shipment_method__is_active=True,
                pricing_method__is_active=True,
            )
            .select_related("shipment_method", "pricing_method")
            .order_by("-is_default", "id")
        )

    @classmethod
    @transaction.atomic
    def create_shipment(cls, business, **values):
        cls._lock_business(business)
        shipment_method = values["shipment_method"]
        pricing_method = values["pricing_method"]

        cls._require_active_shipment_method(shipment_method)
        values["cost"] = cls._validated_cost(pricing_method, values["cost"])

        if BusinessShipment.objects.filter(
            business=business, shipment_method=shipment_method
        ).exists():
            raise cls.ValidationError(
                {
                    "shipment_method": [
                        _("This shipment method is already configured for this business.")
                    ]
                }
            )

        if values.get("is_default") and values.get("is_active") is False:
            raise cls.ValidationError(
                {"is_default": [_("A default shipment method must be active.")]}
            )

        if values.get("is_default"):
            BusinessShipment.objects.filter(
                business=business, is_default=True
            ).update(is_default=False)

        return BusinessShipment.objects.create(business=business, **values)

    @classmethod
    @transaction.atomic
    def update_shipment(cls, shipment, **values):
        cls._lock_business(shipment.business)
        shipment = (
            BusinessShipment.objects.select_for_update()
            .select_related("shipment_method", "pricing_method")
            .get(pk=shipment.pk)
        )

        new_method = values.get("shipment_method", shipment.shipment_method)
        new_pricing = values.get("pricing_method", shipment.pricing_method)
        method_changed = new_method.pk != shipment.shipment_method_id
        pricing_changed = new_pricing.pk != shipment.pricing_method_id
        cost_changed = "cost" in values and values["cost"] != shipment.cost

        # Offering the configuration again (activate/default) also requires
        # the global method and pricing method to still be selectable.
        offering_again = (
            values.get("is_active") is True or values.get("is_default") is True
        )
        if method_changed or offering_again:
            cls._require_active_shipment_method(new_method)
        if (method_changed or pricing_changed or cost_changed or offering_again) and (
            not new_pricing.is_active
        ):
            raise cls.ValidationError(
                {"pricing_method": [_("This pricing method is inactive.")]}
            )

        if method_changed:
            if (
                BusinessShipment.objects.filter(
                    business=shipment.business, shipment_method=new_method
                )
                .exclude(pk=shipment.pk)
                .exists()
            ):
                raise cls.ValidationError(
                    {
                        "shipment_method": [
                            _(
                                "This shipment method is already configured for this business."
                            )
                        ]
                    }
                )

        # Revalidate through the shipping service only when the rule can
        # change. Deactivating an existing configuration must stay possible
        # even if its pricing method was retired globally in the meantime.
        if method_changed or pricing_changed or cost_changed:
            values["cost"] = cls._validated_cost(
                new_pricing, values.get("cost", shipment.cost)
            )

        effective_active = values.get("is_active", shipment.is_active)
        if values.get("is_default") is True and not effective_active:
            raise cls.ValidationError(
                {"is_default": [_("A default shipment method must be active.")]}
            )

        if values.get("is_active") is False:
            # A retired configuration cannot remain the default.
            values["is_default"] = False
        elif values.get("is_default") is True:
            BusinessShipment.objects.filter(
                business=shipment.business, is_default=True
            ).exclude(pk=shipment.pk).update(is_default=False)

        for field, value in values.items():
            setattr(shipment, field, value)
        shipment.save()
        return shipment

    @classmethod
    @transaction.atomic
    def delete_shipment(cls, shipment):
        cls._lock_business(shipment.business)
        shipment.delete()

    @classmethod
    def calculate_price(cls, shipment):
        """Price a usable configuration through the shipping service."""
        if not shipment.is_active:
            raise cls.ValidationError(
                {"shipment": [_("This shipment configuration is inactive.")]}
            )
        if not shipment.shipment_method.is_active:
            raise cls.ValidationError(
                {"shipment": [_("This shipment method is globally inactive.")]}
            )
        if not shipment.pricing_method.is_active:
            raise cls.ValidationError(
                {"shipment": [_("This pricing method is inactive.")]}
            )
        return cls._validated_cost(shipment.pricing_method, shipment.cost)

    @staticmethod
    def _lock_business(business):
        # Serialize shipment changes for this business, including the first
        # configuration when there is no shipment row to lock yet. The partial
        # unique index remains the final guard.
        BusinessProfile.objects.select_for_update().filter(pk=business.pk).first()

    @staticmethod
    def _require_active_shipment_method(shipment_method):
        if not shipment_method.is_active:
            raise BusinessShipmentService.ValidationError(
                {"shipment_method": [_("This shipment method is inactive.")]}
            )

    @staticmethod
    def _validated_cost(pricing_method, cost):
        try:
            return ShipmentPricingService().calculate(
                pricing_method, {"cost": cost}
            )
        except ShipmentPricingService.ValidationError as exc:
            raise BusinessShipmentService.ValidationError(exc.errors) from exc
