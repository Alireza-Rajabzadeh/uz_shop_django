"""Advance the business_profile sequence past the row inventory.0022 inserted.

``inventory.0022_migrate_inventory_data`` creates ``BusinessProfile id=1`` so
that migrated inventory rows have a business to point at. Inserting an
explicit key never calls ``nextval``, so on a fresh database the sequence
still hands out 1 and the first profile created afterwards collides with
that row.

The test suite hit it first: ``BusinessAPITests`` could not build its fixture,
which silently took the whole class out of every run.

The ordering matters: this must run after ``inventory.0022``, not merely
after the business migrations, or the insert it is repairing would still be
ahead of it.
"""

from django.db import migrations


def advance_profile_sequence(apps, schema_editor):
    connection = schema_editor.connection
    if connection.vendor != "postgresql":
        return

    from psycopg import sql

    table = apps.get_model("business", "BusinessProfile")._meta.db_table
    query = sql.SQL(
        "SELECT setval(pg_get_serial_sequence({name}, 'id'), "
        "COALESCE((SELECT MAX(id) FROM {table}), 0) + 1, false)"
    ).format(name=sql.Literal(table), table=sql.Identifier(table))
    with connection.cursor() as cursor:
        cursor.execute(query)


class Migration(migrations.Migration):
    dependencies = [
        ("business", "0008_businesscategory"),
        ("inventory", "0022_migrate_inventory_data"),
    ]

    operations = [
        migrations.RunPython(advance_profile_sequence, migrations.RunPython.noop),
    ]
