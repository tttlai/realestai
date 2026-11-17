import pytest

from app.listings.model import ListingIn
from app.listings.sync import REMOVED, EmptySourceError, sync_listings
from tests.fakes import FakeDatabase


def listing(external_id: str, **fields: object) -> ListingIn:
    base = {"id": external_id, "title": f"Flat {external_id}", "area": "Wakad"}
    return ListingIn.model_validate(base | fields)


@pytest.fixture
def db() -> FakeDatabase:
    fake = FakeDatabase()
    fake.add_broker(access_token_enc="unused")
    return fake


def by_external_id(db: FakeDatabase) -> dict[str | None, tuple[str, str]]:
    return {p.external_id: (p.title, p.status) for p in db.properties}


async def test_first_sync_adds_everything(db: FakeDatabase) -> None:
    broker_id = db.brokers[0].id
    result = await sync_listings(db, broker_id, [listing("P1"), listing("P2")])
    assert (result.added, result.updated, result.removed) == (2, 0, 0)
    assert str(result) == "2 added, 0 updated, 0 removed"
    assert by_external_id(db) == {"P1": ("Flat P1", "available"), "P2": ("Flat P2", "available")}


async def test_resync_updates_in_place_and_marks_missing_removed(db: FakeDatabase) -> None:
    broker_id = db.brokers[0].id
    await sync_listings(db, broker_id, [listing("P1"), listing("P2", notes="corner flat")])
    ids_before = {p.external_id: p.id for p in db.properties}

    result = await sync_listings(db, broker_id, [listing("P1", title="Renamed", status="sold")])

    assert (result.added, result.updated, result.removed) == (0, 1, 1)
    assert by_external_id(db) == {"P1": ("Renamed", "sold"), "P2": ("Flat P2", REMOVED)}
    assert {p.external_id: p.id for p in db.properties} == ids_before  # rows kept, not replaced

    # Back in the source: available again, same row.
    result = await sync_listings(db, broker_id, [listing("P1"), listing("P2")])
    assert (result.added, result.updated, result.removed) == (0, 2, 0)
    assert by_external_id(db)["P2"] == ("Flat P2", "available")
    assert {p.external_id: p.id for p in db.properties} == ids_before


async def test_cleared_cells_are_cleared(db: FakeDatabase) -> None:
    broker_id = db.brokers[0].id
    await sync_listings(db, broker_id, [listing("P1", notes="corner flat", bhk="2 BHK")])
    await sync_listings(db, broker_id, [listing("P1")])
    [prop] = db.properties
    assert (prop.notes, prop.bhk) == (None, None)


async def test_unreadable_rows_keep_their_current_values(db: FakeDatabase) -> None:
    broker_id = db.brokers[0].id
    await sync_listings(db, broker_id, [listing("P1"), listing("P2")])
    result = await sync_listings(
        db, broker_id, [listing("P1")], unreadable_ids=["P2"], errors=["row 3 (id P2): bad"]
    )
    assert result.removed == 0
    assert result.errors == ["row 3 (id P2): bad"]
    assert str(result).endswith("1 row(s) skipped")
    assert by_external_id(db)["P2"] == ("Flat P2", "available")


async def test_listings_without_an_id_are_retired(db: FakeDatabase) -> None:
    broker_id = db.brokers[0].id
    db.add_property(broker_id, title="Loaded before ids existed", area="Baner")
    result = await sync_listings(db, broker_id, [listing("P1")])
    assert result.removed == 1
    assert by_external_id(db)[None] == ("Loaded before ids existed", REMOVED)


async def test_empty_source_changes_nothing_unless_allowed(db: FakeDatabase) -> None:
    broker_id = db.brokers[0].id
    await sync_listings(db, broker_id, [listing("P1")])
    with pytest.raises(EmptySourceError):
        await sync_listings(db, broker_id, [])
    assert by_external_id(db)["P1"][1] == "available"

    result = await sync_listings(db, broker_id, [], allow_empty=True)
    assert result.removed == 1


async def test_other_brokers_are_untouched(db: FakeDatabase) -> None:
    other = db.add_broker(phone_number_id="999", access_token_enc="unused")
    await sync_listings(db, other.id, [listing("P1")])
    await sync_listings(db, db.brokers[0].id, [listing("P9")])
    assert [(p.broker_id, p.status) for p in db.properties if p.external_id == "P1"] == [
        (other.id, "available")
    ]


@pytest.mark.parametrize(
    ("fields", "message"),
    [
        ({"type": "sale", "price_min": 85}, "looks too low"),
        ({"type": "rent", "price_min": 500}, "looks too low"),
        ({"price_min": 9_500_000, "price_max": 8_500_000}, "above price_max"),
        ({"colour": "blue"}, "Extra inputs"),
    ],
)
def test_listing_validation(fields: dict[str, object], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        listing("P1", **fields)
