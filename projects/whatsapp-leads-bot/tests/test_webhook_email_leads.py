import base64
import json
import logging
from collections.abc import AsyncIterator, Iterator
from typing import Any

import httpx
import pytest
import respx

from app.config import Settings, get_settings
from app.intake.email_parser import EmailParser, email_text
from app.main import app
from app.webhooks.email_leads import parse_postmark
from app.whatsapp.client import WhatsAppClient
from tests.fakes import PHONE_NUMBER_ID, FakeDatabase, FakeLLM, text_response

SECRET = "inbound-secret"
SEND_URL = f"https://graph.facebook.com/v24.0/{PHONE_NUMBER_ID}/messages"
ENQUIRY = {
    "is_lead": True,
    "name": "Rohan Mehta",
    "phone": "98765 43210",
    "email": "rohan@example.com",
    "property": "2 BHK in Riverside Towers, Kharadi",
    "portal": "99acres",
    "message": "Is it still available? Can I visit this weekend?",
}


def email(message_id: str = "<m1@99acres.com>", **overrides: Any) -> dict[str, Any]:
    fields: dict[str, Any] = {
        "MessageID": message_id,
        "From": "alerts@99acres.com",
        "Subject": "New enquiry for your property",
        "TextBody": "Rohan Mehta (9876543210) is interested in 2 BHK, Riverside Towers.",
        "HtmlBody": "",
        "MailboxHash": "ravi",
        "OriginalRecipient": "abc123+ravi@inbound.postmarkapp.com",
    }
    return fields | overrides


