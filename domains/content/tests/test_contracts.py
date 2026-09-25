from django.contrib.auth.models import Permission, User
from rest_framework import serializers
from rest_framework.test import APITestCase

from core.services import CacheService
from domains.catalog.models import Category, CategoryStatus, Product, ProductStatus

from ..contracts import (
    empty_draft_content,
    load_content_contracts,
    validate_contracts_payload,
    validate_draft_content,
)
from ..models import LandingPage, Page, SEORecord
from ..services import LandingPageService, PageService


class ContractFileInvariantTests(APITestCase):
    def test_committed_contracts_file_is_valid(self):
        payload = load_content_contracts()
        self.assertEqual(validate_contracts_payload(payload), payload)
        self.assertEqual(payload["contract_version"], 4)
        keys = [component["key"] for component in payload["components"]]
        self.assertEqual(
            sorted(keys),
            [
                "business_contact",
                "category_grid",
                "hero_slider",
                "link_list",
                "picture",
                "product_slider",
                "promotional_product_slider",
                "rich_text",
                "small_banner",
                "social_links",
            ],
        )

    def test_small_banner_image_prop_carries_ratio_metadata(self):
        payload = load_content_contracts()
        small_banner = next(
            component
            for component in payload["components"]
            if component["key"] == "small_banner"
        )
        image = small_banner["props"]["items"]["items"]["properties"]["image"]
        self.assertEqual(image["type"], "image")
        self.assertEqual(image["ratio"], "4:3")
        self.assertEqual((image["width"], image["height"]), (640, 480))

    def test_hero_slider_requires_wide_image_dimensions(self):
        payload = load_content_contracts()
        hero_slider = next(
            component
            for component in payload["components"]
            if component["key"] == "hero_slider"
        )
        image = hero_slider["props"]["slides"]["items"]["properties"]["image"]
        self.assertEqual(image["ratio"], "8:3")
        self.assertEqual((image["width"], image["height"]), (1920, 720))
        self.assertTrue(image["enforce_dimensions"])


class ContractsPayloadValidationTests(APITestCase):
    def valid_payload(self):
        return {
            "contract_version": 4,
            "components": [
                {
                    "key": "test_component",
                    "name": "Test Component",
                    "version": 1,
                    "props": {
                        "products": {
                            "type": "model",
                            "cardinality": "many",
                            "data_source": {"resource": "products", "store": "id"},
                        },
                        "cover": {"type": "image", "ratio": "4:3"},
                    },
                }
            ],
        }

    def test_accepts_valid_payload(self):
        self.assertEqual(validate_contracts_payload(self.valid_payload()), self.valid_payload())

    def test_rejects_unknown_prop_type(self):
        payload = self.valid_payload()
        payload["components"][0]["props"]["bad"] = {"type": "product"}
        with self.assertRaises(serializers.ValidationError):
            validate_contracts_payload(payload)

    def test_rejects_model_without_cardinality(self):
        payload = self.valid_payload()
        payload["components"][0]["props"]["products"].pop("cardinality")
        with self.assertRaises(serializers.ValidationError):
            validate_contracts_payload(payload)

    def test_rejects_model_with_unsupported_resource(self):
        payload = self.valid_payload()
        payload["components"][0]["props"]["products"]["data_source"] = {
            "resource": "pages",
            "store": "id",
        }
        with self.assertRaises(serializers.ValidationError):
            validate_contracts_payload(payload)

    def test_rejects_model_storing_more_than_ids(self):
        payload = self.valid_payload()
        payload["components"][0]["props"]["products"]["data_source"]["store"] = "slug"
        with self.assertRaises(serializers.ValidationError):
            validate_contracts_payload(payload)

    def test_rejects_duplicate_component_key_version(self):
        payload = self.valid_payload()
        payload["components"].append(dict(payload["components"][0]))
        with self.assertRaises(serializers.ValidationError):
            validate_contracts_payload(payload)

    def test_rejects_extra_top_level_fields(self):
        payload = self.valid_payload()
        payload["extra"] = True
        with self.assertRaises(serializers.ValidationError):
            validate_contracts_payload(payload)


class DraftContentValidationTests(APITestCase):
    def test_empty_draft_normalizes_to_versioned_envelope(self):
        self.assertEqual(
            validate_draft_content({}),
            {"schema_version": 1, "contract_version": 4, "components": []},
        )

    def test_rejects_duplicate_component_ids_and_invalid_props(self):
        component = {
            "id": "banner-1",
            "key": "small_banner",
            "version": 1,
            "props": {"items": [{"link": "/sale", "title": "Sale"}]},
        }
        with self.assertRaises(serializers.ValidationError):
            validate_draft_content({
                "schema_version": 1,
                "contract_version": 4,
                "components": [component, component],
            })

        component["props"] = {"items": [{"link": 4, "title": "Sale"}]}
        with self.assertRaises(serializers.ValidationError):
            validate_draft_content({
                "schema_version": 1,
                "contract_version": 4,
                "components": [component],
            })

    def test_accepts_model_ids_and_rejects_empty_required_selection(self):
        component = {
            "id": "products-1",
            "key": "product_slider",
            "version": 1,
            "props": {"title": "Featured", "items": [4, 8]},
        }
        content = {
            "schema_version": 1,
            "contract_version": 4,
            "components": [component],
        }
        self.assertEqual(validate_draft_content(content), content)

        component["props"]["items"] = []
        with self.assertRaises(serializers.ValidationError):
            validate_draft_content(content)

    def test_link_accepts_internal_and_external_destinations(self):
        def content_with_link(link):
            return {
                "schema_version": 1,
                "contract_version": 4,
                "components": [
                    {
                        "id": "links-1",
                        "key": "link_list",
                        "version": 1,
                        "props": {"links": [{"title": "About", "link": link}]},
                    }
                ],
            }

        for link in ("/about", "https://example.com/about", "mailto:info@example.com"):
            with self.subTest(link=link):
                content = content_with_link(link)
                self.assertEqual(validate_draft_content(content), content)


