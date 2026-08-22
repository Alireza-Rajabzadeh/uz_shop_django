from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("order", "0011_detach_return_request_from_order_status"),
    ]

    operations = [
        migrations.AddField(
            model_name="returnrequest",
            name="customer_response",
            field=models.TextField(blank=True, null=True),
        ),
    ]
