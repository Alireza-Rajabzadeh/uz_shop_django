from rest_framework.test import APITestCase

from core.management.seeders.business_service_modes import (
    BusinessServiceModeSeeder,
)
from domains.business.enums.BusinessStatusEnum import BusinessStatusEnum
from domains.business.models import (
    BusinessCategory,
    BusinessProfile,
    BusinessProfileServiceMode,
    BusinessServiceMode,
)
from domains.catalog.models import Category, CategoryStatus
from domains.location.models import City, Country, State

CARD_FIELDS = {
    "id",
    "name",
    "city",
    "logo_url",
    "availability_status",
    "service_modes",
}


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
            CARD_FIELDS,
        )

    def test_card_lists_only_active_service_modes(self):
        BusinessServiceModeSeeder().run()
        online = BusinessServiceMode.objects.get(code="online")
        in_person = BusinessServiceMode.objects.get(code="in_person")
        retired = BusinessServiceMode.objects.create(
            code="retired", name="Retired", is_active=False
        )
        BusinessProfileServiceMode.objects.create(
            business_profile=self.active, service_mode=online
        )
        BusinessProfileServiceMode.objects.create(
            business_profile=self.active, service_mode=in_person, is_active=False
        )
        BusinessProfileServiceMode.objects.create(
            business_profile=self.active, service_mode=retired
        )
        # Another listed business's selection stays on its own card.
        BusinessCategory.objects.create(business=self.other, category=self.root)
        BusinessProfileServiceMode.objects.create(
            business_profile=self.other, service_mode=in_person
        )

        cards = {
            item["name"]: item["service_modes"]
            for item in self.get(self.root.slug).data["data"]["results"]
        }

        self.assertEqual(cards["Alpha"], [{"code": "online", "name": "Online"}])
        self.assertEqual(cards["Gamma"], [{"code": "in_person", "name": "In Person"}])

    def test_card_service_modes_are_empty_without_configuration(self):
        response = self.get(self.root.slug)

        card = next(
            item for item in response.data["data"]["results"] if item["name"] == "Alpha"
        )
        self.assertEqual(card["service_modes"], [])

    def test_card_exposes_city_title(self):
        country = Country.objects.create(name="Iran", code="IR", phone_code="98")
        state = State.objects.create(country=country, name="Tehran")
        city = City.objects.create(state=state, name="Tehran", fa_title="تهران")
        self.active.city = city
        self.active.save(update_fields=["city"])

        response = self.get(self.root.slug)

        card = next(
            item for item in response.data["data"]["results"] if item["name"] == "Alpha"
        )
        self.assertEqual(card["city"], "تهران")

    def test_card_city_is_null_when_business_has_no_city(self):
        response = self.get(self.root.slug)

        card = next(
            item for item in response.data["data"]["results"] if item["name"] == "Alpha"
        )
        self.assertIsNone(card["city"])


class PublicBusinessDetailTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.active = BusinessProfile.objects.create(
            business_name="Alpha Trading",
            display_name="Alpha",
            status_id=BusinessStatusEnum.ACTIVE.value,
        )
        cls.pending = BusinessProfile.objects.create(
            business_name="Beta Trading",
            display_name="Beta",
            status_id=BusinessStatusEnum.CONFIRMATION_AWAIT.value,
        )

    def get(self, pk):
        return self.client.get(f"/api/business/public/{pk}")

    def test_active_business_returns_its_public_card(self):
        response = self.get(self.active.id)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(response.data["data"]), CARD_FIELDS)
        self.assertEqual(response.data["data"]["id"], self.active.id)
        self.assertEqual(response.data["data"]["name"], "Alpha")

    def test_detail_lists_active_service_modes(self):
        BusinessServiceModeSeeder().run()
        online = BusinessServiceMode.objects.get(code="online")
        BusinessProfileServiceMode.objects.create(
            business_profile=self.active, service_mode=online
        )

        response = self.get(self.active.id)

        self.assertEqual(
            response.data["data"]["service_modes"], [{"code": "online", "name": "Online"}]
        )

    def test_inactive_business_returns_404(self):
        self.assertEqual(self.get(self.pending.id).status_code, 404)

    def test_unknown_business_returns_404(self):
        self.assertEqual(self.get(999_999).status_code, 404)
