"""Replace `component_lists` with the placement `context`.

`component_lists` held a raw component allow-list per suggestion, which scaled
with components x suggestions and could silently go stale when a component was
renamed. The placement now lives on the component contract instead
(`allowedContexts`), and a suggestion only declares *which* placement it is.

`context` defaults to `page`, which is what every standard shop page is, so
the column is stamped from the default and then re-seeded from
`data/suggestion_pages.py` so the data file stays the single source.
"""

from django.db import migrations, models

from domains.business_content.data.suggestion_pages import SUGGESTION_PAGES


def seed_contexts(apps, schema_editor):
    SuggestionPage = apps.get_model("business_content", "SuggestionPage")
    for row in SUGGESTION_PAGES:
        SuggestionPage.objects.filter(slug=row["slug"]).update(
            context=row["context"]
        )


def unseed_contexts(apps, schema_editor):
    # Nothing to undo: `context` was added with the `page` default, so
    # resetting every row to it is the inverse of applying the seed data.
    SuggestionPage = apps.get_model("business_content", "SuggestionPage")
    SuggestionPage.objects.all().update(context="page")


class Migration(migrations.Migration):
    dependencies = [
        ("business_content", "0004_seed_suggestion_pages"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="suggestionpage",
            name="component_lists",
        ),
        migrations.AddField(
            model_name="suggestionpage",
            name="context",
            field=models.CharField(
                choices=[
                    ("page", "Page"),
                    ("section", "Section"),
                    ("footer", "Footer"),
                ],
                default="page",
                max_length=16,
            ),
        ),
        migrations.RunPython(seed_contexts, unseed_contexts),
    ]
