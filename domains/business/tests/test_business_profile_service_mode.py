from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.test import TestCase

from domains.business.models import (
    BusinessProfile,
    BusinessProfileServiceMode,
    BusinessServiceMode,
)


class BusinessProfileServiceModeModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.profile = BusinessProfile.objects.create(
            business_name="Mode Business", display_name="Mode Business"
        )
        cls.other_profile = BusinessProfile.objects.create(
            business_name="Other Business", display_name="Other Business"
        )
        cls.online = BusinessServiceMode.objects.create(
            code="online", name="Online"
        )
        cls.in_person = BusinessServiceMode.objects.create(
            code="in_person", name="In Person"
        )

    def test_a_mode_is_enabled_by_default(self):
        configuration = BusinessProfileServiceMode.objects.create(
            business_profile=self.profile, service_mode=self.online
        )

        self.assertTrue(configuration.is_active)

    def test_a_profile_cannot_select_the_same_mode_twice(self):
        BusinessProfileServiceMode.objects.create(
            business_profile=self.profile, service_mode=self.online
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                BusinessProfileServiceMode.objects.create(
                    business_profile=self.profile, service_mode=self.online
                )

    def test_different_profiles_may_select_the_same_mode(self):
        BusinessProfileServiceMode.objects.create(
            business_profile=self.profile, service_mode=self.online
        )
        BusinessProfileServiceMode.objects.create(
            business_profile=self.other_profile, service_mode=self.online
        )

        self.assertEqual(BusinessProfileServiceMode.objects.count(), 2)

    def test_deleting_a_profile_removes_its_selections(self):
        BusinessProfileServiceMode.objects.create(
            business_profile=self.profile, service_mode=self.online
        )
        profile_id = self.profile.pk

        self.profile.delete()

        self.assertFalse(
            BusinessProfileServiceMode.objects.filter(
                business_profile_id=profile_id
            ).exists()
        )
        self.assertTrue(BusinessServiceMode.objects.filter(pk=self.online.pk).exists())

    def test_a_selected_mode_cannot_be_deleted(self):
        BusinessProfileServiceMode.objects.create(
            business_profile=self.profile, service_mode=self.online
        )

        with self.assertRaises(ProtectedError):
            self.online.delete()

        self.assertTrue(BusinessServiceMode.objects.filter(pk=self.online.pk).exists())
