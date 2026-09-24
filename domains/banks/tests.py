from unittest.mock import Mock

from django.test import TestCase

from .models import Bank
from .services import BankService


class BankServiceTests(TestCase):
    def setUp(self):
        self.cache = Mock()
        self.service = BankService(cache=self.cache)

    def create_bank(self, *, name="Bank", fa_name="بانک", is_active=True):
        return Bank.objects.create(
            name=name,
            fa_name=fa_name,
            card_number_regex=r"^123456\d{10}$",
            account_number_regex=r"^\d{10,24}$",
            sheba_regex=r"^IR\d{24}$",
            is_active=is_active,
        )

    def test_list_banks_returns_cached_data_without_database_query(self):
        cached = [
            {
                "id": 100,
                "name": "National Bank of Iran",
                "fa_name": "بانک ملی ایران",
                "card_number_regex": r"^603799\d{10}$",
                "account_number_regex": r"^\d{10,24}$",
                "sheba_regex": r"^IR\d{24}$",
            }
        ]
        self.cache.get_public.return_value = cached

        with self.assertNumQueries(0):
            result = self.service.list_banks()

        self.assertEqual(result, cached)
        self.cache.get_public.assert_called_once_with("banks:active")
        self.cache.put_public.assert_not_called()

    def test_list_banks_queries_active_banks_and_caches_them_on_miss(self):
        active = self.create_bank(name="Mellat", fa_name="بانک ملت")
        self.create_bank(name="Inactive", fa_name="غیرفعال", is_active=False)
        self.cache.get_public.return_value = None

        with self.assertNumQueries(1):
            result = self.service.list_banks()

        self.assertEqual(
            result,
            [
                {
                    "id": active.id,
                    "name": "Mellat",
                    "fa_name": "بانک ملت",
                    "card_number_regex": r"^123456\d{10}$",
                    "account_number_regex": r"^\d{10,24}$",
                    "sheba_regex": r"^IR\d{24}$",
                }
            ],
        )
        self.cache.put_public.assert_called_once_with("banks:active", result)

    def test_list_banks_recognizes_an_empty_cached_list(self):
        self.cache.get_public.return_value = []

        with self.assertNumQueries(0):
            result = self.service.list_banks()

        self.assertEqual(result, [])
        self.cache.put_public.assert_not_called()

    def test_force_clear_cache_skips_read_and_refreshes_from_database(self):
        self.cache.get_public.return_value = [{"id": 1, "name": "Stale"}]
        active = self.create_bank(name="Fresh", fa_name="تازه")

        result = self.service.list_banks(force_clear_cache=True)

        self.cache.delete_public.assert_called_once_with("banks:active")
        self.cache.get_public.assert_not_called()
        self.assertEqual(result[0]["id"], active.id)
        self.cache.put_public.assert_called_once_with("banks:active", result)

    def test_cache_write_failure_does_not_fail_list_banks(self):
        active = self.create_bank()
        self.cache.get_public.return_value = None
        self.cache.put_public.return_value = False

        result = self.service.list_banks()

        self.assertEqual(result[0]["id"], active.id)
