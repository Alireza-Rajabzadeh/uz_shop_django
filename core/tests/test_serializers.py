from django.test import RequestFactory, SimpleTestCase
from rest_framework import serializers

from core.serializers import BusinessAwareSerializer, TenantScopedSerializer


class DummySerializer(TenantScopedSerializer):
    business_id = serializers.IntegerField(required=False)
    name = serializers.CharField()


class TenantScopedSerializerTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_precedence_of_request_business_id(self):
        from types import SimpleNamespace
        request = self.factory.get("/")
        request.business = SimpleNamespace(id=42)

        serializer = DummySerializer(
            data={"business_id": 999, "name": "Test"},
            context={"request": request},
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data["business_id"], 42)

    def test_without_request_business_id_uses_client_data(self):
        request = self.factory.get("/")
        request.business = None

        serializer = DummySerializer(
            data={"business_id": 999, "name": "Test"},
            context={"request": request},
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data["business_id"], 999)

    def test_without_request_in_context_uses_client_data(self):
        serializer = DummySerializer(
            data={"business_id": 999, "name": "Test"},
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data["business_id"], 999)

    def test_alias_equivalence(self):
        self.assertIs(TenantScopedSerializer, BusinessAwareSerializer)
