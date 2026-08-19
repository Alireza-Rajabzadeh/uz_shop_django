from copy import deepcopy

from django.utils import timezone

from domains.catalog.services import CategoryService, ProductService, StorefrontProductService

from .contracts import load_content_contracts
from .models import LandingPage, Page


class PageService:
    HOME_SLUG = "home"

    def get_by_slug(self, slug):
        return Page.objects.get(slug=slug)

    def get_home_page(self):
        return self.get_by_slug(self.HOME_SLUG)

    def delete_page(self, instance):
        instance.delete()

    def publish_page(self, instance):
        instance.published_content = instance.draft_content
        instance.status = Page.Status.PUBLISHED
        instance.published_at = timezone.now()
        instance.save()
        return instance


class LandingPageService:
    def get_by_slug(self, slug):
        return LandingPage.objects.get(slug=slug)

    def delete_page(self, instance):
        instance.delete()

    def publish_page(self, instance):
        instance.published_content = instance.draft_content
        instance.status = LandingPage.Status.PUBLISHED
        instance.published_at = timezone.now()
        instance.save()
        return instance


class LandingPageContentResolver:
    def __init__(self, loaders=None):
        self.loaders = loaders or {
            "products": lambda ids: StorefrontProductService().get_content_items(ids),
            "categories": lambda ids: CategoryService().get_storefront_content_items(ids),
        }

    @classmethod
    def for_authoring(cls):
        return cls({
            "products": lambda ids: ProductService().get_authoring_content_items(ids),
            "categories": lambda ids: CategoryService().get_authoring_content_items(ids),
        })

    def resolve(self, content):
        resolved = deepcopy(content)
        contracts = load_content_contracts()
        definitions = {
            (component["key"], component["version"]): component
            for component in contracts.get("components", [])
        }
        references = {resource: [] for resource in self.loaders}

        for component in resolved.get("components", []):
            definition = definitions.get((component.get("key"), component.get("version")))
            if not definition:
                continue
            for name, prop_definition in definition.get("props", {}).items():
                if name in component.get("props", {}):
                    self._collect_references(
                        component["props"][name], prop_definition, references
                    )

        loaded = {}
        for resource, ids in references.items():
            unique_ids = list(dict.fromkeys(ids))
            items = self.loaders[resource](unique_ids)
            loaded[resource] = {item["id"]: item for item in items}

        for component in resolved.get("components", []):
            definition = definitions.get((component.get("key"), component.get("version")))
            if not definition:
                continue
            for name, prop_definition in definition.get("props", {}).items():
                if name in component.get("props", {}):
                    component["props"][name] = self._resolve_value(
                        component["props"][name], prop_definition, loaded
                    )
        return resolved

    def _collect_references(self, value, definition, references):
        value_type = definition.get("type")
        if value_type == "model":
            resource = definition.get("data_source", {}).get("resource")
            if resource not in references:
                return
            values = value if definition.get("cardinality", "one") == "many" else [value]
            references[resource].extend(item for item in values if type(item) is int)
        elif value_type == "array" and isinstance(value, list):
            for item in value:
                self._collect_references(item, definition.get("items", {}), references)
        elif value_type == "object" and isinstance(value, dict):
            for name, item_definition in definition.get("properties", {}).items():
                if name in value:
                    self._collect_references(value[name], item_definition, references)

    def _resolve_value(self, value, definition, loaded):
        value_type = definition.get("type")
        if value_type == "model":
            resource = definition.get("data_source", {}).get("resource")
            items = loaded.get(resource, {})
            if definition.get("cardinality", "one") == "many":
                return [items[item] for item in value if item in items]
            return items.get(value)
        if value_type == "array" and isinstance(value, list):
            item_definition = definition.get("items", {})
            return [self._resolve_value(item, item_definition, loaded) for item in value]
        if value_type == "object" and isinstance(value, dict):
            properties = definition.get("properties", {})
            return {
                name: self._resolve_value(item, properties[name], loaded)
                if name in properties else item
                for name, item in value.items()
            }
        return value
