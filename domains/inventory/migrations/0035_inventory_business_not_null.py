"""Require a business owner on warehouses and supplies.

With ``inventory.0034`` backfilling the historic ``NULL`` rows, both columns
can now be ``NOT NULL``. ``Warehouse.business`` also moves from ``SET_NULL`` to
``PROTECT`` so a business that owns warehouses cannot be deleted out from
under them; this matches ``Inventory.business`` and ``InventorySupply.business``.
"""

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("inventory", "0034_backfill_inventory_business"),
    ]

    operations = [
        migrations.AlterField(
            model_name="warehouse",
            name="business",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="warehouses",
                to="business.businessprofile",
            ),
        ),
        migrations.AlterField(
            model_name="inventorysupply",
            name="business",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="supplies",
                to="business.businessprofile",
            ),
        ),
    ]
