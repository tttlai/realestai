from app.webhooks.signature import verify_signature
from tests.fakes import APP_SECRET, sign

BODY = b'{"object":"whatsapp_business_account"}'


def test_valid_signature() -> None:
    assert verify_signature(BODY, sign(BODY), APP_SECRET)


def test_wrong_secret() -> None:
    assert not verify_signature(BODY, sign(BODY, "other-secret"), APP_SECRET)


def test_tampered_body() -> None:
    assert not verify_signature(BODY + b" ", sign(BODY), APP_SECRET)


def test_missing_or_malformed_header() -> None:
    digest = sign(BODY).removeprefix("sha256=")
    assert not verify_signature(BODY, None, APP_SECRET)
    assert not verify_signature(BODY, "", APP_SECRET)
    assert not verify_signature(BODY, digest, APP_SECRET)
    assert not verify_signature(BODY, "sha1=" + digest, APP_SECRET)
    assert not verify_signature(BODY, "sha256=ünïcode", APP_SECRET)
