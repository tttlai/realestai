from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment configuration. Secrets are SecretStr so they never appear in reprs or logs."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    supabase_url: str
    supabase_service_role_key: SecretStr

    meta_app_secret: SecretStr
    meta_verify_token: SecretStr
    meta_graph_version: str

    token_encryption_key: SecretStr

    # Used from phase 2 onwards.
    anthropic_api_key: SecretStr | None = None
    default_model: str = "claude-haiku-5-5"

    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]  # populated from the environment
