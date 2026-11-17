"""connect_facebook_page and set_inbound_email, plus email extraction edge cases."""

import pytest
import respx

from app.crypto import decrypt_token
from app.db import Database
from app.intake.email_parser import MAX_EMAIL_CHARS, EmailParser
from scripts import connect_facebook_page, set_inbound_email
from tests.fakes import PHONE_NUMBER_ID, FakeDatabase, FakeLLM, text_response

GRAPH = "https://graph.facebook.com/v24.0"
PAGE_ID = "555000111"


@pytest.fixture
def db(monkeypatch: pytest.MonkeyPatch) -> FakeDatabase:
    fake = FakeDatabase()
    fake.add_broker(name="Ravi")

    async def connect(settings: object) -> FakeDatabase:
        return fake

    monkeypatch.setattr(Database, "connect", connect)
    return fake


@respx.mock
async def test_connect_page_with_a_system_user_token(
    db: FakeDatabase, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("META_PAGE_SETUP_TOKEN", "system-user-token")
    page = respx.get(f"{GRAPH}/{PAGE_ID}").respond(
        200, json={"name": "Ravi Realty", "access_token": "page-token", "id": PAGE_ID}
    )
    subscribe = respx.post(f"{GRAPH}/{PAGE_ID}/subscribed_apps").respond(
        200, json={"success": True}
    )

    await connect_facebook_page.main(["--phone-number-id", PHONE_NUMBER_ID, "--page-id", PAGE_ID])

    assert page.calls.last.request.headers["Authorization"] == "Bearer system-user-token"
    request = subscribe.calls.last.request
    assert request.headers["Authorization"] == "Bearer page-token"
    assert request.url.params["subscribed_fields"] == "leadgen"
    broker = db.brokers[0]
    assert broker.fb_page_id == PAGE_ID
    assert decrypt_token(broker.leads_access_token_enc or "") == "page-token"
    out = capsys.readouterr().out
    assert "Connected Page 'Ravi Realty' to Ravi" in out and "page-token" not in out


@respx.mock
async def test_connect_page_accepts_a_page_token(
    db: FakeDatabase, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("META_PAGE_SETUP_TOKEN", "page-token")
    respx.get(f"{GRAPH}/{PAGE_ID}").respond(200, json={"name": "Ravi Realty", "id": PAGE_ID})
    respx.get(f"{GRAPH}/me").respond(200, json={"id": PAGE_ID, "name": "Ravi Realty"})
    respx.post(f"{GRAPH}/{PAGE_ID}/subscribed_apps").respond(200, json={"success": True})
    await connect_facebook_page.main(["--phone-number-id", PHONE_NUMBER_ID, "--page-id", PAGE_ID])
    assert decrypt_token(db.brokers[0].leads_access_token_enc or "") == "page-token"


@respx.mock
async def test_connect_page_explains_missing_access(
    db: FakeDatabase, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("META_PAGE_SETUP_TOKEN", "user-token")
    respx.get(f"{GRAPH}/{PAGE_ID}").respond(200, json={"name": "Ravi Realty", "id": PAGE_ID})
    respx.get(f"{GRAPH}/me").respond(200, json={"id": "someone-else"})
    with pytest.raises(SystemExit, match="assign the Page to the system user"):
        await connect_facebook_page.main(
            ["--phone-number-id", PHONE_NUMBER_ID, "--page-id", PAGE_ID]
        )
    assert db.brokers[0].fb_page_id is None


@respx.mock
async def test_connect_page_reports_meta_errors(
    db: FakeDatabase, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("META_PAGE_SETUP_TOKEN", "t")
    respx.get(f"{GRAPH}/{PAGE_ID}").respond(
        400, json={"error": {"code": 190, "message": "Invalid OAuth access token"}}
    )
    with pytest.raises(SystemExit, match=r"Meta refused: .*code=190"):
        await connect_facebook_page.main(
            ["--phone-number-id", PHONE_NUMBER_ID, "--page-id", PAGE_ID]
        )


async def test_set_inbound_email_key(
    db: FakeDatabase, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from app.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("INBOUND_EMAIL_ADDRESS", "abc123@inbound.postmarkapp.com")
    try:
        await set_inbound_email.main(["--phone-number-id", PHONE_NUMBER_ID, "--key", "Ravi"])
    finally:
        get_settings.cache_clear()
    assert db.brokers[0].inbound_email_key == "ravi"
    assert "abc123+ravi@inbound.postmarkapp.com" in capsys.readouterr().out


async def test_inbound_email_key_must_be_valid_and_unique(db: FakeDatabase) -> None:
    with pytest.raises(SystemExit, match="lowercase"):
        await set_inbound_email.main(["--phone-number-id", PHONE_NUMBER_ID, "--key", "ra vi"])
    db.add_broker(phone_number_id="999", name="Meera", inbound_email_key="meera")
    with pytest.raises(SystemExit, match="already used by Meera"):
        await set_inbound_email.main(["--phone-number-id", PHONE_NUMBER_ID, "--key", "meera"])


def test_forwarding_address() -> None:
    assert (
        set_inbound_email.forwarding_address("abc@inbound.postmarkapp.com", "ravi")
        == "abc+ravi@inbound.postmarkapp.com"
    )
    assert set_inbound_email.forwarding_address("leads+x@realestai.in", "ravi") == (
        "leads+ravi@realestai.in"
    )


@pytest.mark.parametrize("stop_reason", ["refusal", "max_tokens"])
async def test_extraction_gives_up_when_the_model_stops_early(stop_reason: str) -> None:
    llm = FakeLLM()
    llm.queue(text_response("{}", stop_reason=stop_reason))
    parser = EmailParser(llm, "claude-haiku-5-5")  # type: ignore[arg-type]
    assert await parser.parse(sender="a", subject="b", body="c", broker_number="91") is None


async def test_long_emails_are_cut_before_sending() -> None:
    llm = FakeLLM()
    llm.queue(text_response('{"is_lead": false}'))
    parser = EmailParser(llm, "claude-haiku-5-5")  # type: ignore[arg-type]
    result = await parser.parse(
        sender="a", subject="b", body="x" * (MAX_EMAIL_CHARS + 500), broker_number="91"
    )
    assert result is not None and result.is_lead is False and result.phone is None
    assert len(llm.calls[0]["messages"][0]["content"]) < MAX_EMAIL_CHARS + 100
