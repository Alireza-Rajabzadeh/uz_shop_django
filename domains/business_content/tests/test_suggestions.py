from django.db import IntegrityError, transaction
from django.test import TestCase
from rest_framework.test import APITestCase

from domains.vendor.enums.VendorStatusEnum import VendorStatusEnum
from domains.vendor.models import Vendor, VendorStatus

from ..data.suggestion_pages import SUGGESTION_PAGES
from ..models import SuggestionPage
from .factories import storefront_business

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
        # Every standard shop page is an ordinary full page, so all of them
        # are authored in the `page` context — which every current component
        # allows, leaving the palette unrestricted until a narrower context
        # is actually used.
        self.assertEqual(home.context, SuggestionPage.Context.PAGE)
        self.assertFalse(SuggestionPage.objects.get(slug="faq").required)

    def test_context_vocabulary_is_the_contract_vocabulary(self):
        # `contracts.ALLOWED_CONTEXTS` is what a contract may declare and
        # `SuggestionPage.Context` is what a row may hold; if they ever drift,
        # a suggestion could name a context no component recognises (or vice
        # versa) and the palette would silently empty out.
        from ..contracts import ALLOWED_CONTEXTS

        self.assertEqual(
            {choice.value for choice in SuggestionPage.Context}, ALLOWED_CONTEXTS
        )

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
        self.assertEqual(suggestion.context, "page")
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
        # membership. `context` is the exception — the editor filters its
        # component palette by it.
        self.assertEqual(
            set(rows[0]), {"id", "title", "descriptions", "required", "slug", "context"}
        )
        self.assertEqual(rows[0]["context"], "page")

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


class SuggestionContextEnforcementTests(APITestCase):
    """The API, not the palette, is what actually restricts a page.

    The panel filters its component picker by the suggestion holding the
    page's slug, but that is cosmetic — it only decides what gets *offered*.
    This holds the rule server-side, so a component outside the page's
    context is a 400 however it arrives.
    """

    PAGES_URL = "/api/business-content/vendor/pages"

    def setUp(self):
        vendor_status = VendorStatus.objects.create(
            id=VendorStatusEnum.ACTIVE.value, name="active", title="Active"
        )
        self.vendor = Vendor.objects.create_user(
            phone="09127770093",
            password="pass1234",
            first_name="Context",
            last_name="Vendor",
            national_id="11227770093",
            status=vendor_status,
        )
        self.client.force_authenticate(self.vendor)
        self.business = storefront_business()
        self.business.vendor = self.vendor
        self.business.save()

    @staticmethod
    def draft(components):
        return {
            "schema_version": 1,
            "contract_version": 4,
            "components": [
                {"id": f"item-{index}", "key": key, "version": 1, "props": props}
                for index, (key, props) in enumerate(components)
            ],
        }

    def test_every_standard_page_keeps_the_whole_vocabulary(self):
        # All eight suggestions are `page`, and every component declares
        # `page`, so the restriction costs nothing until a narrower context
        # is actually used.
        response = self.client.post(
            self.PAGES_URL,
            {
                "title": "About us",
                "slug": "about",
                "draft_content": self.draft(
                    [("picture", {"image": "/a.png", "altText": "About"})]
                ),
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201, response.data)

    def test_a_component_outside_the_pages_context_is_rejected(self):
        # `picture` declares page+section only; `social_links` also allows
        # footer, so the same page passes once the component matches.
        SuggestionPage.objects.filter(slug="faq").update(context="footer")
        rejected = self.client.post(
            self.PAGES_URL,
            {
                "title": "Questions",
                "slug": "faq",
                "draft_content": self.draft(
                    [("picture", {"image": "/q.png", "altText": "Q"})]
                ),
            },
            format="json",
        )
        accepted = self.client.post(
            self.PAGES_URL,
            {
                "title": "Questions",
                "slug": "faq",
                "draft_content": self.draft([("social_links", {})]),
            },
            format="json",
        )

        self.assertEqual(rejected.status_code, 400, rejected.data)
        self.assertEqual(accepted.status_code, 201, accepted.data)

    def test_a_slug_outside_the_standard_set_defaults_to_the_full_vocabulary(self):
        # No suggestion holds this slug, so it falls back to the default
        # context and the whole vocabulary stays available.
        response = self.client.post(
            self.PAGES_URL,
            {
                "title": "Size guide",
                "slug": "size-guide",
                "draft_content": self.draft(
                    [("picture", {"image": "/s.png", "altText": "Sizes"})]
                ),
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201, response.data)

    def test_updating_without_a_slug_still_resolves_the_stored_context(self):
        SuggestionPage.objects.filter(slug="faq").update(context="footer")
        created = self.client.post(
            self.PAGES_URL,
            {
                "title": "Questions",
                "slug": "faq",
                "draft_content": self.draft([("social_links", {})]),
            },
            format="json",
        )
        self.assertEqual(created.status_code, 201, created.data)

        # A PATCH that omits `slug` (the panel does on save) must still
        # resolve the context from the stored row, not fall back to `page`.
        response = self.client.patch(
            f"{self.PAGES_URL}/{created.data['data']['id']}",
            {"draft_content": self.draft([("picture", {"image": "/q.png", "altText": "Q"})])},
            format="json",
        )

        self.assertEqual(response.status_code, 400, response.data)
