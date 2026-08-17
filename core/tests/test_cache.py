from unittest.mock import Mock, patch

from django.test import SimpleTestCase, override_settings

from core.services import CacheService


@override_settings(CACHE_PUBLIC_PREFIX="public", CACHE_PRIVATE_PREFIX="private")
class CacheServiceTests(SimpleTestCase):
    def setUp(self):
        self.connection = Mock()
        self.service = CacheService(self.connection)

    def test_get_returns_deserialized_data(self):
        self.connection.get.return_value = b'{"items":[1,true,null]}'

        result = self.service.get("public:categories")

        self.assertEqual(result, {"items": [1, True, None]})
        self.connection.get.assert_called_once_with("public:categories")

    def test_get_returns_none_for_missing_or_malformed_values(self):
        self.connection.get.return_value = None
        self.assertIsNone(self.service.get("public:missing"))

        self.connection.get.return_value = "not-json"
        with self.assertLogs("core.services.cache", level="WARNING"):
            self.assertIsNone(self.service.get("public:malformed"))

    def test_get_treats_connection_failure_as_cache_miss(self):
        self.connection.get.side_effect = ConnectionError("offline")

        with self.assertLogs("core.services.cache", level="WARNING"):
            result = self.service.get("private:profile")

        self.assertIsNone(result)

    def test_public_and_private_writes_use_configured_prefixes(self):
        self.assertTrue(self.service.put_public("categories", {"name": "کالا"}))
        self.assertTrue(self.service.put_private("some_cache", [1, 2]))

        self.assertEqual(
            self.connection.set.call_args_list[0].args,
            ("public:categories", '{"name":"کالا"}'),
        )
        self.assertEqual(
            self.connection.set.call_args_list[1].args,
            ("private:some_cache", "[1,2]"),
        )

    def test_public_and_private_writes_delegate_to_put(self):
        with patch.object(self.service, "_put", return_value=True) as put:
            self.service.put_public("categories", [])
            self.service.put_private("some_cache", {})

        self.assertEqual(
            [call.args for call in put.call_args_list],
            [
                ("public:categories", []),
                ("private:some_cache", {}),
            ],
        )

    def test_put_returns_false_when_redis_is_unavailable(self):
        self.connection.set.side_effect = ConnectionError("offline")

        with self.assertLogs("core.services.cache", level="WARNING"):
            result = self.service.put_public("categories", [])

        self.assertFalse(result)

    def test_serialization_errors_are_not_hidden_as_redis_failures(self):
        with self.assertRaises(TypeError):
            self.service.put_private("unsupported", {object()})

        self.connection.set.assert_not_called()

    def test_non_finite_numbers_are_rejected(self):
        with self.assertRaises(ValueError):
            self.service.put_public("invalid-number", {"value": float("nan")})

        self.connection.set.assert_not_called()
