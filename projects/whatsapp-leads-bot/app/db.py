"""Supabase access. All queries the app makes live here."""

from datetime import UTC, datetime
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
    listings_sheet_url: str | None = None
    fb_page_id: str | None = None
    leads_access_token_enc: str | None = Field(default=None, repr=False)
    inbound_email_key: str | None = None
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
    external_id: str | None = None  # the listing's ID in its source (sheet or file)
    title: str
    area: str
    bhk: str | None = None
    price_min: int | None = None  # rupees
    price_max: int | None = None
    type: str | None = None  # sale / rent
    status: str = "available"  # available / sold / on_hold / removed
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
        self,
        broker_id: str,
        phone: str,
        *,
        name: str | None,
        source: str,
        source_detail: str | None = None,
    ) -> Lead:
        # Insert-if-absent so an existing lead's fields (e.g. a name the agent learned) are
        # never overwritten by intake data.
        row = {"broker_id": broker_id, "phone": phone, "name": name, "source": source}
        if source_detail:
            row["source_detail"] = source_detail
        res = (
            await self._client.table("leads")
            .upsert(
                row,
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

    async def list_properties(self, broker_id: str) -> list[Property]:
        """All of the broker's listings, whatever their status."""
        res = (
            await self._client.table("properties").select("*").eq("broker_id", broker_id).execute()
        )
        return [Property.model_validate(r) for r in _rows(res.data)]

    async def upsert_properties(self, broker_id: str, rows: list[dict[str, Any]]) -> None:
        """Insert or update listings, matched on (broker_id, external_id)."""
        if not rows:
            return
        now = datetime.now(UTC).isoformat()
        await (
            self._client.table("properties")
            .upsert(
                [{**r, "broker_id": broker_id, "updated_at": now} for r in rows],
                on_conflict="broker_id,external_id",
            )
            .execute()
        )

    async def set_properties_status(self, property_ids: list[str], status: str) -> None:
        if not property_ids:
            return
        await (
            self._client.table("properties")
            .update({"status": status, "updated_at": datetime.now(UTC).isoformat()})
            .in_("id", property_ids)
            .execute()
        )

    async def set_listings_sheet(self, broker_id: str, url: str) -> None:
        await (
            self._client.table("brokers")
            .update({"listings_sheet_url": url})
            .eq("id", broker_id)
            .execute()
        )

    async def list_brokers_with_listings_sheet(self) -> list[Broker]:
        res = (
            await self._client.table("brokers")
            .select("*")
            .eq("active", True)
            .not_.is_("listings_sheet_url", "null")
            .execute()
        )
        return [Broker.model_validate(r) for r in _rows(res.data)]

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

    async def get_broker_by_page_id(self, page_id: str) -> Broker | None:
        return await self._one_broker("fb_page_id", page_id)

    async def get_broker_by_email_key(self, key: str) -> Broker | None:
        return await self._one_broker("inbound_email_key", key)

    async def _one_broker(self, column: str, value: str) -> Broker | None:
        res = (
            await self._client.table("brokers")
            .select("*")
            .eq(column, value)
            .eq("active", True)
            .limit(1)
            .execute()
        )
        rows = _rows(res.data)
        return Broker.model_validate(rows[0]) if rows else None

    async def update_broker(self, broker_id: str, fields: dict[str, Any]) -> None:
        await self._client.table("brokers").update(fields).eq("id", broker_id).execute()

    async def start_intake_event(self, broker_id: str, source: str, external_id: str) -> bool:
        """Record an incoming lead. Returns False if this one was already received (a retry)."""
        res = (
            await self._client.table("intake_events")
            .upsert(
                {"broker_id": broker_id, "source": source, "external_id": external_id},
                on_conflict="source,external_id",
                ignore_duplicates=True,
            )
            .execute()
        )
        return bool(res.data)

    async def intake_event_exists(self, source: str, external_id: str) -> bool:
        res = (
            await self._client.table("intake_events")
            .select("id")
            .eq("source", source)
            .eq("external_id", external_id)
            .limit(1)
            .execute()
        )
        return bool(_rows(res.data))

    async def finish_intake_event(
        self,
        source: str,
        external_id: str,
        *,
        status: str,
        lead_id: str | None = None,
        detail: str | None = None,
    ) -> None:
        await (
            self._client.table("intake_events")
            .update({"status": status, "lead_id": lead_id, "detail": detail})
            .eq("source", source)
            .eq("external_id", external_id)
            .execute()
        )

    async def opener_sent_since(self, lead_id: str, since: datetime) -> bool:
        res = (
            await self._client.table("intake_events")
            .select("id")
            .eq("lead_id", lead_id)
            .eq("status", "opener_sent")
            .gte("created_at", since.isoformat())
            .limit(1)
            .execute()
        )
        return bool(_rows(res.data))
