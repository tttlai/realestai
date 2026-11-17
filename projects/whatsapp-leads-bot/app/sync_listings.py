"""Sync brokers' listings from their Google Sheets.

    python -m app.sync_listings                     # every broker with a sheet (Railway cron)
    python -m app.sync_listings --phone-number-id 123456789012345 \\
        --sheet "https://docs.google.com/spreadsheets/d/.../edit"   # save a broker's sheet, sync
    python -m app.sync_listings --phone-number-id 123456789012345     # sync one broker now

See app/listings/sheet.py for the sheet's columns and app/listings/sync.py for what a sync
changes. Exits with status 1 if any broker's sheet couldn't be synced.
"""

import argparse
import asyncio
import logging
import sys

import httpx

from app.config import get_settings
from app.db import Broker, Database
from app.listings.sheet import SheetError, fetch_sheet_csv, parse_listings_csv
from app.listings.sync import EmptySourceError, SyncResult, sync_listings
from app.log import bind_context, configure_logging

log = logging.getLogger(__name__)


async def sync_broker(
    db: Database, http: httpx.AsyncClient, broker: Broker, *, allow_empty: bool = False
) -> SyncResult:
    if not broker.listings_sheet_url:
        raise SheetError(f"{broker.name} has no listings sheet")
    text = await fetch_sheet_csv(http, broker.listings_sheet_url)
    listings, errors = parse_listings_csv(text)
    for error in errors:
        log.warning("listing row skipped", extra={"row": error.row, "problem": error.message})
    return await sync_listings(
        db,
        broker.id,
        listings,
        unreadable_ids=[e.external_id for e in errors if e.external_id],
        errors=[str(e) for e in errors],
        allow_empty=allow_empty,
    )


async def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--phone-number-id", help="sync just this broker")
    parser.add_argument("--sheet", help="save this Google Sheet link for the broker first")
    parser.add_argument(
        "--allow-empty", action="store_true", help="let an empty sheet mark every listing removed"
    )
    args = parser.parse_args(argv)
    if args.sheet and not args.phone_number_id:
        parser.error("--sheet needs --phone-number-id")

    settings = get_settings()
    configure_logging(settings.log_level)
    db = await Database.connect(settings)

    if args.phone_number_id:
        broker = await db.get_broker_by_phone_number_id(args.phone_number_id)
        if broker is None:
            print(f"No active broker on phone_number_id {args.phone_number_id}")
            return 1
        if args.sheet:
            await db.set_listings_sheet(broker.id, args.sheet)
            broker = broker.model_copy(update={"listings_sheet_url": args.sheet})
        brokers = [broker]
    else:
        brokers = await db.list_brokers_with_listings_sheet()

    failed = 0
    async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as http:
        for broker in brokers:
            with bind_context(broker_id=broker.id):
                try:
                    result = await sync_broker(db, http, broker, allow_empty=args.allow_empty)
                except (SheetError, EmptySourceError, httpx.HTTPError) as e:
                    failed += 1
                    log.error("listings sync failed", extra={"problem": str(e)})
                    print(f"{broker.name}: not synced: {e}")
                    continue
            print(f"{broker.name}: {result}")
            for error in result.errors:
                print(f"  skipped {error}")
    if not brokers:
        print("No brokers have a listings sheet yet.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
