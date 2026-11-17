import json
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
import respx

from app.intake.leads import IncomingLead, intake_lead, record_skipped
from app.whatsapp.client import WhatsAppClient, WhatsAppError
from app.whatsapp.templates import LEAD_OPENER, lead_opener_params, template_param
from tests.fakes import BROKER_TOKEN, PHONE_NUMBER_ID, FakeDatabase

SEND_URL = f"https://graph.facebook.com/v24.0/{PHONE_NUMBER_ID}/messages"


def incoming(external_id: str = "lead-1", **overrides: Any) -> IncomingLead:
    fields: dict[str, Any] = {
        "source": "meta_ads",
        "external_id": external_id,
        "kind": "lead_form",
        "phone": "+91 98765 43210",
        "name": "Asha Patil",
        "enquiry": "Skyline Residency 2 BHK",
        "source_detail": "Skyline form",
        "summary": "Facebook lead form 'Skyline':\n- Budget: 90 L",
    }
    return IncomingLead(**(fields | overrides))


@pytest.fixture
def db() -> FakeDatabase:
    fake = FakeDatabase()
    fake.add_broker(name="Ravi", agency_name="Ravi Realty")
    return fake


@pytest.fixture
def graph() -> Iterator[respx.MockRouter]:
    with respx.mock(assert_all_called=False) as router:
        router.post(SEND_URL).respond(200, json={"messages": [{"id": "wamid.OPENER"}]})
        yield router


@pytest.fixture
async def whatsapp(graph: respx.MockRouter) -> AsyncIterator[WhatsAppClient]:
    async with httpx.AsyncClient() as http:
        yield WhatsAppClient(http, "v24.0")


def sent(graph: respx.MockRouter) -> list[dict[str, Any]]:
    return [json.loads(c.request.content) for c in graph.routes[0].calls]


async def test_new_lead_gets_the_opener_template(
    db: FakeDatabase, whatsapp: WhatsAppClient, graph: respx.MockRouter
) -> None:
    status = await intake_lead(db, whatsapp, db.brokers[0], incoming())

    assert status == "opener_sent"
    assert sent(graph) == [
        {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": "919876543210",
            "type": "template",
            "template": {
                "name": "lead_opener",
                "language": {"code": "en"},
                "components": [
                    {
                        "type": "body",
                        "parameters": [
                            {"type": "text", "text": "Asha"},
                            {"type": "text", "text": "Skyline Residency 2 BHK"},
                            {"type": "text", "text": "Ravi Realty"},
                        ],
                    }
                ],
            },
        }
    ]
    assert graph.routes[0].calls.last.request.headers["Authorization"] == f"Bearer {BROKER_TOKEN}"

    [lead] = db.leads
    assert (lead.phone, lead.name, lead.source, lead.source_detail) == (
        "919876543210",
        "Asha Patil",
        "meta_ads",
        "Skyline form",
    )
    assert lead.last_inbound_at is None  # a form is not a WhatsApp message: no window
    assert [(m["direction"], m["kind"], m["body"]) for m in db.messages] == [
        ("inbound", "lead_form", "Facebook lead form 'Skyline':\n- Budget: 90 L"),
        (
            "outbound",
            "template",
            "Hi Asha, thanks for your enquiry about Skyline Residency 2 BHK with Ravi Realty. "
            "Are you looking to buy or rent?",
        ),
    ]
    assert db.messages[1]["wa_message_id"] == "wamid.OPENER"
    [event] = db.intake_events
    assert (event["status"], event["lead_id"]) == ("opener_sent", lead.id)


async def test_retry_of_the_same_lead_is_handled_once(
    db: FakeDatabase, whatsapp: WhatsAppClient, graph: respx.MockRouter
) -> None:
    assert await intake_lead(db, whatsapp, db.brokers[0], incoming()) == "opener_sent"
    assert await intake_lead(db, whatsapp, db.brokers[0], incoming()) == "duplicate"
    assert len(sent(graph)) == 1
    assert len(db.messages) == 2


