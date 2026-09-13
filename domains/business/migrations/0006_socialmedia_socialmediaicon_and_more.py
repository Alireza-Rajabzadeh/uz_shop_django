import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("files", "0001_initial"),
        ("business", "0005_remove_businessphone_business_phone_vendor_key_unique_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="SocialMedia",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("name", models.CharField(max_length=80)),
                ("fa_name", models.CharField(max_length=80)),
                ("slug", models.SlugField(max_length=80, unique=True)),
                ("is_active", models.BooleanField(default=True)),
                ("position", models.PositiveIntegerField(default=0)),
            ],
            options={
                "db_table": "social_media",
                "ordering": ["position", "id"],
            },
        ),
        migrations.CreateModel(
            name="SocialMediaIcon",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("label", models.CharField(blank=True, max_length=80)),
                ("position", models.PositiveIntegerField(default=0)),
                ("file", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="social_media_icons", to="files.file")),
                ("social_media", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="icons", to="business.socialmedia")),
            ],
            options={
                "db_table": "social_media_icon",
                "ordering": ["position", "id"],
            },
        ),
        migrations.AddField(
            model_name="businesssociallink",
            name="social_media",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="business_links", to="business.socialmedia"),
        ),
        migrations.AddField(
            model_name="businesssociallink",
            name="icon",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="business_links", to="business.socialmediaicon"),
        ),
    ]
