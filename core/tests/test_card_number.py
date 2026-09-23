from django.test import SimpleTestCase
from django.utils import translation

from core.utils import CardNumberValidationError, normalize_card_number


class NormalizeCardNumberTests(SimpleTestCase):
    def test_accepts_sixteen_digits(self):
        self.assertEqual(
            normalize_card_number("6104337890123456"), "6104337890123456"
        )

    def test_strips_spaces_and_hyphens(self):
        self.assertEqual(
            normalize_card_number("6104 3378-9012 3456"), "6104337890123456"
        )

    def test_converts_persian_digits(self):
        self.assertEqual(
            normalize_card_number("۶۱۰۴۳۳۷۸۹۰۱۲۳۴۵۶"), "6104337890123456"
        )

    def test_rejects_fifteen_digits(self):
        with self.assertRaises(CardNumberValidationError):
            normalize_card_number("610433789012345")

    def test_rejects_seventeen_digits(self):
        with self.assertRaises(CardNumberValidationError):
            normalize_card_number("61043378901234567")

    def test_rejects_letters(self):
        with self.assertRaises(CardNumberValidationError):
            normalize_card_number("610433789012345a")

    def test_rejects_none(self):
        with self.assertRaises(CardNumberValidationError):
            normalize_card_number(None)

    def test_rejects_empty(self):
        with self.assertRaises(CardNumberValidationError):
            normalize_card_number("")

    def test_length_error_translates_to_farsi(self):
        with translation.override("fa"):
            with self.assertRaises(CardNumberValidationError) as ctx:
                normalize_card_number("1234")
        self.assertEqual(
            str(ctx.exception), "شماره کارت باید ۱۶ رقمی باشد."
        )
