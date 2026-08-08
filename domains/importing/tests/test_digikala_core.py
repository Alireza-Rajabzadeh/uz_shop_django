import json
from pathlib import Path
import tempfile
from unittest import TestCase

import requests

from domains.importing.integrations.digikala.cli import main
from domains.importing.integrations.digikala.client import DigikalaClient, DigikalaHTTPError
from domains.importing.integrations.digikala.contracts import (
    ApprovedCategory,
    ListingOptions,
    ValidationError,
    load_approved_mapping,
)
from domains.importing.integrations.digikala.detail import normalize_detail
from domains.importing.integrations.digikala.filesystem import read_json
from domains.importing.integrations.digikala.listing import find_total_pages
from domains.importing.integrations.digikala.pipeline import (
    CollectionCancelled,
    collect_details,
    collect_listings,
    validate_listing_document,
)


def mapping(category_id=1001, digikala_id=10):
    return {
        "category_id": category_id,
        "name": f"Category {category_id}",
        "digikala_category_id": digikala_id,
        "api_url": f"https://api.digikala.com/discovery/api/v2/categories/{digikala_id}/products",
    }


def widget(product_id, *, ad=False):
    return {
        "type": "product",
        "data": {
            "id": product_id,
            "title_fa": f"Product {product_id}",
            "images": {"main": {"url": [f"https://img/{product_id}.jpg"]}},
            "properties": {"is_ad": ad},
            "default_variant": {"id": product_id * 10, "price": {"selling_price": 100}},
        },
    }


class FakeClient:
    def __init__(self, listings=None, details=None):
        self.listings = iter(listings or [])
        self.details = details or {}
        self.listing_urls = []

    def get_listing(self, url):
        self.listing_urls.append(url)
        return next(self.listings)

    def get_detail(self, url, expected_product_id=None):
        return self.details[expected_product_id]


class FakeResponse:
    def __init__(self, status, body=b"{}", headers=None):
        self.status_code = status
        self.body = body
        self.headers = {"Content-Type": "application/json", **(headers or {})}
        self.encoding = "utf-8"
        self.closed = False

    def iter_content(self, chunk_size):
        yield self.body

    def close(self):
        self.closed = True


class FakeSession:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.headers = {}
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        response = next(self.responses)
        if isinstance(response, Exception):
            raise response
        return response


