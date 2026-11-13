import json
import re
from decimal import Decimal
from pathlib import Path

from django.db import transaction

from core.management.seeders.base import BaseSeeder
from core.utils.transliteration import persian_to_latin
from domains.location.models import Country, State, City

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"


class LocationSeeder(BaseSeeder):
    COUNTRY_FILE = DATA_DIR / "country.json"
    PROVINCE_FILE = DATA_DIR / "province.json"
    CITIES_FILE = DATA_DIR / "cities.json"

    def __init__(self, country_file=None, province_file=None, cities_file=None):
        self.country_file = Path(country_file) if country_file else self.COUNTRY_FILE
        self.province_file = Path(province_file) if province_file else self.PROVINCE_FILE
        self.cities_file = Path(cities_file) if cities_file else self.CITIES_FILE

    @transaction.atomic
    def run(self):
        with open(self.country_file, encoding="utf-8") as f:
            countries = json.load(f)
        with open(self.province_file, encoding="utf-8") as f:
            provinces = json.load(f)
        with open(self.cities_file, encoding="utf-8") as f:
            cities = json.load(f)

        new_state_ids = {p["id"] for p in provinces}
        new_city_ids = {c["id"] for c in cities}

        # Free unique names on legacy states and cities to avoid unique constraint collisions
        for state in State.objects.select_for_update().exclude(id__in=new_state_ids):
            state.name = f"__legacy_state_{state.id}__"
            state.save(update_fields=["name"])

        for city in City.objects.select_for_update().exclude(id__in=new_city_ids):
            city.name = f"__legacy_city_{city.id}__"
            city.save(update_fields=["name"])

        # Seed countries
        for c in countries:
            Country.objects.update_or_create(
                id=c["id"],
                defaults={
                    "name": c.get("name_en") or c.get("name"),
                    "fa_title": c.get("name", ""),
                    "code": c.get("iso2"),
                    "phone_code": c.get("calling_code", ""),
                },
            )

        # Seed states / provinces
        seen_states = set()
        for p in provinces:
            name = p.get("name_en") or persian_to_latin(p.get("name", ""))
            if not name:
                name = f"state-{p['id']}"
            if (p["country_id"], name.lower()) in seen_states:
                name = f"{name}-{p['id']}"
            seen_states.add((p["country_id"], name.lower()))

            State.objects.update_or_create(
                id=p["id"],
                defaults={
                    "country_id": p["country_id"],
                    "name": name,
                    "fa_title": p.get("name", ""),
                },
            )

        # Seed cities
        seen_cities = set()
        for c in cities:
            state_id = c["province_id"]
            name = c.get("name_en") or persian_to_latin(c.get("name", ""))
            if not name:
                name = f"city-{c['id']}"
            if (state_id, name.lower()) in seen_cities:
                name = f"{name}-{c['id']}"
            seen_cities.add((state_id, name.lower()))

            lat = Decimal(str(c["latitude"])) if c.get("latitude") is not None else None
            lng = Decimal(str(c["longitude"])) if c.get("longitude") is not None else None

            City.objects.update_or_create(
                id=c["id"],
                defaults={
                    "state_id": state_id,
                    "name": name,
                    "fa_title": c.get("name", ""),
                    "latitude": lat,
                    "longitude": lng,
                },
            )

        # Remap legacy references if any exist
        self._remap_and_cleanup_legacy(new_state_ids, new_city_ids)

        self.sync_sequences(Country, State, City)

    def _remap_and_cleanup_legacy(self, new_state_ids, new_city_ids):
        def norm(s):
            if not s:
                return ""
            s = s.strip().replace("ي", "ی").replace("ك", "ک")
            return re.sub(r"\s*\d+$", "", s).strip()

        # Remap states
        new_states_by_norm = {norm(s.fa_title): s for s in State.objects.filter(id__in=new_state_ids)}
        for old_state in State.objects.exclude(id__in=new_state_ids):
            target = new_states_by_norm.get(norm(old_state.fa_title))
            if target:
                from domains.business.models import BusinessProfile
                from domains.customer.models import CustomerAddress

                BusinessProfile.objects.filter(province=old_state).update(province=target)
                CustomerAddress.objects.filter(state=old_state).update(state=target)

        # Remap cities
        new_cities_by_norm = {norm(c.fa_title): c for c in City.objects.filter(id__in=new_city_ids)}
        for old_city in City.objects.exclude(id__in=new_city_ids):
            target = new_cities_by_norm.get(norm(old_city.fa_title))
            if target:
                from domains.business.models import BusinessProfile
                from domains.inventory.models import Warehouse
                from domains.customer.models import CustomerAddress

                BusinessProfile.objects.filter(city=old_city).update(city=target)
                Warehouse.objects.filter(city=old_city).update(city=target)
                CustomerAddress.objects.filter(city=old_city).update(city=target, state=target.state)

        # Clean up unreferenced legacy records
        try:
            City.objects.exclude(id__in=new_city_ids).delete()
            State.objects.exclude(id__in=new_state_ids).delete()
        except Exception:
            pass
