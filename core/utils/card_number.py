import unicodedata


class CardNumberValidationError(ValueError):
    pass


# Current rule: exactly 16 digits. Future algorithms (Luhn, IBAN, ...)
# are appended to _RULES without touching callers.
CARD_NUMBER_LENGTHS = (16,)


def _check_length(value: str) -> None:
    if len(value) not in CARD_NUMBER_LENGTHS:
        raise CardNumberValidationError("Card number must be 16 digits.")


_RULES = (_check_length,)


def normalize_card_number(value):
    if value is None:
        raise CardNumberValidationError("Card number is required.")

    normalized = []
    for character in str(value).strip():
        if character.isspace() or character == "-":
            continue
        try:
            normalized.append(str(unicodedata.decimal(character)))
        except (TypeError, ValueError) as exc:
            raise CardNumberValidationError(
                "Card number must contain digits only."
            ) from exc

    digits = "".join(normalized)
    if not digits:
        raise CardNumberValidationError("Card number is required.")
    if not digits.isascii() or not digits.isdigit():
        raise CardNumberValidationError("Card number must contain digits only.")
    for rule in _RULES:
        rule(digits)
    return digits
