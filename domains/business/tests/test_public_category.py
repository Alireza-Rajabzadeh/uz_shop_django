from rest_framework.test import APITestCase

from domains.business.enums.BusinessStatusEnum import BusinessStatusEnum
from domains.business.models import BusinessCategory, BusinessProfile
from domains.catalog.models import Category, CategoryStatus


class PublicBusinessByCategoryTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.active_status, _ = CategoryStatus.objects.get_or_create(name="active")
        cls.inactive_status, _ = CategoryStatus.objects.get_or_create(name="inactive")

        cls.root = Category.objects.create(name="Mobile", status=cls.active_status)
        cls.child = Category.objects.create(
            name="Phones", parent=cls.root, status=cls.active_status
        )
        cls.other_root = Category.objects.create(
            name="Laptops", status=cls.active_status
        )
        cls.inactive_root = Category.objects.create(
            name="Disabled", status=cls.inactive_status
        )

        cls.active = cls.make_business(
            "Alpha Trading", "Alpha", BusinessStatusEnum.ACTIVE.value
        )
        cls.pending = cls.make_business(
            "Beta Trading", "Beta", BusinessStatusEnum.CONFIRMATION_AWAIT.value
        )
        cls.other = cls.make_business(
            "Gamma Trading", "Gamma", BusinessStatusEnum.ACTIVE.value
        )

        BusinessCategory.objects.create(business=cls.active, category=cls.root)
        BusinessCategory.objects.create(business=cls.pending, category=cls.root)
        BusinessCategory.objects.create(business=cls.other, category=cls.other_root)

    @classmethod
    def make_business(cls, business_name, display_name, status_id):
        return BusinessProfile.objects.create(
            business_name=business_name,
            display_name=display_name,
            status_id=status_id,
        )

    def get(self, slug, **params):
        return self.client.get(f"/api/business/category/{slug}", params)

    def names(self, response):
        return [item["name"] for item in response.data["data"]["results"]]

    def test_unknown_slug_returns_404(self):
        self.assertEqual(self.get("does-not-exist").status_code, 404)

    def test_only_active_businesses_are_listed(self):
        response = self.get(self.root.slug)

        self.assertEqual(response.status_code, 200)
        self.assertIn("Alpha", self.names(response))
        self.assertNotIn("Beta", self.names(response))

    def test_businesses_from_another_root_are_excluded(self):
        response = self.get(self.root.slug)

        self.assertNotIn("Gamma", self.names(response))

    def test_child_slug_resolves_to_root(self):
        response = self.get(self.child.slug)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.names(response), ["Alpha"])

    def test_inactive_root_returns_404(self):
        self.assertEqual(self.get(self.inactive_root.slug).status_code, 404)

    def test_search_matches_display_and_business_name(self):
        self.assertEqual(self.names(self.get(self.root.slug, q="Alpha")), ["Alpha"])
        self.assertEqual(self.names(self.get(self.root.slug, q="Alpha Trading")), ["Alpha"])
        self.assertEqual(self.names(self.get(self.root.slug, q="Gamma")), [])

    def test_pagination_envelope(self):
        for index in range(25):
            business = self.make_business(
                f"Business {index}", f"Business {index}", BusinessStatusEnum.ACTIVE.value
            )
            BusinessCategory.objects.create(business=business, category=self.root)

        first = self.get(self.root.slug)
        data = first.data["data"]
        self.assertEqual(data["count"], 26)
        self.assertIsNotNone(data["next"])
        self.assertIsNone(data["previous"])
        self.assertEqual(len(data["results"]), 20)

        second = self.get(self.root.slug, page=2)
        self.assertIsNotNone(second.data["data"]["previous"])

    def test_payload_exposes_only_public_card_fields(self):
        response = self.get(self.root.slug)

        self.assertEqual(
            set(response.data["data"]["results"][0]),
            {"id", "name", "logo_url", "availability_status"},
        )
