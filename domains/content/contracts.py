import json
import math
from pathlib import Path

from rest_framework import serializers


CONTRACTS_FILE = Path(__file__).resolve().parent / "data" / "content_contracts.json"
SCHEMA_VERSION = 1

ALLOWED_PROP_TYPES = {
    "string",
    "number",
    "integer",
    "boolean",
    "object",
    "array",
    "model",
    "image",
    "link",
    "rich_text",
    "relative_link",
}
ALLOWED_MODEL_RESOURCES = {"products", "categories"}
ALLOWED_CARDINALITIES = {"one", "many"}


def load_content_contracts():
    try:
        return json.loads(CONTRACTS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise serializers.ValidationError(
            "The content component contract is unavailable or invalid."
        ) from exc


def validate_contracts_payload(payload):
    if not isinstance(payload, dict) or set(payload) != {"contract_version", "components"}:
        raise serializers.ValidationError(
            "A content contracts payload must contain only contract_version and components."
        )
    if type(payload["contract_version"]) is not int:
        raise serializers.ValidationError("contract_version must be an integer.")
    if not isinstance(payload["components"], list):
        raise serializers.ValidationError("components must be an array.")

    definitions = {}
    for index, component in enumerate(payload["components"]):
        location = f"components[{index}]"
        if not isinstance(component, dict):
            raise serializers.ValidationError(f"{location} must be an object.")
        required = {"key", "name", "version", "props"}
        if set(component) - required - {"description"}:
            raise serializers.ValidationError(
                f"{location} must contain only key, name, version, description, and props."
            )
        if (
            not isinstance(component.get("key"), str)
            or not component["key"].strip()
        ):
            raise serializers.ValidationError(f"{location}.key must be a non-empty string.")
        if not isinstance(component.get("name"), str):
            raise serializers.ValidationError(f"{location}.name must be a string.")
        if type(component.get("version")) is not int:
            raise serializers.ValidationError(f"{location}.version must be an integer.")
        key = (component["key"], component["version"])
        if key in definitions:
            raise serializers.ValidationError(
                f"Duplicate component key/version: {component['key']}@{component['version']}."
            )
        definitions[key] = component
        _validate_props(component.get("props", {}), f"{location}.props")
    return payload


def _validate_props(properties, location):
    if not isinstance(properties, dict):
        raise serializers.ValidationError(f"{location} must be an object.")
    for name, definition in properties.items():
        _validate_prop(definition, f"{location}.{name}")


def _validate_prop(definition, location):
    if not isinstance(definition, dict):
        raise serializers.ValidationError(f"{location} must be an object.")
    value_type = definition.get("type")
    if value_type not in ALLOWED_PROP_TYPES:
        raise serializers.ValidationError(
            f"{location} uses unsupported contract type {value_type!r}."
        )

    optional_booleans = {"required"}
    optional_numbers = {"min_items", "max_items"}
    optional_strings = {"description", "ratio"}
    optional_positive_numbers = {"width", "height"}
    for field in optional_booleans:
        if field in definition and type(definition[field]) is not bool:
            raise serializers.ValidationError(f"{location}.{field} must be a boolean.")
    for field in optional_numbers:
        if field in definition and type(definition[field]) is not int:
            raise serializers.ValidationError(f"{location}.{field} must be an integer.")
    for field in optional_strings:
        if field in definition and not isinstance(definition[field], str):
            raise serializers.ValidationError(f"{location}.{field} must be a string.")
    for field in optional_positive_numbers:
        if field in definition and (
            type(definition[field]) is not int or definition[field] <= 0
        ):
            raise serializers.ValidationError(f"{location}.{field} must be a positive integer.")
    if "enum" in definition and (
        not isinstance(definition["enum"], list)
        or not all(type(item) in {str, int} for item in definition["enum"])
    ):
        raise serializers.ValidationError(f"{location}.enum must be an array of strings or integers.")

    if value_type == "model":
        _validate_model_prop(definition, location)
    if value_type == "object":
        _validate_props(definition.get("properties", {}), f"{location}.properties")
    if value_type == "array":
        _validate_prop(definition.get("items", {}), f"{location}.items")


def _validate_model_prop(definition, location):
    cardinality = definition.get("cardinality")
    if cardinality not in ALLOWED_CARDINALITIES:
        raise serializers.ValidationError(
            f"{location}.cardinality must be one of {', '.join(sorted(ALLOWED_CARDINALITIES))}."
        )
    data_source = definition.get("data_source")
    if not isinstance(data_source, dict):
        raise serializers.ValidationError(f"{location}.data_source must be an object.")
    if data_source.get("resource") not in ALLOWED_MODEL_RESOURCES:
        raise serializers.ValidationError(
            f"{location}.data_source.resource must be one of "
            f"{', '.join(sorted(ALLOWED_MODEL_RESOURCES))}."
        )
    if data_source.get("store") != "id":
        raise serializers.ValidationError(f"{location}.data_source.store must be 'id'.")
    if "searchable" in data_source and type(data_source["searchable"]) is not bool:
        raise serializers.ValidationError(f"{location}.data_source.searchable must be a boolean.")


def empty_draft_content():
    contract = load_content_contracts()
    return {
        "schema_version": SCHEMA_VERSION,
        "contract_version": contract["contract_version"],
        "components": [],
    }


def validate_draft_content(value):
    if value in ({}, None):
        return empty_draft_content()
    if not isinstance(value, dict):
        raise serializers.ValidationError("Draft content must be an object.")

    expected_fields = {"schema_version", "contract_version", "components"}
    if set(value) != expected_fields:
        raise serializers.ValidationError(
            "Draft content must contain only schema_version, contract_version, and components."
        )

    contract = load_content_contracts()
    if type(value["schema_version"]) is not int or value["schema_version"] != SCHEMA_VERSION:
        raise serializers.ValidationError(f"schema_version must be {SCHEMA_VERSION}.")
    if (
        type(value["contract_version"]) is not int
        or value["contract_version"] != contract.get("contract_version")
    ):
        raise serializers.ValidationError(
            f"contract_version must be {contract.get('contract_version')}."
        )
    if not isinstance(value["components"], list):
        raise serializers.ValidationError("components must be an array.")

    definitions = {
        (component["key"], component["version"]): component
        for component in contract.get("components", [])
    }
    instance_ids = set()
    for index, component in enumerate(value["components"]):
        location = f"components[{index}]"
        if not isinstance(component, dict) or set(component) != {"id", "key", "version", "props"}:
            raise serializers.ValidationError(
                f"{location} must contain only id, key, version, and props."
            )
        if not isinstance(component["id"], str) or not component["id"].strip():
            raise serializers.ValidationError(f"{location}.id must be a non-empty string.")
        if component["id"] in instance_ids:
            raise serializers.ValidationError(f"Duplicate component id: {component['id']}.")
        instance_ids.add(component["id"])
        if not isinstance(component["key"], str) or type(component["version"]) is not int:
            raise serializers.ValidationError(f"{location} has an invalid key or version.")
        definition = definitions.get((component["key"], component["version"]))
        if definition is None:
            raise serializers.ValidationError(
                f"Unknown component key/version: {component['key']}@{component['version']}."
            )
        _validate_object(component["props"], definition.get("props", {}), f"{location}.props")
    return value


def _validate_object(value, properties, location):
    if not isinstance(value, dict):
        raise serializers.ValidationError(f"{location} must be an object.")
    unknown = set(value) - set(properties)
    if unknown:
        raise serializers.ValidationError(
            f"{location} contains unknown properties: {', '.join(sorted(unknown))}."
        )
    missing = [name for name, definition in properties.items() if definition.get("required") and name not in value]
    if missing:
        raise serializers.ValidationError(
            f"{location} is missing required properties: {', '.join(sorted(missing))}."
        )
    for name, item in value.items():
        if properties[name].get("required") and item in (None, "", []):
            raise serializers.ValidationError(
                f"{location}.{name} cannot be empty."
            )
        _validate_value(item, properties[name], f"{location}.{name}")


def _validate_value(value, definition, location):
    value_type = definition.get("type")
    if value_type == "model":
        cardinality = definition.get("cardinality", "one")
        data_source = definition.get("data_source", {})
        if data_source.get("resource") not in {"products", "categories"}:
            raise serializers.ValidationError(
                f"{location} uses an unsupported model resource."
            )
        if data_source.get("store") != "id":
            raise serializers.ValidationError(
                f"{location} must store model IDs."
            )
        if cardinality == "many":
            valid = isinstance(value, list) and all(
                type(item) is int and item > 0 for item in value
            )
        elif cardinality == "one":
            valid = type(value) is int and value > 0
        else:
            raise serializers.ValidationError(
                f"{location} uses unsupported cardinality {cardinality!r}."
            )
    elif value_type in {"string", "link", "image"}:
        valid = isinstance(value, str)
    elif value_type == "relative_link":
        valid = isinstance(value, str) and value.startswith("/")
    elif value_type == "rich_text":
        valid = isinstance(value, str)
    elif value_type == "number":
        valid = type(value) in {int, float} and math.isfinite(value)
    elif value_type == "integer":
        valid = type(value) is int
    elif value_type == "boolean":
        valid = type(value) is bool
    elif value_type == "array":
        valid = isinstance(value, list)
        if valid:
            for index, item in enumerate(value):
                _validate_value(item, definition.get("items", {}), f"{location}[{index}]")
    elif value_type == "object":
        _validate_object(value, definition.get("properties", {}), location)
        valid = True
    else:
        raise serializers.ValidationError(f"{location} uses unsupported contract type {value_type!r}.")

    if not valid:
        raise serializers.ValidationError(f"{location} must be a valid {value_type}.")
    if isinstance(value, list):
        minimum = definition.get("min_items")
        maximum = definition.get("max_items")
        if minimum is not None and len(value) < minimum:
            raise serializers.ValidationError(
                f"{location} must contain at least {minimum} item(s)."
            )
        if maximum is not None and len(value) > maximum:
            raise serializers.ValidationError(
                f"{location} must contain at most {maximum} item(s)."
            )
    if "enum" in definition and value not in definition["enum"]:
        raise serializers.ValidationError(f"{location} must be one of {definition['enum']}.")
