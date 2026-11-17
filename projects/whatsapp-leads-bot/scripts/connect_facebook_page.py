"""Connect a broker's Facebook Page so its lead-form submissions reach the bot.

    uv run python -m scripts.connect_facebook_page --phone-number-id 123456789012345 \\
        --page-id 987654321

Reads an access token from META_PAGE_SETUP_TOKEN, or prompts for it: a System User token that
has the Page assigned (with leads access) and the leads_retrieval, pages_show_list,
pages_read_engagement and pages_manage_metadata permissions. A Page access token also works.

It gets the Page's own token, subscribes your Meta app to the Page's `leadgen` field, and saves
the Page ID and the Page token (encrypted) on the broker. Re-run it to replace the token.
"""

import argparse
import asyncio
import getpass
import os
from typing import Any

import httpx

from app.config import get_settings
from app.crypto import encrypt_token
from app.db import Database
from app.whatsapp.client import WhatsAppClient, WhatsAppError


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--phone-number-id", required=True, help="the broker's WhatsApp number ID")
    parser.add_argument("--page-id", required=True, help="the Facebook Page ID")
    return parser.parse_args(argv)


async def page_token(graph: WhatsAppClient, page_id: str, token: str) -> tuple[str, str]:
    """(page token, page name). Exchanges a user/system-user token; accepts a page token."""
    page: dict[str, Any] = await graph.get(f"/{page_id}", token, {"fields": "name,access_token"})
    if page.get("access_token"):
        return str(page["access_token"]), str(page.get("name", page_id))
    me = await graph.get("/me", token, {"fields": "id,name"})
    if str(me.get("id")) == page_id:
        return token, str(me.get("name", page_id))
    raise SystemExit(
        "This token can't act for the Page. In Business Settings, assign the Page to the system "
        "user (with leads access) and generate the token with leads_retrieval, pages_show_list, "
        "pages_read_engagement and pages_manage_metadata."
    )


async def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    token = (
        os.environ.get("META_PAGE_SETUP_TOKEN") or getpass.getpass("Access token for the Page: ")
    ).strip()
    if not token:
        raise SystemExit("an access token is required")

    settings = get_settings()
    db = await Database.connect(settings)
    broker = await db.get_broker_by_phone_number_id(args.phone_number_id)
    if broker is None:
        raise SystemExit(f"no active broker on phone_number_id {args.phone_number_id}")

    async with httpx.AsyncClient(timeout=httpx.Timeout(20.0)) as http:
        graph = WhatsAppClient(http, settings.meta_graph_version)
        try:
            token_for_page, page_name = await page_token(graph, args.page_id, token)
            result = await graph.post(
                f"/{args.page_id}/subscribed_apps",
                token_for_page,
                {"subscribed_fields": "leadgen"},
            )
        except WhatsAppError as e:
            raise SystemExit(f"Meta refused: {e}") from None
    if not result.get("success"):
        raise SystemExit(f"Meta didn't confirm the subscription: {result}")

    await db.update_broker(
        broker.id,
        {"fb_page_id": args.page_id, "leads_access_token_enc": encrypt_token(token_for_page)},
    )
    print(f"Connected Page '{page_name}' to {broker.name}. Lead forms on it now reach the bot.")


if __name__ == "__main__":
    asyncio.run(main())
