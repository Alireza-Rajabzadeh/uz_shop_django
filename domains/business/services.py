from .models import BusinessPhone, BusinessProfile, BusinessSocialLink, BusinessWorkingDay, RecordStatus, Visibility


class BusinessService:
    @staticmethod
    def public_data():
        return {
            "profile": BusinessProfile.objects.first(),
            "phones": BusinessPhone.objects.filter(status=RecordStatus.ACTIVE, visibility=Visibility.PUBLIC),
            "social_links": BusinessSocialLink.objects.filter(
                status=RecordStatus.ACTIVE, visibility=Visibility.PUBLIC
            ).select_related("logo_file__status"),
            "working_hours": BusinessWorkingDay.objects.all(),
        }
