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

    vendor = models.ForeignKey(
        "vendor.Vendor",
        on_delete=models.CASCADE,
        related_name="business_profiles",
        null=True,
        blank=True,
    )
    business_name = models.CharField(max_length=200)
    display_name = models.CharField(max_length=200)
    legal_name = models.CharField(max_length=200, blank=True)
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True)
    postal_code = models.CharField(max_length=32, blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True, validators=[MinValueValidator(-90), MaxValueValidator(90)])
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True, validators=[MinValueValidator(-180), MaxValueValidator(180)])
    light_logo = models.ForeignKey(
        "files.File",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="business_light_logos",
    )
    dark_logo = models.ForeignKey(
        "files.File",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="business_dark_logos",
    )
    enamad_link = models.URLField(max_length=500, blank=True)
    availability_status = models.CharField(max_length=32, choices=Availability.choices, default=Availability.OPEN)
    availability_message = models.CharField(max_length=500, blank=True)
    availability_until = models.DateTimeField(null=True, blank=True)
    cache_ttl = models.PositiveIntegerField(default=3600)

    class Meta:
        db_table = "business_profile"
        constraints = [
            models.UniqueConstraint(fields=["vendor"], name="business_profile_one_per_vendor"),
        ]

    def __str__(self):
        return self.display_name


class ImmutableKeyModel(TimestampedModel):
    key = models.SlugField(max_length=80)

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if self.pk:
            original = type(self).objects.filter(pk=self.pk).values_list("key", flat=True).first()
            if original is not None and original != self.key:
                raise ValidationError({"key": "Key cannot be changed after creation."})
        return super().save(*args, **kwargs)


class SocialMedia(TimestampedModel):
    name = models.CharField(max_length=80)
    fa_name = models.CharField(max_length=80)
    slug = models.SlugField(max_length=80, unique=True)
    is_active = models.BooleanField(default=True)
    position = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "social_media"
        ordering = ["position", "id"]

    def __str__(self):
        return self.name


class SocialMediaIcon(TimestampedModel):
    social_media = models.ForeignKey(
        SocialMedia,
        on_delete=models.CASCADE,
        related_name="icons",
    )
    file = models.ForeignKey(
        "files.File",
        on_delete=models.CASCADE,
        related_name="social_media_icons",
    )
    label = models.CharField(max_length=80, blank=True)
    position = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "social_media_icon"
        ordering = ["position", "id"]

    def __str__(self):
        return f"{self.social_media.name} - {self.label or self.file.original_name}"


class BusinessPhone(ImmutableKeyModel):
    business = models.ForeignKey(
        "business.BusinessProfile",
        on_delete=models.CASCADE,
        related_name="phones",
        null=True,
        blank=True,
    )
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
        constraints = [
            models.UniqueConstraint(fields=["business", "key"], name="business_phone_business_key_unique"),
        ]

    def __str__(self):
        return self.title


class BusinessSocialLink(ImmutableKeyModel):
    business = models.ForeignKey(
        "business.BusinessProfile",
        on_delete=models.CASCADE,
        related_name="social_links",
        null=True,
        blank=True,
    )
    title = models.CharField(max_length=120)
    social_media = models.ForeignKey(
        SocialMedia,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="business_links",
    )
    url = models.URLField(max_length=500)
    icon = models.ForeignKey(
        SocialMediaIcon,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="business_links",
    )
    visibility = models.CharField(max_length=10, choices=Visibility.choices, default=Visibility.PUBLIC)
    status = models.CharField(max_length=10, choices=RecordStatus.choices, default=RecordStatus.ACTIVE)
    position = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "business_social_link"
        ordering = ["position", "id"]
        constraints = [
            models.UniqueConstraint(fields=["business", "key"], name="business_social_link_business_key_unique"),
        ]

    def __str__(self):
        return self.title


class BusinessWorkingDay(TimestampedModel):
    vendor = models.ForeignKey(
        "vendor.Vendor",
        on_delete=models.CASCADE,
        related_name="business_working_days",
        null=True,
        blank=True,
    )
    weekday = models.PositiveSmallIntegerField(validators=[MinValueValidator(0), MaxValueValidator(6)])
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
            models.UniqueConstraint(fields=["vendor", "weekday"], name="business_working_day_vendor_weekday_unique"),
            models.CheckConstraint(condition=Q(weekday__gte=0, weekday__lte=6), name="business_working_day_weekday_range"),
            models.CheckConstraint(condition=(Q(second_opens_at__isnull=True, second_closes_at__isnull=True) | Q(second_opens_at__isnull=False, second_closes_at__isnull=False)), name="business_working_day_second_pair"),
        ]

    def __str__(self):
        return str(self.weekday)
