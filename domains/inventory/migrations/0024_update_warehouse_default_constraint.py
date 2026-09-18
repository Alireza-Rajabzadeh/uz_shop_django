from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0023_add_business_to_inventorysupply'),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name='warehouse',
            name='inventory_single_default_warehouse',
        ),
        migrations.AddConstraint(
            model_name='warehouse',
            constraint=models.UniqueConstraint(
                condition=models.Q(('is_default', True)),
                fields=('business', 'is_default'),
                name='inventory_single_default_warehouse_per_business',
            ),
        ),
    ]
