from django.db import models


class Bank(models.Model):
    class Meta:
        db_table = "banks_bank"

    name = models.CharField(max_length=100)
    code = models.CharField(max_length=20, unique=True)
    card_number_regex = models.CharField(max_length=255)
    account_number_regex = models.CharField(max_length=255)
    sheba_regex = models.CharField(max_length=255)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name
