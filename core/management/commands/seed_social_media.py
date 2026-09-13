from django.core.management.base import BaseCommand

from core.management.seeders.social_media import SocialMediaSeeder


class Command(BaseCommand):
    help = "Seed social media platforms"

    def handle(self, *args, **kwargs):
        self.stdout.write("Running SocialMediaSeeder...")
        SocialMediaSeeder().run()
        self.stdout.write(self.style.SUCCESS("Social media seeding completed"))
