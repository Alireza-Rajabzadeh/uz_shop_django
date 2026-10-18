
from django.conf import settings
from django.db import models
from django.utils.text import slugify


class VendorProductStatus(models.Model):
    """Review state of a vendor product submission.

    Deliberately a separate vocabulary from `ProductStatus`: the catalog
    describes what is live, this describes what is waiting for an admin.
    """

    class Code(models.TextChoices):
        # The vendor's working copy: freely editable, never in the admin
        # queue. `product` is null for a new product, set when staging
        # changes to an already-live one.
        DRAFT = "draft", "Draft"
        # Sent for review, first time; `product` is null until confirmed.
        CONFIRMATION_AWAIT = "confirmation_await", "Confirmation await"
        # Sent for review, changes aimed at an already-live product.
        REQUEST_UPDATE = "request_update", "Request update"
        # Admin asked for changes; nothing was copied to the catalog.
        NEED_RECHECK = "need_recheck", "Need recheck"
        # Admin refused; nothing was copied to the catalog.
        REJECT = "reject", "Reject"
        # Approved: for a first submission the catalog row now exists, for an
        # update the checked fields were copied onto the live row.
        CONFIRMED = "confirmed", "Confirmed"

    # The only two states that mean "with an admin, not with the vendor".
    # Everything else is either being written by the vendor or has already
    # been decided, so the vendor can act on it.
    PENDING_CODES = frozenset({
        Code.CONFIRMATION_AWAIT,
        Code.REQUEST_UPDATE,
    })

    class Meta:
        db_table = "catalog_vendor_product_status"

    name = models.CharField(max_length=50, unique=True)

    def __str__(self):
        return self.name


class VendorProduct(models.Model):
    """A vendor's copy of a product aggregate, held out of `catalog_product`.

    The row is either a first-time draft (`product` is null) or a pending
    revision of an already-live product (`product` points at it). Nothing here
    is served to a customer until an admin copies it into the catalog.
    """

    class Meta:
        db_table = "catalog_vendor_product"
        constraints = [
            # Editing a live product must reopen its submission rather than
            # forking a second one, otherwise the admin queue shows the same
            # product twice with no way to tell which is current.
            models.UniqueConstraint(
                fields=["product"],
                condition=models.Q(product__isnull=False),
                name="vendor_product_one_per_catalog",
            ),
        ]
        indexes = [
            models.Index(fields=["vendor", "status"], name="vp_vendor_status_idx"),
            models.Index(fields=["status", "id"], name="vp_status_idx"),
            models.Index(fields=["product"], name="vp_product_idx"),
        ]

    name = models.CharField(max_length=250)
    slug = models.SlugField(max_length=280, unique=True, editable=False)

    status = models.ForeignKey(
        VendorProductStatus,
        on_delete=models.PROTECT,
        related_name="vendor_products",
    )

    vendor = models.ForeignKey(
        "vendor.Vendor",
        on_delete=models.CASCADE,
        related_name="product_submissions",
    )

    # Null until an admin confirms the submission; afterwards it is the live
    # catalog row this submission feeds. SET_NULL rather than PROTECT so that
    # deleting a catalog product does not strand the audit row — `status` is
    # what says whether it was ever approved.
    product = models.ForeignKey(
        "Product",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="vendor_submissions",
    )

    confirmed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="confirmed_vendor_products",
    )
    confirmed_at = models.DateTimeField(null=True, blank=True)
    admin_response = models.TextField(blank=True, null=True)

    categories = models.ManyToManyField(
        "Category",
        related_name="vendor_products",
        blank=True,
        db_table="catalog_vendor_product_categories",
    )

    brand = models.ForeignKey(
        "Brand",
        on_delete=models.PROTECT,
        related_name="vendor_products",
        null=True,
        blank=True,
    )

    description = models.TextField(blank=True, null=True)
    json_description = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        # Same rule as `Product.save`: the slug is derived, never supplied, so
        # a submission cannot reserve the slug of a product it has not become
        # yet. Conflicts are resolved inside this table only.
        if not self.slug:
            base = slugify(self.name, allow_unicode=True)[:250] or "product"
            candidate = base
            suffix = 2
            while type(self).objects.exclude(pk=self.pk).filter(slug=candidate).exists():
                candidate = f"{base[:270 - len(str(suffix))]}-{suffix}"
                suffix += 1
            self.slug = candidate
        super().save(*args, **kwargs)


class VendorProductDetails(models.Model):
    class Meta:
        db_table = "catalog_vendor_product_details"
        constraints = [
            models.UniqueConstraint(
                fields=["vendor_product", "detail"],
                name="vendor_product_detail_unique",
            ),
        ]

    vendor_product = models.ForeignKey(
        VendorProduct,
        on_delete=models.PROTECT,
        related_name="details",
    )

    detail = models.ForeignKey("CategoryDetail", on_delete=models.CASCADE)

    option = models.ForeignKey(
        "CategoryDetailOption",
        on_delete=models.SET_NULL,
        related_name="vendor_product_values",
        null=True,
        blank=True,
    )

    value = models.CharField(max_length=250, blank=True)
    extra_value = models.CharField(max_length=250, blank=True, null=True)

    def __str__(self):
        return f"{self.vendor_product} - {self.detail}"


class VendorProductFile(models.Model):
    """Media attached to a submission.

    `file` is the shared `files.File` object, so confirming a submission
    re-points the same stored object at the catalog product instead of
    copying bytes.
    """

    class Role(models.TextChoices):
        GALLERY = "gallery", "Gallery"
        THUMBNAIL = "thumbnail", "Thumbnail"
        VIDEO = "video", "Video"
        DOCUMENT = "document", "Document"

    vendor_product = models.ForeignKey(
        VendorProduct,
        on_delete=models.CASCADE,
        related_name="product_files",
    )
    file = models.ForeignKey(
        "files.File",
        on_delete=models.PROTECT,
        related_name="vendor_product_files",
    )
    role = models.CharField(max_length=20, choices=Role.choices)
    position = models.PositiveIntegerField(default=0)
    is_primary = models.BooleanField(default=False)
    alt_text = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "catalog_vendor_product_file"
        ordering = ["position", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["vendor_product", "file"],
                name="vendor_product_file_unique",
            ),
            models.UniqueConstraint(
                fields=["vendor_product"],
                condition=models.Q(is_primary=True),
                name="vendor_product_file_one_primary",
            ),
        ]
        indexes = [
            models.Index(
                fields=["vendor_product", "role", "position"],
                name="vp_file_order_idx",
            ),
        ]

    def __str__(self):
        return f"{self.vendor_product} - {self.file}"
