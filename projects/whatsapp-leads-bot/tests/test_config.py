import pytest
from pydantic import ValidationError

from app.config import Settings


def test_missing_setting_error_names_the_field_without_exposing_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secrets = {
        "META_APP_SECRET": "app-secret-canary",
        "META_VERIFY_TOKEN": "verify-token-canary",
        "TOKEN_ENCRYPTION_KEY": "encryption-key-canary",
    }
    for name, value in secrets.items():
        monkeypatch.setenv(name, value)
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY")

    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None)  # type: ignore[call-arg]

    message = str(exc_info.value)
    assert "supabase_service_role_key" in message
    assert "canary" not in message
