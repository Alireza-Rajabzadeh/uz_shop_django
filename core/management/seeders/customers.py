from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from django.db import transaction

from core.management.seeders.base import BaseSeeder
from domains.customer.models import (
    Customer,
    CustomerAddress,
    CustomerPreference,
    CustomerStatus,
)
from domains.customer.enums.CustomerStatusEnum import CustomerStatusEnum
from domains.location.models import City


TEST_CUSTOMER_PASSWORD = "Customer123!"


class CustomerSeeder(BaseSeeder):
    @transaction.atomic
    def run(self):
        statuses = {
            CustomerStatusEnum.ACTIVE: {
                "title": "Active",
                "description": "Active customer account",
                "is_active": True,
            },
            CustomerStatusEnum.INACTIVE: {
                "title": "Inactive",
                "description": "Inactive customer account",
                "is_active": False,
            },
            CustomerStatusEnum.PENDING: {
                "title": "Pending",
                "description": "Pending customer account",
                "is_active": False,
            },
            CustomerStatusEnum.BANNED: {
                "title": "Banned",
                "description": "Banned customer account",
                "is_active": False,
            },
        }

        for status_enum, data in statuses.items():
            CustomerStatus.objects.update_or_create(
                id=status_enum.value,
                defaults={
                    "name": status_enum.name.lower(),
                    "title": data["title"],
                    "description": data["description"],
                    "is_active": data["is_active"],
                },
            )

        cities = list(City.objects.select_related("state__country").order_by("id"))
        if not cities:
            raise RuntimeError("Locations must be seeded before test customers.")

        fixed_time = datetime(2025, 1, 1, 12, tzinfo=timezone.utc)
        status_ids = [status.value for status in CustomerStatusEnum]
        genders = ["male", "female", "other", None]

        for index in range(1, 101):
            phone = f"0999{index:07d}"
            status_id = status_ids[(index - 1) % len(status_ids)]
            gender = genders[(index - 1) % len(genders)]
            birth_date = date(
                1980 + ((index - 1) % 25),
                1 + ((index - 1) % 12),
                1 + ((index * 3) % 27),
            )
            defaults = {
                "first_name": "Test",
                "last_name": f"Customer {index:03d}",
                "email": f"test.customer.{index:03d}@uzshop.local",
                "status_id": status_id,
                "date_of_birth": birth_date,
                "gender": gender,
            }
            customer, created = Customer.objects.get_or_create(
                phone=phone,
                defaults=defaults,
            )
            for field, value in defaults.items():
                setattr(customer, field, value)
            customer.email_verified_at = fixed_time - timedelta(days=index) if index % 2 == 0 else None
            customer.phone_verified_at = fixed_time - timedelta(days=index) if index % 3 else None
            customer.last_login = fixed_time - timedelta(hours=index) if index % 4 == 0 else None
            update_fields = [
                *defaults,
                "email_verified_at",
                "phone_verified_at",
                "last_login",
                "updated_at",
            ]
            if created or not customer.has_usable_password():
                customer.set_password(TEST_CUSTOMER_PASSWORD)
                update_fields.append("password")
            customer.save(update_fields=update_fields)

            CustomerPreference.objects.update_or_create(
                customer=customer,
                defaults={
                    "receive_order_emails": index % 2 == 0,
                    "receive_sms_notifications": index % 3 != 0,
                    "receive_push_notifications": index % 4 != 0,
                },
            )

            address_count = 1 + ((index - 1) % 3)
            expected_titles = [f"Test Address {number}" for number in range(1, address_count + 1)]
            CustomerAddress.objects.filter(customer=customer, is_default=True).update(
                is_default=False
            )
            CustomerAddress.objects.filter(
                customer=customer, title__startswith="Test Address "
            ).exclude(title__in=expected_titles).delete()

            for address_number, title in enumerate(expected_titles, start=1):
                city = cities[((index - 1) * 7 + address_number - 1) % len(cities)]
                CustomerAddress.objects.update_or_create(
                    customer=customer,
                    title=title,
                    defaults={
                        "country": city.state.country,
                        "state": city.state,
                        "city": city,
                        "postal_code": f"{1000000000 + index * 10 + address_number:010d}",
                        "address_line1": f"Test street {index}, building {address_number}",
                        "address_line2": f"Development fixture {index:03d}",
                        "house_number": str(address_number),
                        "latitude": Decimal("35.0000000") + Decimal(index) / Decimal("10000"),
                        "longitude": Decimal("51.0000000") + Decimal(address_number) / Decimal("10000"),
                        "is_default": address_number == 1,
                    },
                )
