from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q

from domains.business.enums.BusinessStatusEnum import BusinessStatusEnum
from domains.packages.models import DEFAULT_PACKAGE_CODE, Package


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
    # PROTECT guards the package, not the business: a business can still be
    # deleted, but a tier cannot be removed out from under the businesses on
    # it. Matches `PackagePriceHistory.package`.
    package = models.ForeignKey(
        "packages.Package",
        on_delete=models.PROTECT,
        related_name="business_profiles",
        null=True,
        blank=True,
    )
    # Lifecycle state, decided by the admin's confirmation flow — unrelated
    # to the storefront's `availability_status` below. PROTECT: a status row
    # cannot be removed from under the businesses standing on it. Default 3
    # (confirmation_await): every new registration starts unconfirmed.
    status = models.ForeignKey(
        BusinessStatus,
        on_delete=models.PROTECT,
        related_name="business_profiles",
        default=BusinessStatusEnum.CONFIRMATION_AWAIT.value,
    )
    business_name = models.CharField(max_length=200)
    display_name = models.CharField(max_length=200)
    legal_name = models.CharField(max_length=200, blank=True)
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True)
    province = models.ForeignKey(
        "location.State",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="business_profiles",
    )
    city = models.ForeignKey(
        "location.City",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="business_profiles",
    )
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

    def save(self, *args, **kwargs):
        # A new business starts on the default tier.
        #
        # Create-only, so an explicit `null` written by a later update is
        # left alone rather than silently reassigned. `.filter().first()`
        # rather than `.get()` because an environment that has not seeded
        # packages should keep NULL instead of raising, which is also what
        # lets the many call sites that build a profile without seeding keep
        # working.
        if self._state.adding and self.package_id is None:
            self.package = Package.objects.filter(code=DEFAULT_PACKAGE_CODE).first()
        super().save(*args, **kwargs)

    @property
    def package_code(self):
        """The tier this business is on; a missing package means the default."""
        return self.package.code if self.package_id else DEFAULT_PACKAGE_CODE

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


class BusinessCategory(TimestampedModel):
    business = models.ForeignKey(
        BusinessProfile,
        on_delete=models.CASCADE,
        related_name="categories",
    )
    category = models.ForeignKey(
        "catalog.Category",
        on_delete=models.CASCADE,
        related_name="business_categories",
    )

    class Meta:
        db_table = "business_category"
        constraints = [
            models.UniqueConstraint(
                fields=["business", "category"],
                name="business_category_unique",
            ),
        ]

    def __str__(self):
        return f"{self.business} → {self.category}"