def basic(password: str) -> dict[str, str]:
    token = base64.b64encode(f"postmark:{password}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


@pytest.fixture
def db() -> FakeDatabase:
    fake = FakeDatabase()
    fake.add_broker(name="Ravi", agency_name="Ravi Realty", inbound_email_key="ravi")
    return fake


@pytest.fixture
def llm() -> FakeLLM:
    return FakeLLM()


@pytest.fixture
def graph() -> Iterator[respx.MockRouter]:
    with respx.mock(assert_all_called=False) as router:
        router.post(SEND_URL).respond(200, json={"messages": [{"id": "wamid.OPENER"}]})
        yield router


@pytest.fixture
async def client(
    db: FakeDatabase, llm: FakeLLM, graph: respx.MockRouter
) -> AsyncIterator[httpx.AsyncClient]:
    app.dependency_overrides[get_settings] = lambda: Settings(inbound_email_secret=SECRET)  # type: ignore[arg-type]
    async with httpx.AsyncClient() as graph_http:
        app.state.db = db
        app.state.whatsapp = WhatsAppClient(graph_http, "v24.0")
        app.state.email_parser = EmailParser(llm, "claude-haiku-5-5")  # type: ignore[arg-type]
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            yield c
    app.dependency_overrides.clear()


async def post(
    client: httpx.AsyncClient, payload: dict[str, Any], password: str = SECRET
) -> httpx.Response:
    return await client.post("/webhooks/email-leads", json=payload, headers=basic(password))


async def test_portal_email_creates_lead_and_sends_opener(
    client: httpx.AsyncClient, db: FakeDatabase, llm: FakeLLM, graph: respx.MockRouter
) -> None:
    llm.queue(text_response(json.dumps(ENQUIRY)))
    assert (await post(client, email())).status_code == 200

    [call] = llm.calls
    assert call["output_config"]["format"]["type"] == "json_schema"
    assert "919800000000" in call["system"]  # the broker's own number, to be ignored
    assert "Rohan Mehta (9876543210)" in call["messages"][0]["content"]

    [body] = [json.loads(c.request.content) for c in graph.routes[0].calls]
    assert body["to"] == "919876543210"
    assert [p["text"] for p in body["template"]["components"][0]["parameters"]] == [
        "Rohan",
        "2 BHK in Riverside Towers, Kharadi",
        "Ravi Realty",
    ]
    [lead] = db.leads
    assert (lead.source, lead.source_detail) == ("portal_email", "99acres")
    assert db.messages[0]["body"] == (
        "Enquiry via 99acres about 2 BHK in Riverside Towers, Kharadi:\n"
        "- Name: Rohan Mehta\n"
        "- Email: rohan@example.com\n"
        "- Their message: Is it still available? Can I visit this weekend?"
    )
    assert db.intake_events[0]["status"] == "opener_sent"


async def test_retried_email_is_not_read_twice(
    client: httpx.AsyncClient, llm: FakeLLM, graph: respx.MockRouter
) -> None:
    llm.queue(text_response(json.dumps(ENQUIRY)))
    await post(client, email())
    await post(client, email())
    assert len(llm.calls) == 1
    assert graph.routes[0].call_count == 1


async def test_non_enquiry_email_is_recorded_and_skipped(
    client: httpx.AsyncClient, db: FakeDatabase, llm: FakeLLM, graph: respx.MockRouter
) -> None:
    llm.queue(text_response(json.dumps(ENQUIRY | {"is_lead": False, "phone": None})))
    await post(client, email(Subject="Your monthly listing report"))
    assert not graph.routes[0].called and db.leads == []
    assert db.intake_events[0]["status"] == "skipped_not_a_lead"


async def test_unreadable_extraction_is_recorded_as_failed(
    client: httpx.AsyncClient, db: FakeDatabase, llm: FakeLLM
) -> None:
    llm.queue(text_response("not json"))
    await post(client, email())
    assert (db.intake_events[0]["status"], db.intake_events[0]["detail"]) == (
        "failed",
        "could not read email",
    )


@pytest.mark.parametrize("password", ["wrong", ""])
async def test_wrong_credentials_are_rejected(
    client: httpx.AsyncClient, llm: FakeLLM, password: str
) -> None:
    response = await post(client, email(), password=password)
    assert response.status_code == 401
    assert llm.calls == []
    no_auth = await client.post("/webhooks/email-leads", json=email())
    assert no_auth.status_code == 401


async def test_endpoint_is_off_without_a_secret(client: httpx.AsyncClient) -> None:
    app.dependency_overrides[get_settings] = lambda: Settings()  # type: ignore[call-arg]
    assert (await post(client, email())).status_code == 404


async def test_unknown_broker_key_is_ignored(
    client: httpx.AsyncClient, llm: FakeLLM, db: FakeDatabase
) -> None:
    await post(client, email(MailboxHash="nobody", OriginalRecipient="abc+nobody@x.com"))
    assert llm.calls == [] and db.intake_events == []


async def test_gmail_forwarding_confirmation_code_is_logged(
    client: httpx.AsyncClient, llm: FakeLLM, caplog: pytest.LogCaptureFixture
) -> None:
    gmail = email(
        From="Gmail Team <forwarding-noreply@google.com>",
        Subject="(#123456789) Gmail Forwarding Confirmation - Receive Mail from ravi@gmail.com",
    )
    with caplog.at_level(logging.WARNING):
        await post(client, gmail)
    assert llm.calls == []
    [record] = [r for r in caplog.records if "forwarding confirmation" in r.getMessage()]
    assert record.confirmation_code == "123456789"  # type: ignore[attr-defined]


async def test_without_api_key_emails_are_not_read(
    client: httpx.AsyncClient, db: FakeDatabase, llm: FakeLLM
) -> None:
    app.state.email_parser = None
    await post(client, email())
    assert llm.calls == [] and db.intake_events == []


def test_broker_key_from_recipient_when_no_mailbox_hash() -> None:
    parsed = parse_postmark(email(MailboxHash="", OriginalRecipient="abc123+Ravi@inbound.x.com"))
    assert parsed is not None and parsed.broker_key == "ravi"
    parsed = parse_postmark(
        email(MailboxHash="", OriginalRecipient="", ToFull=[{"Email": "abc+meera@in.x.com"}])
    )
    assert parsed is not None and parsed.broker_key == "meera"
    assert parse_postmark(email(MailboxHash="", OriginalRecipient="abc@x.com")) is None
    assert parse_postmark(email(MessageID="")) is None


def test_html_only_email_is_turned_into_text() -> None:
    html_body = (
        "<html><style>p{color:red}</style><body><p>Name: Rohan &amp; family</p>"
        "<div>Phone:<b>9876543210</b></div><script>x()</script></body></html>"
    )
    text = email_text("", html_body)
    assert "Rohan & family" in text and "9876543210" in text
    assert "color" not in text and "x()" not in text
