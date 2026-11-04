import re

INDIA_CODE = "91"


class InvalidPhoneError(ValueError):
    pass


def normalise_phone(raw: str) -> str:
    """Return E.164 digits without '+', e.g. '919876543210'.

    Bare 10-digit Indian mobiles (and the trunk-prefixed '0XXXXXXXXXX' form) get +91.
    Anything else is assumed to already carry a country code.
    """
    digits = re.sub(r"\D", "", raw)
    if digits.startswith("00"):
        digits = digits[2:]
    if len(digits) == 11 and digits.startswith("0") and digits[1] in "6789":
        digits = digits[1:]
    if len(digits) == 10 and digits[0] in "6789":
        digits = INDIA_CODE + digits
    if not 8 <= len(digits) <= 15 or digits.startswith("0"):
        raise InvalidPhoneError(f"not a valid phone number: {raw!r}")
    return digits
