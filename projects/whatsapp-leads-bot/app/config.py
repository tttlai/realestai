from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment configuration.

    Secrets are SecretStr so they never appear in reprs or logs. hide_input_in_errors does the
    same for startup errors, which would otherwise print part of the raw environment values.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", hide_input_in_errors=True)

    supabase_url: str
    supabase_service_role_key: SecretStr

    meta_app_secret: SecretStr
    meta_verify_token: SecretStr
    meta_graph_version: str

    token_encryption_key: SecretStr

    # The agent. Without an API key the bot stores messages but does not reply.
    anthropic_api_key: SecretStr | None = None
    default_model: str = "claude-haiku-5-5"  # a broker's own `model` overrides this
    agent_effort: str = "medium"  # low / medium / high: how much the model thinks per reply

    # Portal emails (phase 3). The email provider's webhook must send this as the HTTP basic-auth
    # password; without it the email endpoint is switched off.
    inbound_email_secret: SecretStr | None = None
    # The provider's inbound address, e.g. abc123@inbound.postmarkapp.com. Only used to print
    # each broker's forwarding address.
    inbound_email_address: str | None = None

    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]  # populated from the environment
