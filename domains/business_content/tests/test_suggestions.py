from django.db import IntegrityError, transaction
from django.test import TestCase
from rest_framework.test import APITestCase

from domains.vendor.enums.VendorStatusEnum import VendorStatusEnum
from domains.vendor.models import Vendor, VendorStatus

from ..data.suggestion_pages import SUGGESTION_PAGES
from ..models import SuggestionPage

SUGGESTION_URL = "/api/business-content/vendor/suggestions"


class SuggestionPageModelTests(TestCase):
    """A suggestion describes what the panel offers a vendor to create.

    It is shared reference data rather than authored content, so it carries no
    `business` owner — the per-business part of the flow is the `Page` the
    vendor ends up creating from it.
    """

    def test_seeds_the_standard_shop_pages_in_order(self):
        self.assertEqual(
            list(SuggestionPage.objects.values_list("slug", flat=True)),
            [row["slug"] for row in SUGGESTION_PAGES],
        )

        home = SuggestionPage.objects.get(slug="home")
        self.assertEqual(home.title, "خانه")
        self.assertTrue(home.required)
        self.assertTrue(home.activate)
        # The allowed-component vocabulary starts empty; which components a
        # suggestion may hold is decided separately.
        self.assertEqual(home.component_lists, [])
        self.assertFalse(SuggestionPage.objects.get(slug="faq").required)

    def test_table_name_and_field_defaults_for_a_later_row(self):
        suggestion = SuggestionPage.objects.create(
            title="Size guide", slug="size-guide"
        )

        self.assertEqual(
            SuggestionPage._meta.db_table, "business_content_suggestion_page"
        )
        self.assertEqual(suggestion.slug, "size-guide")
        self.assertEqual(suggestion.descriptions, "")
        self.assertFalse(suggestion.required)
        self.assertTrue(suggestion.activate)
        self.assertEqual(suggestion.component_lists, [])
        self.assertIsNotNone(suggestion.created_at)
        self.assertIsNotNone(suggestion.updated_at)

    def test_slug_is_unique_across_suggestions(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            SuggestionPage.objects.create(title="Duplicate", slug="about")

    def test_is_not_business_owned(self):
        # Unlike `Page` and `LandingPage`, every vendor loads the same
        # suggestions, so there is deliberately no `business` foreign key.
        field_names = {field.name for field in SuggestionPage._meta.fields}
        self.assertNotIn("business", field_names)


class VendorSuggestionEndpointTests(APITestCase):
    def setUp(self):
        vendor_status = VendorStatus.objects.create(
            id=VendorStatusEnum.ACTIVE.value, name="active", title="Active"
        )
        self.vendor = Vendor.objects.create_user(
            phone="09127770091",
            password="pass1234",
            first_name="Suggestion",
            last_name="Vendor",
            national_id="11227770091",
            status=vendor_status,
        )
        self.client.force_authenticate(self.vendor)

    def test_returns_active_suggestions_in_seeded_order(self):
        response = self.client.get(SUGGESTION_URL)

        self.assertEqual(response.status_code, 200, response.data)
        rows = response.data["data"]
        self.assertEqual(
            [row["slug"] for row in rows],
            [row["slug"] for row in SUGGESTION_PAGES],
        )
        # Management-only fields stay server-side: `activate` already decided
        # membership, and nothing consumes the component vocabulary yet.
        self.assertEqual(
            set(rows[0]), {"id", "title", "descriptions", "required", "slug"}
        )

    def test_deactivated_suggestions_are_not_offered(self):
        SuggestionPage.objects.filter(slug="faq").update(activate=False)

        response = self.client.get(SUGGESTION_URL)

        self.assertEqual(response.status_code, 200, response.data)
        slugs = [row["slug"] for row in response.data["data"]]
        self.assertNotIn("faq", slugs)
        self.assertIn("home", slugs)

    def test_requires_a_vendor_principal(self):
        self.client.force_authenticate(None)

        response = self.client.get(SUGGESTION_URL)

        self.assertIn(response.status_code, (401, 403))
