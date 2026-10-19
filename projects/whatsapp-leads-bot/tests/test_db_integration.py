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
