"""Broker alerts: from the lead's WhatsApp message to the template the broker receives."""

import json
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import anthropic
import httpx
import httpx2
import pytest
import respx

from app.agent.handlers import ASSISTANT_FAILED
from app.agent.run import FALLBACK_REPLY, STOP_CONFIRMATION, Agent
from app.alerts import MAX_ALERTS
from app.main import app
from app.whatsapp.client import WhatsAppClient
from app.whatsapp.templates import HOT_LEAD_ALERT, LEAD_NEEDS_REPLY, broker_alert_params
from tests.fakes import (
    BROKER_TOKEN,
    PHONE_NUMBER_ID,
    FakeDatabase,
    FakeLLM,
    encode,
    message_payload,
    sign,
    text_response,
    tool_response,
)

SEND_URL = f"https://graph.facebook.com/v24.0/{PHONE_NUMBER_ID}/messages"
ALERT_NUMBER = "919800000000"
SUMMARY = "Wants a 2 BHK in Wakad, budget 90 L, visit Saturday 11 AM"


@pytest.fixture
def db() -> FakeDatabase:
    fake = FakeDatabase()
    fake.add_broker(name="Ravi")
    return fake


@pytest.fixture
def llm() -> FakeLLM:
    return FakeLLM()


@pytest.fixture
def graph() -> Iterator[respx.MockRouter]:
    ids = (f"wamid.OUT{i}" for i in range(100))

    def accept(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"messages": [{"id": next(ids)}]})

    with respx.mock(assert_all_called=False) as router:
        router.post(SEND_URL).mock(side_effect=accept)
        yield router


@pytest.fixture
async def client(
    db: FakeDatabase, graph: respx.MockRouter, llm: FakeLLM
) -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient() as graph_http:
        app.state.db = db
        app.state.whatsapp = WhatsAppClient(graph_http, "v24.0")
        app.state.agent = Agent(llm, db, default_model="claude-haiku-5-5", effort="medium")  # type: ignore[arg-type]
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            yield c


async def post(client: httpx.AsyncClient, payload: dict[str, Any]) -> None:
    body = encode(payload)
    response = await client.post(
        "/webhooks/whatsapp", content=body, headers={"X-Hub-Signature-256": sign(body)}
    )
    assert response.status_code == 200


async def say(client: httpx.AsyncClient, text: str, n: int = 1, **kwargs: Any) -> None:
    await post(client, message_payload(text=text, wa_message_id=f"wamid.IN{n}", **kwargs))


def sent(graph: respx.MockRouter) -> list[dict[str, Any]]:
    return [json.loads(c.request.content) for c in graph.routes[0].calls]


def alerts(graph: respx.MockRouter) -> list[dict[str, Any]]:
    return [b for b in sent(graph) if b["to"] == ALERT_NUMBER]


def hand_off(llm: FakeLLM, reason: str = "hot_lead", reply: str = "Ravi will confirm.") -> None:
    llm.queue(
        tool_response(("handoff_to_broker", {"summary": SUMMARY, "reason": reason})),
        text_response(reply),
    )


async def test_hot_lead_alerts_the_broker_after_the_lead_is_answered(
    client: httpx.AsyncClient, db: FakeDatabase, graph: respx.MockRouter, llm: FakeLLM
) -> None:
    hand_off(llm)
    await say(client, "Saturday 11 am visit chahiye")

    reply, alert = sent(graph)
    assert (reply["to"], reply["text"]["body"]) == ("919876543210", "Ravi will confirm.")
    assert alert["to"] == ALERT_NUMBER
    assert alert["template"] == {
        "name": "hot_lead_alert",
        "language": {"code": "en"},
        "components": [
            {
                "type": "body",
                "parameters": [
                    {"type": "text", "text": "Asha"},
                    {"type": "text", "text": "+919876543210"},
                    {"type": "text", "text": SUMMARY + "."},
                ],
            }
        ],
    }
    assert graph.routes[0].calls.last.request.headers["Authorization"] == f"Bearer {BROKER_TOKEN}"

    [row] = db.broker_messages
    assert (row["status"], row["reason"], row["lead_id"]) == ("sent", "hot_lead", db.leads[0].id)
    assert row["body"] == (
        f"New hot lead for you: Asha, +919876543210. {SUMMARY}. Please call or WhatsApp them soon."
    )
    # The alert is not part of the lead's own conversation.
    assert [m["direction"] for m in db.messages] == ["inbound", "outbound"]


