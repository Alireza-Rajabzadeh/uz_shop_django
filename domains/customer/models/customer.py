from django.db import models
from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager


GENDER_CHOICES = [
    ("male", "Male"),
    ("female", "Female"),
    ("other", "Other"),
]


class CustomerManager(BaseUserManager):
    def create_user(self, phone, password=None, **extra_fields):
        if not phone:
            raise ValueError("Phone number is required")
        customer = self.model(phone=phone, **extra_fields)
        customer.set_password(password)
        customer.save(using=self._db)
        return customer

    use_in_migrations = True


class Customer(AbstractBaseUser):
    USERNAME_FIELD = "phone"
    REQUIRED_FIELDS = ["first_name", "last_name"]

    objects = CustomerManager()

    class Meta:
        db_table = "customer"
        verbose_name_plural = "customers"

    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    email = models.EmailField(null=True, blank=True)
    phone = models.CharField(max_length=20, unique=True, db_index=True)
    status = models.ForeignKey(
        "CustomerStatus",
        on_delete=models.PROTECT,
        related_name="customers",
    )
    customer_code = models.CharField(max_length=50, unique=True, db_index=True)
    date_of_birth = models.DateField(null=True, blank=True)
    gender = models.CharField(max_length=10, choices=GENDER_CHOICES, null=True, blank=True)
    email_verified_at = models.DateTimeField(null=True, blank=True)
    phone_verified_at = models.DateTimeField(null=True, blank=True)
    last_login = models.DateTimeField(null=True, blank=True, db_column="last_login_at")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def generate_customer_code(self):
        last = Customer.objects.order_by("id").last()
        if last is None:
            return "CUS-00001"
        num = int(last.customer_code.split("-")[1]) + 1
        return f"CUS-{num:05d}"

    def save(self, *args, **kwargs):
        if not self.customer_code:
            self.customer_code = self.generate_customer_code()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.customer_code})"
