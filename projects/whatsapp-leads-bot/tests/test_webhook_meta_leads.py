import json
from collections.abc import AsyncIterator, Iterator
from typing import Any

import httpx
import pytest
import respx

from app.agent.run import Agent
from app.crypto import encrypt_token
from app.main import app
from app.webhooks.meta_leads import parse_leadgen, to_incoming
from app.whatsapp.client import WhatsAppClient
from tests.fakes import PHONE_NUMBER_ID, FakeDatabase, FakeLLM, encode, message_payload, sign

GRAPH = "https://graph.facebook.com/v24.0"
PAGE_ID = "555000111"
PAGE_TOKEN = "EAAG-page-token"
LEAD = {
    "created_time": "2026-11-18T05:00:00+0000",
    "form_id": "form-1",
    "ad_name": "Wakad Diwali offer",
    "platform": "fb",
    "field_data": [
        {"name": "full_name", "values": ["Asha Patil"]},
        {"name": "phone_number", "values": ["+919876543210"]},
        {"name": "email", "values": ["asha@example.com"]},
        {"name": "what_is_your_budget?", "values": ["80-90 lakh"]},
    ],
}


def leadgen_payload(leadgen_id: str = "lg-1", page_id: str = PAGE_ID) -> dict[str, Any]:
    return {
        "object": "page",
        "entry": [
            {
                "id": page_id,
                "time": 1_794_900_000,
                "changes": [
                    {
                        "field": "leadgen",
                        "value": {
                            "leadgen_id": leadgen_id,
                            "page_id": page_id,
                            "form_id": "form-1",
                            "ad_id": "ad-1",
                            "created_time": 1_794_900_000,
                        },
                    }
                ],
            }
        ],
    }


@pytest.fixture
def db() -> FakeDatabase:
    fake = FakeDatabase()
    fake.add_broker(
        name="Ravi",
        agency_name="Ravi Realty",
        fb_page_id=PAGE_ID,
        leads_access_token_enc=encrypt_token(PAGE_TOKEN),
    )
    return fake


@pytest.fixture
def graph() -> Iterator[respx.MockRouter]:
    with respx.mock(assert_all_called=False) as router:
        router.get(f"{GRAPH}/lg-1", name="lead").respond(200, json=LEAD)
        router.get(f"{GRAPH}/form-1", name="form").respond(
            200, json={"name": "Skyline Residency 2 BHK"}
        )
        router.post(f"{GRAPH}/{PHONE_NUMBER_ID}/messages", name="send").respond(
            200, json={"messages": [{"id": "wamid.OPENER"}]}
        )
        yield router


@pytest.fixture
async def client(db: FakeDatabase, graph: respx.MockRouter) -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient() as graph_http:
        app.state.db = db
        app.state.whatsapp = WhatsAppClient(graph_http, "v24.0")
        app.state.agent = None
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            yield c


async def post_signed(
    client: httpx.AsyncClient, payload: dict[str, Any], path: str
) -> httpx.Response:
    body = encode(payload)
    return await client.post(
        path,
        content=body,
        headers={"X-Hub-Signature-256": sign(body), "Content-Type": "application/json"},
    )


async def test_verify_echoes_challenge(client: httpx.AsyncClient) -> None:
    params = {
        "hub.mode": "subscribe",
        "hub.verify_token": "test-verify-token",
        "hub.challenge": "7",
    }
    response = await client.get("/webhooks/meta-leads", params=params)
    assert (response.status_code, response.text) == (200, "7")
    params["hub.verify_token"] = "wrong"
    assert (await client.get("/webhooks/meta-leads", params=params)).status_code == 403


async def test_bad_signature_is_rejected(
    client: httpx.AsyncClient, graph: respx.MockRouter
) -> None:
    response = await client.post("/webhooks/meta-leads", content=encode(leadgen_payload()))
    assert response.status_code == 401
    assert not graph["lead"].called


