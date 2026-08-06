from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit

import requests

from .contracts import DETAIL_PATH, LISTING_PATH, validate_api_url, validate_detail_url


class DigikalaHTTPError(RuntimeError):
    pass


IMAGE_MAX_BYTES = 12 * 1024 * 1024
IMAGE_EXTENSION_TYPES = {
    ".avif": "image/avif",
    ".gif": "image/gif",
    ".jpeg": "image/jpeg",
    ".jpg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}


def _allowed_image_host(hostname: str | None) -> bool:
    hostname = (hostname or "").lower()
    return hostname == "digikala.com" or hostname.endswith(".digikala.com")


class DigikalaClient:
    def __init__(
        self,
        *,
        timeout: int = 30,
        retries: int = 3,
        delay: float = 1.0,
        max_response_bytes: int = 10 * 1024 * 1024,
        max_image_bytes: int = IMAGE_MAX_BYTES,
        session: requests.Session | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.timeout = timeout
        self.retries = retries
        self.delay = delay
        self.max_response_bytes = max_response_bytes
        self.max_image_bytes = max_image_bytes
        self.session = session or requests.Session()
        self.sleep = sleep
        self.session.headers.update(
            {
                "Accept": "application/json",
                "User-Agent": "UzShop-Digikala-Integration/1.0",
            }
        )

    def get_listing(self, url: str) -> Any:
        validate_api_url(url, LISTING_PATH, "listing URL")
        return self._get_json(url)

    def get_detail(self, url: str, expected_product_id: int | None = None) -> Any:
        validate_detail_url(url, expected_product_id)
        return self._get_json(url)

    def get_image_bytes(
        self, url: str, *, max_image_bytes: int | None = None
    ) -> tuple[bytes, str]:
        """Download an image from a Digikala CDN host, returning (bytes, content_type)."""
        if not isinstance(url, str):
            raise DigikalaHTTPError("image URL must be a string")
        parts = urlsplit(url)
        if parts.scheme != "https" or not _allowed_image_host(parts.hostname):
            raise DigikalaHTTPError("image URL must use https on a Digikala host")
        limit = max_image_bytes or self.max_image_bytes
        response = None
        try:
            response = self.session.get(
                url, timeout=self.timeout, stream=True, allow_redirects=True
            )
            if not 200 <= response.status_code < 300:
                raise DigikalaHTTPError(f"image HTTP {response.status_code}")
            final_host = urlsplit(response.url).hostname
            if not _allowed_image_host(final_host):
                raise DigikalaHTTPError("image redirect left the Digikala host")
            content_type = (
                response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
            )
            extension = Path(urlsplit(url).path).suffix.lower()
            if not content_type.startswith("image/"):
                content_type = IMAGE_EXTENSION_TYPES.get(extension, content_type)
            if not content_type.startswith("image/"):
                raise DigikalaHTTPError("response is not an image")
            try:
                declared_length = int(response.headers.get("Content-Length") or 0)
            except ValueError:
                declared_length = 0
            if declared_length > limit:
                raise DigikalaHTTPError("image exceeds size limit")
            body = bytearray()
            for chunk in response.iter_content(chunk_size=64 * 1024):
                body.extend(chunk)
                if len(body) > limit:
                    raise DigikalaHTTPError("image exceeds size limit")
            return bytes(body), content_type
        except requests.RequestException as error:
            raise DigikalaHTTPError(str(error)) from error
        finally:
            if response is not None:
                response.close()

    def _get_json(self, url: str) -> Any:
        last_error: Exception | None = None
        attempt = 1
        cookie_challenge_used = False
        while attempt <= self.retries:
            response = None
            try:
                response = self.session.get(
                    url, timeout=self.timeout, stream=True, allow_redirects=False
                )
                if (
                    response.status_code == 307
                    and response.headers.get("Location") == url
                    and response.headers.get("Set-Cookie")
                    and not cookie_challenge_used
                ):
                    cookie_challenge_used = True
                    continue
                if response.status_code == 429 or response.status_code >= 500:
                    raise DigikalaHTTPError(f"transient HTTP {response.status_code}")
                if not 200 <= response.status_code < 300:
                    raise DigikalaHTTPError(f"HTTP {response.status_code}")
                content_type = response.headers.get("Content-Type", "").split(";", 1)[0].lower()
                if content_type not in {"application/json", "application/problem+json"} and not content_type.endswith("+json"):
                    raise DigikalaHTTPError("response is not JSON")
                length = response.headers.get("Content-Length")
                try:
                    declared_length = int(length) if length else 0
                except ValueError:
                    declared_length = 0
                if declared_length > self.max_response_bytes:
                    raise DigikalaHTTPError("response exceeds size limit")
                body = bytearray()
                for chunk in response.iter_content(chunk_size=64 * 1024):
                    body.extend(chunk)
                    if len(body) > self.max_response_bytes:
                        raise DigikalaHTTPError("response exceeds size limit")
                return json.loads(body.decode(response.encoding or "utf-8"))
            except (requests.RequestException, json.JSONDecodeError, UnicodeError, DigikalaHTTPError) as error:
                last_error = error
                transient = isinstance(error, requests.RequestException) or (
                    isinstance(error, DigikalaHTTPError)
                    and str(error).startswith("transient")
                )
                if not transient or attempt == self.retries:
                    break
                retry_after = _retry_after(response)
                self.sleep(retry_after if retry_after is not None else self.delay * attempt)
                attempt += 1
            finally:
                if response is not None:
                    response.close()
        raise DigikalaHTTPError(str(last_error or "request failed")) from last_error


def _retry_after(response: requests.Response | None) -> float | None:
    if response is None:
        return None
    value = response.headers.get("Retry-After")
    if value is None:
        return None
    try:
        return max(0.0, min(float(value), 60.0))
    except ValueError:
        return None
