"""WhatsApp alerts to the broker when a lead is handed over.

Alerts are templates, because brokers rarely message the bot and so are outside the 24-hour
window. Every alert is recorded in broker_messages, including ones that failed or were skipped.
Alerting never gets in the way of the lead's own reply: problems are recorded and logged, not
raised.
"""

import logging
from datetime import UTC, datetime, timedelta

from app.agent.handlers import ASSISTANT_FAILED, Handoff
from app.crypto import decrypt_token
from app.db import Broker, Database, Lead
from app.intake.leads import describe_error
from app.whatsapp.client import WhatsAppClient
from app.whatsapp.templates import HOT_LEAD_ALERT, LEAD_NEEDS_REPLY, broker_alert_params

log = logging.getLogger(__name__)

ALERT_PERIOD = timedelta(hours=24)
# Per lead and reason. Enough for real changes (a new visit time) without a chatty lead flooding
# the broker, and counted per reason so earlier questions never block a hot-lead alert.
MAX_ALERTS = 3
# An outage fails every message a lead sends; the broker needs to hear about it once.
MAX_FAILURE_ALERTS = 1


async def alert_broker(
    db: Database, whatsapp: WhatsAppClient, broker: Broker, lead: Lead, handoff: Handoff
) -> str:
    """Tell the broker about a handed-over lead. Returns sent / skipped / failed; never raises."""
    template = HOT_LEAD_ALERT if handoff.reason == "hot_lead" else LEAD_NEEDS_REPLY
    params = broker_alert_params(lead.name, lead.phone, handoff.summary)
    status, wa_message_id, detail = "sent", None, None
    try:
        if skip := await _skip_reason(db, lead, handoff):
            status, detail = "skipped", skip
        else:
            wa_message_id = await whatsapp.send_template(
                phone_number_id=broker.phone_number_id,
                access_token=decrypt_token(broker.access_token_enc),
                to=broker.alert_number,
                name=template.name,
                language=template.language,
                body_params=params,
            )
    except Exception as e:
        log.exception("broker alert failed")
        status, detail = "failed", describe_error(e)
    try:
        await db.insert_broker_message(
            broker_id=broker.id,
            lead_id=lead.id,
            direction="outbound",
            kind="template",
            body=template.render(params),
            status=status,
            reason=handoff.reason,
            wa_message_id=wa_message_id,
            detail=detail,
        )
    except Exception:
        log.exception("broker alert could not be recorded")
    log.info("broker alert finished", extra={"status": status, "reason": handoff.reason})
    return status


async def _skip_reason(db: Database, lead: Lead, handoff: Handoff) -> str | None:
    if lead.opted_out:
        return "the lead opted out"
    limit = MAX_FAILURE_ALERTS if handoff.reason == ASSISTANT_FAILED else MAX_ALERTS
    since = datetime.now(UTC) - ALERT_PERIOD
    if await db.count_alerts_sent(lead.id, since, reason=handoff.reason) >= limit:
        return f"{limit} alert(s) for this reason already sent in the last 24 hours"
    return None
