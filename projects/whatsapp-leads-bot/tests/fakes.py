"""In-memory stand-ins for the database and the Claude API, plus webhook payload helpers."""

import copy
import hashlib
import hmac
import json
import time
import uuid
from datetime import UTC, datetime
from typing import Any

from anthropic.types import Message

from app.crypto import encrypt_token
from app.db import Broker, Lead, Property, StoredMessage

APP_SECRET = "test-app-secret"
PHONE_NUMBER_ID = "123456789012345"
BROKER_TOKEN = "EAAG-test-broker-token"


class FakeDatabase:
    """Same behaviour as app.db.Database, including dedupe on wa_message_id."""

    def __init__(self) -> None:
        self.brokers: list[Broker] = []
        self.leads: list[Lead] = []
        self.messages: list[dict[str, Any]] = []
        self.properties: list[Property] = []
        self.followups: list[dict[str, Any]] = []
        self.agent_logs: list[dict[str, Any]] = []
        self.intake_events: list[dict[str, Any]] = []

    def add_broker(self, **overrides: Any) -> Broker:
        fields: dict[str, Any] = {
            "id": str(uuid.uuid4()),
            "name": "Test Broker",
            "agency_name": "Test Realty",
            "phone_number_id": PHONE_NUMBER_ID,
            "alert_number": "919800000000",
        }
        if "access_token_enc" not in overrides:
            fields["access_token_enc"] = encrypt_token(BROKER_TOKEN)
        broker = Broker(**(fields | overrides))
        self.brokers.append(broker)
        return broker

    def add_property(self, broker_id: str, **fields: Any) -> Property:
        prop = Property(id=str(uuid.uuid4()), broker_id=broker_id, **fields)
        self.properties.append(prop)
        return prop

    def lead(self, lead_id: str) -> Lead:
        return next(lead for lead in self.leads if lead.id == lead_id)

    async def get_broker_by_phone_number_id(self, phone_number_id: str) -> Broker | None:
        return next(
            (b for b in self.brokers if b.phone_number_id == phone_number_id and b.active), None
        )

    async def get_or_create_lead(
        self,
        broker_id: str,
        phone: str,
        *,
        name: str | None,
        source: str,
        source_detail: str | None = None,
    ) -> Lead:
        for lead in self.leads:
            if lead.broker_id == broker_id and lead.phone == phone:
                return lead.model_copy()
        lead = Lead(
            id=str(uuid.uuid4()),
            broker_id=broker_id,
            phone=phone,
            name=name,
            source=source,
            source_detail=source_detail,
        )
        self.leads.append(lead)
        return lead.model_copy()

    async def get_lead(self, lead_id: str) -> Lead | None:
        return next((lead.model_copy() for lead in self.leads if lead.id == lead_id), None)

    async def set_last_inbound_at(self, lead_id: str, at: datetime) -> None:
        await self.update_lead(lead_id, {"last_inbound_at": at})

    async def update_lead(self, lead_id: str, fields: dict[str, Any]) -> None:
        for i, lead in enumerate(self.leads):
            if lead.id == lead_id:
                self.leads[i] = lead.model_copy(update=fields)

    async def mark_opted_out(self, lead_id: str) -> None:
        await self.update_lead(lead_id, {"opted_out": True, "status": "closed"})
        for f in self.followups:
            if f["lead_id"] == lead_id and not f["sent"]:
                f["cancelled"] = True

    async def insert_message(
        self,
        *,
        lead_id: str,
        direction: str,
        kind: str,
        body: str | None,
        wa_message_id: str | None,
    ) -> bool:
        if wa_message_id is not None and any(
            m["wa_message_id"] == wa_message_id for m in self.messages
        ):
            return False
        self.messages.append(
            {
                "lead_id": lead_id,
                "direction": direction,
                "kind": kind,
                "body": body,
                "wa_message_id": wa_message_id,
            }
        )
        return True

    async def recent_messages(self, lead_id: str, limit: int = 20) -> list[StoredMessage]:
        rows = [m for m in self.messages if m["lead_id"] == lead_id][-limit:]
        return [StoredMessage.model_validate(m) for m in rows]

    async def list_available_properties(self, broker_id: str) -> list[Property]:
        return [p for p in self.properties if p.broker_id == broker_id and p.status == "available"]

    async def list_properties(self, broker_id: str) -> list[Property]:
        return [p for p in self.properties if p.broker_id == broker_id]

    async def upsert_properties(self, broker_id: str, rows: list[dict[str, Any]]) -> None:
        for row in rows:
            match = next(
                (
                    i
                    for i, p in enumerate(self.properties)
                    if p.broker_id == broker_id and p.external_id == row["external_id"]
                ),
                None,
            )
            if match is None:
                self.add_property(broker_id, **row)
            else:
                self.properties[match] = self.properties[match].model_copy(update=row)

    async def set_properties_status(self, property_ids: list[str], status: str) -> None:
        for i, p in enumerate(self.properties):
            if p.id in property_ids:
                self.properties[i] = p.model_copy(update={"status": status})

    async def set_listings_sheet(self, broker_id: str, url: str) -> None:
        for i, b in enumerate(self.brokers):
            if b.id == broker_id:
                self.brokers[i] = b.model_copy(update={"listings_sheet_url": url})

    async def list_brokers_with_listings_sheet(self) -> list[Broker]:
        return [b for b in self.brokers if b.active and b.listings_sheet_url]

    async def insert_agent_log(self, **row: Any) -> None:
        self.agent_logs.append(row)

    async def get_broker_by_page_id(self, page_id: str) -> Broker | None:
        return next((b for b in self.brokers if b.fb_page_id == page_id and b.active), None)

    async def get_broker_by_email_key(self, key: str) -> Broker | None:
        return next((b for b in self.brokers if b.inbound_email_key == key and b.active), None)

    async def update_broker(self, broker_id: str, fields: dict[str, Any]) -> None:
        for i, b in enumerate(self.brokers):
            if b.id == broker_id:
                self.brokers[i] = b.model_copy(update=fields)

    async def start_intake_event(self, broker_id: str, source: str, external_id: str) -> bool:
        if await self.intake_event_exists(source, external_id):
            return False
        self.intake_events.append(
            {
                "broker_id": broker_id,
                "source": source,
                "external_id": external_id,
                "lead_id": None,
                "status": "received",
                "detail": None,
                "created_at": datetime.now(UTC),
            }
        )
        return True

    async def intake_event_exists(self, source: str, external_id: str) -> bool:
        return any(
            e["source"] == source and e["external_id"] == external_id for e in self.intake_events
        )

    async def finish_intake_event(
        self,
        source: str,
        external_id: str,
        *,
        status: str,
        lead_id: str | None = None,
        detail: str | None = None,
    ) -> None:
        for e in self.intake_events:
            if e["source"] == source and e["external_id"] == external_id:
                e.update(status=status, lead_id=lead_id, detail=detail)

    async def opener_sent_since(self, lead_id: str, since: datetime) -> bool:
        return any(
            e["lead_id"] == lead_id and e["status"] == "opener_sent" and e["created_at"] >= since
            for e in self.intake_events
        )


