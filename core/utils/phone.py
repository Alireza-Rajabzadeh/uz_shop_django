import unicodedata


class PhoneNormalizationError(ValueError):
    pass


def normalize_phone(value):
    if value is None:
        raise PhoneNormalizationError("Phone number is required.")

    normalized = []
    for character in str(value).strip():
        if character == "+" and not normalized:
            normalized.append(character)
            continue
        if character.isspace() or character in "-()":
            continue
        try:
            normalized.append(str(unicodedata.decimal(character)))
        except (TypeError, ValueError) as exc:
            raise PhoneNormalizationError("Enter a valid mobile number.") from exc

    phone = "".join(normalized)
    digits = phone[1:] if phone.startswith("+") else phone
    if not digits.isascii() or not digits.isdigit() or not 8 <= len(digits) <= 15:
        raise PhoneNormalizationError("Enter a valid mobile number.")
    return phone
