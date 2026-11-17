"""Give a broker an inbound email key and print the address to forward portal emails to.

    uv run python -m scripts.set_inbound_email --phone-number-id 123456789012345 --key ravi

The key goes after '+' in the inbound address: with INBOUND_EMAIL_ADDRESS set to
abc123@inbound.postmarkapp.com, the broker forwards to abc123+ravi@inbound.postmarkapp.com.
Use lowercase letters, digits and '-' only. Each broker needs a different key.
"""

import argparse
import asyncio
import re

from app.config import get_settings
from app.db import Database

KEY = re.compile(r"[a-z0-9][a-z0-9-]{1,39}")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--phone-number-id", required=True, help="the broker's WhatsApp number ID")
    parser.add_argument("--key", required=True, help="e.g. the broker's first name: 'ravi'")
    return parser.parse_args(argv)


def forwarding_address(inbound_address: str, key: str) -> str:
    local, _, domain = inbound_address.partition("@")
    return f"{local.split('+')[0]}+{key}@{domain}"


async def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    key = args.key.strip().lower()
    if not KEY.fullmatch(key):
        raise SystemExit("the key must be 2-40 lowercase letters, digits or '-'")
    settings = get_settings()
    db = await Database.connect(settings)
    broker = await db.get_broker_by_phone_number_id(args.phone_number_id)
    if broker is None:
        raise SystemExit(f"no active broker on phone_number_id {args.phone_number_id}")
    other = await db.get_broker_by_email_key(key)
    if other is not None and other.id != broker.id:
        raise SystemExit(f"'{key}' is already used by {other.name}")

    await db.update_broker(broker.id, {"inbound_email_key": key})
    if settings.inbound_email_address:
        address = forwarding_address(settings.inbound_email_address, key)
        print(f"{broker.name}: forward portal enquiry emails to {address}")
    else:
        print(
            f"{broker.name}: key '{key}' saved. Set INBOUND_EMAIL_ADDRESS to print the full "
            f"forwarding address (<inbound address with +{key} before the @>)."
        )


if __name__ == "__main__":
    asyncio.run(main())
