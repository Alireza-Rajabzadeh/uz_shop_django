from django.db import transaction
from django.utils.translation import gettext as _

from domains.business.models import (
    BusinessProfile,
    BusinessProfileServiceMode,
    BusinessServiceMode,
)


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
