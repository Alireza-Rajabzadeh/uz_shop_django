from core.services import CacheService

from .models import Bank


class BankService:
    CACHE_KEY = "banks:active"
    RESPONSE_FIELDS = (
        "id",
        "name",
        "fa_name",
        "card_number_regex",
        "account_number_regex",
        "sheba_regex",
    )

    def __init__(self, cache=None):
        self.cache = cache if cache is not None else CacheService()

    def list_banks(self, *, force_clear_cache=False):
        if force_clear_cache:
            self.cache.delete_public(self.CACHE_KEY)
        else:
            cached = self.cache.get_public(self.CACHE_KEY)
            if cached is not None:
                return cached

        banks = list(
            Bank.objects.filter(is_active=True)
            .order_by("id")
            .values(*self.RESPONSE_FIELDS)
        )
        self.cache.put_public(self.CACHE_KEY, banks)
        return banks
