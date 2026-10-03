from django.db import IntegrityError, transaction
from django.test import TestCase

from ..models import SuggestionPage


class SuggestionPageModelTests(TestCase):
    """A suggestion describes what the panel offers a vendor to create.

    It is shared reference data rather than authored content, so it carries no
    `business` owner — the per-business part of the flow is the `Page` the
    vendor ends up creating from it.
    """

    def test_table_name_and_field_defaults(self):
        suggestion = SuggestionPage.objects.create(title="About us", slug="about")

        self.assertEqual(
            SuggestionPage._meta.db_table, "business_content_suggestion_page"
        )
        self.assertEqual(suggestion.title, "About us")
        self.assertEqual(suggestion.slug, "about")
        self.assertEqual(suggestion.descriptions, "")
        self.assertFalse(suggestion.required)
        self.assertTrue(suggestion.activate)
        # The allowed-component vocabulary starts empty; which components a
        # suggestion may hold is decided separately.
        self.assertEqual(suggestion.component_lists, [])
        self.assertIsNotNone(suggestion.created_at)
        self.assertIsNotNone(suggestion.updated_at)

    def test_slug_is_unique_across_suggestions(self):
        SuggestionPage.objects.create(title="About us", slug="about")

        with self.assertRaises(IntegrityError), transaction.atomic():
            SuggestionPage.objects.create(title="Duplicate", slug="about")

    def test_is_not_business_owned(self):
        # Unlike `Page` and `LandingPage`, every vendor loads the same
        # suggestions, so there is deliberately no `business` foreign key.
        field_names = {field.name for field in SuggestionPage._meta.fields}
        self.assertNotIn("business", field_names)
