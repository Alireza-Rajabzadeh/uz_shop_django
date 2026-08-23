import csv
from pathlib import Path

from django.db import migrations


DATA_DIR = Path(__file__).resolve().parents[3] / "core" / "management" / "data"


def populate_coordinates(apps, schema_editor):
    City = apps.get_model("location", "City")
    State = apps.get_model("location", "State")

    with open(DATA_DIR / "iran_city_coordinates.csv", encoding="utf-8") as source:
        coordinates = {
            row["city_source_id"]: (row["latitude"], row["longitude"])
            for row in csv.DictReader(source)
        }
    with open(DATA_DIR / "iran_provinces.csv", encoding="utf-8") as source:
        provinces = {row["id"]: row["name"] for row in csv.DictReader(source)}

    city_coordinates = {}
    with open(DATA_DIR / "iran_cities.csv", encoding="utf-8") as source:
        for row in csv.DictReader(source):
            coordinate = coordinates.get(row["id"])
            if coordinate:
                city_coordinates[(provinces[row["province_id"]], row["name"])] = coordinate

    states = {
        state.fa_title: state.id
        for state in State.objects.filter(country__code="IR").only("id", "fa_title")
    }
    cities = list(City.objects.filter(state_id__in=states.values()))
    state_titles = {state_id: title for title, state_id in states.items()}
    changed = []
    for city in cities:
        coordinate = city_coordinates.get((state_titles[city.state_id], city.fa_title))
        if coordinate:
            city.latitude, city.longitude = coordinate
            changed.append(city)
    City.objects.bulk_update(changed, ["latitude", "longitude"])


def clear_coordinates(apps, schema_editor):
    apps.get_model("location", "City").objects.update(
        latitude=None, longitude=None
    )


class Migration(migrations.Migration):
    dependencies = [("location", "0004_city_coordinates")]

    operations = [migrations.RunPython(populate_coordinates, clear_coordinates)]
