"""Supabase access. All queries the app makes live here."""

from datetime import datetime
from typing import Any, Literal, cast

from pydantic import BaseModel, ConfigDict, Field
from supabase import AsyncClient, acreate_client

from app.config import Settings

Direction = Literal["inbound", "outbound"]


class Broker(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    name: str
    agency_name: str | None = None
    phone_number_id: str
    access_token_enc: str = Field(repr=False)
    alert_number: str
    timezone: str = "Asia/Kolkata"
    business_hours: dict[str, list[str]] | None = None  # {"mon": ["10:00", "19:00"], ...}
    model: str | None = None
    active: bool = True


class Lead(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    broker_id: str
    phone: str
    name: str | None = None
    source: str | None = None
    source_detail: str | None = None
    intent: str | None = None
    budget: str | None = None
    area: str | None = None
    bhk: str | None = None
    timeline: str | None = None
    needs_loan: bool | None = None
    score: str | None = None
    status: str = "new"
    opted_out: bool = False
    last_inbound_at: datetime | None = None


class Property(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    broker_id: str
    title: str
    area: str
    bhk: str | None = None
    price_min: int | None = None  # rupees
    price_max: int | None = None
    type: str | None = None  # sale / rent
    status: str = "available"
    notes: str | None = None


class StoredMessage(BaseModel):
    model_config = ConfigDict(extra="ignore")

    direction: Direction
    kind: str = "text"
    body: str | None = None
    created_at: datetime | None = None


def _rows(data: Any) -> list[dict[str, Any]]:
    return cast(list[dict[str, Any]], data or [])


class Database:
    def __init__(self, client: AsyncClient) -> None:
        self._client = client

    @classmethod
    async def connect(cls, settings: Settings) -> "Database":
        client = await acreate_client(
            settings.supabase_url, settings.supabase_service_role_key.get_secret_value()
        )
        return cls(client)

    async def get_broker_by_phone_number_id(self, phone_number_id: str) -> Broker | None:
        res = (
            await self._client.table("brokers")
            .select("*")
            .eq("phone_number_id", phone_number_id)
            .eq("active", True)
            .limit(1)
            .execute()
        )
        rows = _rows(res.data)
        return Broker.model_validate(rows[0]) if rows else None

    async def upsert_broker(self, row: dict[str, Any]) -> Broker:
        res = (
            await self._client.table("brokers").upsert(row, on_conflict="phone_number_id").execute()
        )
        return Broker.model_validate(_rows(res.data)[0])

    async def get_or_create_lead(
        self, broker_id: str, phone: str, *, name: str | None, source: str
    ) -> Lead:
        # Insert-if-absent so an existing lead's fields (e.g. a name the agent learned) are
        # never overwritten by intake data.
        res = (
            await self._client.table("leads")
            .upsert(
                {"broker_id": broker_id, "phone": phone, "name": name, "source": source},
                on_conflict="broker_id,phone",
                ignore_duplicates=True,
            )
            .execute()
        )
        rows = _rows(res.data)
        if not rows:
            res = (
                await self._client.table("leads")
                .select("*")
                .eq("broker_id", broker_id)
                .eq("phone", phone)
                .limit(1)
                .execute()
            )
            rows = _rows(res.data)
        return Lead.model_validate(rows[0])

    async def set_last_inbound_at(self, lead_id: str, at: datetime) -> None:
        await (
            self._client.table("leads")
            .update({"last_inbound_at": at.isoformat()})
            .eq("id", lead_id)
            .execute()
        )

    async def insert_message(
        self,
        *,
        lead_id: str,
        direction: Direction,
        kind: str,
        body: str | None,
        wa_message_id: str | None,
    ) -> bool:
        """Store a message. Returns False if `wa_message_id` was already stored (a retry)."""
        row = {
            "lead_id": lead_id,
            "direction": direction,
            "kind": kind,
            "body": body,
            "wa_message_id": wa_message_id,
        }
        table = self._client.table("messages")
        if wa_message_id is None:
            await table.insert(row).execute()
            return True
        res = await table.upsert(row, on_conflict="wa_message_id", ignore_duplicates=True).execute()
        return bool(res.data)

    async def get_lead(self, lead_id: str) -> Lead | None:
        res = await self._client.table("leads").select("*").eq("id", lead_id).limit(1).execute()
        rows = _rows(res.data)
        return Lead.model_validate(rows[0]) if rows else None

    async def update_lead(self, lead_id: str, fields: dict[str, Any]) -> None:
        await self._client.table("leads").update(fields).eq("id", lead_id).execute()

    async def mark_opted_out(self, lead_id: str) -> None:
        """Opt the lead out for good and cancel any follow-ups still waiting to be sent."""
        await (
            self._client.table("leads")
            .update({"opted_out": True, "status": "closed"})
            .eq("id", lead_id)
            .execute()
        )
        await (
            self._client.table("followups")
            .update({"cancelled": True})
            .eq("lead_id", lead_id)
            .eq("sent", False)
            .execute()
        )

    async def recent_messages(self, lead_id: str, limit: int = 20) -> list[StoredMessage]:
        """The lead's latest messages, oldest first."""
        res = (
            await self._client.table("messages")
            .select("direction,kind,body,created_at")
            .eq("lead_id", lead_id)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        return [StoredMessage.model_validate(r) for r in reversed(_rows(res.data))]

    async def list_available_properties(self, broker_id: str) -> list[Property]:
        res = (
            await self._client.table("properties")
            .select("*")
            .eq("broker_id", broker_id)
            .eq("status", "available")
            .order("area")
            .order("title")
            .execute()
        )
        return [Property.model_validate(r) for r in _rows(res.data)]

    async def count_properties(self, broker_id: str) -> int:
        res = (
            await self._client.table("properties").select("id").eq("broker_id", broker_id).execute()
        )
        return len(_rows(res.data))

    async def replace_properties(self, broker_id: str, rows: list[dict[str, Any]]) -> int:
        """Delete the broker's properties and insert `rows` instead. Returns the number added."""
        await self._client.table("properties").delete().eq("broker_id", broker_id).execute()
        if not rows:
            return 0
        res = (
            await self._client.table("properties")
            .insert([{**r, "broker_id": broker_id} for r in rows])
            .execute()
        )
        return len(_rows(res.data))

    async def insert_agent_log(
        self,
        *,
        lead_id: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        tool_calls: list[dict[str, Any]],
        reply: str | None,
    ) -> None:
        await (
            self._client.table("agent_logs")
            .insert(
                {
                    "lead_id": lead_id,
                    "model": model,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "tool_calls": tool_calls,
                    "reply": reply,
                }
            )
            .execute()
        )
