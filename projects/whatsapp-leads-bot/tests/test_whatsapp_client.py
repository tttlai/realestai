import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest
import respx

from app.whatsapp.client import OutsideWindowError, WhatsAppClient, WhatsAppError

URL = "https://graph.facebook.com/v24.0/123/messages"
RECENT = datetime.now(UTC) - timedelta(minutes=5)


async def send(client: WhatsAppClient, last_inbound_at: datetime | None = RECENT) -> str:
    return await client.send_text(
        phone_number_id="123",
        access_token="tok",
        to="919876543210",
        body="hi",
        last_inbound_at=last_inbound_at,
    )


@respx.mock
async def test_send_text_payload_and_auth() -> None:
    route = respx.post(URL).respond(200, json={"messages": [{"id": "wamid.OUT"}]})
    async with httpx.AsyncClient() as http:
        assert await send(WhatsAppClient(http, "v24.0")) == "wamid.OUT"
    request = route.calls.last.request
    assert request.headers["Authorization"] == "Bearer tok"
    assert json.loads(request.content) == {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": "919876543210",
        "type": "text",
        "text": {"preview_url": False, "body": "hi"},
    }


@respx.mock
async def test_refuses_outside_window() -> None:
    route = respx.post(URL)
    async with httpx.AsyncClient() as http:
        client = WhatsAppClient(http, "v24.0")
        with pytest.raises(OutsideWindowError):
            await send(client, datetime.now(UTC) - timedelta(hours=25))
        with pytest.raises(OutsideWindowError):
            await send(client, None)
    assert not route.called


@respx.mock
async def test_retries_once_on_5xx() -> None:
    route = respx.post(URL).mock(
        side_effect=[httpx.Response(503), httpx.Response(200, json={"messages": [{"id": "w"}]})]
    )
    async with httpx.AsyncClient() as http:
        assert await send(WhatsAppClient(http, "v24.0")) == "w"
    assert route.call_count == 2


@respx.mock
async def test_gives_up_after_second_5xx() -> None:
    route = respx.post(URL).respond(500)
    async with httpx.AsyncClient() as http:
        with pytest.raises(WhatsAppError):
            await send(WhatsAppClient(http, "v24.0"))
    assert route.call_count == 2


@respx.mock
async def test_no_retry_on_4xx() -> None:
    route = respx.post(URL).respond(
        400, json={"error": {"code": 131047, "message": "Re-engagement message"}}
    )
    async with httpx.AsyncClient() as http:
        with pytest.raises(WhatsAppError, match="131047"):
            await send(WhatsAppClient(http, "v24.0"))
    assert route.call_count == 1
