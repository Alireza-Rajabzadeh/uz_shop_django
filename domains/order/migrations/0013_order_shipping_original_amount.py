from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("order", "0012_returnrequest_customer_response"),
    ]

    operations = [
        migrations.AddField(
            model_name="order",
            name="shipping_original_amount",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("200000.00"),
                max_digits=15,
            ),
        ),
    ]
