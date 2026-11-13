from django.db import models


class PackageFeature(models.Model):
    """One feature granted by one package, with its configuration.

    Limits live in `config` rather than in their own columns so a new
    limit-taking feature does not need a schema change.
    """

    package = models.ForeignKey(
        "packages.Package",
        on_delete=models.CASCADE,
        related_name="package_features",
    )
    feature = models.ForeignKey(
        "packages.Feature",
        on_delete=models.PROTECT,
        related_name="package_features",
    )
    config = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "packages_package_feature"
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(
                fields=["package", "feature"],
                name="packages_package_feature_unique",
            ),
        ]

    def __str__(self):
        return f"{self.package.code} → {self.feature.code}"
