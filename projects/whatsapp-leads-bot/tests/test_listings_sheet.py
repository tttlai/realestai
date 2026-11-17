from pathlib import Path

import httpx
import pytest
import respx

from app.listings.sheet import (
    SheetError,
    csv_export_url,
    fetch_sheet_csv,
    parse_listings_csv,
    parse_price,
)

SHEET_ID = "1AbCdEfGhIjKlMnOpQrStUvWxYz0123456789"
EXPORT_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid=0"
TEMPLATE = Path(__file__).parent.parent / "scripts" / "listings_template.csv"


@pytest.mark.parametrize(
    ("link", "expected"),
    [
        (f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit", EXPORT_URL),
        (f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit#gid=0", EXPORT_URL),
        (
            f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit?gid=987#gid=987",
            EXPORT_URL.replace("gid=0", "gid=987"),
        ),
        (SHEET_ID, EXPORT_URL),
        (
            "https://docs.google.com/spreadsheets/d/e/2PACX-1vabc/pub?output=csv",
            "https://docs.google.com/spreadsheets/d/e/2PACX-1vabc/pub?output=csv",
        ),
    ],
)
def test_csv_export_url(link: str, expected: str) -> None:
    assert csv_export_url(link) == expected


def test_not_a_sheet_link() -> None:
    with pytest.raises(SheetError, match="not a Google Sheets link"):
        csv_export_url("https://example.com/listings")


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("8500000", [8_500_000]),
        ("85,00,000", [8_500_000]),
        ("₹85,00,000/-", [8_500_000]),
        ("85 L", [8_500_000]),
        ("1.2 Cr", [12_000_000]),
        ("28k", [28_000]),
        ("85-95 L", [8_500_000, 9_500_000]),
    ],
)
def test_parse_price(text: str, expected: list[int]) -> None:
    assert parse_price(text) == expected


@pytest.mark.parametrize("text", ["on request", "85 L or 90 L or 95 L"])
def test_unreadable_price(text: str) -> None:
    with pytest.raises(ValueError, match="can't read the price"):
        parse_price(text)


def test_template_reads_cleanly() -> None:
    listings, errors = parse_listings_csv(TEMPLATE.read_text(encoding="utf-8"))
    assert errors == []
    assert len(listings) == 10
    first = listings[0]
    assert (first.external_id, first.price_min, first.price_max) == ("P01", 8_500_000, 9_500_000)


def test_rows_are_read_with_header_aliases_and_extra_columns_ignored() -> None:
    text = (
        "Listing ID,Project,Location,Configuration,For,Min Price,Max Price,Status,Details,Owner\n"
        "A1, Skyline ,Wakad,2 BHK,Sale,85 L,95 L,On Hold,Ready,9800000000\n"
        ",,,,,,,,,\n"
        "A2,Green Arc,Wakad,2 BHK,lease,28000,,,,\n"
    )
    listings, errors = parse_listings_csv(text)
    assert errors == []
    assert [lst.to_row() for lst in listings] == [
        {
            "external_id": "A1",
            "title": "Skyline",
            "area": "Wakad",
            "bhk": "2 BHK",
            "type": "sale",
            "price_min": 8_500_000,
            "price_max": 9_500_000,
            "status": "on_hold",
            "notes": "Ready",
        },
        {
            "external_id": "A2",
            "title": "Green Arc",
            "area": "Wakad",
            "bhk": "2 BHK",
            "type": "rent",
            "price_min": 28_000,
            "price_max": None,
            "status": "available",
            "notes": None,
        },
    ]


def test_bad_rows_are_reported_and_the_rest_kept() -> None:
    text = (
        "id,title,area,type,price,status\n"
        "P1,Skyline,Wakad,sale,85,available\n"  # no unit: 85 rupees
        "P2,Green Arc,Wakad,lease out,28k,\n"
        "P3,Plots,Wagholi,sale,1 cr,gone\n"
        ",No id,Baner,sale,1 cr,\n"
        "P4,Dup A,Baner,sale,1 cr,\n"
        "P5,Fine,Kharadi,sale,92 L,\n"
        "P4,Dup B,Baner,sale,1.1 cr,\n"
    )
    listings, errors = parse_listings_csv(text)
    assert [lst.external_id for lst in listings] == ["P5"]
    assert [(e.row, e.external_id) for e in errors] == [
        (2, "P1"),
        (3, "P2"),
        (4, "P3"),
        (5, None),
        (6, "P4"),
        (8, "P4"),
    ]
    assert "looks too low" in errors[0].message
    assert "should be sale or rent" in errors[1].message
    assert "should be available, sold or on hold" in errors[2].message
    assert "id" in errors[3].message
    assert str(errors[4]) == "row 6 (id P4): same id as row(s) 8"


def test_missing_required_columns() -> None:
    with pytest.raises(SheetError, match="missing column"):
        parse_listings_csv("title,price\nSkyline,85 L\n")
    with pytest.raises(SheetError, match="empty"):
        parse_listings_csv("")


@respx.mock
async def test_fetch_returns_csv() -> None:
    respx.get(EXPORT_URL).respond(200, text="id,title,area\n", headers={"content-type": "text/csv"})
    async with httpx.AsyncClient() as http:
        assert await fetch_sheet_csv(http, SHEET_ID) == "id,title,area\n"


@respx.mock
@pytest.mark.parametrize(
    ("status", "content_type", "message"),
    [
        (200, "text/html; charset=utf-8", "isn't shared"),  # Google's sign-in page
        (401, "text/html", "isn't shared"),
        (404, "text/html", "isn't shared"),
        (404, "text/plain", "not found"),
        (500, "text/plain", "500"),
    ],
)
async def test_fetch_explains_failures(status: int, content_type: str, message: str) -> None:
    respx.get(EXPORT_URL).respond(status, text="x", headers={"content-type": content_type})
    async with httpx.AsyncClient() as http:
        with pytest.raises(SheetError, match=message):
            await fetch_sheet_csv(http, SHEET_ID)