async def test_lead_form_submission_creates_lead_and_sends_opener(
    client: httpx.AsyncClient, db: FakeDatabase, graph: respx.MockRouter
) -> None:
    response = await post_signed(client, leadgen_payload(), "/webhooks/meta-leads")
    assert response.status_code == 200

    lead_request = graph["lead"].calls.last.request
    assert lead_request.headers["Authorization"] == f"Bearer {PAGE_TOKEN}"
    assert "field_data" in lead_request.url.params["fields"]
    [body] = [json.loads(c.request.content) for c in graph["send"].calls]
    assert [p["text"] for p in body["template"]["components"][0]["parameters"]] == [
        "Asha",
        "Skyline Residency 2 BHK",
        "Ravi Realty",
    ]
    [lead] = db.leads
    assert (lead.phone, lead.name, lead.source, lead.source_detail) == (
        "919876543210",
        "Asha Patil",
        "meta_ads",
        "Skyline Residency 2 BHK / Wakad Diwali offer",
    )
    assert db.messages[0]["body"] == (
        "Facebook lead form 'Skyline Residency 2 BHK' (ad: Wakad Diwali offer):\n"
        "- Full name: Asha Patil\n"
        "- Email: asha@example.com\n"
        "- What is your budget?: 80-90 lakh"
    )

    # Meta retries: handled once.
    await post_signed(client, leadgen_payload(), "/webhooks/meta-leads")
    assert graph["send"].call_count == 1


async def test_reply_to_the_opener_reaches_the_agent_with_the_form_answers(
    client: httpx.AsyncClient, db: FakeDatabase, graph: respx.MockRouter
) -> None:
    llm = FakeLLM()
    app.state.agent = Agent(llm, db, default_model="claude-haiku-5-5", effort="medium")  # type: ignore[arg-type]
    await post_signed(client, leadgen_payload(), "/webhooks/meta-leads")
    await post_signed(client, message_payload(text="buy karna hai"), "/webhooks/whatsapp")

    roles = [(m["role"], m["content"][:30]) for m in llm.calls[0]["messages"]]
    assert roles == [
        ("user", "Facebook lead form 'Skyline Re"),
        ("assistant", "Hi Asha, thanks for your enqui"),
        ("user", "buy karna hai"),
    ]


async def test_unknown_page_is_ignored(
    client: httpx.AsyncClient, db: FakeDatabase, graph: respx.MockRouter
) -> None:
    await post_signed(client, leadgen_payload(page_id="999"), "/webhooks/meta-leads")
    assert not graph["lead"].called and db.leads == []


async def test_broker_without_page_token_uses_the_whatsapp_token(
    client: httpx.AsyncClient, db: FakeDatabase, graph: respx.MockRouter
) -> None:
    db.brokers[0] = db.brokers[0].model_copy(update={"leads_access_token_enc": None})
    await post_signed(client, leadgen_payload(), "/webhooks/meta-leads")
    assert (
        graph["lead"].calls.last.request.headers["Authorization"] == "Bearer EAAG-test-broker-token"
    )


async def test_graph_error_is_logged_and_nothing_sent(
    client: httpx.AsyncClient, db: FakeDatabase, graph: respx.MockRouter
) -> None:
    graph["lead"].respond(400, json={"error": {"code": 100, "message": "no permission"}})
    response = await post_signed(client, leadgen_payload(), "/webhooks/meta-leads")
    assert response.status_code == 200
    assert not graph["send"].called and db.leads == []


def test_parse_ignores_other_fields_and_malformed_changes() -> None:
    payload = leadgen_payload()
    payload["entry"][0]["changes"] += [
        {"field": "feed", "value": {}},
        {"field": "leadgen", "value": {"page_id": PAGE_ID}},
    ]
    assert [e.leadgen_id for e in parse_leadgen(payload)] == ["lg-1"]


def test_split_name_instagram_and_enquiry_question() -> None:
    lead = {
        "platform": "ig",
        "field_data": [
            {"name": "first_name", "values": ["Vikram"]},
            {"name": "last_name", "values": ["Rao"]},
            {"name": "phone", "values": ["9876543210"]},
            {"name": "property", "values": ["Baner Greens 3 BHK"]},
        ],
    }
    result = to_incoming("lg-9", lead, form_name="Nov form")
    assert (result.name, result.phone, result.enquiry) == (
        "Vikram Rao",
        "9876543210",
        "Baner Greens 3 BHK",
    )
    assert result.summary.startswith("Instagram lead form 'Nov form':")
    assert "9876543210" not in result.summary
