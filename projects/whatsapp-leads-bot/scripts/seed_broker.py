"""Add a broker, or update the one already on this phone_number_id.

    uv run python -m scripts.seed_broker --name "Test Broker" --agency-name "Test Realty" \\
        --phone-number-id 123456789012345 --alert-number 9198XXXXXXXX

The WhatsApp access token is read from BROKER_ACCESS_TOKEN, or prompted for. It is never taken
as an argument, which would leave it in shell history. It is stored encrypted.
"""

import argparse
import asyncio
import getpass
import os
from typing import Any

from app.config import get_settings
from app.crypto import encrypt_token
from app.db import Database
from app.intake.normalise import normalise_phone


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--name", required=True)
    parser.add_argument("--agency-name")
    parser.add_argument("--phone-number-id", required=True, help="WhatsApp Cloud API number ID")
    parser.add_argument("--waba-id", help="WhatsApp Business Account ID")
    parser.add_argument("--alert-number", required=True, help="where hot-lead alerts go")
    parser.add_argument("--timezone", default="Asia/Kolkata")
    return parser.parse_args(argv)


def build_row(args: argparse.Namespace, access_token: str) -> dict[str, Any]:
    row = {
        "name": args.name,
        "agency_name": args.agency_name,
        "phone_number_id": args.phone_number_id,
        "waba_id": args.waba_id,
        "access_token_enc": encrypt_token(access_token),
        "alert_number": normalise_phone(args.alert_number),
        "timezone": args.timezone,
        "active": True,
    }
    # Leave unspecified optional fields untouched when updating an existing broker.
    return {k: v for k, v in row.items() if v is not None}


async def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    token = (
        os.environ.get("BROKER_ACCESS_TOKEN") or getpass.getpass("WhatsApp access token: ")
    ).strip()
    if not token:
        raise SystemExit("an access token is required")
    db = await Database.connect(get_settings())
    broker = await db.upsert_broker(build_row(args, token))
    print(f"Saved broker {broker.id} ({broker.name}) on phone_number_id {broker.phone_number_id}")


if __name__ == "__main__":
    asyncio.run(main())
