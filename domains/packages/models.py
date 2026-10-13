from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils.translation import gettext as _

# The tier a business falls back to. Referenced by code, never by id: package
# ids are not portable between environments, and this is the one code the rest
# of the system is allowed to assume exists.
DEFAULT_PACKAGE_CODE = "free"


class TimestampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class ImmutableCodeModel(TimestampedModel):
    """A record identified by a stable ``code``.

    Application logic keys off ``code``, never off a display name or a
    database id: ids are not portable between environments and names are
    editable. Mirrors `domains.business_payments.ImmutableCodeModel`, kept
    local so this domain does not depend on another domain's models.
    """

    code = models.CharField(max_length=50, unique=True)

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if self.pk:
            stored = (
                type(self).objects.filter(pk=self.pk)
                .values_list("code", flat=True)
                .first()
            )
            if stored is not None and stored != self.code:
                raise ValidationError({"code": _("Code cannot be changed after creation.")})
        super().save(*args, **kwargs)


class Package(ImmutableCodeModel):
    """A purchasable plan. Reservations and subscriptions are out of scope.

    `is_active` only governs whether the package may be offered for new
    reservations in the future; it does not describe any existing
    reservation, because there are none yet.
    """

    name = models.CharField(max_length=100)
    price = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        validators=[MinValueValidator(0)],
    )
    # A percentage from 0 to 100. Sized like `expected_profit_percentage`
    # in the marketplace domain so percentages read the same everywhere.
    off_discount = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "packages_package"
        ordering = ["id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(price__gte=0),
                name="packages_package_price_gte_zero",
            ),
            models.CheckConstraint(
                condition=models.Q(off_discount__gte=0) & models.Q(off_discount__lte=100),
                name="packages_package_off_discount_between_zero_and_hundred",
            ),
        ]

    def __str__(self):
        return self.code


class Feature(ImmutableCodeModel):
    """A capability a package can grant, e.g. ``shop.products``.

    Codes are the contract for future backend authorization checks and for
    the panels' feature-availability logic. Names and descriptions are
    editable display text only.
    """

    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, default="")

    class Meta:
        db_table = "packages_feature"
        ordering = ["id"]

    def __str__(self):
        return self.code


class PackageFeature(models.Model):
    """One feature granted by one package, with its configuration.

    Limits live in `config` rather than in their own columns so a new
    limit-taking feature does not need a schema change.
    """

    package = models.ForeignKey(
        Package,
        on_delete=models.CASCADE,
        related_name="package_features",
    )
    feature = models.ForeignKey(
        Feature,
        on_delete=models.PROTECT,
        related_name="package_features",
    )
    config = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "packages_package_feature"
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(
                fields=["package", "feature"],
                name="packages_package_feature_unique",
            ),
        ]

    def __str__(self):
        return f"{self.package.code} → {self.feature.code}"


class PackagePriceHistory(models.Model):
    """Append-only audit of a package's price and discount.

    Written by `domains.packages.signals`, not by any one view or service,
    so every write path that reaches `Package.save()` leaves the same trail.
    Only the new values are stored: the previous row is the "before".

    `package` is PROTECT so deleting a package can never take its pricing
    audit with it — the same policy as `OfferPriceHistory`.
    """

    package = models.ForeignKey(
        Package,
        on_delete=models.PROTECT,
        related_name="price_history",
    )
    price = models.DecimalField(max_digits=15, decimal_places=2)
    off_discount = models.DecimalField(max_digits=5, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "packages_package_price_history"
        # Chronological: readers get oldest first, so the newest row is the
        # current pricing and the rows below it are the path taken here.
        ordering = ["created_at", "id"]
        indexes = [
            models.Index(
                fields=["package", "created_at"],
                name="pph_package_created_idx",
            ),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(price__gte=0),
                name="packages_price_history_price_gte_zero",
            ),
            models.CheckConstraint(
                condition=models.Q(off_discount__gte=0) & models.Q(off_discount__lte=100),
                name="packages_price_history_off_discount_between_zero_and_hundred",
            ),
        ]

    def __str__(self):
        return f"{self.package.code}: {self.price} (-{self.off_discount}%)"
