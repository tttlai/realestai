"""WhatsApp Cloud API (Graph API) client. Official API only."""

import logging
from datetime import datetime
from typing import Any

import httpx

from app.whatsapp.window import is_window_open

log = logging.getLogger(__name__)

GRAPH_BASE_URL = "https://graph.facebook.com"


class WhatsAppError(Exception):
    pass


class OutsideWindowError(WhatsAppError):
    """Free-form text was attempted outside the 24-hour window; a template is required."""


class WhatsAppClient:
    def __init__(self, http: httpx.AsyncClient, graph_version: str) -> None:
        self._http = http
        self._base_url = f"{GRAPH_BASE_URL}/{graph_version}"

    async def send_text(
        self,
        *,
        phone_number_id: str,
        access_token: str,
        to: str,
        body: str,
        last_inbound_at: datetime | None,
    ) -> str:
        """Send a free-form text message and return its WhatsApp message ID."""
        if not is_window_open(last_inbound_at):
            raise OutsideWindowError("24-hour window is closed; only templates may be sent")
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "text",
            "text": {"preview_url": False, "body": body},
        }
        data = await self._post(f"/{phone_number_id}/messages", access_token, payload)
        return str(data["messages"][0]["id"])

    async def _post(self, path: str, access_token: str, payload: dict[str, Any]) -> dict[str, Any]:
        url = self._base_url + path
        headers = {"Authorization": f"Bearer {access_token}"}
        response = await self._http.post(url, json=payload, headers=headers)
        if response.status_code >= 500:
            log.warning(
                "graph api server error, retrying once", extra={"status": response.status_code}
            )
            response = await self._http.post(url, json=payload, headers=headers)
        if response.is_error:
            raise WhatsAppError(
                f"graph api returned {response.status_code}: {_error_detail(response)}"
            )
        return dict(response.json())


def _error_detail(response: httpx.Response) -> str:
    try:
        error = response.json().get("error", {})
    except ValueError:
        return "non-JSON error body"
    return f"code={error.get('code')} message={error.get('message')!r}"
