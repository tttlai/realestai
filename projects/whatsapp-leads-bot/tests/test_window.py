from datetime import UTC, datetime, timedelta

from app.whatsapp.window import is_window_open

NOW = datetime(2026, 10, 19, 12, 0, tzinfo=UTC)


def test_closed_when_lead_never_messaged() -> None:
    assert not is_window_open(None, NOW)


def test_open_within_24_hours() -> None:
    assert is_window_open(NOW - timedelta(minutes=1), NOW)
    assert is_window_open(NOW - timedelta(hours=23, minutes=59, seconds=59), NOW)


def test_closed_at_and_after_24_hours() -> None:
    assert not is_window_open(NOW - timedelta(hours=24), NOW)
    assert not is_window_open(NOW - timedelta(days=3), NOW)


def test_defaults_to_current_time() -> None:
    assert is_window_open(datetime.now(UTC) - timedelta(hours=1))
    assert not is_window_open(datetime.now(UTC) - timedelta(hours=25))
