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

    async def send_template(
        self,
        *,
        phone_number_id: str,
        access_token: str,
        to: str,
        name: str,
        language: str,
        body_params: list[str],
    ) -> str:
        """Send an approved template (allowed outside the 24-hour window). Returns its ID."""
        payload: dict[str, Any] = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "template",
            "template": {"name": name, "language": {"code": language}},
        }
        if body_params:
            payload["template"]["components"] = [
                {
                    "type": "body",
                    "parameters": [{"type": "text", "text": p} for p in body_params],
                }
            ]
        data = await self._post(f"/{phone_number_id}/messages", access_token, payload)
        return str(data["messages"][0]["id"])

    async def get(
        self, path: str, access_token: str, params: dict[str, str] | None = None
    ) -> dict[str, Any]:
        """GET a Graph API object, e.g. a lead-form submission."""
        return await self._request("GET", path, access_token, params=params)

    async def post(
        self, path: str, access_token: str, params: dict[str, str] | None = None
    ) -> dict[str, Any]:
        """POST to a Graph API edge with query parameters, e.g. subscribing an app to a Page."""
        return await self._request("POST", path, access_token, params=params)

    async def _post(self, path: str, access_token: str, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._request("POST", path, access_token, json=payload)

    async def _request(
        self,
        method: str,
        path: str,
        access_token: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        url = self._base_url + path
        headers = {"Authorization": f"Bearer {access_token}"}

        async def send() -> httpx.Response:
            return await self._http.request(method, url, json=json, params=params, headers=headers)

        response = await send()
        if response.status_code >= 500:
            log.warning(
                "graph api server error, retrying once", extra={"status": response.status_code}
            )
            response = await send()
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
    text = f"code={error.get('code')} message={error.get('message')!r}"
    # The message is often only a title ("Invalid parameter"); this says which and why.
    details = (error.get("error_data") or {}).get("details")
    return f"{text} details={details!r}" if details else text
