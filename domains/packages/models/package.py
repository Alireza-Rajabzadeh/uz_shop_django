from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from .base import ImmutableCodeModel

# The tier a business falls back to. Referenced by code, never by id: package
# ids are not portable between environments, and this is the one code the rest
# of the system is allowed to assume exists.
DEFAULT_PACKAGE_CODE = "free"


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
