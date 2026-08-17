import hashlib
import hmac
import json
import re
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from django.conf import settings
from django_redis import get_redis_connection


class ConfirmedRequestError(Exception):
    pass


class ConfirmedRequestInvalid(ConfirmedRequestError):
    pass


class ConfirmedRequestThrottled(ConfirmedRequestError):
    def __init__(self, retry_after):
        self.retry_after = max(int(retry_after), 1)
        super().__init__(f"Try again in {self.retry_after} seconds.")


class ConfirmedRequestConfigurationError(ConfirmedRequestError):
    pass


@dataclass(frozen=True)
class GeneratedConfirmation:
    request_id: str
    code: str
    expires_in: int
    resend_after: int
    expires_at: datetime
    resend_at: datetime


class ConfirmedRequestService:
    cache_alias = "confirmed_requests"
    key_prefix = "backend:confirmed-request"
    code_pattern = re.compile(r"^[0-9]{6}$")

    generate_script = """
if tonumber(ARGV[4]) > 0 and redis.call('EXISTS', KEYS[1]) == 1 then
    return {'throttled', redis.call('TTL', KEYS[1])}
end

local previous = redis.call('GET', KEYS[2])
if previous then redis.call('DEL', ARGV[5] .. previous) end
redis.call('SET', KEYS[3], ARGV[2], 'EX', ARGV[3])
redis.call('SET', KEYS[2], ARGV[1], 'EX', ARGV[3])
if tonumber(ARGV[4]) > 0 then
    redis.call('SET', KEYS[1], ARGV[1], 'EX', ARGV[4])
end
return {'ok'}
"""

    consume_script = """
local raw = redis.call('GET', KEYS[1])
if not raw then return {'invalid'} end

local state = cjson.decode(raw)
if state['purpose'] ~= ARGV[1] then return {'invalid'} end
if redis.call('GET', state['active_key']) ~= ARGV[3] then
    redis.call('DEL', KEYS[1])
    return {'invalid'}
end
if state['code_hash'] ~= ARGV[2] then
    state['attempts'] = state['attempts'] - 1
    if state['attempts'] <= 0 then
        redis.call('DEL', KEYS[1])
        if redis.call('GET', state['active_key']) == ARGV[3] then
            redis.call('DEL', state['active_key'])
        end
        return {'invalid'}
    end
    redis.call('SET', KEYS[1], cjson.encode(state), 'KEEPTTL')
    return {'invalid'}
end

if ARGV[4] == '0' then
    return {'ok', cjson.encode(state['payload'])}
end
redis.call('DEL', KEYS[1])
if redis.call('GET', state['active_key']) == ARGV[3] then
    redis.call('DEL', state['active_key'])
end
return {'ok', cjson.encode(state['payload'])}
"""

    cancel_script = """
local raw = redis.call('GET', KEYS[1])
if not raw then return 0 end
local state = cjson.decode(raw)
redis.call('DEL', KEYS[1])
if redis.call('GET', state['active_key']) == ARGV[1] then
    redis.call('DEL', state['active_key'])
end
if state['cooldown_key'] and redis.call('GET', state['cooldown_key']) == ARGV[1] then
    redis.call('DEL', state['cooldown_key'])
end
return 1
"""

    def __init__(self, connection=None):
        self.connection = connection or get_redis_connection(self.cache_alias)

    def generate_code(
        self,
        *,
        purpose,
        subject,
        payload,
        ttl=120,
        max_attempts=5,
        cooldown=30,
    ):
        self._validate_generation(purpose, subject, payload, ttl, max_attempts, cooldown)
        request_id = secrets.token_urlsafe(32)
        code = self._generate_code()
        subject_hash = self._digest(str(subject))
        active_key = f"{self.key_prefix}:active:{purpose}:{subject_hash}"
        cooldown_key = f"{self.key_prefix}:cooldown:{purpose}:{subject_hash}"
        request_key = self._request_key(request_id)

        state = {
            "purpose": purpose,
            "payload": payload,
            "code_hash": self._code_hash(request_id, code),
            "attempts": max_attempts,
            "active_key": active_key,
            "cooldown_key": cooldown_key,
        }
        result = self.connection.eval(
            self.generate_script,
            3,
            cooldown_key,
            active_key,
            request_key,
            request_id,
            json.dumps(state, separators=(",", ":")),
            ttl,
            cooldown,
            f"{self.key_prefix}:request:",
        )
        if self._decode(result[0]) == "throttled":
            raise ConfirmedRequestThrottled(self._decode(result[1]))

        now = datetime.now(UTC)
        remaining_ms = max(self.connection.pttl(request_key), 0)
        cooldown_ms = max(self.connection.pttl(cooldown_key), 0) if cooldown else 0
        return GeneratedConfirmation(
            request_id=request_id,
            code=code,
            expires_in=max((remaining_ms + 999) // 1000, 0),
            resend_after=max((cooldown_ms + 999) // 1000, 0),
            expires_at=now + timedelta(milliseconds=remaining_ms),
            resend_at=now + timedelta(milliseconds=cooldown_ms),
        )

    def get_code(self, *, request_id, code, purpose):
        return self._validate_code(
            request_id=request_id,
            code=code,
            purpose=purpose,
            consume=True,
        )

    def check_code(self, *, request_id, code, purpose):
        return self._validate_code(
            request_id=request_id,
            code=code,
            purpose=purpose,
            consume=False,
        )

    def _validate_code(self, *, request_id, code, purpose, consume):
        if not request_id or not self.code_pattern.fullmatch(str(code)):
            raise ConfirmedRequestInvalid("Invalid or expired confirmation request.")
        result = self.connection.eval(
            self.consume_script,
            1,
            self._request_key(request_id),
            purpose,
            self._code_hash(request_id, str(code)),
            request_id,
            "1" if consume else "0",
        )
        status = self._decode(result[0]) if result else "invalid"
        if status != "ok" or len(result) < 2:
            raise ConfirmedRequestInvalid("Invalid or expired confirmation request.")
        return json.loads(self._decode(result[1]))

    def cancel(self, request_id):
        self.connection.eval(
            self.cancel_script,
            1,
            self._request_key(request_id),
            request_id,
        )

    def remaining_ttl(self, request_id):
        return max(self.connection.ttl(self._request_key(request_id)), 0)

    @classmethod
    def _validate_generation(cls, purpose, subject, payload, ttl, max_attempts, cooldown):
        if not isinstance(purpose, str) or not re.fullmatch(
            r"[a-z][a-z0-9_-]{0,99}", purpose
        ):
            raise ConfirmedRequestConfigurationError("Purpose must be a lowercase code.")
        if subject is None or not str(subject).strip():
            raise ConfirmedRequestConfigurationError("Subject is required.")
        if not isinstance(payload, dict):
            raise ConfirmedRequestConfigurationError("Payload must be a JSON object.")
        try:
            json.dumps(payload)
        except (TypeError, ValueError) as exc:
            raise ConfirmedRequestConfigurationError("Payload must be JSON serializable.") from exc
        if not 10 <= ttl <= 900:
            raise ConfirmedRequestConfigurationError("TTL must be between 10 and 900 seconds.")
        if not 1 <= max_attempts <= 10:
            raise ConfirmedRequestConfigurationError("Attempts must be between 1 and 10.")
        if not 0 <= cooldown <= 300:
            raise ConfirmedRequestConfigurationError("Cooldown must be between 0 and 300 seconds.")

    @classmethod
    def _generate_code(cls):
        development_code = settings.CONFIRMED_REQUEST_DEV_CODE.strip()
        if development_code:
            if not settings.CONFIRMED_REQUEST_DEV_MODE:
                raise ConfirmedRequestConfigurationError(
                    "Development confirmation codes are disabled."
                )
            if not cls.code_pattern.fullmatch(development_code):
                raise ConfirmedRequestConfigurationError(
                    "CONFIRMED_REQUEST_DEV_CODE must contain exactly six digits."
                )
            return development_code
        return f"{secrets.randbelow(1_000_000):06d}"

    @classmethod
    def _request_key(cls, request_id):
        return f"{cls.key_prefix}:request:{request_id}"

    @staticmethod
    def _decode(value):
        return value.decode() if isinstance(value, bytes) else value

    @staticmethod
    def _digest(value):
        return hmac.new(
            settings.SECRET_KEY.encode(), value.encode(), hashlib.sha256
        ).hexdigest()

    @classmethod
    def _code_hash(cls, request_id, code):
        return cls._digest(f"{request_id}:{code}")
