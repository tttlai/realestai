"""Load a broker's listings from a JSON file. The agent quotes only what is listed.

    uv run python -m scripts.seed_properties --phone-number-id 123456789012345
    uv run python -m scripts.seed_properties --phone-number-id 123456789012345 \\
        --file my_listings.json

For brokers who keep listings in a Google Sheet, use `python -m app.sync_listings` instead.

The file is a list of objects with: id (unique, stays the same for a listing), title, area,
and optionally bhk, type ("sale" or "rent"), price_min and price_max (rupees; monthly rent for
rentals), status ("available", "sold", "on_hold") and notes. See scripts/sample_properties.json.

The file is the broker's full list: listings in it are added or updated by id, and the broker's
other listings are marked 'removed' (never deleted).
"""

import argparse
import asyncio
import json
from pathlib import Path

from pydantic import TypeAdapter

from app.config import get_settings
from app.db import Database
from app.listings.model import ListingIn
from app.listings.sync import EmptySourceError, sync_listings

SAMPLE_FILE = Path(__file__).with_name("sample_properties.json")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--phone-number-id", required=True, help="the broker's number ID")
    parser.add_argument("--file", type=Path, default=SAMPLE_FILE, help="listings JSON file")
    parser.add_argument(
        "--allow-empty", action="store_true", help="let an empty file mark every listing removed"
    )
    return parser.parse_args(argv)


def load_listings(path: Path) -> list[ListingIn]:
    listings = TypeAdapter(list[ListingIn]).validate_python(
        json.loads(path.read_text(encoding="utf-8"))
    )
    ids = [lst.external_id for lst in listings]
    if duplicates := sorted({i for i in ids if ids.count(i) > 1}):
        raise SystemExit(f"{path}: these ids are used more than once: {', '.join(duplicates)}")
    return listings


async def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    listings = load_listings(args.file)
    db = await Database.connect(get_settings())
    broker = await db.get_broker_by_phone_number_id(args.phone_number_id)
    if broker is None:
        raise SystemExit(f"no active broker on phone_number_id {args.phone_number_id}")
    try:
        result = await sync_listings(db, broker.id, listings, allow_empty=args.allow_empty)
    except EmptySourceError as e:
        raise SystemExit(str(e)) from None
    print(f"{broker.name}: {result}")


if __name__ == "__main__":
    asyncio.run(main())
