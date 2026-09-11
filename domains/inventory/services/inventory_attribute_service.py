import datetime
import re

from django.core.exceptions import ValidationError
from django.db import transaction

from ..enums.InventoryAttributeTypeEnum import InventoryAttributeTypeEnum
from ..models.inventory_attribute import InventoryAttribute
from ..models.inventory_attribute_definition import InventoryAttributeDefinition
from ..models.inventory_unit_attribute import InventoryUnitAttribute


class InventoryAttributeService:
    @staticmethod
    def validate_value(value, attr_type):
        if value == "":
            return True
        if attr_type == InventoryAttributeTypeEnum.TEXT.value:
            return isinstance(value, str)
        if attr_type == InventoryAttributeTypeEnum.INTEGER.value:
            try:
                int(value)
                return True
            except (ValueError, TypeError):
                return False
        if attr_type == InventoryAttributeTypeEnum.DECIMAL.value:
            try:
                float(value)
                return True
            except (ValueError, TypeError):
                return False
        if attr_type == InventoryAttributeTypeEnum.BOOLEAN.value:
            return value.lower() in ("true", "false", "1", "0", "yes", "no")
        if attr_type == InventoryAttributeTypeEnum.DATE.value:
            try:
                datetime.date.fromisoformat(value)
                return True
            except (ValueError, TypeError):
                return False
        if attr_type == InventoryAttributeTypeEnum.DATETIME.value:
            try:
                datetime.datetime.fromisoformat(value)
                return True
            except (ValueError, TypeError):
                return False
        return False

    @staticmethod
    def normalize_code(name):
        code = re.sub(r"[^a-z0-9]+", "_", name.strip().lower())
        code = code.strip("_")
        return code

    @classmethod
    def get_or_create_definition(cls, business, name, attr_type=None):
        code = cls.normalize_code(name)
        if attr_type is None:
            attr_type = InventoryAttributeTypeEnum.TEXT.value
        definition, _ = InventoryAttributeDefinition.objects.get_or_create(
            business=business,
            code=code,
            defaults={"name": name, "type": attr_type},
        )
        return definition

    @classmethod
    @transaction.atomic
    def set_inventory_attribute(cls, inventory, name, value, attr_type=None):
        definition = cls.get_or_create_definition(
            business=inventory.business,
            name=name,
            attr_type=attr_type,
        )
        if value == "" or value is None:
            InventoryAttribute.objects.filter(
                inventory=inventory,
                attribute_definition=definition,
            ).delete()
            return None
        attr, _ = InventoryAttribute.objects.update_or_create(
            inventory=inventory,
            attribute_definition=definition,
            defaults={"value": str(value)},
        )
        return attr

    @classmethod
    @transaction.atomic
    def set_unit_attribute(cls, inventory_unit, name, value, attr_type=None):
        definition = cls.get_or_create_definition(
            business=inventory_unit.inventory.business,
            name=name,
            attr_type=attr_type,
        )
        if value == "" or value is None:
            InventoryUnitAttribute.objects.filter(
                inventory_unit=inventory_unit,
                attribute_definition=definition,
            ).delete()
            return None
        attr, _ = InventoryUnitAttribute.objects.update_or_create(
            inventory_unit=inventory_unit,
            attribute_definition=definition,
            defaults={"value": str(value)},
        )
        return attr

    @classmethod
    def get_inventory_attribute(cls, inventory, code):
        try:
            attr = InventoryAttribute.objects.select_related("attribute_definition").get(
                inventory=inventory,
                attribute_definition__code=code,
            )
            return attr.value
        except InventoryAttribute.DoesNotExist:
            return None

    @classmethod
    def get_unit_attribute(cls, inventory_unit, code):
        try:
            attr = InventoryUnitAttribute.objects.select_related("attribute_definition").get(
                inventory_unit=inventory_unit,
                attribute_definition__code=code,
            )
            return attr.value
        except InventoryUnitAttribute.DoesNotExist:
            return None

    @classmethod
    def get_all_inventory_attributes(cls, inventory):
        attrs = InventoryAttribute.objects.select_related("attribute_definition").filter(
            inventory=inventory,
        )
        return {attr.attribute_definition.code: attr.value for attr in attrs}

    @classmethod
    def get_all_unit_attributes(cls, inventory_unit):
        attrs = InventoryUnitAttribute.objects.select_related("attribute_definition").filter(
            inventory_unit=inventory_unit,
        )
        return {attr.attribute_definition.code: attr.value for attr in attrs}
