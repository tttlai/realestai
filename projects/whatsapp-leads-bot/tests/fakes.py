"""In-memory stand-in for app.db.Database with the same dedupe semantics."""

import hashlib
import hmac
import json
import time
import uuid
from datetime import datetime
from typing import Any

from app.crypto import encrypt_token
from app.db import Broker, Lead

APP_SECRET = "test-app-secret"
PHONE_NUMBER_ID = "123456789012345"
BROKER_TOKEN = "EAAG-test-broker-token"


class FakeDatabase:
    def __init__(self) -> None:
        self.brokers: list[Broker] = []
        self.leads: list[Lead] = []
        self.messages: list[dict[str, Any]] = []

    def add_broker(self, **overrides: Any) -> Broker:
        fields: dict[str, Any] = {
            "id": str(uuid.uuid4()),
            "name": "Test Broker",
            "agency_name": "Test Realty",
            "phone_number_id": PHONE_NUMBER_ID,
            "access_token_enc": encrypt_token(BROKER_TOKEN),
            "alert_number": "919800000000",
        }
        broker = Broker(**(fields | overrides))
        self.brokers.append(broker)
        return broker

    async def get_broker_by_phone_number_id(self, phone_number_id: str) -> Broker | None:
        return next(
            (b for b in self.brokers if b.phone_number_id == phone_number_id and b.active), None
        )

    async def get_or_create_lead(
        self, broker_id: str, phone: str, *, name: str | None, source: str
    ) -> Lead:
        for lead in self.leads:
            if lead.broker_id == broker_id and lead.phone == phone:
                return lead.model_copy()
        lead = Lead(
            id=str(uuid.uuid4()), broker_id=broker_id, phone=phone, name=name, source=source
        )
        self.leads.append(lead)
        return lead.model_copy()

    async def set_last_inbound_at(self, lead_id: str, at: datetime) -> None:
        for lead in self.leads:
            if lead.id == lead_id:
                lead.last_inbound_at = at

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
