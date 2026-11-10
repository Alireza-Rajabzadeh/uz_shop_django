from django.db import models


class Visibility(models.TextChoices):
    PUBLIC = "public", "Public"
    PRIVATE = "private", "Private"


class RecordStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    INACTIVE = "inactive", "Inactive"


class BusinessChargeType(models.TextChoices):
    TAX = "tax", "Tax"
    EXTRA = "extra", "Extra"


class BusinessChargeCalculationType(models.TextChoices):
    FIXED = "fixed", "Fixed"
    PERCENTAGE = "percentage", "Percentage"
