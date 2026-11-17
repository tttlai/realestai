"""Runs app.db against a real PostgREST (the API layer Supabase uses) to check upsert/dedupe.

Skipped unless TEST_POSTGREST_URL is set. Point it at a throwaway database with the migration
applied, e.g. a local `supabase start` (http://127.0.0.1:54321/rest/v1, with TEST_POSTGREST_KEY
set to its service-role key). Never point it at production: it writes and deletes rows.
"""

import os
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any, cast

import pytest
from postgrest import AsyncPostgrestClient

from app.db import Broker, Database

URL = os.environ.get("TEST_POSTGREST_URL")
KEY = os.environ.get("TEST_POSTGREST_KEY")

pytestmark = pytest.mark.skipif(not URL, reason="TEST_POSTGREST_URL not set")


@pytest.fixture
async def db() -> AsyncIterator[Database]:
    headers = {"apikey": KEY, "Authorization": f"Bearer {KEY}"} if KEY else {}
    async with AsyncPostgrestClient(cast(str, URL), headers=headers) as client:
        yield Database(cast(Any, client))


@pytest.fixture
async def broker(db: Database) -> AsyncIterator[Broker]:
    broker = await db.upsert_broker(
        {
            "name": "Integration Test",
            "phone_number_id": f"test-{uuid.uuid4()}",
            "access_token_enc": "not-a-real-token",
            "alert_number": "919800000000",
        }
    )
    yield broker
    await db._client.table("brokers").delete().eq("id", broker.id).execute()


async def test_broker_lookup(db: Database, broker: Broker) -> None:
    found = await db.get_broker_by_phone_number_id(broker.phone_number_id)
    assert found is not None and found.id == broker.id
    assert await db.get_broker_by_phone_number_id("no-such-number") is None

    await db._client.table("brokers").update({"active": False}).eq("id", broker.id).execute()
    assert await db.get_broker_by_phone_number_id(broker.phone_number_id) is None


async def test_get_or_create_lead_keeps_existing_fields(db: Database, broker: Broker) -> None:
    first = await db.get_or_create_lead(broker.id, "919876543210", name="Asha", source="whatsapp")
    again = await db.get_or_create_lead(broker.id, "919876543210", name="Other", source="website")
    assert again.id == first.id
    assert (again.name, again.source) == ("Asha", "whatsapp")


async def test_insert_message_dedupes_on_wa_message_id(db: Database, broker: Broker) -> None:
    lead = await db.get_or_create_lead(broker.id, "919876543210", name=None, source="whatsapp")
    wa_id = f"wamid.{uuid.uuid4()}"
    kwargs: dict[str, Any] = {
        "lead_id": lead.id,
        "direction": "inbound",
        "kind": "text",
        "body": "hi",
    }
    assert await db.insert_message(**kwargs, wa_message_id=wa_id) is True
    assert await db.insert_message(**kwargs, wa_message_id=wa_id) is False
    assert await db.insert_message(**kwargs, wa_message_id=None) is True
    assert await db.insert_message(**kwargs, wa_message_id=None) is True

    rows = (
        await db._client.table("messages").select("wa_message_id").eq("lead_id", lead.id).execute()
    )
    assert sorted(str(r["wa_message_id"]) for r in rows.data) == ["None", "None", wa_id]


async def test_set_last_inbound_at(db: Database, broker: Broker) -> None:
    lead = await db.get_or_create_lead(broker.id, "919876543210", name=None, source="whatsapp")
    assert lead.last_inbound_at is None
    at = datetime(2026, 10, 19, 6, 30, tzinfo=UTC)
    await db.set_last_inbound_at(lead.id, at)
    lead = await db.get_or_create_lead(broker.id, "919876543210", name=None, source="whatsapp")
    assert lead.last_inbound_at == at


async def test_lead_updates_and_opt_out(db: Database, broker: Broker) -> None:
    lead = await db.get_or_create_lead(broker.id, "919876543210", name=None, source="whatsapp")
    await db.update_lead(lead.id, {"intent": "buy", "area": "Wakad", "status": "qualifying"})
    await (
        db._client.table("followups")
        .insert({"lead_id": lead.id, "due_at": "2030-01-01T00:00:00Z", "template": "followup_day1"})
        .execute()
    )

    await db.mark_opted_out(lead.id)

    saved = await db.get_lead(lead.id)
    assert saved is not None
    assert (saved.intent, saved.area, saved.opted_out, saved.status) == (
        "buy",
        "Wakad",
        True,
        "closed",
    )
    rows = await db._client.table("followups").select("cancelled").eq("lead_id", lead.id).execute()
    assert [r["cancelled"] for r in rows.data] == [True]


async def test_recent_messages_are_oldest_first(db: Database, broker: Broker) -> None:
    lead = await db.get_or_create_lead(broker.id, "919876543210", name=None, source="whatsapp")
    for i in range(3):
        await db.insert_message(
            lead_id=lead.id, direction="inbound", kind="text", body=str(i), wa_message_id=None
        )
    assert [m.body for m in await db.recent_messages(lead.id, limit=2)] == ["1", "2"]


async def test_listing_upsert_status_and_agent_log(db: Database, broker: Broker) -> None:
    row = {"title": "A", "area": "Wakad", "price_min": 8500000, "price_max": 9500000}
    await db.upsert_properties(
        broker.id,
        [
            {"external_id": "P1", **row, "status": "available"},
            {"external_id": "P2", **row, "title": "B", "status": "sold"},
        ],
    )
    [p1] = await db.list_available_properties(broker.id)
    assert (p1.external_id, p1.title) == ("P1", "A")

    # Same external_id: updated in place, keeping its row id.
    await db.upsert_properties(broker.id, [{"external_id": "P1", **row, "title": "A2"}])
    all_props = {p.external_id: p for p in await db.list_properties(broker.id)}
    assert all_props["P1"].id == p1.id and all_props["P1"].title == "A2"
    assert len(all_props) == 2

    await db.set_properties_status([p1.id], "removed")
    assert await db.list_available_properties(broker.id) == []

    sheet = "https://docs.google.com/spreadsheets/d/abc/edit"
    await db.set_listings_sheet(broker.id, sheet)
    synced = [b.id for b in await db.list_brokers_with_listings_sheet()]
    assert broker.id in synced

    lead = await db.get_or_create_lead(broker.id, "919876543210", name=None, source="whatsapp")
    await db.insert_agent_log(
        lead_id=lead.id,
        model="claude-haiku-5-5",
        input_tokens=10,
        output_tokens=5,
        tool_calls=[{"name": "update_lead", "input": {"area": "Wakad"}}],
        reply="hi",
    )
    rows = await db._client.table("agent_logs").select("*").eq("lead_id", lead.id).execute()
    assert rows.data[0]["tool_calls"] == [{"name": "update_lead", "input": {"area": "Wakad"}}]
