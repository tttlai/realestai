"""WhatsApp webhook: Meta verification (GET) and inbound messages (POST).

POST checks the signature, returns 200 straight away and handles messages in the background.
Each message is stored once (Meta retries are dropped on the WhatsApp message ID), then the agent
writes the reply. One lead's messages are answered one at a time, so a quick second message
waits for the first reply and is answered with it in the history. Failed delivery updates are
logged, because Meta can accept a message and only report later that it could not be delivered.
"""

import asyncio
import hmac
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated, Any
from weakref import WeakValueDictionary

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse

from app.agent.run import Agent
from app.alerts import alert_broker
from app.config import Settings, get_settings
from app.crypto import decrypt_token
from app.db import Database
from app.intake.normalise import normalise_wa_id
from app.log import add_log_context, bind_context
from app.webhooks.signature import verify_signature
from app.whatsapp.client import WhatsAppClient
from app.whatsapp.window import is_window_open

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


@dataclass(frozen=True)
class FailedDelivery:
    phone_number_id: str
    wa_message_id: str | None
    error_code: int | None
    error_title: str | None
    error_details: str | None


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
        process_payload,
        payload,
        request.app.state.db,
        request.app.state.whatsapp,
        getattr(request.app.state, "agent", None),
    )
    return {"status": "ok"}


def parse_messages(payload: dict[str, Any]) -> list[InboundMessage]:
    """Pull inbound messages out of a webhook payload."""
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


def parse_failed_deliveries(payload: dict[str, Any]) -> list[FailedDelivery]:
    """Pull failed delivery updates out of a webhook payload, one per reported error."""
    failures: list[FailedDelivery] = []
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            if change.get("field") != "messages":
                continue
            value = change.get("value", {})
            phone_number_id = value.get("metadata", {}).get("phone_number_id")
            for status in value.get("statuses", []):
                if status.get("status") != "failed":
                    continue
                for error in status.get("errors") or [{}]:
                    failures.append(
                        FailedDelivery(
                            phone_number_id=phone_number_id,
                            wa_message_id=status.get("id"),
                            error_code=error.get("code"),
                            error_title=error.get("title"),
                            error_details=error.get("error_data", {}).get("details"),
                        )
                    )
    return failures


async def process_payload(
    payload: dict[str, Any], db: Database, whatsapp: WhatsAppClient, agent: Agent | None
) -> None:
    for message in parse_messages(payload):
        with bind_context(wa_message_id=message.wa_message_id):
            try:
                await handle_message(message, db, whatsapp, agent)
            except Exception:
                log.exception("failed to handle inbound message")

    for failure in parse_failed_deliveries(payload):
        with bind_context(
            phone_number_id=failure.phone_number_id,
            wa_message_id=failure.wa_message_id,
            error_code=failure.error_code,
            error_title=failure.error_title,
            error_details=failure.error_details,
        ):
            try:
                await log_failed_delivery(failure, db)
            except Exception:
                log.exception("failed to process delivery failure")


async def log_failed_delivery(failure: FailedDelivery, db: Database) -> None:
    """Log the failure, and mark it on the alert if it was one. The recipient's number is left
    out of the log; wa_message_id identifies the message."""
    broker = await db.get_broker_by_phone_number_id(failure.phone_number_id)
    if broker is not None:
        add_log_context(broker_id=broker.id)
    log.warning("outbound message failed")
    if failure.wa_message_id is not None:
        detail = f"not delivered: code={failure.error_code} {failure.error_title or ''}".strip()
        await db.mark_alert_failed(failure.wa_message_id, detail)


async def handle_message(
    message: InboundMessage, db: Database, whatsapp: WhatsAppClient, agent: Agent | None
) -> None:
    broker = await db.get_broker_by_phone_number_id(message.phone_number_id)
    if broker is None:
        log.warning(
            "no active broker for phone_number_id",
            extra={"phone_number_id": message.phone_number_id},
        )
        return
    add_log_context(broker_id=broker.id)

    phone = normalise_wa_id(message.from_phone)
    if phone == broker.alert_number:
        # The broker replying to an alert. Treating them as a lead would have the agent try to
        # sell them their own listings.
        await db.insert_broker_message(
            broker_id=broker.id,
            lead_id=None,
            direction="inbound",
            kind=message.type,
            body=message.text,
            status="received",
            wa_message_id=message.wa_message_id,
        )
        log.info("message from the broker's alert number stored; not answered")
        return
    lead = await db.get_or_create_lead(
        broker.id, phone, name=message.profile_name, source="whatsapp"
    )
    add_log_context(lead_id=lead.id)

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
    if message.type != "text":
        log.info("non-text message stored; not answered yet")
        return
    if agent is None:
        log.warning("agent not configured (ANTHROPIC_API_KEY is not set); not replying")
        return
    if not is_window_open(lead.last_inbound_at):
        log.info("message is older than the 24-hour window; not replying")
        return

    async with _lead_lock(lead.id):
        # Re-read: a reply that finished while this one waited may have changed the lead.
        lead = await db.get_lead(lead.id) or lead
        if lead.opted_out:
            log.info("lead has opted out; not replying")
            return
        result = await agent.reply(broker, lead)
        if result.text is None:
            return
        try:
            wa_message_id = await whatsapp.send_text(
                phone_number_id=broker.phone_number_id,
                access_token=decrypt_token(broker.access_token_enc),
                to=lead.phone,
                body=result.text,
                last_inbound_at=lead.last_inbound_at,
            )
            await db.insert_message(
                lead_id=lead.id,
                direction="outbound",
                kind="text",
                body=result.text,
                wa_message_id=wa_message_id,
            )
            log.info("reply sent")
        finally:
            # After the lead's reply, so it never waits, and even if that reply failed to send:
            # that is when the broker most needs to know.
            if result.handoff is not None:
                await alert_broker(db, whatsapp, broker, result.lead, result.handoff)


_locks: WeakValueDictionary[str, asyncio.Lock] = WeakValueDictionary()


def _lead_lock(lead_id: str) -> asyncio.Lock:
    lock = _locks.get(lead_id)
    if lock is None:
        lock = asyncio.Lock()
        _locks[lead_id] = lock
    return lock
