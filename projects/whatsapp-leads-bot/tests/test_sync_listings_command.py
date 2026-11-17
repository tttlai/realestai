"""The `python -m app.sync_listings` command, with Google and the database faked."""

import pytest
import respx

from app import sync_listings
from app.db import Database
from tests.fakes import PHONE_NUMBER_ID, FakeDatabase

SHEET_ID = "1AbCdEfGhIjKlMnOpQrStUvWxYz0123456789"
SHEET_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit#gid=0"
EXPORT_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid=0"
CSV = "id,title,area,type,price\nP1,Skyline,Wakad,sale,85-95 L\nP2,Bad,Wakad,sale,85\n"


@pytest.fixture
def db(monkeypatch: pytest.MonkeyPatch) -> FakeDatabase:
    fake = FakeDatabase()
    fake.add_broker()

    async def connect(settings: object) -> FakeDatabase:
        return fake

    monkeypatch.setattr(Database, "connect", connect)
    return fake


@pytest.fixture
def google() -> respx.MockRouter:
    with respx.mock(assert_all_called=False) as router:
        router.get(EXPORT_URL).respond(200, text=CSV, headers={"content-type": "text/csv"})
        yield router


async def test_saves_the_sheet_and_syncs_one_broker(
    db: FakeDatabase, google: respx.MockRouter, capsys: pytest.CaptureFixture[str]
) -> None:
    code = await sync_listings.main(["--phone-number-id", PHONE_NUMBER_ID, "--sheet", SHEET_URL])

    assert code == 0
    assert db.brokers[0].listings_sheet_url == SHEET_URL
    assert [(p.external_id, p.price_min) for p in db.properties] == [("P1", 8_500_000)]
    out = capsys.readouterr().out
    assert "Test Broker: 1 added, 0 updated, 0 removed, 1 row(s) skipped" in out
    assert "skipped row 3 (id P2): price 85 looks too low" in out


async def test_no_arguments_syncs_every_broker_with_a_sheet(
    db: FakeDatabase, google: respx.MockRouter, capsys: pytest.CaptureFixture[str]
) -> None:
    db.brokers[0] = db.brokers[0].model_copy(update={"listings_sheet_url": SHEET_URL})
    db.add_broker(phone_number_id="999", name="No Sheet")
    assert await sync_listings.main([]) == 0
    out = capsys.readouterr().out
    assert "Test Broker: 1 added" in out
    assert "No Sheet" not in out


async def test_unshared_sheet_fails_without_changing_listings(
    db: FakeDatabase, google: respx.MockRouter, capsys: pytest.CaptureFixture[str]
) -> None:
    google.get(EXPORT_URL).respond(200, text="<html>", headers={"content-type": "text/html"})
    db.add_property(db.brokers[0].id, title="Keep", area="Baner", external_id="K1")
    code = await sync_listings.main(["--phone-number-id", PHONE_NUMBER_ID, "--sheet", SHEET_URL])
    assert code == 1
    assert "isn't shared" in capsys.readouterr().out
    assert [p.status for p in db.properties] == ["available"]


async def test_broker_without_a_sheet(db: FakeDatabase, capsys: pytest.CaptureFixture[str]) -> None:
    assert await sync_listings.main(["--phone-number-id", PHONE_NUMBER_ID]) == 1
    assert "has no listings sheet" in capsys.readouterr().out


async def test_unknown_broker(db: FakeDatabase, capsys: pytest.CaptureFixture[str]) -> None:
    assert await sync_listings.main(["--phone-number-id", "999"]) == 1
    assert "No active broker" in capsys.readouterr().out
