import io
import json
import logging
import time
from collections.abc import AsyncIterator, Iterator
from typing import Any

import httpx
import pytest
import respx

from app.log import JsonFormatter
from app.main import app
from app.webhooks.whatsapp import parse_messages
from app.whatsapp.client import WhatsAppClient
from tests.fakes import (
    BROKER_TOKEN,
    PHONE_NUMBER_ID,
    FakeDatabase,
    encode,
    message_payload,
    sign,
)

SEND_URL = f"https://graph.facebook.com/v24.0/{PHONE_NUMBER_ID}/messages"


@pytest.fixture
def db() -> FakeDatabase:
    fake = FakeDatabase()
    fake.add_broker()
    return fake


@pytest.fixture
def graph() -> Iterator[respx.MockRouter]:
    with respx.mock(assert_all_called=False) as router:
        router.post(SEND_URL).respond(200, json={"messages": [{"id": "wamid.OUT1"}]})
        yield router


@pytest.fixture
async def client(db: FakeDatabase, graph: respx.MockRouter) -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient() as graph_http:
        app.state.db = db
        app.state.whatsapp = WhatsAppClient(graph_http, "v24.0")
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            yield c


async def post_signed(client: httpx.AsyncClient, payload: dict[str, Any]) -> httpx.Response:
    body = encode(payload)
    return await client.post(
        "/webhooks/whatsapp",
        content=body,
        headers={"X-Hub-Signature-256": sign(body), "Content-Type": "application/json"},
    )


def sent_bodies(graph: respx.MockRouter) -> list[dict[str, Any]]:
    return [json.loads(call.request.content) for call in graph.routes[0].calls]


# --- GET verification -------------------------------------------------------------------


async def test_verify_echoes_challenge(client: httpx.AsyncClient) -> None:
    params = {
        "hub.mode": "subscribe",
        "hub.verify_token": "test-verify-token",
        "hub.challenge": "42",
    }
    response = await client.get("/webhooks/whatsapp", params=params)
    assert response.status_code == 200
    assert response.text == "42"


@pytest.mark.parametrize(
    "params",
    [
        {"hub.mode": "subscribe", "hub.verify_token": "wrong", "hub.challenge": "42"},
        {"hub.mode": "unsubscribe", "hub.verify_token": "test-verify-token", "hub.challenge": "42"},
        {"hub.mode": "subscribe", "hub.challenge": "42"},
        {},
    ],
)
async def test_verify_rejects(client: httpx.AsyncClient, params: dict[str, str]) -> None:
    response = await client.get("/webhooks/whatsapp", params=params)
    assert response.status_code == 403


# --- POST signature ---------------------------------------------------------------------


async def test_rejects_bad_signature(
    client: httpx.AsyncClient, db: FakeDatabase, graph: respx.MockRouter
) -> None:
    body = encode(message_payload())
    for headers in ({}, {"X-Hub-Signature-256": sign(body, "wrong-secret")}):
        response = await client.post("/webhooks/whatsapp", content=body, headers=headers)
        assert response.status_code == 401
    assert db.messages == []
    assert not graph.routes[0].called


# --- POST inbound -----------------------------------------------------------------------


async def test_text_is_stored_and_echoed(
    client: httpx.AsyncClient, db: FakeDatabase, graph: respx.MockRouter
) -> None:
    response = await post_signed(client, message_payload(text="2bhk wakad mein kitna hai?"))
    assert response.status_code == 200

    assert sent_bodies(graph) == [
        {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": "919876543210",
            "type": "text",
            "text": {"preview_url": False, "body": "2bhk wakad mein kitna hai?"},
        }
    ]
    assert graph.routes[0].calls.last.request.headers["Authorization"] == f"Bearer {BROKER_TOKEN}"

    [lead] = db.leads
    assert (lead.phone, lead.name, lead.source) == ("919876543210", "Asha", "whatsapp")
    assert lead.last_inbound_at is not None
    assert [(m["direction"], m["body"], m["wa_message_id"]) for m in db.messages] == [
        ("inbound", "2bhk wakad mein kitna hai?", "wamid.TEST1"),
        ("outbound", "2bhk wakad mein kitna hai?", "wamid.OUT1"),
    ]


async def test_duplicate_delivery_is_stored_and_answered_once(
    client: httpx.AsyncClient, db: FakeDatabase, graph: respx.MockRouter
) -> None:
    payload = message_payload()
    for _ in range(3):
        assert (await post_signed(client, payload)).status_code == 200
    assert len([m for m in db.messages if m["direction"] == "inbound"]) == 1
    assert len(sent_bodies(graph)) == 1


