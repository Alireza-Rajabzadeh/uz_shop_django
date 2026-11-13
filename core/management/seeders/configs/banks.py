import json
from pathlib import Path

from core.management.seeders.base import BaseSeeder
from domains.banks.models import Bank


class BankSeeder(BaseSeeder):
    DATA_PATH = Path(__file__).resolve().parents[2] / "data" / "banks.json"
    ACCOUNT_NUMBER_REGEX = r"^\d{10,24}$"
    SHEBA_REGEX = r"^IR\d{24}$"

    def __init__(self, data_path=None):
        self.data_path = Path(data_path) if data_path else self.DATA_PATH

    def _load_banks(self):
        with self.data_path.open(encoding="utf-8") as f:
            data = json.load(f)

        if isinstance(data, dict):
            banks = data.get("banks", [])
        elif isinstance(data, list):
            banks = data
        else:
            raise ValueError(
                "Invalid banks data format: expected list or object with 'banks' array."
            )

        return banks

    @property
    def BANKS(self):
        """Backward-compatible attribute access."""
        return self._load_banks()

    def run(self):
        banks = self._load_banks()
        for record in banks:
            Bank.objects.update_or_create(
                id=record["id"],
                defaults={
                    "name": record["name"],
                    "fa_name": record["fa_name"],
                    "card_number_regex": record["card_number_regex"],
                    "account_number_regex": record.get(
                        "account_number_regex", self.ACCOUNT_NUMBER_REGEX
                    ),
                    "sheba_regex": record.get("sheba_regex", self.SHEBA_REGEX),
                    "is_active": record.get("is_active", True),
                },
            )
        self.sync_sequence(Bank)
