from __future__ import annotations

from dataclasses import dataclass

import httpx

from app.config import Settings


@dataclass(frozen=True)
class ZaloResult:
    sent: bool
    reason: str
    response_status: int | None = None
    response_body: str = ""


class ZaloClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def send_message(self, text: str) -> ZaloResult:
        if not self._settings.zalo_message_url:
            return ZaloResult(sent=False, reason="ZALO_MESSAGE_URL is missing")
        if not self._settings.zalo_token:
            return ZaloResult(sent=False, reason="ZALO_TOKEN is missing")

        payload = _message_payload(text, self._settings.zalo_recipient_id)
        headers = {
            "Content-Type": "application/json",
            self._settings.zalo_auth_header: _auth_value(self._settings.zalo_token, self._settings.zalo_auth_scheme),
        }

        try:
            async with httpx.AsyncClient(timeout=self._settings.request_timeout_seconds) as client:
                response = await client.post(self._settings.zalo_message_url, json=payload, headers=headers)
        except httpx.HTTPError as exc:
            return ZaloResult(sent=False, reason=f"Zalo request failed: {exc}")

        if response.is_success:
            return ZaloResult(sent=True, reason="sent", response_status=response.status_code, response_body=response.text[:500])
        return ZaloResult(
            sent=False,
            reason="Zalo API returned error",
            response_status=response.status_code,
            response_body=response.text[:500],
        )


def _message_payload(text: str, recipient_id: str) -> dict[str, object]:
    if recipient_id:
        return {
            "recipient": {"user_id": recipient_id},
            "message": {"text": text},
        }
    return {"message": text}


def _auth_value(token: str, scheme: str) -> str:
    if not scheme:
        return token
    return f"{scheme} {token}"
