from django.db import transaction
from django.db.models import Q

from .enums.BusinessStatusEnum import BusinessStatusEnum
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
