from django.db import models

from .payment import Payment


class PaymentDocument(models.Model):
    payment = models.ForeignKey(
        Payment, on_delete=models.CASCADE, related_name="documents"
    )
    file = models.ForeignKey(
        "files.File", on_delete=models.PROTECT, related_name="payment_documents"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "shop_payment_document"
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(
                fields=["payment", "file"], name="shop_payment_document_unique"
            )
        ]