async def test_alert_uses_the_name_learned_in_the_same_turn(
    client: httpx.AsyncClient, graph: respx.MockRouter, llm: FakeLLM
) -> None:
    llm.queue(
        tool_response(
            ("update_lead", {"name": "Asha Patil"}),
            ("handoff_to_broker", {"summary": SUMMARY, "reason": "hot_lead"}),
        ),
        text_response("ok"),
    )
    await say(client, "I'm Asha Patil")
    [alert] = alerts(graph)
    assert alert["template"]["components"][0]["parameters"][0]["text"] == "Asha Patil"


@pytest.mark.parametrize("reason", ["question", "complaint", "other"])
async def test_other_handoffs_are_not_called_hot(
    client: httpx.AsyncClient, graph: respx.MockRouter, llm: FakeLLM, reason: str
) -> None:
    hand_off(llm, reason)
    await say(client, "can I talk to someone?")
    [alert] = alerts(graph)
    assert alert["template"]["name"] == "lead_needs_reply"


async def test_no_handoff_no_alert(
    client: httpx.AsyncClient, db: FakeDatabase, graph: respx.MockRouter, llm: FakeLLM
) -> None:
    llm.queue(text_response("Buy or rent?"))
    await say(client, "hi")
    assert alerts(graph) == [] and db.broker_messages == []


async def test_repeat_alerts_are_capped_per_reason(
    client: httpx.AsyncClient, db: FakeDatabase, graph: respx.MockRouter, llm: FakeLLM
) -> None:
    for n in range(MAX_ALERTS + 1):
        hand_off(llm, "question")
        await say(client, f"question {n}", n)
    assert len(alerts(graph)) == MAX_ALERTS
    assert [r["status"] for r in db.broker_messages] == ["sent"] * MAX_ALERTS + ["skipped"]

    # Earlier questions never block a hot-lead alert.
    hand_off(llm, "hot_lead")
    await say(client, "visit tomorrow", 50)
    assert alerts(graph)[-1]["template"]["name"] == "hot_lead_alert"

    # And the cap lifts after a day.
    for row in db.broker_messages:
        row["created_at"] = datetime.now(UTC) - timedelta(hours=25)
    hand_off(llm, "question")
    await say(client, "another question", 51)
    assert db.broker_messages[-1]["status"] == "sent"


def api_error() -> anthropic.APIConnectionError:
    return anthropic.APIConnectionError(
        request=httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    )


async def test_assistant_failure_alerts_once_however_many_messages_fail(
    client: httpx.AsyncClient, db: FakeDatabase, graph: respx.MockRouter, llm: FakeLLM
) -> None:
    for n in range(3):
        llm.queue(api_error())
        await say(client, f"hello {n}", n)
    [alert] = alerts(graph)
    assert alert["template"]["name"] == "lead_needs_reply"
    assert [(r["reason"], r["status"]) for r in db.broker_messages] == [
        (ASSISTANT_FAILED, "sent"),
        (ASSISTANT_FAILED, "skipped"),
        (ASSISTANT_FAILED, "skipped"),
    ]


async def test_failure_after_a_handoff_keeps_the_hot_lead_summary(
    client: httpx.AsyncClient, graph: respx.MockRouter, llm: FakeLLM
) -> None:
    llm.queue(
        tool_response(("handoff_to_broker", {"summary": SUMMARY, "reason": "hot_lead"})),
        api_error(),
    )
    await say(client, "visit saturday")
    reply, alert = sent(graph)
    assert reply["text"]["body"] == FALLBACK_REPLY.format(broker="Ravi")
    assert alert["template"]["name"] == "hot_lead_alert"
    assert alert["template"]["components"][0]["parameters"][2]["text"] == SUMMARY + "."


async def test_failure_after_an_opt_out_promises_no_contact(
    client: httpx.AsyncClient, db: FakeDatabase, graph: respx.MockRouter, llm: FakeLLM
) -> None:
    llm.queue(tool_response(("mark_opted_out", {})), api_error())
    await say(client, "mat bhejo message")
    assert [b["text"]["body"] for b in sent(graph)] == [STOP_CONFIRMATION]
    assert (db.leads[0].opted_out, db.leads[0].status) == (True, "closed")
    assert db.broker_messages == []


