"""Turn a lead from a form or an email into a lead row and a WhatsApp opener.

Every submission is recorded in intake_events first, keyed on the source's own ID, so retries
from Meta or the email provider are handled once. What came in is stored as the lead's first
message, so when they reply the agent knows what they enquired about. The opener is a template,
because the lead hasn't messaged the broker yet.
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.crypto import decrypt_token
from app.db import Broker, Database
from app.intake.normalise import InvalidPhoneError, normalise_phone
from app.log import add_log_context
from app.whatsapp.client import WhatsAppClient, WhatsAppError
from app.whatsapp.templates import LEAD_OPENER, lead_opener_params
from app.whatsapp.window import is_window_open

log = logging.getLogger(__name__)

# One opener per lead per day, however many forms or portal emails they trigger.
OPENER_COOLDOWN = timedelta(hours=24)
MAX_DETAIL_CHARS = 500


@dataclass(frozen=True)
class IncomingLead:
    source: str  # meta_ads / portal_email
    external_id: str  # leadgen_id / email Message-ID
    kind: str  # how it is stored in messages: lead_form / email
    phone: str | None  # as typed by the lead
    name: str | None
    enquiry: str | None  # what they asked about, used in the opener ("Skyline Residency 2 BHK")
    source_detail: str | None  # form or portal name, saved on a new lead
    summary: str  # everything the agent should know, stored as the lead's first message


async def intake_lead(
    db: Database, whatsapp: WhatsAppClient, broker: Broker, incoming: IncomingLead
) -> str:
    """Handle one incoming lead and return what happened (the intake_events status)."""
    if not await db.start_intake_event(broker.id, incoming.source, incoming.external_id):
        log.info("duplicate lead delivery ignored")
        return "duplicate"
    lead_id: str | None = None
    try:
        status, lead_id, detail = await _intake(db, whatsapp, broker, incoming)
    except Exception as e:
        await db.finish_intake_event(
            incoming.source,
            incoming.external_id,
            status="failed",
            lead_id=lead_id,
            detail=describe_error(e),
        )
        raise
    await db.finish_intake_event(
        incoming.source, incoming.external_id, status=status, lead_id=lead_id, detail=detail
    )
    log.info("lead intake finished", extra={"status": status})
    return status


async def _intake(
    db: Database, whatsapp: WhatsAppClient, broker: Broker, incoming: IncomingLead
) -> tuple[str, str | None, str | None]:
    if not incoming.phone:
        return "skipped_no_phone", None, "no phone number in the lead"
    try:
        phone = normalise_phone(incoming.phone)
    except InvalidPhoneError:
        return "skipped_bad_phone", None, "phone number could not be read"

    lead = await db.get_or_create_lead(
        broker.id,
        phone,
        name=incoming.name,
        source=incoming.source,
        source_detail=incoming.source_detail,
    )
    add_log_context(lead_id=lead.id)
    await db.insert_message(
        lead_id=lead.id,
        direction="inbound",
        kind=incoming.kind,
        body=incoming.summary,
        wa_message_id=None,
    )

    if lead.opted_out:
        return "skipped_opted_out", lead.id, None
    if is_window_open(lead.last_inbound_at):
        # Already chatting on WhatsApp: the agent sees this enquiry with their next message.
        return "skipped_in_conversation", lead.id, None
    if await db.opener_sent_since(lead.id, datetime.now(UTC) - OPENER_COOLDOWN):
        return "skipped_recent_opener", lead.id, None

    params = lead_opener_params(
        incoming.name or lead.name, incoming.enquiry, broker.agency_name or broker.name
    )
    wa_message_id = await whatsapp.send_template(
        phone_number_id=broker.phone_number_id,
        access_token=decrypt_token(broker.access_token_enc),
        to=lead.phone,
        name=LEAD_OPENER.name,
        language=LEAD_OPENER.language,
        body_params=params,
    )
    await db.insert_message(
        lead_id=lead.id,
        direction="outbound",
        kind="template",
        body=LEAD_OPENER.render(params),
        wa_message_id=wa_message_id,
    )
    return "opener_sent", lead.id, None


async def record_skipped(
    db: Database,
    broker_id: str | None,
    source: str,
    external_id: str,
    status: str,
    detail: str | None = None,
) -> None:
    """Record something that arrived but won't get an opener: not a lead, or it failed before
    a lead could be made (unknown Page or address, lead unreadable). `broker_id` is None when no
    broker matched."""
    if await db.start_intake_event(broker_id, source, external_id):
        await db.finish_intake_event(
            source, external_id, status=status, detail=_cap(detail) if detail else None
        )


def describe_error(error: Exception) -> str:
    """What to store in intake_events.detail. Meta's errors say what to fix (code and message,
    never the token); other errors only by type, since their text may echo lead data."""
    if isinstance(error, WhatsAppError):
        return _cap(str(error))
    return type(error).__name__


def _cap(text: str) -> str:
    return text if len(text) <= MAX_DETAIL_CHARS else text[: MAX_DETAIL_CHARS - 1] + "…"
