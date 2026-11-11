from django.db import models

from .business_payment import BusinessPayment


class BusinessPaymentDocument(models.Model):
    payment = models.ForeignKey(
        BusinessPayment,
        on_delete=models.CASCADE,
        related_name="documents",
    )
    file = models.ForeignKey(
        "files.File",
        on_delete=models.PROTECT,
        related_name="business_payment_documents",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "business_payment_document"
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(
                fields=["payment", "file"],
                name="bp_payment_document_unique",
            ),
        ]

    def __str__(self):
        return f"Document for BusinessPayment #{self.payment_id}"