async def test_opted_out_lead_is_not_passed_to_the_broker(
    client: httpx.AsyncClient, db: FakeDatabase, graph: respx.MockRouter, llm: FakeLLM
) -> None:
    llm.queue(
        tool_response(
            ("handoff_to_broker", {"summary": "Upset", "reason": "complaint"}),
            ("mark_opted_out", {}),
        ),
        text_response("Done."),
    )
    await say(client, "leave me alone")
    assert alerts(graph) == []
    assert (db.broker_messages[0]["status"], db.broker_messages[0]["detail"]) == (
        "skipped",
        "the lead opted out",
    )


async def test_rejected_alert_is_recorded_and_the_lead_is_still_answered(
    client: httpx.AsyncClient, db: FakeDatabase, graph: respx.MockRouter, llm: FakeLLM
) -> None:
    def reject_alert(request: httpx.Request) -> httpx.Response:
        if json.loads(request.content)["to"] == ALERT_NUMBER:
            return httpx.Response(400, json={"error": {"code": 132001, "message": "no template"}})
        return httpx.Response(200, json={"messages": [{"id": "wamid.REPLY"}]})

    graph.routes[0].mock(side_effect=reject_alert)
    hand_off(llm)
    await say(client, "visit saturday")

    assert db.messages[-1]["wa_message_id"] == "wamid.REPLY"
    [row] = db.broker_messages
    assert (row["status"], row["detail"]) == (
        "failed",
        "graph api returned 400: code=132001 message='no template'",
    )


async def test_broker_is_alerted_even_when_the_reply_to_the_lead_fails(
    client: httpx.AsyncClient, db: FakeDatabase, graph: respx.MockRouter, llm: FakeLLM
) -> None:
    def reject_lead(request: httpx.Request) -> httpx.Response:
        if json.loads(request.content)["to"] == ALERT_NUMBER:
            return httpx.Response(200, json={"messages": [{"id": "wamid.ALERT"}]})
        return httpx.Response(400, json={"error": {"code": 131047, "message": "no"}})

    graph.routes[0].mock(side_effect=reject_lead)
    hand_off(llm)
    await say(client, "visit saturday")
    assert db.broker_messages[0]["status"] == "sent"


async def test_undelivered_alert_is_marked_failed(
    client: httpx.AsyncClient, db: FakeDatabase, llm: FakeLLM
) -> None:
    hand_off(llm)
    await say(client, "visit saturday")
    payload = message_payload()
    value = payload["entry"][0]["changes"][0]["value"]
    del value["messages"], value["contacts"]
    value["statuses"] = [
        {
            "id": db.broker_messages[0]["wa_message_id"],
            "status": "failed",
            "errors": [{"code": 131026, "title": "Message undeliverable"}],
        }
    ]
    await post(client, payload)
    assert (db.broker_messages[0]["status"], db.broker_messages[0]["detail"]) == (
        "failed",
        "not delivered: code=131026 Message undeliverable",
    )


async def test_message_from_the_alert_number_is_stored_but_is_not_a_lead(
    client: httpx.AsyncClient, db: FakeDatabase, graph: respx.MockRouter, llm: FakeLLM
) -> None:
    for _ in range(2):  # Meta retries
        await say(client, "ok calling them now", from_phone=ALERT_NUMBER)
    assert llm.calls == [] and sent(graph) == []
    assert db.leads == [] and db.messages == []
    [row] = db.broker_messages
    assert (row["direction"], row["body"], row["status"]) == (
        "inbound",
        "ok calling them now",
        "received",
    )


def test_alert_templates_meet_metas_rules() -> None:
    for template in (HOT_LEAD_ALERT, LEAD_NEEDS_REPLY):
        assert not template.body.startswith("{{") and template.body.endswith("soon.")
    assert broker_alert_params(None, "919876543210", "Line one\nline two") == [
        "Name not given",
        "+919876543210",
        "Line one line two.",
    ]
    assert broker_alert_params("A", "91", "Visit at 11?")[2] == "Visit at 11?"
    assert len(broker_alert_params("A", "91", "x" * 2000)[2]) <= 600
    assert broker_alert_params("A", "91", "  ")[2] == "No details were noted."
