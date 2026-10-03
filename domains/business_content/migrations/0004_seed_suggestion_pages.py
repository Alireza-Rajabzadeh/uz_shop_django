"""Seed the standard shop pages the panel offers to create.

`slug` is the identity, so re-running updates copy and `required` in place.
`activate` and `component_lists` are deliberately absent from `defaults`: an
operator's activation choice and the component vocabulary under discussion
must survive a re-seed.
"""

from django.db import migrations

from domains.business_content.data.suggestion_pages import SUGGESTION_PAGES


def seed_suggestion_pages(apps, schema_editor):
    SuggestionPage = apps.get_model("business_content", "SuggestionPage")
    for row in SUGGESTION_PAGES:
        SuggestionPage.objects.update_or_create(
            slug=row["slug"],
            defaults={
                "title": row["title"],
                "descriptions": row["descriptions"],
                "required": row["required"],
            },
        )


def unseed_suggestion_pages(apps, schema_editor):
    SuggestionPage = apps.get_model("business_content", "SuggestionPage")
    SuggestionPage.objects.filter(
        slug__in=[row["slug"] for row in SUGGESTION_PAGES]
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("business_content", "0003_move_stranded_home_landing_page"),
    ]

    operations = [
        migrations.RunPython(seed_suggestion_pages, unseed_suggestion_pages),
    ]
