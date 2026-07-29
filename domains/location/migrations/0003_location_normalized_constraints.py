from django.db import migrations, models
from django.db.models import F
from django.db.models.functions import Lower, Trim


def normalize_existing_locations(apps, schema_editor):
    Country = apps.get_model("location", "Country")
    State = apps.get_model("location", "State")
    City = apps.get_model("location", "City")

    def normalized(value):
        return " ".join(value.split())

    collections = (
        (Country, lambda row: (normalized(row.name).casefold(),)),
        (State, lambda row: (row.country_id, normalized(row.name).casefold())),
        (City, lambda row: (row.state_id, normalized(row.name).casefold())),
    )
    for model, key_for in collections:
        seen = set()
        codes = set()
        rows = list(model.objects.order_by("id"))
        for row in rows:
            key = key_for(row)
            if key in seen:
                raise RuntimeError(
                    f"Cannot normalize {model._meta.label}: duplicate location names exist."
                )
            seen.add(key)
            if model is Country:
                code = row.code.upper()
                if code in codes:
                    raise RuntimeError(
                        "Cannot normalize location.Country: duplicate country codes exist."
                    )
                codes.add(code)
        for row in rows:
            row.name = normalized(row.name)
            fields = ["name"]
            if model is Country:
                row.code = row.code.upper()
                fields.append("code")
            row.save(update_fields=fields)


class Migration(migrations.Migration):
    dependencies = [("location", "0002_add_fa_title")]

    operations = [
        migrations.RunPython(normalize_existing_locations, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="country",
            constraint=models.UniqueConstraint(
                Lower(Trim("name")), name="location_country_normalized_name_unique"
            ),
        ),
        migrations.AddConstraint(
            model_name="country",
            constraint=models.CheckConstraint(
                condition=models.Q(("code__regex", "^[A-Z]{2}$")),
                name="location_country_code_format",
            ),
        ),
        migrations.AddConstraint(
            model_name="state",
            constraint=models.UniqueConstraint(
                F("country"), Lower(Trim("name")),
                name="location_state_country_normalized_name_unique",
            ),
        ),
        migrations.AddConstraint(
            model_name="city",
            constraint=models.UniqueConstraint(
                F("state"), Lower(Trim("name")),
                name="location_city_state_normalized_name_unique",
            ),
        ),
    ]
