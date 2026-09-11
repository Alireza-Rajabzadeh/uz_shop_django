from enum import Enum


class InventoryAttributeTypeEnum(Enum):
    TEXT = "text"
    INTEGER = "integer"
    DECIMAL = "decimal"
    BOOLEAN = "boolean"
    DATE = "date"
    DATETIME = "datetime"

    @classmethod
    def choices(cls):
        return [(member.value, member.name.replace("_", " ").capitalize()) for member in cls]
