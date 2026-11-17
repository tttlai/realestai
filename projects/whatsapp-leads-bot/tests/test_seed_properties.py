import json
from pathlib import Path

import pydantic
import pytest

from app.db import Database
from scripts import seed_properties
from tests.fakes import PHONE_NUMBER_ID, FakeDatabase


def test_sample_file_is_valid() -> None:
    listings = seed_properties.load_listings(seed_properties.SAMPLE_FILE)
    assert len(listings) == 10
    assert len({lst.external_id for lst in listings}) == 10


@pytest.mark.parametrize(
    "item",
    [
        {"id": "1", "title": "A", "area": "Wakad", "price_min": 10_000_000, "price_max": 5},
        {"id": "1", "title": "A", "area": "Wakad", "type": "lease"},
        {"id": "1", "title": "A", "area": "Wakad", "colour": "blue"},
        {"title": "A", "area": "Wakad"},
    ],
)
def test_bad_listings_are_rejected(tmp_path: Path, item: dict[str, object]) -> None:
    path = tmp_path / "listings.json"
    path.write_text(json.dumps([item]))
    with pytest.raises(pydantic.ValidationError):
        seed_properties.load_listings(path)


def test_duplicate_ids_are_rejected(tmp_path: Path) -> None:
    path = tmp_path / "listings.json"
    item = {"id": "P1", "title": "A", "area": "Wakad"}
    path.write_text(json.dumps([item, item]))
    with pytest.raises(SystemExit, match="P1"):
        seed_properties.load_listings(path)


@pytest.fixture
def db(monkeypatch: pytest.MonkeyPatch) -> FakeDatabase:
    fake = FakeDatabase()
    fake.add_broker()

    async def connect(settings: object) -> FakeDatabase:
        return fake

    monkeypatch.setattr(Database, "connect", connect)
    return fake


async def test_loads_listings_and_rerunning_updates_in_place(
    db: FakeDatabase, capsys: pytest.CaptureFixture[str]
) -> None:
    await seed_properties.main(["--phone-number-id", PHONE_NUMBER_ID])
    assert len(db.properties) == 10
    ids = {p.id for p in db.properties}

    await seed_properties.main(["--phone-number-id", PHONE_NUMBER_ID])
    assert {p.id for p in db.properties} == ids
    assert "0 added, 10 updated, 0 removed" in capsys.readouterr().out


async def test_listings_not_in_the_file_are_marked_removed(db: FakeDatabase) -> None:
    db.add_property(db.brokers[0].id, title="Old upload", area="Baner")
    await seed_properties.main(["--phone-number-id", PHONE_NUMBER_ID])
    old = next(p for p in db.properties if p.title == "Old upload")
    assert old.status == "removed"


async def test_empty_file_needs_allow_empty(db: FakeDatabase, tmp_path: Path) -> None:
    await seed_properties.main(["--phone-number-id", PHONE_NUMBER_ID])
    empty = tmp_path / "empty.json"
    empty.write_text("[]")
    with pytest.raises(SystemExit, match="allow-empty"):
        await seed_properties.main(["--phone-number-id", PHONE_NUMBER_ID, "--file", str(empty)])


async def test_unknown_broker_is_an_error(db: FakeDatabase) -> None:
    with pytest.raises(SystemExit, match="no active broker"):
        await seed_properties.main(["--phone-number-id", "999"])
