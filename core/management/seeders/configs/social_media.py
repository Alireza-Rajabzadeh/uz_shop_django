import json
from pathlib import Path

from core.management.seeders.base import BaseSeeder
from domains.business.models import SocialMedia


class SocialMediaSeeder(BaseSeeder):
    DATA_PATH = Path(__file__).resolve().parents[2] / "data" / "social_media.json"

    def __init__(self, data_path=None):
        self.data_path = Path(data_path) if data_path else self.DATA_PATH

    def _load_platforms(self):
        with self.data_path.open(encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data.get("platforms", [])
        return data

    @property
    def PLATFORMS(self):
        return self._load_platforms()

    def run(self):
        platforms = self._load_platforms()
        for platform in platforms:
            SocialMedia.objects.update_or_create(
                slug=platform["slug"],
                defaults={
                    "name": platform["name"],
                    "fa_name": platform["fa_name"],
                    "position": platform["position"],
                    "is_active": platform.get("is_active", True),
                },
            )
