from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q


class TimestampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Visibility(models.TextChoices):
    PUBLIC = "public", "Public"
    PRIVATE = "private", "Private"


class RecordStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    INACTIVE = "inactive", "Inactive"


class BusinessProfile(TimestampedModel):
    class Availability(models.TextChoices):
        OPEN = "open", "Open"
        CLOSED = "closed", "Closed"
        TEMPORARILY_UNAVAILABLE = "temporarily_unavailable", "Temporarily unavailable"
        MAINTENANCE = "maintenance", "Maintenance"
        HOLIDAY = "holiday", "Holiday"

    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    business_name = models.CharField(max_length=200)
    display_name = models.CharField(max_length=200)
    legal_name = models.CharField(max_length=200, blank=True)
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True)
    postal_code = models.CharField(max_length=32, blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True, validators=[MinValueValidator(-90), MaxValueValidator(90)])
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True, validators=[MinValueValidator(-180), MaxValueValidator(180)])
    availability_status = models.CharField(max_length=32, choices=Availability.choices, default=Availability.OPEN)
    availability_message = models.CharField(max_length=500, blank=True)
    availability_until = models.DateTimeField(null=True, blank=True)
    cache_ttl = models.PositiveIntegerField(default=3600)

    class Meta:
        db_table = "business_profile"
        constraints = [models.CheckConstraint(condition=Q(id=1), name="business_profile_singleton_id")]

    def save(self, *args, **kwargs):
        self.pk = 1
        return super().save(*args, **kwargs)

    def __str__(self):
        return self.display_name


class ImmutableKeyModel(TimestampedModel):
    key = models.SlugField(max_length=80, unique=True)

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if self.pk:
            original = type(self).objects.filter(pk=self.pk).values_list("key", flat=True).first()
            if original is not None and original != self.key:
                raise ValidationError({"key": "Key cannot be changed after creation."})
        return super().save(*args, **kwargs)


class BusinessPhone(ImmutableKeyModel):
    title = models.CharField(max_length=120)
    number = models.CharField(max_length=40)
    extension = models.CharField(max_length=16, blank=True)
    visibility = models.CharField(max_length=10, choices=Visibility.choices, default=Visibility.PUBLIC)
    status = models.CharField(max_length=10, choices=RecordStatus.choices, default=RecordStatus.ACTIVE)
    notes = models.TextField(blank=True)
    position = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "business_phone"
        ordering = ["position", "id"]

    def __str__(self):
        return self.title


class BusinessSocialLink(ImmutableKeyModel):
    title = models.CharField(max_length=120)
    platform = models.CharField(max_length=80)
    url = models.URLField(max_length=500)
    logo_file = models.ForeignKey(
        "files.File",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="business_social_links",
    )
    visibility = models.CharField(max_length=10, choices=Visibility.choices, default=Visibility.PUBLIC)
    status = models.CharField(max_length=10, choices=RecordStatus.choices, default=RecordStatus.ACTIVE)
    position = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "business_social_link"
        ordering = ["position", "id"]

    def __str__(self):
        return self.title


class BusinessWorkingDay(TimestampedModel):
    weekday = models.PositiveSmallIntegerField(unique=True, validators=[MinValueValidator(0), MaxValueValidator(6)])
    is_open = models.BooleanField(default=False)
    opens_at = models.TimeField(null=True, blank=True)
    closes_at = models.TimeField(null=True, blank=True)
    second_opens_at = models.TimeField(null=True, blank=True)
    second_closes_at = models.TimeField(null=True, blank=True)
    description = models.CharField(max_length=300, blank=True)

    class Meta:
        db_table = "business_working_day"
        ordering = ["weekday"]
        constraints = [
            models.CheckConstraint(condition=Q(weekday__gte=0, weekday__lte=6), name="business_working_day_weekday_range"),
            models.CheckConstraint(condition=(Q(second_opens_at__isnull=True, second_closes_at__isnull=True) | Q(second_opens_at__isnull=False, second_closes_at__isnull=False)), name="business_working_day_second_pair"),
        ]

    def __str__(self):
        return str(self.weekday)
