import unicodedata

from django.db import migrations, models


def normalize(value):
    normalized = []
    for character in value.strip():
        if character == "+" and not normalized:
            normalized.append(character)
        elif character.isspace() or character in "-()":
            continue
        else:
            normalized.append(str(unicodedata.decimal(character)))
    return "".join(normalized)


def normalize_customer_phones(apps, schema_editor):
    Customer = apps.get_model("customer", "Customer")
    normalized_owners = {}
    updates = []
    for customer in Customer.objects.only("id", "phone").order_by("id"):
        phone = normalize(customer.phone)
        owner = normalized_owners.get(phone)
        if owner is not None:
            raise RuntimeError(
                f"Customers {owner} and {customer.pk} normalize to the same phone."
            )
        normalized_owners[phone] = customer.pk
        if phone != customer.phone:
            customer.phone = phone
            updates.append(customer)
    if updates:
        Customer.objects.bulk_update(updates, ["phone"])


class Migration(migrations.Migration):
    dependencies = [("customer", "0003_customeraddress_one_default")]

    operations = [
        migrations.RunPython(normalize_customer_phones, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="customer",
            constraint=models.CheckConstraint(
                condition=models.Q(phone__regex=r"^\+?[0-9]{8,15}$"),
                name="customer_phone_canonical_format",
            ),
        ),
    ]
