from django.contrib.auth.models import BaseUserManager
from django.db import models
from django.contrib.auth.models import AbstractBaseUser
from core.utils.phone import normalize_phone


GENDER_CHOICES = [
    ("male", "Male"),
    ("female", "Female"),
    ("other", "Other"),
]


class VendorManager(BaseUserManager):
    def create_user(self, phone, password=None, **extra_fields):
        if not phone:
            raise ValueError("Phone number is required")
        vendor = self.model(phone=normalize_phone(phone), **extra_fields)
        vendor.set_password(password)
        vendor.save(using=self._db)
        return vendor

    use_in_migrations = True


class Vendor(AbstractBaseUser):
    USERNAME_FIELD = "phone"
    REQUIRED_FIELDS = ["first_name", "last_name", "national_id"]

    objects = VendorManager()

    class Meta:
        db_table = "vendor"
        verbose_name_plural = "vendors"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(phone__regex=r"^\+?[0-9]{8,15}$"),
                name="vendor_phone_canonical_format",
            ),
            models.UniqueConstraint(
                fields=["national_id"],
                name="vendor_national_id_unique",
            ),
        ]

    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    email = models.EmailField(null=True, blank=True)
    phone = models.CharField(max_length=20, unique=True, db_index=True)
    national_id = models.CharField(max_length=20, db_index=True)
    status = models.ForeignKey(
        "VendorStatus",
        on_delete=models.PROTECT,
        related_name="vendors",
    )
    vendor_code = models.CharField(max_length=50, unique=True, db_index=True)
    date_of_birth = models.DateField(null=True, blank=True)
    gender = models.CharField(max_length=10, choices=GENDER_CHOICES, null=True, blank=True)
    email_verified_at = models.DateTimeField(null=True, blank=True)
    phone_verified_at = models.DateTimeField(null=True, blank=True)
    last_login = models.DateTimeField(null=True, blank=True, db_column="last_login_at")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def generate_vendor_code(self):
        last = Vendor.objects.order_by("id").last()
        if last is None:
            return "VEN-00001"
        num = int(last.vendor_code.split("-")[1]) + 1
        return f"VEN-{num:05d}"

    def save(self, *args, **kwargs):
        self.phone = normalize_phone(self.phone)
        if not self.vendor_code:
            self.vendor_code = self.generate_vendor_code()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.vendor_code})"
