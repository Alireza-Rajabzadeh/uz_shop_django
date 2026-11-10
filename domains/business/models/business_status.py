from django.db import models


class BusinessStatus(models.Model):
    """Reference rows for the business lifecycle.

    Seeded reference data with fixed ids (see `BusinessStatusEnum` and
    `domains.business.data.business_statuses`): there is no admin or
    vendor write path, only the migration that creates the table and the
    `BusinessStatusSeeder`. `code` is the API contract; `title` carries
    the Persian display string.
    """

    code = models.CharField(max_length=32, unique=True)
    name = models.CharField(max_length=64)
    title = models.CharField(max_length=64)

    class Meta:
        db_table = "business_status"

    def __str__(self):
        return self.code
