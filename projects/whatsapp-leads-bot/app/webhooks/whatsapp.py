"""WhatsApp webhook: Meta verification (GET) and inbound messages (POST).

POST checks the signature, returns 200 straight away and handles messages in the background.
Each message is stored once (Meta retries are dropped on the WhatsApp message ID), then replied
to. Phase 1 replies by echoing the text back.
"""

import hmac
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse

from app.config import Settings, get_settings
from app.crypto import decrypt_token
from app.db import Broker, Database, Lead
from app.intake.normalise import normalise_phone
from app.log import bind_context
from app.webhooks.signature import verify_signature
from app.whatsapp.client import WhatsAppClient

log = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks/whatsapp", tags=["whatsapp"])


@dataclass(frozen=True)
class InboundMessage:
    phone_number_id: str
    wa_message_id: str
    from_phone: str
    profile_name: str | None
    timestamp: datetime
    type: str
    text: str | None


@router.get("")
async def verify_webhook(
    settings: Annotated[Settings, Depends(get_settings)],
    mode: Annotated[str | None, Query(alias="hub.mode")] = None,
    token: Annotated[str | None, Query(alias="hub.verify_token")] = None,
    challenge: Annotated[str | None, Query(alias="hub.challenge")] = None,
) -> PlainTextResponse:
    expected = settings.meta_verify_token.get_secret_value()
    if (
        mode == "subscribe"
        and token is not None
        and challenge is not None
        and hmac.compare_digest(token.encode(), expected.encode())
    ):
        return PlainTextResponse(challenge)
    raise HTTPException(status_code=403)


@router.post("")
async def receive_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, str]:
    body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256")
    if not verify_signature(body, signature, settings.meta_app_secret.get_secret_value()):
        log.warning("whatsapp webhook signature mismatch")
        raise HTTPException(status_code=401)
    try:
        payload = json.loads(body)
    except ValueError:
        raise HTTPException(status_code=400) from None
    background_tasks.add_task(
        process_payload, payload, request.app.state.db, request.app.state.whatsapp
    )
    return {"status": "ok"}


def parse_messages(payload: dict[str, Any]) -> list[InboundMessage]:
    """Pull inbound messages out of a webhook payload. Status updates are ignored."""
    messages: list[InboundMessage] = []
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            if change.get("field") != "messages":
                continue
            value = change.get("value", {})
            phone_number_id = value.get("metadata", {}).get("phone_number_id")
            names = {
                c.get("wa_id"): c.get("profile", {}).get("name") for c in value.get("contacts", [])
            }
            for m in value.get("messages", []):
                try:
                    messages.append(
                        InboundMessage(
                            phone_number_id=phone_number_id,
                            wa_message_id=m["id"],
                            from_phone=m["from"],
                            profile_name=names.get(m["from"]),
                            timestamp=datetime.fromtimestamp(int(m["timestamp"]), UTC),
                            type=m.get("type", "unknown"),
                            text=m.get("text", {}).get("body") if m.get("type") == "text" else None,
                        )
                    )
                except (KeyError, TypeError, ValueError):
                    log.warning("skipping malformed message in webhook payload")
    return messages


async def process_payload(payload: dict[str, Any], db: Database, whatsapp: WhatsAppClient) -> None:
    for message in parse_messages(payload):
        with bind_context(wa_message_id=message.wa_message_id):
            try:
                await handle_message(message, db, whatsapp)
            except Exception:
                log.exception("failed to handle inbound message")


async def handle_message(message: InboundMessage, db: Database, whatsapp: WhatsAppClient) -> None:
    broker = await db.get_broker_by_phone_number_id(message.phone_number_id)
    if broker is None:
        log.warning(
            "no active broker for phone_number_id",
            extra={"phone_number_id": message.phone_number_id},
        )
        return
    with bind_context(broker_id=broker.id):
        phone = normalise_phone(message.from_phone)
        lead = await db.get_or_create_lead(
            broker.id, phone, name=message.profile_name, source="whatsapp"
        )
        with bind_context(lead_id=lead.id):
            await _handle_for_lead(message, broker, lead, db, whatsapp)


async def _handle_for_lead(
    message: InboundMessage, broker: Broker, lead: Lead, db: Database, whatsapp: WhatsAppClient
) -> None:
    stored = await db.insert_message(
        lead_id=lead.id,
        direction="inbound",
        kind=message.type,
        body=message.text,
        wa_message_id=message.wa_message_id,
    )
    if not stored:
        log.info("duplicate delivery ignored")
        return
    log.info("inbound message stored", extra={"kind": message.type})

    if lead.last_inbound_at is None or message.timestamp > lead.last_inbound_at:
        await db.set_last_inbound_at(lead.id, message.timestamp)
        lead.last_inbound_at = message.timestamp

    if lead.opted_out:
        log.info("lead has opted out; not replying")
        return

    reply = echo_reply(message)
    if reply is None:
        return

    wa_message_id = await whatsapp.send_text(
        phone_number_id=broker.phone_number_id,
        access_token=decrypt_token(broker.access_token_enc),
        to=lead.phone,
        body=reply,
        last_inbound_at=lead.last_inbound_at,
    )
    await db.insert_message(
        lead_id=lead.id,
        direction="outbound",
        kind="text",
        body=reply,
        wa_message_id=wa_message_id,
    )
    log.info("reply sent")


def echo_reply(message: InboundMessage) -> str | None:
    """Phase 1: send text back unchanged. Replaced by the agent in phase 2."""
    return message.text
