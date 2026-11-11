from django.contrib.auth.models import User
from rest_framework.test import APITestCase


class LocationRootURLTests(APITestCase):
    def test_location_crud_is_mounted(self):
        admin = User.objects.create_superuser("location-root", password="password")
        self.client.force_authenticate(admin)
        self.assertEqual(self.client.get("/api/location/countries").status_code, 200)
