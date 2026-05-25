from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from app.config import Settings
from app.payload import ChatEvent


@dataclass(frozen=True)
class SendResult:
    sent: bool
    reason: str
    response_status: int | None = None
    response_body: str = ""


class SaleworkClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def send_reply(self, event: ChatEvent, message: str) -> SendResult:
        if not self._settings.salework_reply_url:
            return SendResult(sent=False, reason="SALEWORK_REPLY_URL is missing")
        if not self._settings.salework_token:
            return SendResult(sent=False, reason="SALEWORK_TOKEN is missing")

        payload: dict[str, Any] = {
            "conversation_id": event.conversation_id,
            "customer_id": event.customer_id,
            "reply_to_message_id": event.message_id,
            "message": message,
        }
        headers = {
            "Content-Type": "application/json",
            self._settings.salework_auth_header: _auth_value(
                self._settings.salework_token,
                self._settings.salework_auth_scheme,
            ),
        }

        try:
            async with httpx.AsyncClient(timeout=self._settings.request_timeout_seconds) as client:
                response = await client.post(self._settings.salework_reply_url, json=payload, headers=headers)
        except httpx.HTTPError as exc:
            return SendResult(sent=False, reason=f"Salework request failed: {exc}")

        if response.is_success:
            return SendResult(sent=True, reason="sent", response_status=response.status_code, response_body=response.text[:500])
        return SendResult(
            sent=False,
            reason="Salework API returned error",
            response_status=response.status_code,
            response_body=response.text[:500],
        )


def _auth_value(token: str, scheme: str) -> str:
    if not scheme:
        return token
    return f"{scheme} {token}"