class ContractTests(TestCase):
    def test_options_enforce_bounds_and_defaults(self):
        options = ListingOptions()
        self.assertEqual(options.currency, "IRR")
        self.assertFalse(options.include_ads)
        for values in (
            {"products_per_category": 101},
            {"timeout": 61},
            {"retries": 6},
            {"delay": 0.49},
            {"currency": "USD"},
            {"timeout": 1.5},
            {"retries": True},
        ):
            with self.subTest(values=values), self.assertRaises(ValidationError):
                ListingOptions(**values)

    def test_mapping_requires_exact_https_host_path_and_matching_id(self):
        self.assertEqual(ApprovedCategory.from_dict(mapping()).digikala_category_id, 10)
        invalid_urls = (
            "http://api.digikala.com/discovery/api/v2/categories/10/products",
            "https://evil.example/discovery/api/v2/categories/10/products",
            "https://api.digikala.com/v2/product/10/",
            "https://api.digikala.com:443/discovery/api/v2/categories/10/products",
        )
        for url in invalid_urls:
            with self.subTest(url=url), self.assertRaises(ValidationError):
                ApprovedCategory.from_dict({**mapping(), "api_url": url})

    def test_mapping_file_accepts_categories_wrapper_and_many_categories(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "mapping.json"
            path.write_text(json.dumps({"categories": [mapping()]}), encoding="utf-8")
            self.assertEqual(len(load_approved_mapping(path)), 1)
            path.write_text(
                json.dumps([mapping(1000 + index, index) for index in range(1, 7)]),
                encoding="utf-8",
            )
            self.assertEqual(len(load_approved_mapping(path)), 6)
            path.write_text(
                json.dumps([mapping(1000 + index, index) for index in range(1, 51)]),
                encoding="utf-8",
            )
            self.assertEqual(len(load_approved_mapping(path)), 50)


class ClientTests(TestCase):
    def test_retries_same_url_cookie_challenge_without_following_redirect(self):
        url = "https://api.digikala.com/v2/product/12/"
        challenge = FakeResponse(
            307,
            b"",
            {"Location": url, "Set-Cookie": "digicdn_cookie=value"},
        )
        session = FakeSession([challenge, FakeResponse(200, b'{"ok": true}')])

        result = DigikalaClient(session=session, retries=1).get_detail(url, 12)

        self.assertEqual(result, {"ok": True})
        self.assertEqual(len(session.calls), 2)

    def test_retries_transient_response_using_retry_after(self):
        first = FakeResponse(429, headers={"Retry-After": "2"})
        second = FakeResponse(200, b'{"ok": true}')
        session = FakeSession([first, second])
        sleeps = []
        client = DigikalaClient(session=session, retries=2, sleep=sleeps.append)

        result = client.get_detail("https://api.digikala.com/v2/product/12/", 12)

        self.assertEqual(result, {"ok": True})
        self.assertEqual(sleeps, [2.0])
        self.assertTrue(first.closed)
        self.assertEqual(
            session.calls[0][1],
            {"timeout": 30, "stream": True, "allow_redirects": False},
        )

    def test_retries_request_errors_and_rejects_large_or_non_json_response(self):
        session = FakeSession([requests.ConnectionError("offline"), FakeResponse(200)])
        client = DigikalaClient(session=session, retries=2, sleep=lambda value: None)
        self.assertEqual(client.get_detail("https://api.digikala.com/v2/product/1/"), {})

        for response in (
            FakeResponse(200, b"{}", {"Content-Length": "100"}),
            FakeResponse(200, b"{}", {"Content-Type": "text/html"}),
        ):
            with self.subTest(headers=response.headers), self.assertRaises(DigikalaHTTPError):
                DigikalaClient(
                    session=FakeSession([response]), retries=1, max_response_bytes=10
                ).get_detail("https://api.digikala.com/v2/product/1/")


class PipelineTests(TestCase):
    def test_pagination_prefers_operational_pager_over_tracker_metadata(self):
        self.assertEqual(
            find_total_pages(
                {
                    "pager": {"total_pages": 100},
                    "tracker_data": {"total_pages": 367},
                }
            ),
            100,
        )

    def test_collects_sequentially_dedupes_filters_ads_and_aggregates(self):
        pages = [
            {"data": {"pager": {"total_pages": 1}, "widgets": [widget(1), widget(1), widget(2, ad=True), widget(3)]}},
            {"data": {"pager": {"total_pages": 1}, "widgets": [widget(3), widget(4)]}},
        ]
        client = FakeClient(listings=pages)
        events = []
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "listing.json"
            result = collect_listings(
                [mapping(1001, 10), mapping(1002, 20)],
                ListingOptions(products_per_category=2),
                output,
                client=client,
                progress=events.append,
            )
            disk_result = validate_listing_document(read_json(output))

            self.assertEqual(result, disk_result)
            self.assertEqual([item["product_id"] for item in result["products"]], [1, 3, 4])
            product_three = next(item for item in result["products"] if item["product_id"] == 3)
            self.assertEqual(product_three["category_ids"], [1001, 1002])
            self.assertEqual(result["summary"]["category_product_count"], 4)
            self.assertEqual(len(events), 2)
            self.assertIn("page=1", client.listing_urls[0])
            with self.assertRaises(FileExistsError):
                collect_listings(
                    [mapping()], ListingOptions(products_per_category=1), output,
                    client=FakeClient(listings=[{"widgets": [widget(1)]}]),
                )

    def test_cancellation_writes_no_partial_listing(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "listing.json"
            with self.assertRaises(CollectionCancelled):
                collect_listings(
                    [mapping()], ListingOptions(products_per_category=1), output,
                    client=FakeClient(), cancel=lambda: True,
                )
            self.assertFalse(output.exists())

    def test_details_selects_listing_ids_and_writes_normalized_files(self):
        with tempfile.TemporaryDirectory() as directory:
            listing_path = Path(directory) / "listing.json"
            collect_listings(
                [mapping()], ListingOptions(products_per_category=2), listing_path,
                client=FakeClient(listings=[{"widgets": [widget(1), widget(2)]}]),
            )
            output = Path(directory) / "details"
            paths = collect_details(
                listing_path, output, product_ids=[2],
                client=FakeClient(details={2: {"data": {"product": {"id": 2}}}}),
            )
            self.assertEqual(paths, [output / "2.json"])
            self.assertEqual(read_json(paths[0])["source"]["id"], 2)
            with self.assertRaisesRegex(ValueError, "not in listing"):
                collect_details(listing_path, output, product_ids=[99], client=FakeClient())


class DetailTests(TestCase):
    def test_flexible_normalizer_preserves_import_fields_and_handles_missing_values(self):
        payload = {
            "data": {
                "product": {
                    "id": 42,
                    "title_fa": "Title",
                    "description": "<p>Hello&nbsp; world</p>",
                    "status": "marketable",
                    "brand": {"id": 7, "code": "brand", "title_fa": "Brand"},
                    "category": {
                        "id": 8,
                        "title": "Category",
                        "breadcrumb": [{"id": 9, "title_fa": "Root"}],
                    },
                    "specifications": [{"title": "General", "attributes": [{"id": 1, "title": "Weight", "values": ["1kg"]}]}],
                    "variants": [{
                        "id": 5, "status": "active", "themes": ["light"],
                        "color": {"id": 3, "title": "Red"},
                        "price": {"selling_price": 100}, "marketable_stock": 4,
                        "seller": {"id": 2, "title": "Seller"},
                        "warranty": {"id": 1, "title_fa": "Warranty"},
                    }],
                    "images": {"main": {"url": ["main.jpg"]}, "list": [{"url": ["one.jpg"]}]},
                }
            }
        }

        result = normalize_detail(payload, 42)

        self.assertEqual(result["description"], "Hello world")
        self.assertEqual(result["brand"]["code"], "brand")
        self.assertEqual(result["breadcrumb"][0]["title_fa"], "Root")
        self.assertEqual(result["specifications"][0]["attributes"][0]["values"], ["1kg"])
        self.assertEqual(result["variants"][0]["stock"]["marketable"], 4)
        self.assertEqual(result["images"], {"main": ["main.jpg"], "gallery": ["one.jpg"]})
        self.assertEqual(normalize_detail({"product": {"id": 1}})["variants"], [])
        with self.assertRaisesRegex(ValueError, "does not match"):
            normalize_detail(payload, 41)


class CLITests(TestCase):
    def test_validate_returns_clear_success_and_input_error_codes(self):
        with tempfile.TemporaryDirectory() as directory:
            valid = Path(directory) / "valid.json"
            valid.write_text(json.dumps([mapping()]), encoding="utf-8")
            invalid = Path(directory) / "invalid.json"
            invalid.write_text("{}", encoding="utf-8")
            self.assertEqual(main(["validate", "--mapping", str(valid)]), 0)
            self.assertEqual(main(["validate", "--mapping", str(invalid)]), 2)
