import pytest

from app.intake.normalise import InvalidPhoneError, normalise_phone, normalise_wa_id


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("919876543210", "919876543210"),
        ("+91 98765 43210", "919876543210"),
        ("+91-98765-43210", "919876543210"),
        ("9876543210", "919876543210"),
        ("098765 43210", "919876543210"),
        ("0091 9876543210", "919876543210"),
        ("(+91) 6123 456 789", "916123456789"),
        ("+1 631 555 1234", "16315551234"),
        ("16315551234", "16315551234"),
        ("+44 20 7946 0958", "442079460958"),
        ("+65 9123 4567", "6591234567"),
        ("0065 9123 4567", "6591234567"),
        ("6591234567", "916591234567"),  # no country code marker, so read as an Indian mobile
    ],
)
def test_normalise_phone(raw: str, expected: str) -> None:
    assert normalise_phone(raw) == expected


@pytest.mark.parametrize("raw", ["", "abc", "12345", "0123456789", "1234567890123456"])
def test_rejects_invalid(raw: str) -> None:
    with pytest.raises(InvalidPhoneError):
        normalise_phone(raw)


@pytest.mark.parametrize("raw", ["919876543210", "6591234567", "6421234567", "14155552671"])
def test_wa_id_is_kept_unchanged(raw: str) -> None:
    assert normalise_wa_id(raw) == raw


@pytest.mark.parametrize("raw", ["", "abc", "+919876543210", "12345", "0123456789"])
def test_wa_id_rejects_invalid(raw: str) -> None:
    with pytest.raises(InvalidPhoneError):
        normalise_wa_id(raw)
