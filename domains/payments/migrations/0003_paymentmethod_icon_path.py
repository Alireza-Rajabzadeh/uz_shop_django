from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("payments", "0002_refactor_payment_models")]

    operations = [
        migrations.AddField(
            model_name="paymentmethod",
            name="icon_path",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
    ]
