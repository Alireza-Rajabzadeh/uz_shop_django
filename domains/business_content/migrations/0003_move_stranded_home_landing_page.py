"""Move a stranded `home` landing page into `business_content_page`.

The suggestion tile on the pages list used to route `home` through the
landing-page create form, so a vendor creating it from there ended up with a
row in `business_content_landing_page` that `GET /api/business-content/home`
can never serve — that endpoint reads `business_content_page` for `slug=home`.

Idempotent and deliberately narrow: a business that already owns a `home`
page keeps its landing page untouched for a human to resolve, and landing
pages with any other slug are left alone (they are still legitimate to
author).
"""

from django.db import migrations

HOME_SLUG = "home"


def move_stranded_home(apps, schema_editor):
    LandingPage = apps.get_model("business_content", "LandingPage")
    Page = apps.get_model("business_content", "Page")
    SEORecord = apps.get_model("business_content", "SEORecord")

    for landing in LandingPage.objects.filter(slug=HOME_SLUG).iterator():
        if Page.objects.filter(business_id=landing.business_id, slug=HOME_SLUG).exists():
            continue

        page = Page.objects.create(
            business_id=landing.business_id,
            title=landing.title,
            slug=landing.slug,
            draft_content=landing.draft_content,
            published_content=landing.published_content,
            status=landing.status,
            published_at=landing.published_at,
            cache_ttl=landing.cache_ttl,
        )
        # `auto_now_add`/`auto_now` rewrite both columns on insert, so restore
        # the originals rather than silently dropping the page's history.
        Page.objects.filter(pk=page.pk).update(
            created_at=landing.created_at,
            updated_at=landing.updated_at,
        )
        # SEO rows are resource-referencing: retarget them at the new owner
        # instead of orphaning them on a row that is about to disappear.
        SEORecord.objects.filter(
            resource_type="landing_page", resource_id=landing.pk
        ).update(resource_type="page", resource_id=page.pk)

        landing.delete()


class Migration(migrations.Migration):
    dependencies = [
        ("business_content", "0002_suggestionpage"),
    ]

    operations = [
        # Reversing would strand the page again, so this stays forward-only.
        migrations.RunPython(move_stranded_home, migrations.RunPython.noop),
    ]
