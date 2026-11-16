"""Load a broker's property listings from a JSON file. The agent quotes only what is listed.

    uv run python -m scripts.seed_properties --phone-number-id 123456789012345
    uv run python -m scripts.seed_properties --phone-number-id 123456789012345 \\
        --file my_listings.json --replace

The file is a list of objects with: title, area, and optionally bhk, type ("sale" or "rent"),
price_min and price_max (rupees; monthly rent for rentals), status ("available", "sold",
"on_hold") and notes. See scripts/sample_properties.json.

A broker who already has properties is left alone unless --replace is given, which deletes
their current listings first.
"""

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator

from app.config import get_settings
from app.db import Database

SAMPLE_FILE = Path(__file__).with_name("sample_properties.json")


class PropertyIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1)
    area: str = Field(min_length=1)
    bhk: str | None = None
    type: Literal["sale", "rent"] | None = None
    price_min: int | None = Field(default=None, ge=0)
    price_max: int | None = Field(default=None, ge=0)
    status: Literal["available", "sold", "on_hold"] = "available"
    notes: str | None = None

    @model_validator(mode="after")
    def _min_not_above_max(self) -> "PropertyIn":
        if self.price_min is not None and self.price_max is not None:
            if self.price_min > self.price_max:
                raise ValueError("price_min is above price_max")
        return self


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--phone-number-id", required=True, help="the broker's number ID")
    parser.add_argument("--file", type=Path, default=SAMPLE_FILE, help="listings JSON file")
    parser.add_argument(
        "--replace", action="store_true", help="delete the broker's current listings first"
    )
    return parser.parse_args(argv)


def load_rows(path: Path) -> list[dict[str, Any]]:
    items = TypeAdapter(list[PropertyIn]).validate_python(
        json.loads(path.read_text(encoding="utf-8"))
    )
    return [item.model_dump(exclude_none=True) for item in items]


async def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    rows = load_rows(args.file)
    db = await Database.connect(get_settings())
    broker = await db.get_broker_by_phone_number_id(args.phone_number_id)
    if broker is None:
        raise SystemExit(f"no active broker on phone_number_id {args.phone_number_id}")
    existing = await db.count_properties(broker.id)
    if existing and not args.replace:
        raise SystemExit(
            f"{broker.name} already has {existing} properties. Re-run with --replace to delete "
            "them and load this file instead."
        )
    added = await db.replace_properties(broker.id, rows)
    print(f"Loaded {added} properties for {broker.name} (replaced {existing})")


if __name__ == "__main__":
    asyncio.run(main())