async def test_second_enquiry_within_a_day_is_stored_without_another_opener(
    db: FakeDatabase, whatsapp: WhatsAppClient, graph: respx.MockRouter
) -> None:
    await intake_lead(db, whatsapp, db.brokers[0], incoming("lead-1"))
    status = await intake_lead(
        db, whatsapp, db.brokers[0], incoming("email-9", source="portal_email", kind="email")
    )
    assert status == "skipped_recent_opener"
    assert len(sent(graph)) == 1
    assert [m["kind"] for m in db.messages] == ["lead_form", "template", "email"]

    db.intake_events[0]["created_at"] = datetime.now(UTC) - timedelta(hours=25)
    assert await intake_lead(db, whatsapp, db.brokers[0], incoming("lead-3")) == "opener_sent"


@pytest.mark.parametrize(
    ("phone", "status"),
    [(None, "skipped_no_phone"), ("12345", "skipped_bad_phone")],
)
async def test_unusable_phone_is_recorded_not_sent(
    db: FakeDatabase,
    whatsapp: WhatsAppClient,
    graph: respx.MockRouter,
    phone: str | None,
    status: str,
) -> None:
    assert await intake_lead(db, whatsapp, db.brokers[0], incoming(phone=phone)) == status
    assert db.leads == [] and not sent(graph)
    assert db.intake_events[0]["status"] == status


async def test_opted_out_lead_gets_nothing(
    db: FakeDatabase, whatsapp: WhatsAppClient, graph: respx.MockRouter
) -> None:
    lead = await db.get_or_create_lead(db.brokers[0].id, "919876543210", name=None, source="x")
    await db.mark_opted_out(lead.id)
    assert await intake_lead(db, whatsapp, db.brokers[0], incoming()) == "skipped_opted_out"
    assert not sent(graph)


async def test_lead_already_chatting_gets_no_template(
    db: FakeDatabase, whatsapp: WhatsAppClient, graph: respx.MockRouter
) -> None:
    lead = await db.get_or_create_lead(
        db.brokers[0].id, "919876543210", name="A", source="whatsapp"
    )
    await db.set_last_inbound_at(lead.id, datetime.now(UTC) - timedelta(hours=1))
    status = await intake_lead(db, whatsapp, db.brokers[0], incoming())
    assert status == "skipped_in_conversation"
    assert not sent(graph)
    assert db.leads[0].source == "whatsapp"  # existing lead keeps its source and name
    assert db.messages[-1]["kind"] == "lead_form"  # the agent sees it with the next message


async def test_send_failure_is_recorded_and_raised(
    db: FakeDatabase, whatsapp: WhatsAppClient, graph: respx.MockRouter
) -> None:
    graph.routes[0].respond(400, json={"error": {"code": 132001, "message": "template missing"}})
    with pytest.raises(WhatsAppError):
        await intake_lead(db, whatsapp, db.brokers[0], incoming())
    assert (db.intake_events[0]["status"], db.intake_events[0]["detail"]) == (
        "failed",
        "WhatsAppError",
    )


async def test_record_skipped_only_once(db: FakeDatabase) -> None:
    await record_skipped(db, db.brokers[0], "portal_email", "m1", "skipped_not_a_lead")
    await record_skipped(db, db.brokers[0], "portal_email", "m1", "failed")
    [event] = db.intake_events
    assert event["status"] == "skipped_not_a_lead"


def test_template_params_are_safe_for_meta() -> None:
    assert lead_opener_params(None, None, "Ravi Realty") == [
        "there",
        "your property search",
        "Ravi Realty",
    ]
    assert template_param("2 BHK\n\nWakad\t ", "x") == "2 BHK Wakad"
    long = template_param("x" * 100, "x")
    assert len(long) == 60 and long.endswith("…")
    assert LEAD_OPENER.render(["A", "B", "C"]).startswith("Hi A, thanks for your enquiry about B")
