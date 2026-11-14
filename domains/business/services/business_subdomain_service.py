import logging
from datetime import timedelta
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from domains.business.enums import BusinessSubdomainEnum
from domains.business.models import (
    BusinessProfile,
    BusinessSubdomain,
    BusinessSubdomainStatus,
    RESERVED_SUBDOMAINS,
    validate_subdomain_format,
)

logger = logging.getLogger(__name__)


class BusinessSubdomainService:
    """Manages lifecycle, eligibility, validation, and transitions for business subdomains."""

    FIRST_CHANGE_COOLDOWN_DAYS = 30
    SUBSEQUENT_CHANGE_COOLDOWN_DAYS = 90

    @classmethod
    def check_availability(cls, subdomain: str, current_business=None) -> dict:
        """Check whether a subdomain string is valid and available for registration."""
        if not subdomain:
            return {
                "available": False,
                "subdomain": "",
                "reason": "Subdomain cannot be empty.",
            }

        try:
            cleaned = validate_subdomain_format(subdomain)
        except (DjangoValidationError, ValidationError) as exc:
            msg = exc.messages[0] if hasattr(exc, "messages") else str(exc)
            return {
                "available": False,
                "subdomain": str(subdomain).strip().lower(),
                "reason": msg,
            }

        # Check reserved subdomains
        if cleaned in RESERVED_SUBDOMAINS or BusinessSubdomain.objects.filter(
            subdomain=cleaned, status_id=BusinessSubdomainEnum.RESERVED.value
        ).exists():
            return {
                "available": False,
                "subdomain": cleaned,
                "reason": "This subdomain is reserved.",
            }

        # Check existing subdomain records (active, redirect, or reserved)
        existing = BusinessSubdomain.objects.filter(subdomain=cleaned).first()
        if existing:
            if (
                current_business
                and existing.business_id == getattr(current_business, "id", None)
                and existing.status_id == BusinessSubdomainEnum.ACTIVE.value
            ):
                return {
                    "available": False,
                    "subdomain": cleaned,
                    "reason": "This is already your active subdomain.",
                }
            return {
                "available": False,
                "subdomain": cleaned,
                "reason": "This subdomain is already taken.",
            }

        return {
            "available": True,
            "subdomain": cleaned,
            "reason": None,
        }

    @classmethod
    def resolve_subdomain(cls, subdomain: str) -> dict:
        """Resolve a subdomain string to its status, business, and canonical active subdomain.

        Statuses returned:
        - ACTIVE: Active storefront subdomain for a live business.
        - REDIRECT: Historical subdomain pointing to a canonical active subdomain.
        - RESERVED: Platform-reserved subdomain not usable as a storefront.
        - UNKNOWN: Subdomain does not exist or associated business is inactive.
        - INVALID: Subdomain does not conform to format requirements.
        """
        if not subdomain:
            return {
                "status": "UNKNOWN",
                "subdomain": "",
                "business": None,
                "canonical_subdomain": None,
                "error": "Subdomain cannot be empty.",
            }

        try:
            cleaned = validate_subdomain_format(subdomain)
        except (DjangoValidationError, ValidationError) as exc:
            msg = exc.messages[0] if hasattr(exc, "messages") else str(exc)
            return {
                "status": "INVALID",
                "subdomain": str(subdomain).strip().lower(),
                "business": None,
                "canonical_subdomain": None,
                "error": msg,
            }

        if cleaned in RESERVED_SUBDOMAINS:
            return {
                "status": "RESERVED",
                "subdomain": cleaned,
                "business": None,
                "canonical_subdomain": None,
                "error": "This subdomain is reserved.",
            }

        record = (
            BusinessSubdomain.objects.filter(subdomain=cleaned)
            .select_related("business", "business__status", "status")
            .first()
        )
        if not record:
            return {
                "status": "UNKNOWN",
                "subdomain": cleaned,
                "business": None,
                "canonical_subdomain": None,
                "error": "Business not found.",
            }

        status_id = getattr(record.status, "id", record.status_id)

        if status_id == BusinessSubdomainEnum.RESERVED.value:
            return {
                "status": "RESERVED",
                "subdomain": cleaned,
                "business": None,
                "canonical_subdomain": None,
                "error": "This subdomain is reserved.",
            }

        if status_id == BusinessSubdomainEnum.REDIRECT.value:
            canonical = (
                BusinessSubdomain.objects.filter(
                    business=record.business,
                    status_id=BusinessSubdomainEnum.ACTIVE.value,
                )
                .first()
            )
            return {
                "status": "REDIRECT",
                "subdomain": cleaned,
                "business": record.business,
                "canonical_subdomain": canonical.subdomain if canonical else None,
                "error": None,
            }

        if status_id == BusinessSubdomainEnum.ACTIVE.value:
            from domains.business.enums.BusinessStatusEnum import BusinessStatusEnum
            biz = record.business
            if biz and getattr(biz.status, "id", biz.status_id) == BusinessStatusEnum.ACTIVE.value:
                return {
                    "status": "ACTIVE",
                    "subdomain": cleaned,
                    "business": biz,
                    "canonical_subdomain": cleaned,
                    "error": None,
                }
            return {
                "status": "UNKNOWN",
                "subdomain": cleaned,
                "business": None,
                "canonical_subdomain": None,
                "error": "Business is not active.",
            }

        return {
            "status": "UNKNOWN",
            "subdomain": cleaned,
            "business": None,
            "canonical_subdomain": None,
            "error": "Unrecognized subdomain status.",
        }

    @classmethod
    def get_active_subdomain(cls, business: BusinessProfile):
        """Retrieve the current active subdomain for a business."""
        if not business or not business.pk:
            return None
        return BusinessSubdomain.objects.filter(
            business=business, status_id=BusinessSubdomainEnum.ACTIVE.value
        ).select_related("status").first()

    @classmethod
    def check_eligibility(cls, business: BusinessProfile) -> dict:
        """Evaluate if the business is eligible to change its subdomain."""
        if not business or not business.pk:
            return {
                "can_change": False,
                "is_first_change": True,
                "days_remaining": cls.FIRST_CHANGE_COOLDOWN_DAYS,
                "next_allowed_date": None,
                "message": "Business profile not found.",
            }

        now = timezone.now()
        created_at = business.created_at or now

        # Determine if this is the first change by inspecting historical REDIRECT records
        redirects = BusinessSubdomain.objects.filter(
            business=business, status_id=BusinessSubdomainEnum.REDIRECT.value
        ).order_by("-updated_at", "-created_at")

        is_first_change = not redirects.exists()

        if is_first_change:
            target_date = created_at + timedelta(days=cls.FIRST_CHANGE_COOLDOWN_DAYS)
        else:
            latest_redirect = redirects.first()
            last_change_time = latest_redirect.updated_at or latest_redirect.created_at
            target_date = last_change_time + timedelta(days=cls.SUBSEQUENT_CHANGE_COOLDOWN_DAYS)

        if now >= target_date:
            return {
                "can_change": True,
                "is_first_change": is_first_change,
                "days_remaining": 0,
                "next_allowed_date": target_date.isoformat(),
                "message": "You are eligible to change your subdomain.",
            }

        diff = target_date - now
        days_remaining = max(1, diff.days + (1 if diff.seconds > 0 else 0))

        if is_first_change:
            msg = f"First subdomain change is allowed only after {cls.FIRST_CHANGE_COOLDOWN_DAYS} days from registration ({days_remaining} days remaining)."
        else:
            msg = f"Subdomain can only be changed once every {cls.SUBSEQUENT_CHANGE_COOLDOWN_DAYS} days ({days_remaining} days remaining)."

        return {
            "can_change": False,
            "is_first_change": is_first_change,
            "days_remaining": days_remaining,
            "next_allowed_date": target_date.isoformat(),
            "message": msg,
        }

    @classmethod
    def change_subdomain(
        cls,
        business: BusinessProfile,
        new_subdomain: str,
        confirmed: bool = False,
    ) -> BusinessSubdomain:
        """Atomically change a business's active subdomain with database locking."""
        if not confirmed:
            raise ValidationError(
                {"confirmed": ["Explicit confirmation is required to change your subdomain."]}
            )

        with transaction.atomic():
            locked_business = BusinessProfile.objects.select_for_update().get(id=business.id)

            eligibility = cls.check_eligibility(locked_business)
            if not eligibility["can_change"]:
                raise ValidationError({"subdomain": [eligibility["message"]]})

            availability = cls.check_availability(new_subdomain, current_business=locked_business)
            if not availability["available"]:
                raise ValidationError({"subdomain": [availability["reason"]]})

            cleaned = availability["subdomain"]

            current_active = (
                BusinessSubdomain.objects.select_for_update()
                .filter(
                    business=locked_business,
                    status_id=BusinessSubdomainEnum.ACTIVE.value,
                )
                .first()
            )

            if current_active and current_active.subdomain == cleaned:
                raise ValidationError({"subdomain": ["This is already your active subdomain."]})

            # Double-check inside locked transaction to prevent concurrent claims
            if BusinessSubdomain.objects.filter(subdomain=cleaned).exists():
                raise ValidationError({"subdomain": ["This subdomain is already taken."]})

            # 1. Historical active record transitions to REDIRECT
            if current_active:
                current_active.status_id = BusinessSubdomainEnum.REDIRECT.value
                current_active.save(update_fields=["status", "updated_at"])

            # 2. New ACTIVE record is created
            new_active = BusinessSubdomain.objects.create(
                business=locked_business,
                subdomain=cleaned,
                status_id=BusinessSubdomainEnum.ACTIVE.value,
            )

            return new_active

    @classmethod
    def get_subdomain_history(cls, business: BusinessProfile):
        """Retrieve all current and historical subdomains for this business."""
        return BusinessSubdomain.objects.filter(
            business=business
        ).select_related("status").order_by("-created_at")

    @classmethod
    def ensure_initial_subdomain(cls, business: BusinessProfile, preferred: str = None) -> BusinessSubdomain:
        """Ensure an active BusinessSubdomain exists for a newly created or existing business."""
        active = BusinessSubdomain.objects.filter(
            business=business, status_id=BusinessSubdomainEnum.ACTIVE.value
        ).first()
        if active:
            return active

        from core.utils import to_slug

        base_slug = ""
        if preferred:
            base_slug = to_slug(preferred)
        if not base_slug:
            base_slug = to_slug(business.business_name or business.display_name or f"shop-{business.id or ''}")
        if not base_slug or len(base_slug) < 3:
            base_slug = f"shop-{business.id or '1'}"
        if len(base_slug) > 25:
            base_slug = base_slug[:25].rstrip("-")

        candidate = base_slug
        idx = 1
        while (
            candidate in RESERVED_SUBDOMAINS
            or BusinessSubdomain.objects.filter(subdomain=candidate).exists()
        ):
            candidate = f"{base_slug[:24]}-{idx}"
            idx += 1

        active_status, _ = BusinessSubdomainStatus.objects.get_or_create(
            id=BusinessSubdomainEnum.ACTIVE.value,
            defaults={"code": "active", "name": "Active", "title": "فعال"},
        )
        return BusinessSubdomain.objects.create(
            business=business,
            subdomain=candidate,
            status=active_status,
        )