class FakeLLM:
    """Stands in for anthropic.AsyncAnthropic: `.messages.create(...)` returns queued responses.

    With nothing queued it echoes the lead's latest message, which keeps webhook tests simple.
    Every call's arguments are kept in `calls`.
    """

    def __init__(self) -> None:
        self.messages = self
        self.calls: list[dict[str, Any]] = []
        self.queued: list[dict[str, Any] | Exception] = []

    def queue(self, *responses: dict[str, Any] | Exception) -> None:
        self.queued.extend(responses)

    async def create(self, **kwargs: Any) -> Message:
        self.calls.append(copy.deepcopy(kwargs))
        if self.queued:
            nxt = self.queued.pop(0)
            if isinstance(nxt, Exception):
                raise nxt
            return Message.model_validate(nxt)
        last_user = next(m for m in reversed(kwargs["messages"]) if m["role"] == "user")
        content = last_user["content"]
        text = content if isinstance(content, str) else "ok"
        return Message.model_validate(text_response(text.split("\n\n")[-1]))


def _response(content: list[dict[str, Any]], stop_reason: str) -> dict[str, Any]:
    return {
        "id": f"msg_{uuid.uuid4().hex[:12]}",
        "type": "message",
        "role": "assistant",
        "model": "claude-haiku-5-5",
        "content": content,
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": {
            "input_tokens": 100,
            "output_tokens": 20,
            "cache_read_input_tokens": 50,
            "cache_creation_input_tokens": 0,
        },
    }


def text_response(text: str, stop_reason: str = "end_turn") -> dict[str, Any]:
    return _response([{"type": "text", "text": text}], stop_reason)


def tool_response(*calls: tuple[str, dict[str, Any]]) -> dict[str, Any]:
    """A turn that thinks, then calls the given tools."""
    content: list[dict[str, Any]] = [{"type": "thinking", "thinking": "", "signature": "sig"}]
    for name, tool_input in calls:
        content.append(
            {
                "type": "tool_use",
                "id": f"toolu_{uuid.uuid4().hex[:12]}",
                "name": name,
                "input": tool_input,
            }
        )
    return _response(content, "tool_use")


def message_payload(
    *,
    text: str | None = "hello",
    msg_type: str = "text",
    wa_message_id: str = "wamid.TEST1",
    from_phone: str = "919876543210",
    name: str = "Asha",
    phone_number_id: str = PHONE_NUMBER_ID,
    timestamp: int | None = None,
) -> dict[str, Any]:
    message: dict[str, Any] = {
        "from": from_phone,
        "id": wa_message_id,
        "timestamp": str(timestamp if timestamp is not None else int(time.time())),
        "type": msg_type,
    }
    if msg_type == "text":
        message["text"] = {"body": text}
    else:
        message[msg_type] = {"id": "media-id", "mime_type": "image/jpeg"}
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "WABA_ID",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": "15550000000",
                                "phone_number_id": phone_number_id,
                            },
                            "contacts": [{"profile": {"name": name}, "wa_id": from_phone}],
                            "messages": [message],
                        },
                    }
                ],
            }
        ],
    }


def sign(body: bytes, secret: str = APP_SECRET) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def encode(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload).encode()
