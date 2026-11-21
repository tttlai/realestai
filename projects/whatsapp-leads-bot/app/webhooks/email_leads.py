"""Portal enquiry emails, posted by the inbound email provider (Postmark's inbound JSON format).

Brokers forward portal emails to <inbound address>+<their key>@..., so the part after '+'
(Postmark's MailboxHash) says which broker it is for. The provider must authenticate with HTTP
basic auth whose password is INBOUND_EMAIL_SECRET. 200 straight away, work in the background.
"""

import base64
import binascii
import hmac
import json
import logging
import re
from dataclasses import dataclass
from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request

from app.config import Settings, get_settings
from app.db import Database
from app.intake.email_parser import EmailLead, EmailParser, email_text
from app.intake.leads import IncomingLead, intake_lead, record_skipped
from app.log import add_log_context, bind_context
from app.whatsapp.client import WhatsAppClient

log = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks/email-leads", tags=["email-leads"])

SOURCE = "portal_email"
GMAIL_FORWARDING = "forwarding-noreply@google.com"


@dataclass(frozen=True)
class InboundEmail:
    message_id: str
    broker_key: str
    sender: str
    subject: str
    body: str


@router.post("")
async def receive_email(
    request: Request,
    background_tasks: BackgroundTasks,
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, str]:
    if settings.inbound_email_secret is None:
        raise HTTPException(status_code=404)
    if not _password_matches(
        request.headers.get("Authorization"), settings.inbound_email_secret.get_secret_value()
    ):
        log.warning("inbound email rejected: wrong or missing credentials")
        raise HTTPException(status_code=401, headers={"WWW-Authenticate": "Basic"})
    try:
        payload = json.loads(await request.body())
    except ValueError:
        raise HTTPException(status_code=400) from None
    email = parse_postmark(payload)
    if email is None:
        log.warning("inbound email without a message ID or broker key; ignored")
        return {"status": "ignored"}
    background_tasks.add_task(
        process_email,
        email,
        request.app.state.db,
        request.app.state.whatsapp,
        getattr(request.app.state, "email_parser", None),
    )
    return {"status": "ok"}


def parse_postmark(payload: dict[str, Any]) -> InboundEmail | None:
    message_id = payload.get("MessageID") or _header(payload, "Message-ID")
    key = payload.get("MailboxHash") or _plus_part(payload.get("OriginalRecipient") or "")
    if not key:
        for to in payload.get("ToFull") or []:
            key = to.get("MailboxHash") or _plus_part(to.get("Email") or "")
            if key:
                break
    if not message_id or not key:
        return None
    return InboundEmail(
        message_id=str(message_id),
        broker_key=key.strip().lower(),
        sender=str(payload.get("From") or ""),
        subject=str(payload.get("Subject") or ""),
        body=email_text(payload.get("TextBody"), payload.get("HtmlBody")),
    )


async def process_email(
    email: InboundEmail, db: Database, whatsapp: WhatsAppClient, parser: EmailParser | None
) -> None:
    with bind_context(email_message_id=email.message_id):
        try:
            await handle_email(email, db, whatsapp, parser)
        except Exception:
            log.exception("failed to handle inbound email")


async def handle_email(
    email: InboundEmail, db: Database, whatsapp: WhatsAppClient, parser: EmailParser | None
) -> None:
    broker = await db.get_broker_by_email_key(email.broker_key)
    if broker is None:
        log.warning("no active broker for this email address", extra={"key": email.broker_key})
        return
    add_log_context(broker_id=broker.id)

    if GMAIL_FORWARDING in email.sender.lower():
        # Gmail sends a code to confirm a new forwarding address; the broker needs it.
        code = re.search(r"#(\d+)", email.subject)
        log.warning(
            "gmail forwarding confirmation received",
            extra={"confirmation_code": code.group(1) if code else None, "subject": email.subject},
        )
        return
    if await db.intake_event_exists(SOURCE, email.message_id):
        log.info("duplicate email delivery ignored")
        return
    if parser is None:
        log.warning("agent not configured (ANTHROPIC_API_KEY is not set); email not read")
        return

    extracted = await parser.parse(
        sender=email.sender,
        subject=email.subject,
        body=email.body,
        broker_number=broker.alert_number,
    )
    if extracted is None:
        await record_skipped(db, broker, SOURCE, email.message_id, "failed", "could not read email")
        return
    if not extracted.is_lead:
        await record_skipped(db, broker, SOURCE, email.message_id, "skipped_not_a_lead")
        log.info("email is not an enquiry; skipped")
        return
    await intake_lead(db, whatsapp, broker, to_incoming(email, extracted))


def to_incoming(email: InboundEmail, lead: EmailLead) -> IncomingLead:
    heading = f"Enquiry via {lead.portal or 'email'}"
    if lead.property:
        heading += f" about {lead.property}"
    lines = [
        f"- {label}: {value}"
        for label, value in (
            ("Name", lead.name),
            ("Email", lead.email),
            ("Their message", lead.message),
        )
        if value
    ]
    return IncomingLead(
        source=SOURCE,
        external_id=email.message_id,
        kind="email",
        phone=lead.phone,
        name=lead.name,
        enquiry=lead.property,
        source_detail=lead.portal,
        summary=heading + (":\n" + "\n".join(lines) if lines else ""),
    )


def _password_matches(authorization: str | None, secret: str) -> bool:
    if not authorization or not authorization.lower().startswith("basic "):
        return False
    try:
        decoded = base64.b64decode(authorization[6:].strip()).decode()
    except (binascii.Error, UnicodeDecodeError):
        return False
    password = decoded.partition(":")[2]
    return hmac.compare_digest(password.encode(), secret.encode())


def _plus_part(address: str) -> str:
    local = address.split("@", 1)[0]
    return local.split("+", 1)[1] if "+" in local else ""


def _header(payload: dict[str, Any], name: str) -> str | None:
    for h in payload.get("Headers") or []:
        if str(h.get("Name", "")).lower() == name.lower():
            return str(h.get("Value"))
    return None
