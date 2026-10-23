from django.db import transaction
from django.db.models import Q

from .models import BusinessCategory, BusinessPhone, BusinessProfile, BusinessSocialLink, BusinessWorkingDay, RecordStatus, Visibility


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
