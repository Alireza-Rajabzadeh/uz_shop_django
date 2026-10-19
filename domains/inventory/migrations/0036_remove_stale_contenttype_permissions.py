"""Remove content types and permissions left behind by deleted models.

Django never drops a ``ContentType`` (or its cascading ``Permission`` rows)
when a model is removed with ``DeleteModel``; it leaves an orphan that the
permission screen keeps listing. The inventory refactor removed several models
(``warehousestock``, ``serializedstock``, ``serializedstockstatus``,
``inventorystrategy``, ``inventoryattribute``, ``variantpricing``) and catalog
removed ``productvariantsdetails``.

This migration deletes every content type whose model is no longer in the app
registry, together with its permissions and any group/user assignments to them.
It is the repeatable form of ``manage.py remove_stale_contenttypes``.

Safety: the project defines no ``GenericForeignKey`` / ``GenericRelation``, so
nothing but ``Permission`` references these content types. The live
``inventory.view_inventory`` permission lives on the ``Inventory`` model and is
unaffected; only the stale copy on the dead ``warehousestock`` row is removed.
"""

from django.db import migrations


def forwards(apps, schema_editor):
    ContentType = apps.get_model("contenttypes", "ContentType")
    Permission = apps.get_model("auth", "Permission")

    live = {(model._meta.app_label, model._meta.model_name) for model in apps.get_models()}
    stale_ids = [
        content_type.id
        for content_type in ContentType.objects.all()
        if (content_type.app_label, content_type.model) not in live
    ]
    if not stale_ids:
        return

    stale_labels = list(
        ContentType.objects.filter(id__in=stale_ids).values_list("app_label", "model")
    )
    permissions_deleted, _ = Permission.objects.filter(
        content_type_id__in=stale_ids
    ).delete()
    contenttypes_deleted, _ = ContentType.objects.filter(id__in=stale_ids).delete()
    print(
        f"  Removed stale content types: {contenttypes_deleted} "
        f"({', '.join(f'{a}.{m}' for a, m in sorted(stale_labels))}); "
        f"permissions: {permissions_deleted}"
    )


class Migration(migrations.Migration):

    dependencies = [
        ("inventory", "0035_inventory_business_not_null"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
