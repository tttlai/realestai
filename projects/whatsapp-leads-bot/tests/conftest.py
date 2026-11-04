import os

from cryptography.fernet import Fernet

# Test settings must exist before app modules read the environment.
TEST_ENV = {
    "SUPABASE_URL": "https://example.supabase.co",
    "SUPABASE_SERVICE_ROLE_KEY": "test-service-role-key",
    "META_APP_SECRET": "test-app-secret",
    "META_VERIFY_TOKEN": "test-verify-token",
    "META_GRAPH_VERSION": "v24.0",
    "TOKEN_ENCRYPTION_KEY": Fernet.generate_key().decode(),
}
os.environ.update(TEST_ENV)
