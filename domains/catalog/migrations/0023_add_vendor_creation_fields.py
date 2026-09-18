from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0022_remove_inventory_strategy_fk'),
        ('vendor', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='product',
            name='created_by_vendor',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.SET_NULL,
                related_name='created_products',
                to='vendor.vendor',
            ),
        ),
        migrations.AddField(
            model_name='product',
            name='creator_model',
            field=models.CharField(blank=True, default='', max_length=50),
        ),
        migrations.AddIndex(
            model_name='product',
            index=models.Index(
                fields=['created_by_vendor'],
                name='catalog_product_vendor_idx',
            ),
        ),
    ]
