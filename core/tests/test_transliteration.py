from django.test import TestCase

from core.utils import (
    persian_to_finglish,
    to_english_letters,
    to_finglish,
    to_slug,
)
from domains.business.models import BusinessProfile


class TransliterationTests(TestCase):
    def test_to_finglish_converts_persian_letters(self):
        self.assertEqual(to_finglish("بانک ملی"), "bank mly")
        self.assertEqual(to_finglish("ورزشی پهلوان"), "vrzshy phlvan")
        self.assertEqual(to_finglish("chaarchu"), "chaarchu")
        self.assertEqual(persian_to_finglish("بانک تجارت"), "bank tjart")

    def test_to_slug_creates_clean_ascii_slug(self):
        self.assertEqual(to_slug("بانک ملی"), "bank-mly")
        self.assertEqual(to_slug("ورزشی پهلوان"), "vrzshy-phlvan")
        self.assertEqual(to_slug("  فروشگاه   آفتاب  "), "frvshgah-aftab")
        self.assertEqual(to_slug("Test & Co."), "test-co")
        self.assertEqual(to_slug("chaarchu"), "chaarchu")
        self.assertEqual(to_slug("baraf"), "baraf")
        self.assertEqual(to_slug(""), "")

    def test_ensure_initial_subdomain_generates_unique_slug_from_persian_name(self):
        from domains.business.services.business_subdomain_service import BusinessSubdomainService

        biz1 = BusinessProfile.objects.create(
            business_name="موبایل البرز",
            display_name="موبایل البرز",
        )
        sub1 = BusinessSubdomainService.ensure_initial_subdomain(biz1)
        self.assertTrue(sub1.subdomain)
        self.assertTrue(sub1.subdomain.isascii())
        self.assertEqual(sub1.subdomain, "mvbayl-albrz")

        # Second business with identical Persian name receives unique suffixed slug
        biz2 = BusinessProfile.objects.create(
            business_name="موبایل البرز",
            display_name="موبایل البرز",
        )
        sub2 = BusinessSubdomainService.ensure_initial_subdomain(biz2)
        self.assertEqual(sub2.subdomain, "mvbayl-albrz-1")
