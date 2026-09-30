from enum import Enum


class InventoryAttributeDefinitionEnum(Enum):
    """Codes of the global unit attributes seeded for every business.

    The enum is the validation vocabulary for the codes; the seeder owns the
    display rows (``name`` / ``fa_title`` / ``type``), mirroring how
    ``InventorySeeder`` treats ``InventoryTypeEnum``.
    """

    SERIAL_NUMBER = "serial_number"
    IMEI = "imei"
    IMEI_SECOND = "imei_2"
    BARCODE = "barcode"
    MAC_ADDRESS = "mac_address"
    BATCH_NUMBER = "batch_number"
    WARRANTY_MONTHS = "warranty_months"
    MANUFACTURE_DATE = "manufacture_date"

    @classmethod
    def codes(cls):
        return [member.value for member in cls]

    @classmethod
    def choices(cls):
        return [(member.value, member.name.replace("_", " ").capitalize()) for member in cls]
