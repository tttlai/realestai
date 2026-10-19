"""Encrypt broker access tokens at rest with Fernet (key from TOKEN_ENCRYPTION_KEY)."""

from cryptography.fernet import Fernet, InvalidToken

from app.config import get_settings


class TokenDecryptionError(Exception):
    pass


def _fernet() -> Fernet:
    return Fernet(get_settings().token_encryption_key.get_secret_value())


def encrypt_token(token: str) -> str:
    return _fernet().encrypt(token.encode()).decode()


def decrypt_token(token_enc: str) -> str:
    try:
        return _fernet().decrypt(token_enc.encode()).decode()
    except InvalidToken:
        raise TokenDecryptionError("access token could not be decrypted") from None
