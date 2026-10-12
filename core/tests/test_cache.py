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

    def test_public_read_uses_configured_prefix(self):
        self.connection.get.return_value = b'{"ok":true}'

        self.assertEqual(self.service.get_public("content:home"), {"ok": True})
        self.connection.get.assert_called_once_with("public:content:home")

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

    def test_public_write_can_set_positive_ttl(self):
        self.assertTrue(self.service.put_public("content:home", {}, ttl=300))

        self.connection.set.assert_called_once_with("public:content:home", "{}", ex=300)

    def test_public_delete_is_prefixed_and_fails_open(self):
        self.assertTrue(self.service.delete_public("content:home"))
        self.connection.delete.assert_called_once_with("public:content:home")

        self.connection.delete.side_effect = ConnectionError("offline")
        with self.assertLogs("core.services.cache", level="WARNING"):
            self.assertFalse(self.service.delete_public("content:home"))

    def test_serialization_errors_are_not_hidden_as_redis_failures(self):
        with self.assertRaises(TypeError):
            self.service.put_private("unsupported", {object()})

        self.connection.set.assert_not_called()

    def test_non_finite_numbers_are_rejected(self):
        with self.assertRaises(ValueError):
            self.service.put_public("invalid-number", {"value": float("nan")})

        self.connection.set.assert_not_called()

    def test_get_or_set_public_returns_the_cached_payload_without_building(self):
        self.connection.get.return_value = b'{"title":"page"}'
        builder = Mock()

        result = self.service.get_or_set_public(
            "content:pages:about", builder, ttl=300
        )

        self.assertEqual(result, {"title": "page"})
        builder.assert_not_called()
        self.connection.set.assert_not_called()

    def test_get_or_set_public_builds_once_and_stores_with_the_given_ttl(self):
        self.connection.get.return_value = None
        self.connection.set.return_value = True
        builder = Mock(return_value={"title": "page"})

        result = self.service.get_or_set_public(
            "content:pages:about", builder, ttl=300
        )

        self.assertEqual(result, {"title": "page"})
        self.assertEqual(
            self.connection.set.call_args_list[0].args,
            ("private:content:pages:about:rebuild-lock", b"1"),
        )
        self.assertEqual(
            self.connection.set.call_args_list[0].kwargs,
            {"nx": True, "ex": 10},
        )
        self.assertEqual(
            self.connection.set.call_args_list[1].args,
            ("public:content:pages:about", '{"title":"page"}'),
        )
        self.assertEqual(self.connection.set.call_args_list[1].kwargs, {"ex": 300})
        # Released after the write so waiters can observe the new value.
        self.connection.delete.assert_called_once_with(
            "private:content:pages:about:rebuild-lock"
        )

    def test_get_or_set_public_lets_the_builder_choose_its_own_ttl(self):
        self.connection.get.return_value = None
        self.connection.set.return_value = True
        builder = Mock(return_value=({"title": "page"}, 45))

        result = self.service.get_or_set_public("content:pages:about", builder)

        self.assertEqual(result, {"title": "page"})
        self.assertEqual(self.connection.set.call_args_list[1].kwargs, {"ex": 45})

    def test_get_or_set_public_skips_the_write_when_the_builder_disables_it(self):
        self.connection.get.return_value = None
        self.connection.set.return_value = True
        builder = Mock(return_value=({"title": "page"}, 0))

        result = self.service.get_or_set_public("content:pages:about", builder)

        self.assertEqual(result, {"title": "page"})
        # Only the lock was written; `cache_ttl = 0` still means "do not store".
        self.assertEqual(len(self.connection.set.call_args_list), 1)

    def test_get_or_set_public_returns_the_winner_payload_instead_of_rebuilding(self):
        self.connection.get.side_effect = [None, None, b'{"title":"page"}']
        self.connection.set.return_value = None
        self.connection.exists.return_value = True
        builder = Mock()

        with patch("core.services.cache.time.sleep") as sleep:
            result = self.service.get_or_set_public(
                "content:pages:about", builder, ttl=300
            )

        self.assertEqual(result, {"title": "page"})
        builder.assert_not_called()
        sleep.assert_called_once_with(0.05)

    def test_get_or_set_public_builds_at_once_when_the_winner_cached_nothing(self):
        self.connection.get.side_effect = [None, None]
        self.connection.set.return_value = None
        self.connection.exists.return_value = False
        builder = Mock(return_value={"title": "page"})

        result = self.service.get_or_set_public(
            "content:pages:about", builder, ttl=300
        )

        self.assertEqual(result, {"title": "page"})
        builder.assert_called_once_with()

    def test_get_or_set_public_treats_a_falsy_payload_as_a_hit(self):
        self.connection.get.side_effect = [None, b"[]"]
        self.connection.set.return_value = None
        self.connection.exists.return_value = True
        builder = Mock()

        with patch("core.services.cache.time.sleep"):
            result = self.service.get_or_set_public("content:pages:empty", builder)

        self.assertEqual(result, [])
        builder.assert_not_called()

    def test_get_or_set_public_builds_without_a_lock_when_redis_is_down(self):
        self.connection.get.side_effect = ConnectionError("offline")
        self.connection.set.side_effect = ConnectionError("offline")
        self.connection.exists.side_effect = ConnectionError("offline")
        builder = Mock(return_value={"title": "page"})

        with self.assertLogs("core.services.cache", level="WARNING"):
            result = self.service.get_or_set_public(
                "content:pages:about", builder, ttl=300
            )

        self.assertEqual(result, {"title": "page"})
        builder.assert_called_once_with()

    def test_get_or_set_public_returns_the_payload_when_the_write_fails(self):
        self.connection.get.return_value = None
        self.connection.set.side_effect = [True, ConnectionError("offline")]
        builder = Mock(return_value={"title": "page"})

        with self.assertLogs("core.services.cache", level="WARNING"):
            result = self.service.get_or_set_public(
                "content:pages:about", builder, ttl=300
            )

        self.assertEqual(result, {"title": "page"})
