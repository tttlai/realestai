import re

INDIA_CODE = "91"


class InvalidPhoneError(ValueError):
    pass


def normalise_phone(raw: str) -> str:
    """Return E.164 digits without '+', e.g. '919876543210'.

    For numbers entered by people, such as forms and emails. A leading '+' or '00' marks a
    country code and is trusted. Without one, bare 10-digit Indian mobiles (and the
    trunk-prefixed '0XXXXXXXXXX' form) get +91, so a foreign number must carry its marker.
    Anything else is assumed to already carry a country code.
    """
    digits = re.sub(r"\D", "", raw)
    has_country_code = raw.strip().startswith(("+", "00"))
    if digits.startswith("00"):
        digits = digits[2:]
    if not has_country_code:
        if len(digits) == 11 and digits.startswith("0") and digits[1] in "6789":
            digits = digits[1:]
        if len(digits) == 10 and digits[0] in "6789":
            digits = INDIA_CODE + digits
    return _validated(digits, raw)


def normalise_wa_id(raw: str) -> str:
    """Validate a number sent by WhatsApp, which already includes its country code.

    The number is never changed, because a 10-digit number such as Singapore's 6591234567 is
    complete as it stands and only looks like an Indian mobile.
    """
    return _validated(raw if raw.isdigit() else "", raw)


def _validated(digits: str, raw: str) -> str:
    if not 8 <= len(digits) <= 15 or digits.startswith("0"):
        raise InvalidPhoneError(f"not a valid phone number: {raw!r}")
    return digits
