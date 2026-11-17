"""Make a broker's properties match their source (Google Sheet or file).

The source is the full list: listings in it are added or updated (matched on their id), and
listings not in it are marked 'removed'. Nothing is deleted, so a property keeps its row and
anything linked to it. A row that couldn't be read keeps its current values.
"""

import logging
from collections.abc import Iterable
from dataclasses import dataclass, field

from app.db import Database
from app.listings.model import ListingIn

log = logging.getLogger(__name__)

REMOVED = "removed"


class EmptySourceError(Exception):
    """The source has no listings, which would mark every listing removed."""


@dataclass
class SyncResult:
    added: int = 0
    updated: int = 0
    removed: int = 0
    errors: list[str] = field(default_factory=list)

    def __str__(self) -> str:
        text = f"{self.added} added, {self.updated} updated, {self.removed} removed"
        if self.errors:
            text += f", {len(self.errors)} row(s) skipped"
        return text


async def sync_listings(
    db: Database,
    broker_id: str,
    listings: list[ListingIn],
    *,
    unreadable_ids: Iterable[str] = (),
    errors: Iterable[str] = (),
    allow_empty: bool = False,
) -> SyncResult:
    """Upsert `listings` and mark the rest removed.

    `unreadable_ids` are ids of rows that failed validation: their current values are kept.
    """
    existing = await db.list_properties(broker_id)
    keep = {lst.external_id for lst in listings} | set(unreadable_ids)
    if not keep and not allow_empty and any(p.status != REMOVED for p in existing):
        raise EmptySourceError(
            "the source has no readable listings; nothing was changed. If the broker really "
            "has no listings now, run again with --allow-empty."
        )

    known = {p.external_id for p in existing if p.external_id}
    await db.upsert_properties(broker_id, [lst.to_row() for lst in listings])
    to_remove = [p.id for p in existing if p.status != REMOVED and p.external_id not in keep]
    await db.set_properties_status(to_remove, REMOVED)

    result = SyncResult(
        added=sum(1 for lst in listings if lst.external_id not in known),
        updated=sum(1 for lst in listings if lst.external_id in known),
        removed=len(to_remove),
        errors=list(errors),
    )
    log.info(
        "listings synced",
        extra={
            "broker_id": broker_id,
            "added": result.added,
            "updated": result.updated,
            "removed": result.removed,
            "skipped": len(result.errors),
        },
    )
    return result
