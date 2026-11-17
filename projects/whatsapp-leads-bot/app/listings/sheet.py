"""Read a broker's listings from a Google Sheet.

The sheet is read as CSV through its export link, so it must be shared as "Anyone with the
link: Viewer". Don't put anything private in it (owner phone numbers, etc.).

The first row is the header. Columns, in any order (extra columns are ignored):
    id, title, area, bhk, type, price_min, price_max, status, notes
`price` can stand in for price_min/price_max, and prices can be written as 8500000,
85,00,000, 85 L, 1.2 Cr, 28k or a range like 85-95 L.
"""

import csv
import io
import re
from dataclasses import dataclass
from typing import Any

import httpx
from pydantic import ValidationError

from app.agent.prices import rupee_amounts
from app.listings.model import ListingIn

_HEADER_ALIASES = {
    "id": "id",
    "listing_id": "id",
    "ref": "id",
    "title": "title",
    "project": "title",
    "name": "title",
    "area": "area",
    "location": "area",
    "locality": "area",
    "bhk": "bhk",
    "configuration": "bhk",
    "config": "bhk",
    "type": "type",
    "for": "type",
    "price": "price",
    "price_min": "price_min",
    "min_price": "price_min",
    "price_from": "price_min",
    "price_max": "price_max",
    "max_price": "price_max",
    "price_to": "price_max",
    "status": "status",
    "notes": "notes",
    "details": "notes",
    "description": "notes",
}
_TYPES = {
    "sale": "sale",
    "sell": "sale",
    "buy": "sale",
    "resale": "sale",
    "purchase": "sale",
    "rent": "rent",
    "rental": "rent",
    "lease": "rent",
}
_STATUSES = {
    "available": "available",
    "avail": "available",
    "sold": "sold",
    "on hold": "on_hold",
    "on_hold": "on_hold",
    "hold": "on_hold",
}
_SHEET_ID = re.compile(r"/spreadsheets/d/([a-zA-Z0-9_-]{20,})")
_GID = re.compile(r"[#?&]gid=(\d+)")


class SheetError(Exception):
    """The sheet couldn't be read at all (not shared, wrong link, not a sheet)."""


@dataclass
class RowError:
    row: int  # the row number as shown in the sheet
    external_id: str | None
    message: str

    def __str__(self) -> str:
        where = f"row {self.row}" + (f" (id {self.external_id})" if self.external_id else "")
        return f"{where}: {self.message}"


def csv_export_url(sheet: str) -> str:
    """The CSV export link for a sheet link (any tab) or a bare sheet ID."""
    if "output=csv" in sheet or "format=csv" in sheet:
        return sheet
    if match := _SHEET_ID.search(sheet):
        sheet_id = match.group(1)
    elif re.fullmatch(r"[a-zA-Z0-9_-]{20,}", sheet):
        sheet_id = sheet
    else:
        raise SheetError(f"not a Google Sheets link: {sheet!r}")
    gid = m.group(1) if (m := _GID.search(sheet)) else "0"
    return f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}"


async def fetch_sheet_csv(http: httpx.AsyncClient, sheet: str) -> str:
    response = await http.get(csv_export_url(sheet), follow_redirects=True)
    content_type = response.headers.get("content-type", "")
    if response.status_code in (401, 403) or "text/html" in content_type:
        raise SheetError(
            "the sheet isn't shared: in Google Sheets, Share → General access → "
            "'Anyone with the link' (Viewer)"
        )
    if response.status_code == 404:
        raise SheetError("sheet not found: check the link")
    if response.is_error:
        raise SheetError(f"Google returned {response.status_code} for the sheet")
    response.encoding = "utf-8"
    return response.text


def parse_listings_csv(text: str) -> tuple[list[ListingIn], list[RowError]]:
    """Valid listings, plus one error per row that couldn't be read. Blank rows are skipped.

    Rows sharing an id are all rejected, since there's no telling which one is right.
    """
    reader = csv.reader(io.StringIO(text))
    header = next(reader, None)
    if not header:
        raise SheetError("the sheet is empty: the first row must be the column names")
    columns = [_HEADER_ALIASES.get(_normalise_header(h)) for h in header]
    missing = {"id", "title", "area"} - set(columns)
    if missing:
        raise SheetError(f"missing column(s): {', '.join(sorted(missing))}")

    read: list[tuple[int, ListingIn]] = []
    errors: list[RowError] = []
    for row_number, cells in enumerate(reader, start=2):
        values = {c: v.strip() for c, v in zip(columns, cells, strict=False) if c and v.strip()}
        if not values:
            continue
        try:
            read.append((row_number, ListingIn.model_validate(_to_fields(values))))
        except (ValueError, ValidationError) as e:
            errors.append(RowError(row_number, values.get("id"), _describe(e)))

    rows_by_id: dict[str, list[int]] = {}
    for row_number, listing in read:
        rows_by_id.setdefault(listing.external_id, []).append(row_number)
    listings = []
    for row_number, listing in read:
        rows = rows_by_id[listing.external_id]
        if len(rows) > 1:
            others = ", ".join(str(r) for r in rows if r != row_number)
            errors.append(RowError(row_number, listing.external_id, f"same id as row(s) {others}"))
        else:
            listings.append(listing)
    errors.sort(key=lambda e: e.row)
    return listings, errors


def _to_fields(values: dict[str, str]) -> dict[str, Any]:
    fields: dict[str, Any] = {
        k: v for k, v in values.items() if k in {"id", "title", "area", "bhk", "notes"}
    }
    if "type" in values:
        kind = values["type"].lower()
        if kind not in _TYPES:
            raise ValueError(f"type {values['type']!r} should be sale or rent")
        fields["type"] = _TYPES[kind]
    if "status" in values:
        status = values["status"].lower()
        if status not in _STATUSES:
            raise ValueError(f"status {values['status']!r} should be available, sold or on hold")
        fields["status"] = _STATUSES[status]
    if "price" in values:
        amounts = parse_price(values["price"])
        fields["price_min"], fields["price_max"] = amounts[0], amounts[-1]
    for column in ("price_min", "price_max"):
        if column in values:
            [fields[column]] = parse_price(values[column])[:1]
    return fields


def parse_price(text: str) -> list[int]:
    """One amount, or two for a range ("85-95 L"). Raises ValueError if unreadable."""
    amounts = rupee_amounts(text)
    if not amounts:
        digits = re.sub(r"(?i)[₹,\s]|rs\.?|inr|/-", "", text)
        if digits.isdigit():
            amounts = [int(digits)]
    if not amounts or len(amounts) > 2:
        raise ValueError(f"can't read the price {text!r}: write e.g. 8500000, 85 L or 1.2 Cr")
    return amounts


def _normalise_header(header: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", header.strip().lower()).strip("_")


def _describe(error: Exception) -> str:
    if isinstance(error, ValidationError):
        return "; ".join(
            (f"{err['loc'][0]}: " if err["loc"] else "") + err["msg"].removeprefix("Value error, ")
            for err in error.errors()
        )
    return str(error)
