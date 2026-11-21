"""Facebook / Instagram Lead Ads webhook (the Page's `leadgen` field).

Meta sends only IDs, so for each submission the lead's answers are fetched from the Graph API
with the broker's Page token, then handed to app.intake.leads. Same verification and signature
check as the WhatsApp webhook; 200 straight away, work in the background.
"""

import hmac
import json
import logging
from dataclasses import dataclass
from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse

from app.config import Settings, get_settings
from app.crypto import decrypt_token
from app.db import Broker, Database
from app.intake.leads import IncomingLead, intake_lead
from app.log import add_log_context, bind_context
from app.webhooks.signature import verify_signature
from app.whatsapp.client import WhatsAppClient

log = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks/meta-leads", tags=["meta-leads"])

LEAD_FIELDS = "created_time,field_data,form_id,ad_id,ad_name,campaign_name,platform"
NAME_FIELDS = ("full_name", "name")
PHONE_FIELDS = ("phone_number", "phone", "mobile_number", "whatsapp_number")
# Answers to custom questions that describe what the lead wants; used in the opener if present.
ENQUIRY_FIELDS = ("property", "project", "property_interested_in", "which_property")


@dataclass(frozen=True)
class LeadgenEvent:
    page_id: str
    leadgen_id: str
    form_id: str | None


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
        log.warning("lead ads webhook signature mismatch")
        raise HTTPException(status_code=401)
    try:
        payload = json.loads(body)
    except ValueError:
        raise HTTPException(status_code=400) from None
    background_tasks.add_task(
        process_payload, payload, request.app.state.db, request.app.state.whatsapp
    )
    return {"status": "ok"}


def parse_leadgen(payload: dict[str, Any]) -> list[LeadgenEvent]:
    events = []
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            if change.get("field") != "leadgen":
                continue
            value = change.get("value", {})
            leadgen_id, page_id = value.get("leadgen_id"), value.get("page_id") or entry.get("id")
            if not leadgen_id or not page_id:
                log.warning("skipping malformed leadgen change")
                continue
            events.append(
                LeadgenEvent(
                    page_id=str(page_id),
                    leadgen_id=str(leadgen_id),
                    form_id=str(value["form_id"]) if value.get("form_id") else None,
                )
            )
    return events


async def process_payload(payload: dict[str, Any], db: Database, whatsapp: WhatsAppClient) -> None:
    for event in parse_leadgen(payload):
        with bind_context(leadgen_id=event.leadgen_id, page_id=event.page_id):
            try:
                await handle_leadgen(event, db, whatsapp)
            except Exception:
                log.exception("failed to handle lead form submission")


async def handle_leadgen(event: LeadgenEvent, db: Database, whatsapp: WhatsAppClient) -> None:
    broker = await db.get_broker_by_page_id(event.page_id)
    if broker is None:
        log.warning("no active broker for this Facebook Page")
        return
    add_log_context(broker_id=broker.id)
    token = _leads_token(broker)
    lead = await whatsapp.get(f"/{event.leadgen_id}", token, {"fields": LEAD_FIELDS})
    form_name = await _form_name(whatsapp, token, lead.get("form_id") or event.form_id)
    await intake_lead(db, whatsapp, broker, to_incoming(event.leadgen_id, lead, form_name))


def to_incoming(leadgen_id: str, lead: dict[str, Any], form_name: str | None) -> IncomingLead:
    answers = {
        str(f.get("name", "")).strip(): ", ".join(str(v) for v in f.get("values", []) if v)
        for f in lead.get("field_data", [])
    }
    answers = {k: v for k, v in answers.items() if k and v}
    name = _first(answers, NAME_FIELDS) or " ".join(
        x for x in (answers.get("first_name"), answers.get("last_name")) if x
    )
    phone = _first(answers, PHONE_FIELDS)
    enquiry = _first(answers, ENQUIRY_FIELDS) or form_name

    platform = "Instagram" if lead.get("platform") == "ig" else "Facebook"
    heading = f"{platform} lead form" + (f" '{form_name}'" if form_name else "")
    if lead.get("ad_name"):
        heading += f" (ad: {lead['ad_name']})"
    shown = {k: v for k, v in answers.items() if k not in PHONE_FIELDS}
    lines = [f"- {_label(k)}: {v}" for k, v in shown.items()]
    summary = heading + ":\n" + ("\n".join(lines) if lines else "- (no other answers)")

    detail = " / ".join(x for x in (form_name, lead.get("ad_name")) if x) or None
    return IncomingLead(
        source="meta_ads",
        external_id=leadgen_id,
        kind="lead_form",
        phone=phone,
        name=name or None,
        enquiry=enquiry,
        source_detail=detail,
        summary=summary,
    )


def _leads_token(broker: Broker) -> str:
    """The Page token saved for lead forms, else the broker's WhatsApp (system user) token."""
    return decrypt_token(broker.leads_access_token_enc or broker.access_token_enc)


async def _form_name(whatsapp: WhatsAppClient, token: str, form_id: str | None) -> str | None:
    if not form_id:
        return None
    try:
        form = await whatsapp.get(f"/{form_id}", token, {"fields": "name"})
    except Exception:
        log.warning("could not read the lead form's name")
        return None
    return form.get("name") or None


def _first(answers: dict[str, str], keys: tuple[str, ...]) -> str | None:
    return next((answers[k] for k in keys if answers.get(k)), None)


def _label(field_name: str) -> str:
    text = field_name.replace("_", " ").strip()
    return text[:1].upper() + text[1:]
