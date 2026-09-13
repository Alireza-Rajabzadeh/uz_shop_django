from core.management.seeders.base import BaseSeeder
from domains.business.models import SocialMedia


class SocialMediaSeeder(BaseSeeder):
    PLATFORMS = [
        {"slug": "instagram", "name": "Instagram", "fa_name": "اینستاگرام", "position": 0},
        {"slug": "telegram", "name": "Telegram", "fa_name": "تلگرام", "position": 1},
        {"slug": "whatsapp", "name": "WhatsApp", "fa_name": "واتس\u200cاپ", "position": 2},
        {"slug": "twitter", "name": "Twitter/X", "fa_name": "توییتر / ایکس", "position": 3},
        {"slug": "facebook", "name": "Facebook", "fa_name": "فیسبوک", "position": 4},
        {"slug": "linkedin", "name": "LinkedIn", "fa_name": "لینکدین", "position": 5},
        {"slug": "youtube", "name": "YouTube", "fa_name": "یوتیوب", "position": 6},
        {"slug": "pinterest", "name": "Pinterest", "fa_name": "پینترست", "position": 7},
        {"slug": "tiktok", "name": "TikTok", "fa_name": "تیک\u200cتاک", "position": 8},
    ]

    def run(self):
        for platform in self.PLATFORMS:
            SocialMedia.objects.update_or_create(
                slug=platform["slug"],
                defaults={
                    "name": platform["name"],
                    "fa_name": platform["fa_name"],
                    "position": platform["position"],
                    "is_active": True,
                },
            )
