from django.db import models

from .return_request import ReturnRequest


class ReturnRequestEvidence(models.Model):
    class Meta:
        db_table = "shop_return_request_evidence"
        ordering = ["position", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["return_request", "position"],
                name="shop_return_unique_evidence_position",
            ),
        ]

    return_request = models.ForeignKey(
        ReturnRequest,
        on_delete=models.CASCADE,
        related_name="evidence",
    )
    file = models.ForeignKey(
        "files.File",
        on_delete=models.PROTECT,
        related_name="return_request_evidence",
    )
    position = models.PositiveSmallIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
