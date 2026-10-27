from django.db import transaction
from django.db.models import Q
from django.utils.translation import gettext as _

from domains.shipment.services import ShipmentPricingService

from .enums.BusinessStatusEnum import BusinessStatusEnum
from .models import (
    BusinessCategory,
    BusinessPhone,
    BusinessProfile,
    BusinessProfileServiceMode,
    BusinessServiceMode,
    BusinessShipment,
    BusinessSocialLink,
    BusinessWorkingDay,
    RecordStatus,
    Visibility,
)


class BusinessService:
    @staticmethod
    def public_data():
        profile = BusinessProfile.objects.first()
        if profile is None:
            return {
                "profile": None,
                "phones": BusinessPhone.objects.none(),
                "social_links": BusinessSocialLink.objects.none(),
                "working_hours": BusinessWorkingDay.objects.none(),
            }
        working_hours = BusinessWorkingDay.objects.filter(vendor__isnull=True)
        if profile.vendor_id:
            working_hours = BusinessWorkingDay.objects.filter(
                Q(vendor=profile.vendor) | Q(vendor__isnull=True)
            )
        return {
            "profile": profile,
            "phones": BusinessPhone.objects.filter(
                Q(business=profile) | Q(business__isnull=True),
                status=RecordStatus.ACTIVE,
                visibility=Visibility.PUBLIC,
            ),
            "social_links": BusinessSocialLink.objects.filter(
                Q(business=profile) | Q(business__isnull=True),
                status=RecordStatus.ACTIVE,
                visibility=Visibility.PUBLIC,
            ).select_related("social_media", "icon__file__status"),
            "working_hours": working_hours,
        }

    @staticmethod
    def profile_categories(business):
        """The catalog categories one business is registered under."""
        return BusinessCategory.objects.filter(business=business).select_related("category")

    @staticmethod
    def root_category(category):
        """The top-level category a business registration belongs to.

        Only root categories can be registered against a business, so a
        child slug is resolved to its root before filtering.
        """
        seen = set()
        current = category
        while current.parent_id is not None and current.id not in seen:
            seen.add(current.id)
            current = current.parent
        return current

    @staticmethod
    def category_businesses(category, search=""):
        """Active businesses registered under a category's root."""
        root = BusinessService.root_category(category)
        queryset = BusinessProfile.objects.filter(
            status_id=BusinessStatusEnum.ACTIVE.value,
            categories__category_id=root.id,
        ).select_related("city", "light_logo__status", "dark_logo__status")
        if search:
            queryset = queryset.filter(
                Q(display_name__icontains=search)
                | Q(business_name__icontains=search)
            )
        return root, queryset.distinct().order_by("display_name", "id")

    @staticmethod
    @transaction.atomic
    def replace_profile_categories(business, category_ids):
        """Replace the whole registered-category set for one business.

        Only the difference is written, so a category that stays registered
        keeps its row and `created_at`.
        """
        existing_ids = set(
            BusinessCategory.objects.filter(business=business).values_list("category_id", flat=True)
        )
        new_ids = set(category_ids)
        to_remove = existing_ids - new_ids
        to_add = new_ids - existing_ids

        if to_remove:
            BusinessCategory.objects.filter(business=business, category_id__in=to_remove).delete()

        if to_add:
            BusinessCategory.objects.bulk_create([
                BusinessCategory(business=business, category_id=category_id) for category_id in to_add
            ])

        return BusinessService.profile_categories(business)


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


class BusinessServiceModeService:
    """Reads and writes one business profile's service-mode selections.

    Ownership is always a parameter: the caller (the vendor view) resolves the
    business profile from the authenticated vendor, and every lookup is scoped
    to it. The modes themselves stay a shared, seed-managed vocabulary; this
    service only selects from rows that are still globally active.
    """

    class ValidationError(Exception):
        def __init__(self, errors):
            self.errors = errors
            super().__init__(str(errors))

    @staticmethod
    def available_modes():
        """The globally active modes a profile may still enable."""
        return BusinessServiceMode.objects.filter(is_active=True).order_by("id")

    @staticmethod
    def list_configurations(business):
        return (
            BusinessProfileServiceMode.objects.filter(business_profile=business)
            .select_related("service_mode")
            .order_by("id")
        )

    @staticmethod
    def get_configuration(business, configuration_id, *, lock=False):
        queryset = BusinessProfileServiceMode.objects.select_related(
            "service_mode"
        )
        if lock:
            queryset = queryset.select_for_update()
        return queryset.filter(
            pk=configuration_id, business_profile=business
        ).first()

    @classmethod
    @transaction.atomic
    def enable_mode(cls, business, service_mode):
        cls._lock_business(business)
        if not service_mode.is_active:
            raise cls.ValidationError(
                {"service_mode": [_("This service mode is inactive.")]}
            )
        if BusinessProfileServiceMode.objects.filter(
            business_profile=business, service_mode=service_mode
        ).exists():
            raise cls.ValidationError(
                {
                    "service_mode": [
                        _(
                            "This service mode is already configured for this business."
                        )
                    ]
                }
            )
        return BusinessProfileServiceMode.objects.create(
            business_profile=business, service_mode=service_mode
        )

    @classmethod
    @transaction.atomic
    def set_configuration_active(cls, configuration, is_active):
        cls._lock_business(configuration.business_profile)
        configuration = (
            BusinessProfileServiceMode.objects.select_for_update()
            .select_related("service_mode")
            .get(pk=configuration.pk)
        )
        # Re-enabling must respect the global vocabulary; disabling an
        # existing selection always stays possible.
        if is_active and not configuration.service_mode.is_active:
            raise cls.ValidationError(
                {"service_mode": [_("This service mode is inactive.")]}
            )
        if configuration.is_active != is_active:
            configuration.is_active = is_active
            configuration.save(update_fields=["is_active", "updated_at"])
        return configuration

    @staticmethod
    def _lock_business(business):
        # Serialize selections for this profile, including the first one when
        # there is no configuration row to lock yet. The unique constraint
        # remains the final guard.
        BusinessProfile.objects.select_for_update().filter(pk=business.pk).first()
