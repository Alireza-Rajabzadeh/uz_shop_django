import re
from django.core.exceptions import ValidationError
from django.db import models

from domains.business.enums import BusinessSubdomainEnum
from .base import TimestampedModel
from .business_profile import BusinessProfile
from .business_subdomain_status import BusinessSubdomainStatus

SUBDOMAIN_REGEX = re.compile(r"^[a-z0-9](?:[a-z0-9-]{1,28}[a-z0-9])$")

RESERVED_SUBDOMAINS = frozenset([
    "www",
    "api",
    "admin",
    "vendor",
    "client",
    "dashboard",
    "support",
    "help",
    "static",
    "cdn",
    "mail",
    "assets",
    "media",
    "auth",
    "login",
    "root",
    "dev",
    "staging",
    "status",
    "docs",
    "app",
    "charchu",
])


def validate_subdomain_format(value: str) -> str:
    """Validate subdomain string according to format rules.

    - Length: 3–30 characters.
    - Only lowercase English letters, numbers, and hyphens.
    - No leading or trailing hyphens.
    - No spaces, underscores, or special characters.
    """
    if not value:
        raise ValidationError("Subdomain cannot be empty.")
    normalized = str(value).strip().lower()
    if not (3 <= len(normalized) <= 30):
        raise ValidationError("Subdomain must be between 3 and 30 characters in length.")
    if not SUBDOMAIN_REGEX.match(normalized):
        if normalized.startswith("-") or normalized.endswith("-"):
            raise ValidationError("Subdomain cannot start or end with a hyphen.")
        if "_" in normalized or " " in normalized:
            raise ValidationError("Subdomain cannot contain spaces or underscores.")
        raise ValidationError("Subdomain can only contain lowercase English letters, digits, and hyphens.")
    return normalized


class BusinessSubdomain(TimestampedModel):
    """Manages active, redirect (historical), and reserved business subdomains."""

    business = models.ForeignKey(
        BusinessProfile,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="subdomains",
    )
    subdomain = models.CharField(
        max_length=30,
        unique=True,
        db_index=True,
    )
    status = models.ForeignKey(
        BusinessSubdomainStatus,
        on_delete=models.PROTECT,
        related_name="subdomains",
    )

    class Meta:
        db_table = "business_subdomain"
        constraints = [
            models.UniqueConstraint(
                fields=["business"],
                condition=models.Q(status_id=BusinessSubdomainEnum.ACTIVE.value),
                name="unique_active_subdomain_per_business",
            ),
        ]
        indexes = [
            models.Index(fields=["business", "status"], name="idx_biz_subdomain_status"),
        ]

    def __str__(self):
        biz_name = self.business.business_name if self.business else "System"
        return f"{self.subdomain} ({getattr(self.status, 'code', self.status_id)}) - {biz_name}"

    def clean(self):
        super().clean()
        if self.subdomain:
            self.subdomain = validate_subdomain_format(self.subdomain)

            # Reserved subdomain rules: non-reserved subdomains cannot use reserved names
            status_id = getattr(self.status, "id", self.status_id)
            if status_id != BusinessSubdomainEnum.RESERVED.value and self.subdomain in RESERVED_SUBDOMAINS:
                raise ValidationError({"subdomain": "This subdomain is reserved."})

            if status_id == BusinessSubdomainEnum.ACTIVE.value and not self.business_id:
                raise ValidationError({"business": "Active subdomains must be associated with a business."})

    def save(self, *args, **kwargs):
        if self.subdomain:
            self.subdomain = self.subdomain.strip().lower()
        self.full_clean()
        super().save(*args, **kwargs)
