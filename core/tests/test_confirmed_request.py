import uuid
from concurrent.futures import ThreadPoolExecutor

from django.test import SimpleTestCase, override_settings
from django_redis import get_redis_connection

from core.services import (
    ConfirmedRequestInvalid,
    ConfirmedRequestService,
    ConfirmedRequestThrottled,
)


@override_settings(
    CONFIRMED_REQUEST_DEV_CODE="123456",
    CONFIRMED_REQUEST_DEV_MODE=True,
)
class ConfirmedRequestServiceTests(SimpleTestCase):
    def setUp(self):
        self.connection = get_redis_connection("confirmed_requests")
        self.service = ConfirmedRequestService(self.connection)
        self.subject = f"test-{uuid.uuid4()}"
        self.created_ids = []

    def tearDown(self):
        for request_id in self.created_ids:
            self.service.cancel(request_id)

    def generate(self, **overrides):
        values = {
            "purpose": "customer_login",
            "subject": self.subject,
            "payload": {"customer_id": 42},
            "ttl": 120,
            "max_attempts": 5,
            "cooldown": 0,
        }
        values.update(overrides)
        result = self.service.generate_code(**values)
        self.created_ids.append(result.request_id)
        return result

    def test_generates_configured_development_code_and_returns_payload_once(self):
        generated = self.generate(ttl=60)

        self.assertEqual(generated.code, "123456")
        self.assertEqual(generated.expires_in, 60)
        self.assertEqual(
            self.service.get_code(
                request_id=generated.request_id,
                code=generated.code,
                purpose="customer_login",
            ),
            {"customer_id": 42},
        )
        with self.assertRaises(ConfirmedRequestInvalid):
            self.service.get_code(
                request_id=generated.request_id,
                code=generated.code,
                purpose="customer_login",
            )

    def test_wrong_codes_exhaust_attempts(self):
        generated = self.generate(max_attempts=2)

        for _ in range(2):
            with self.assertRaises(ConfirmedRequestInvalid):
                self.service.get_code(
                    request_id=generated.request_id,
                    code="000000",
                    purpose="customer_login",
                )

        with self.assertRaises(ConfirmedRequestInvalid):
            self.service.get_code(
                request_id=generated.request_id,
                code=generated.code,
                purpose="customer_login",
            )

    def test_check_code_does_not_consume_request(self):
        generated = self.generate()

        checked = self.service.check_code(
            request_id=generated.request_id,
            code=generated.code,
            purpose="customer_login",
        )
        consumed = self.service.get_code(
            request_id=generated.request_id,
            code=generated.code,
            purpose="customer_login",
        )

        self.assertEqual(checked, consumed)

    def test_purpose_is_bound_to_request(self):
        generated = self.generate()

        with self.assertRaises(ConfirmedRequestInvalid):
            self.service.get_code(
                request_id=generated.request_id,
                code=generated.code,
                purpose="password_reset",
            )

    def test_new_request_invalidates_previous_request(self):
        first = self.generate()
        second = self.generate()

        with self.assertRaises(ConfirmedRequestInvalid):
            self.service.get_code(
                request_id=first.request_id,
                code=first.code,
                purpose="customer_login",
            )
        self.assertEqual(
            self.service.get_code(
                request_id=second.request_id,
                code=second.code,
                purpose="customer_login",
            )["customer_id"],
            42,
        )

    def test_concurrent_generation_leaves_only_one_valid_request(self):
        def create_request(_):
            return self.service.generate_code(
                purpose="customer_login",
                subject=self.subject,
                payload={"customer_id": 42},
                cooldown=0,
            )

        with ThreadPoolExecutor(max_workers=2) as executor:
            generated = list(executor.map(create_request, range(2)))
        self.created_ids.extend(item.request_id for item in generated)

        successes = 0
        for item in generated:
            try:
                self.service.get_code(
                    request_id=item.request_id,
                    code=item.code,
                    purpose="customer_login",
                )
            except ConfirmedRequestInvalid:
                continue
            successes += 1
        self.assertEqual(successes, 1)

    def test_generation_cooldown_is_enforced(self):
        generated = self.generate(cooldown=30)

        with self.assertRaises(ConfirmedRequestThrottled) as caught:
            self.generate(cooldown=30)

        self.assertGreater(caught.exception.retry_after, 0)
        self.service.cancel(generated.request_id)

    @override_settings(CONFIRMED_REQUEST_DEV_CODE="")
    def test_production_code_is_six_digits(self):
        generated = self.generate()

        self.assertRegex(generated.code, r"^[0-9]{6}$")
