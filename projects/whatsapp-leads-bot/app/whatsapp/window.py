"""WhatsApp's customer-service window: free-form messages are allowed only within 24 hours
of the lead's last inbound message. Outside it, only approved templates may be sent."""

from datetime import UTC, datetime, timedelta

WINDOW = timedelta(hours=24)


def is_window_open(last_inbound_at: datetime | None, now: datetime | None = None) -> bool:
    if last_inbound_at is None:
        return False
    now = now or datetime.now(UTC)
    return now - last_inbound_at < WINDOW
