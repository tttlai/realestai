import json
from pathlib import Path

import pydantic
import pytest

from app.db import Database
from scripts import seed_properties
from tests.fakes import PHONE_NUMBER_ID, FakeDatabase


def test_sample_file_is_valid() -> None:
    rows = seed_properties.load_rows(seed_properties.SAMPLE_FILE)
    assert len(rows) == 10
    assert all(r["status"] == "available" for r in rows)


@pytest.mark.parametrize(
    "item",
    [
        {"title": "A", "area": "Wakad", "price_min": 10, "price_max": 5},
        {"title": "A", "area": "Wakad", "type": "lease"},
        {"title": "A", "area": "Wakad", "colour": "blue"},
        {"title": "A"},
    ],
)
def test_bad_listings_are_rejected(tmp_path: Path, item: dict[str, object]) -> None:
    path = tmp_path / "listings.json"
    path.write_text(json.dumps([item]))
    with pytest.raises(pydantic.ValidationError):
        seed_properties.load_rows(path)


@pytest.fixture
def db(monkeypatch: pytest.MonkeyPatch) -> FakeDatabase:
    fake = FakeDatabase()
    fake.add_broker()

    async def connect(settings: object) -> FakeDatabase:
        return fake

    monkeypatch.setattr(Database, "connect", connect)
    return fake


async def test_loads_listings_for_the_broker(db: FakeDatabase) -> None:
    await seed_properties.main(["--phone-number-id", PHONE_NUMBER_ID])
    assert len(db.properties) == 10
    assert {p.broker_id for p in db.properties} == {db.brokers[0].id}


async def test_existing_listings_need_replace(db: FakeDatabase) -> None:
    db.add_property(db.brokers[0].id, title="Keep me", area="Baner")
    with pytest.raises(SystemExit, match="--replace"):
        await seed_properties.main(["--phone-number-id", PHONE_NUMBER_ID])
    assert [p.title for p in db.properties] == ["Keep me"]

    await seed_properties.main(["--phone-number-id", PHONE_NUMBER_ID, "--replace"])
    assert "Keep me" not in {p.title for p in db.properties}
    assert len(db.properties) == 10


async def test_unknown_broker_is_an_error(db: FakeDatabase) -> None:
    with pytest.raises(SystemExit, match="no active broker"):
        await seed_properties.main(["--phone-number-id", "999"])
