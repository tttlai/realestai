"""Meta webhook signature check (X-Hub-Signature-256), shared by every Meta webhook."""

import hashlib
import hmac


def verify_signature(body: bytes, header: str | None, app_secret: str) -> bool:
    if not header or not header.startswith("sha256="):
        return False
    expected = hmac.new(app_secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected.encode(), header.removeprefix("sha256=").encode())
