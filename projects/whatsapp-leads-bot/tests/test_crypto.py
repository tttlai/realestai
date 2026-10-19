import pytest
from cryptography.fernet import Fernet

from app.config import get_settings
from app.crypto import TokenDecryptionError, decrypt_token, encrypt_token


def test_round_trip() -> None:
    enc = encrypt_token("EAAG-secret-token")
    assert "EAAG-secret-token" not in enc
    assert decrypt_token(enc) == "EAAG-secret-token"


def test_wrong_key_raises_without_leaking() -> None:
    enc = Fernet(Fernet.generate_key()).encrypt(b"EAAG-secret-token").decode()
    with pytest.raises(TokenDecryptionError) as exc_info:
        decrypt_token(enc)
    assert "EAAG" not in str(exc_info.value)
    assert exc_info.value.__cause__ is None


def test_key_comes_from_settings() -> None:
    key = get_settings().token_encryption_key.get_secret_value()
    enc = encrypt_token("abc")
    assert Fernet(key).decrypt(enc.encode()) == b"abc"
