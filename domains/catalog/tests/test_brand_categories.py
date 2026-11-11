from django.test import TestCase

from domains.catalog.api.serializers import BrandSerializer, BrandWriteSerializer
from domains.catalog.models import BrandCategory, Category, CategoryStatus
from domains.catalog.services.brand_service import BrandService


class BrandCategoryTests(TestCase):
    def setUp(self):
        status = CategoryStatus.objects.create(name="active-brand-category-test")
        self.first = Category.objects.create(name="Phones", status=status)
        self.second = Category.objects.create(name="Accessories", status=status)
        self.service = BrandService()

    def test_brand_service_replaces_category_assignments(self):
        brand = self.service.create_brand(
            name="Example Brand", category_ids=[self.first, self.second]
        )

        self.assertEqual(
            set(brand.categories.values_list("id", flat=True)),
            {self.first.id, self.second.id},
        )

        self.service.update_brand(brand, category_ids=[self.second])

        self.assertEqual(list(brand.categories.values_list("id", flat=True)), [self.second.id])

    def test_ensure_categories_is_additive_and_idempotent(self):
        brand = self.service.create_brand(name="Imported Brand")

        self.service.ensure_categories(brand, [self.first])
        self.service.ensure_categories(brand, [self.first, self.second])

        self.assertEqual(BrandCategory.objects.filter(brand=brand).count(), 2)

    def test_brand_serializers_accept_ids_and_return_category_details(self):
        write = BrandWriteSerializer(
            data={"name": "Serialized Brand", "category_ids": [self.first.id]}
        )
        self.assertTrue(write.is_valid(), write.errors)
        brand = self.service.create_brand(**write.validated_data)

        payload = BrandSerializer(brand).data

        self.assertEqual(payload["categories"][0]["id"], self.first.id)
        self.assertEqual(payload["categories"][0]["name"], self.first.name)
