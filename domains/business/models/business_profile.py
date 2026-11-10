from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from domains.business.enums.BusinessStatusEnum import BusinessStatusEnum
from domains.packages.models import DEFAULT_PACKAGE_CODE, Package

from .base import TimestampedModel
from .business_status import BusinessStatus


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
