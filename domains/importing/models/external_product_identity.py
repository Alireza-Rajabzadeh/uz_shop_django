from django.db import models


class ExternalProductIdentity(models.Model):
    provider = models.CharField(max_length=50)
    external_id = models.CharField(max_length=100)
    product = models.ForeignKey(
        "catalog.Product",
        on_delete=models.CASCADE,
        related_name="external_identities",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "importing_external_product_identity"
        constraints = [
            models.UniqueConstraint(
                fields=["provider", "external_id"],
                name="importing_provider_external_product_uniq",
            ),
        ]
