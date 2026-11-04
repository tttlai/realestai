from typing import Any

import pytest

from app.crypto import decrypt_token
from app.db import Broker, Database
from scripts import seed_broker

ARGS = ["--name", "Ravi", "--phone-number-id", "123", "--alert-number", "+91 98765 43210"]


def test_build_row_encrypts_token_and_normalises_alert_number() -> None:
    row = seed_broker.build_row(seed_broker.parse_args(ARGS), "EAAG-token")
    assert "EAAG-token" not in str(row)
    assert decrypt_token(row["access_token_enc"]) == "EAAG-token"
    assert row["alert_number"] == "919876543210"
    assert row["timezone"] == "Asia/Kolkata"
    assert "agency_name" not in row and "waba_id" not in row


async def test_main_upserts_with_token_from_env(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    saved: list[dict[str, Any]] = []

    class StubDatabase:
        async def upsert_broker(self, row: dict[str, Any]) -> Broker:
            saved.append(row)
            return Broker(id="b1", **{k: v for k, v in row.items() if k != "active"})

    async def connect(settings: object) -> StubDatabase:
        return StubDatabase()

    monkeypatch.setenv("BROKER_ACCESS_TOKEN", "  EAAG-token  ")
    monkeypatch.setattr(Database, "connect", connect)
    await seed_broker.main([*ARGS, "--agency-name", "Ravi Realty"])

    [row] = saved
    assert decrypt_token(row["access_token_enc"]) == "EAAG-token"
    assert row["agency_name"] == "Ravi Realty"
    out = capsys.readouterr().out
    assert "b1" in out and "EAAG" not in out
