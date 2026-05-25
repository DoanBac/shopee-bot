from __future__ import annotations

import base64
import json
import re
from dataclasses import dataclass
from typing import Any

import httpx

from app.config import Settings


@dataclass(frozen=True)
class GeminiImage:
    data: bytes
    mime_type: str
    source_url: str


@dataclass(frozen=True)
class GeminiDecision:
    reply: str
    needs_human: bool
    reason: str
    confidence: float
    raw_text: str = ""


class GeminiClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def answer(
        self,
        customer_text: str,
        history: list[dict[str, str]],
        images: list[GeminiImage],
    ) -> GeminiDecision:
        if not self._settings.gemini_api_key:
            return GeminiDecision(
                reply="",
                needs_human=True,
                reason="GEMINI_API_KEY is missing",
                confidence=0.0,
            )

        prompt = self._build_prompt(customer_text, history, bool(images))
        parts: list[dict[str, Any]] = [{"text": prompt}]
        for image in images:
            parts.append(
                {
                    "inline_data": {
                        "mime_type": image.mime_type,
                        "data": base64.b64encode(image.data).decode("ascii"),
                    }
                }
            )

        body = {
            "systemInstruction": {
                "parts": [
                    {
                        "text": (
                            "Ban la tro ly cham soc khach hang Shopee cua shop. "
                            "Chi tra loi bang tieng Viet, ngan gon, lich su, dung thong tin duoc cung cap. "
                            "Khong tu bia gia, ton kho, phi ship, trang thai don hang, cam ket doi tra hoac thong tin chua co. "
                            "Neu khong du thong tin hoac case can nguoi kiem tra, dat needs_human=true."
                        )
                    }
                ]
            },
            "contents": [{"role": "user", "parts": parts}],
            "generationConfig": {
                "temperature": self._settings.gemini_temperature,
                "responseMimeType": "application/json",
            },
        }

        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self._settings.gemini_model}:generateContent"
        )
        async with httpx.AsyncClient(timeout=self._settings.request_timeout_seconds) as client:
            response = await client.post(url, params={"key": self._settings.gemini_api_key}, json=body)
            response.raise_for_status()

        text = _extract_response_text(response.json())
        return _parse_decision(text)

    def _build_prompt(self, customer_text: str, history: list[dict[str, str]], has_images: bool) -> str:
        history_text = "\n".join(f"- {item['role']}: {item['text']}" for item in history) or "(khong co)"
        image_note = "Co anh dinh kem. Hay doc anh neu anh lien quan cau hoi." if has_images else "Khong co anh dinh kem."

        return f"""
Thong tin shop:
{self._settings.bot_shop_profile}

Quy dinh/luu y:
{self._settings.bot_known_policy}

Lich su chat gan nhat:
{history_text}

Tin nhan khach:
{customer_text or "(khach chi gui anh hoac webhook khong co text)"}

Anh:
{image_note}

Hay tra ve DUY NHAT JSON hop le theo schema:
{{
  "reply": "noi dung tra loi gui cho khach, bo trong neu can nguoi xu ly ngay",
  "needs_human": false,
  "reason": "ly do ngan gon",
  "confidence": 0.0
}}

Dat needs_human=true neu:
- Khach hoi ve don hang cu the, khieu nai, hoan/doi tra, bao loi san pham, gia/tinh trang ton kho ma shop chua cung cap du lieu.
- Anh khong doc duoc hoac cau hoi khong ro.
- Can nhan vien xac minh tren Salework/Shopee.
""".strip()


def _extract_response_text(data: dict[str, Any]) -> str:
    candidates = data.get("candidates") or []
    if not candidates:
        return ""
    parts = candidates[0].get("content", {}).get("parts", [])
    texts = [part.get("text", "") for part in parts if isinstance(part, dict)]
    return "\n".join(text for text in texts if text).strip()


def _parse_decision(text: str) -> GeminiDecision:
    if not text:
        return GeminiDecision(reply="", needs_human=True, reason="Gemini returned empty response", confidence=0.0)

    json_text = _extract_json_text(text)
    try:
        data = json.loads(json_text)
    except json.JSONDecodeError:
        return GeminiDecision(reply="", needs_human=True, reason="Gemini returned non-JSON response", confidence=0.0, raw_text=text)

    reply = str(data.get("reply") or "").strip()
    needs_human = bool(data.get("needs_human", not reply))
    reason = str(data.get("reason") or "").strip()
    confidence = _safe_float(data.get("confidence"), 0.0)

    if not reply and not needs_human:
        needs_human = True
        reason = reason or "Gemini did not provide a reply"

    return GeminiDecision(
        reply=reply,
        needs_human=needs_human,
        reason=reason,
        confidence=confidence,
        raw_text=text,
    )


def _extract_json_text(text: str) -> str:
    stripped = text.strip()
    fence_match = re.search(r"```(?:json)?\s*(.*?)```", stripped, flags=re.DOTALL | re.IGNORECASE)
    if fence_match:
        stripped = fence_match.group(1).strip()

    start = stripped.find("{")
    end = stripped.rfind("}")
    if start >= 0 and end > start:
        return stripped[start : end + 1]
    return stripped


def _safe_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default

