import csv
from pathlib import Path

from core.management.seeders.base import BaseSeeder
from core.utils.transliteration import persian_to_latin
from domains.location.models import Country, State, City

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


class LocationSeeder(BaseSeeder):
    def run(self):
        iran, _ = Country.objects.update_or_create(
            code="IR",
            defaults={
                "name": "Iran",
                "fa_title": "\u0627\u06cc\u0631\u0627\u0646",
                "phone_code": "+98",
            },
        )

        cities_by_province = {}
        with open(DATA_DIR / "iran_cities.csv", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                pid = row["province_id"]
                cities_by_province.setdefault(pid, []).append(row["name"])

        with open(DATA_DIR / "iran_provinces.csv", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                fa_name = row["name"]
                state, _ = State.objects.update_or_create(
                    country=iran,
                    name=persian_to_latin(fa_name),
                    defaults={"fa_title": fa_name},
                )
                for city_fa in cities_by_province.get(row["id"], []):
                    City.objects.update_or_create(
                        state=state,
                        name=persian_to_latin(city_fa),
                        defaults={"fa_title": city_fa},
                    )