async def test_second_message_reuses_lead(
    client: httpx.AsyncClient, db: FakeDatabase, graph: respx.MockRouter
) -> None:
    await post_signed(client, message_payload(wa_message_id="wamid.A", text="one"))
    await post_signed(client, message_payload(wa_message_id="wamid.B", text="two"))
    assert len(db.leads) == 1
    assert [b["text"]["body"] for b in sent_bodies(graph)] == ["one", "two"]


async def test_status_updates_are_ignored(
    client: httpx.AsyncClient, db: FakeDatabase, graph: respx.MockRouter
) -> None:
    payload = message_payload()
    value = payload["entry"][0]["changes"][0]["value"]
    del value["messages"], value["contacts"]
    value["statuses"] = [{"id": "wamid.OUT1", "status": "delivered"}]
    assert (await post_signed(client, payload)).status_code == 200
    assert db.messages == []
    assert not graph.routes[0].called


async def test_unknown_phone_number_id_is_ignored(
    client: httpx.AsyncClient, db: FakeDatabase, graph: respx.MockRouter
) -> None:
    await post_signed(client, message_payload(phone_number_id="999"))
    assert db.leads == []
    assert not graph.routes[0].called


async def test_non_text_is_stored_but_not_echoed(
    client: httpx.AsyncClient, db: FakeDatabase, graph: respx.MockRouter
) -> None:
    await post_signed(client, message_payload(msg_type="image"))
    assert [(m["direction"], m["kind"], m["body"]) for m in db.messages] == [
        ("inbound", "image", None)
    ]
    assert not graph.routes[0].called


async def test_opted_out_lead_gets_no_reply(
    client: httpx.AsyncClient, db: FakeDatabase, graph: respx.MockRouter
) -> None:
    await post_signed(client, message_payload(wa_message_id="wamid.A"))
    db.leads[0].opted_out = True
    await post_signed(client, message_payload(wa_message_id="wamid.B"))
    assert len([m for m in db.messages if m["direction"] == "inbound"]) == 2
    assert len(sent_bodies(graph)) == 1


async def test_stale_message_outside_window_gets_no_reply(
    client: httpx.AsyncClient, db: FakeDatabase, graph: respx.MockRouter
) -> None:
    old = int(time.time()) - 25 * 3600
    assert (await post_signed(client, message_payload(timestamp=old))).status_code == 200
    assert len(db.messages) == 1
    assert not graph.routes[0].called


@pytest.fixture
def json_logs() -> Iterator[io.StringIO]:
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    previous_level = root.level
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    yield stream
    root.removeHandler(handler)
    root.setLevel(previous_level)


async def test_send_failure_still_returns_200_and_logs_with_ids(
    client: httpx.AsyncClient,
    db: FakeDatabase,
    graph: respx.MockRouter,
    json_logs: io.StringIO,
) -> None:
    graph.routes[0].respond(500)
    response = await post_signed(client, message_payload())
    assert response.status_code == 200
    assert graph.routes[0].call_count == 2
    assert [m["direction"] for m in db.messages] == ["inbound"]

    lines = [json.loads(line) for line in json_logs.getvalue().splitlines()]
    failure = next(line for line in lines if line["msg"] == "failed to handle inbound message")
    assert failure["broker_id"] == db.brokers[0].id
    assert failure["lead_id"] == db.leads[0].id
    assert failure["wa_message_id"] == "wamid.TEST1"
    assert "WhatsAppError" in failure["exc"]


async def test_token_and_body_never_logged(
    client: httpx.AsyncClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.DEBUG):
        await post_signed(client, message_payload(text="secret-body-text"))
    for record in caplog.records:
        rendered = record.getMessage() + repr(vars(record))
        assert BROKER_TOKEN not in rendered
        if record.levelno >= logging.INFO:
            assert "secret-body-text" not in rendered


# --- payload parsing --------------------------------------------------------------------


def test_parse_messages_extracts_fields() -> None:
    [msg] = parse_messages(message_payload(text="hi", timestamp=1_760_000_000))
    assert msg.phone_number_id == PHONE_NUMBER_ID
    assert msg.wa_message_id == "wamid.TEST1"
    assert msg.from_phone == "919876543210"
    assert msg.profile_name == "Asha"
    assert msg.type == "text"
    assert msg.text == "hi"
    assert int(msg.timestamp.timestamp()) == 1_760_000_000


def test_parse_messages_skips_malformed() -> None:
    payload = message_payload()
    del payload["entry"][0]["changes"][0]["value"]["messages"][0]["id"]
    assert parse_messages(payload) == []
    assert parse_messages({}) == []
