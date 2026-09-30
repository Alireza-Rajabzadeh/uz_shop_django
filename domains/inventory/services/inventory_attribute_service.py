import datetime
import re

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.db.models import F, Q
from django.utils.translation import gettext

from ..enums.InventoryAttributeTypeEnum import InventoryAttributeTypeEnum
from ..models.inventory_attribute_definition import InventoryAttributeDefinition
from ..models.inventory_unit_attribute import InventoryUnitAttribute


class InventoryAttributeService:
    """Unit-attribute validation plus the two-scope definition lookup.

    Definitions are either global (``business IS NULL``, seeded reference
    data) or owned by one business (rows a vendor created because the
    attribute was missing). Every lookup resolves the caller's own row first,
    then the global row, so a business can never lose an attribute it already
    wrote and never shadows a seeded code by accident.
    """

    class ValidationError(Exception):
        def __init__(self, errors):
            self.errors = errors
            super().__init__(str(errors))

    #: The serial number lives in its own column on the snapshot contract, so
    #: it never travels through the generic attribute list.
    SERIAL_NUMBER_CODE = "serial_number"

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

    # ------------------------------------------------------------------
    # Definition lookups (global + business scope)
    # ------------------------------------------------------------------
    @classmethod
    def list_definitions(cls, business):
        """Global definitions plus the ones ``business`` created."""
        return InventoryAttributeDefinition.objects.filter(
            Q(business__isnull=True) | Q(business=business)
        ).order_by(F("business").asc(nulls_first=True), "name", "id")

    @classmethod
    def resolve_definition(cls, code, business=None, *, fallback_to_any=True):
        """Resolve ``code`` for ``business``: own row, then global row.

        ``fallback_to_any`` keeps databases seeded before the global scope
        existed resolving an arbitrary row, exactly like the old
        ``filter(code=...).first()`` did. Write paths pass ``False`` so a
        business never adopts another business's definition.
        """
        if not code:
            return None
        definitions = InventoryAttributeDefinition.objects.filter(code=code)
        if business is not None:
            own = definitions.filter(business=business).first()
            if own is not None:
                return own
        global_row = definitions.filter(business__isnull=True).first()
        if global_row is not None:
            return global_row
        if fallback_to_any:
            return definitions.order_by("id").first()
        return None

    @classmethod
    @transaction.atomic
    def create_definition(cls, business, *, name, fa_title="", attr_type=None, code=None):
        """Insert a definition owned by ``business``.

        Only global rows and the caller's own rows are checked, so a vendor
        can insert an attribute the shared vocabulary is missing while codes
        owned by other businesses stay untouched.
        """
        if business is None:
            raise cls.ValidationError({
                "business": [gettext("A business is required to create an attribute definition.")],
            })
        name = (name or "").strip()
        if not name:
            raise cls.ValidationError({"name": [gettext("This field cannot be blank.")]})
        normalized = cls.normalize_code((code or "").strip() or name)
        if not normalized:
            raise cls.ValidationError({
                "code": [gettext("Provide a code of letters and digits; the name contains none.")],
            })
        if attr_type is None:
            attr_type = InventoryAttributeTypeEnum.TEXT.value
        if attr_type not in [value for value, _label in InventoryAttributeTypeEnum.choices()]:
            raise cls.ValidationError({"type": [gettext("Unsupported attribute type.")]})

        if cls.resolve_definition(normalized, business, fallback_to_any=False) is not None:
            raise cls.ValidationError({
                "code": [gettext("An attribute with this code already exists.")],
            })

        try:
            return InventoryAttributeDefinition.objects.create(
                business=business,
                name=name,
                fa_title=(fa_title or "").strip() or name,
                code=normalized,
                type=attr_type,
            )
        except DjangoValidationError as exc:
            raise cls.ValidationError({"code": exc.messages}) from exc
        except IntegrityError as exc:
            raise cls.ValidationError({
                "code": [gettext("An attribute with this code already exists.")],
            }) from exc

    @classmethod
    def get_or_create_definition(cls, business, name, attr_type=None):
        code = cls.normalize_code(name)
        if attr_type is None:
            attr_type = InventoryAttributeTypeEnum.TEXT.value
        # Reuse the global definition when one exists so unit attributes
        # never split across a seeded row and a business-owned twin.
        existing = cls.resolve_definition(code, business, fallback_to_any=False)
        if existing is not None:
            return existing
        definition, _ = InventoryAttributeDefinition.objects.get_or_create(
            business=business,
            code=code,
            defaults={"name": name, "type": attr_type},
        )
        return definition

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
    def get_all_unit_attributes(cls, inventory_unit):
        attrs = InventoryUnitAttribute.objects.select_related("attribute_definition").filter(
            inventory_unit=inventory_unit,
        )
        return {attr.attribute_definition.code: attr.value for attr in attrs}

    # ------------------------------------------------------------------
    # Serialized-unit attribute snapshots
    # ------------------------------------------------------------------
    @classmethod
    def prepare_attributes(cls, entries, business=None):
        """Resolve and validate one serialized row's attribute entries.

        Returns ``{definition_id: value}``; a blank value means the attribute
        is cleared on that unit. An unknown code is rejected rather than
        created, so inserting a missing attribute stays the job of
        ``create_definition`` and the vendor endpoint behind it.
        """
        desired = {}
        seen = set()
        for entry in entries or []:
            code = cls.normalize_code(str(entry.get("code") or ""))
            if not code:
                raise cls.ValidationError({
                    "attributes": [gettext("An attribute code is required.")],
                })
            if code in seen:
                raise cls.ValidationError({
                    "attributes": [
                        gettext("Attribute submitted twice: %(code)s.") % {"code": code}
                    ],
                })
            seen.add(code)
            if code == cls.SERIAL_NUMBER_CODE:
                raise cls.ValidationError({
                    "attributes": [gettext(
                        "The serial_number attribute belongs to the serial number field."
                    )],
                })
            definition = cls.resolve_definition(code, business, fallback_to_any=False)
            if definition is None:
                raise cls.ValidationError({
                    "attributes": [
                        gettext("Unknown attribute: %(code)s.") % {"code": code}
                    ],
                })
            value = str(entry.get("value") or "")
            if not value.strip():
                continue
            if not cls.validate_value(value, definition.type):
                raise cls.ValidationError({
                    "attributes": [
                        gettext("Invalid value for %(code)s.") % {"code": code}
                    ],
                })
            desired[definition.id] = value
        return desired

    @classmethod
    @transaction.atomic
    def apply_unit_attributes(cls, inventory_unit, desired):
        """Write ``{definition_id: value}`` onto a unit, dropping the rest.

        ``serial_number`` is never touched here; it belongs to the serialized
        snapshot flow.
        """
        existing = {
            attr.attribute_definition_id: attr
            for attr in InventoryUnitAttribute.objects.filter(
                inventory_unit=inventory_unit
            ).exclude(attribute_definition__code=cls.SERIAL_NUMBER_CODE)
        }
        for definition_id, attr in existing.items():
            if definition_id not in desired:
                attr.delete()
        for definition_id, value in desired.items():
            attr = existing.get(definition_id)
            if attr is None:
                InventoryUnitAttribute.objects.create(
                    inventory_unit=inventory_unit,
                    attribute_definition_id=definition_id,
                    value=value,
                )
            elif attr.value != value:
                attr.value = value
                attr.save(update_fields=["value"])

    @classmethod
    def list_unit_attributes(cls, unit_ids):
        """Return ``{unit_id: [attribute payload]}`` for the given units."""
        rows = InventoryUnitAttribute.objects.filter(
            inventory_unit_id__in=list(unit_ids)
        ).exclude(
            attribute_definition__code=cls.SERIAL_NUMBER_CODE
        ).select_related("attribute_definition").order_by("id")
        payload = {}
        for attr in rows:
            definition = attr.attribute_definition
            payload.setdefault(attr.inventory_unit_id, []).append({
                "code": definition.code,
                "name": definition.name,
                "fa_title": definition.fa_title,
                "type": definition.type,
                "value": attr.value,
            })
        return payload
