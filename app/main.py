from __future__ import annotations

import asyncio
import contextlib
import mimetypes
from datetime import date
from typing import Any

import httpx
from fastapi import FastAPI, Header, HTTPException, Request

from app.config import get_settings
from app.gemini import GeminiClient, GeminiImage
from app.payload import ChatEvent, parse_salework_payload
from app.report import build_daily_report, daily_report_loop, send_daily_report
from app.salework import SaleworkClient
from app.storage import log_chat_event, log_human_case
from app.zalo import ZaloClient


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    report_task = asyncio.create_task(daily_report_loop(settings))
    app.state.report_task = report_task
    try:
        yield
    finally:
        report_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await report_task


app = FastAPI(title="Shopee Salework Bot", version="0.1.0", lifespan=lifespan)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/")
async def root() -> dict[str, object]:
    return {
        "status": "ok",
        "docs": "/docs",
        "health": "/health",
        "webhook_salework": "/webhook/salework",
        "daily_report_preview": "/report/daily",
    }


@app.post("/webhook/salework")
async def salework_webhook(
    request: Request,
    x_webhook_secret: str | None = Header(default=None),
    x_salework_webhook_secret: str | None = Header(default=None),
) -> dict[str, Any]:
    settings = get_settings()
    _validate_webhook_secret(settings.salework_webhook_secret, x_webhook_secret, x_salework_webhook_secret)

    payload = await request.json()
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Webhook payload must be a JSON object")

    event = parse_salework_payload(payload)
    log_chat_event(settings, "incoming", _event_log_data(event))

    if not event.is_from_customer:
        return {"status": "ignored", "reason": "message is not from customer"}

    if not event.text and not event.image_urls:
        return {"status": "ignored", "reason": "no text or image URL found"}

    try:
        images = await _download_images(event.image_urls, settings.image_max_bytes, settings.max_images_per_message, settings.request_timeout_seconds)
        decision = await GeminiClient(settings).answer(event.text, event.history, images)
        log_chat_event(
            settings,
            "ai_decision",
            {
                **_event_log_data(event),
                "needs_human": decision.needs_human,
                "reason": decision.reason,
                "confidence": decision.confidence,
                "reply": decision.reply,
            },
        )

        if decision.needs_human:
            await _handle_human_case(settings, event, decision.reason, decision.reply)
            sent_fallback = False
            if settings.auto_reply_enabled and settings.send_fallback_on_human_needed:
                if _uses_webhook_response(settings.salework_reply_mode):
                    log_chat_event(
                        settings,
                        "fallback_webhook_response",
                        {**_event_log_data(event), "reply": settings.human_fallback_message},
                    )
                    return _webhook_reply_response(
                        settings.human_fallback_message,
                        settings.salework_webhook_reply_field,
                        status="human_needed",
                        reason=decision.reason,
                    )
                result = await SaleworkClient(settings).send_reply(event, settings.human_fallback_message)
                sent_fallback = result.sent
                log_chat_event(
                    settings,
                    "fallback_sent",
                    {**_event_log_data(event), "sent": result.sent, "reason": result.reason, "status": result.response_status},
                )
            return {
                "status": "human_needed",
                "reason": decision.reason,
                "fallback_sent": sent_fallback,
            }

        if not settings.auto_reply_enabled:
            return {"status": "dry_run", "reply": decision.reply}

        if _uses_webhook_response(settings.salework_reply_mode):
            log_chat_event(
                settings,
                "reply_webhook_response",
                {**_event_log_data(event), "reply": decision.reply},
            )
            return _webhook_reply_response(
                decision.reply,
                settings.salework_webhook_reply_field,
                status="ok",
                reason="returned in webhook response",
            )

        result = await SaleworkClient(settings).send_reply(event, decision.reply)
        log_chat_event(
            settings,
            "reply_sent",
            {
                **_event_log_data(event),
                "sent": result.sent,
                "reason": result.reason,
                "status": result.response_status,
                "response_body": result.response_body,
                "reply": decision.reply,
            },
        )
        return {"status": "ok", "reply_sent": result.sent, "reason": result.reason}

    except Exception as exc:
        reason = f"{type(exc).__name__}: {exc}"
        log_chat_event(settings, "error", {**_event_log_data(event), "reason": reason})
        await _handle_human_case(settings, event, reason, "")
        return {"status": "error_forwarded_to_human", "reason": reason}


@app.post("/report/daily")
async def trigger_daily_report(report_date: date | None = None) -> dict[str, Any]:
    settings = get_settings()
    result = await send_daily_report(settings, report_date)
    return {"sent": result.sent, "reason": result.reason, "status": result.response_status}


@app.get("/report/daily")
async def preview_daily_report(report_date: date | None = None) -> dict[str, str]:
    settings = get_settings()
    target_date = report_date or date.today()
    return {"report": build_daily_report(settings, target_date)}


def _validate_webhook_secret(expected: str, *received_values: str | None) -> None:
    if not expected:
        return
    if expected not in {value for value in received_values if value}:
        raise HTTPException(status_code=401, detail="Invalid webhook secret")


def _uses_webhook_response(reply_mode: str) -> bool:
    return reply_mode in {"webhook_response", "response", "webhook"}


def _webhook_reply_response(message: str, reply_field: str, status: str, reason: str) -> dict[str, Any]:
    field = reply_field or "reply"
    response: dict[str, Any] = {
        "status": status,
        "reason": reason,
        "reply": message,
        "message": message,
        "text": message,
        "data": {
            "reply": message,
            "message": message,
            "text": message,
        },
    }
    response[field] = message
    return response


async def _download_images(
    urls: list[str],
    max_bytes: int,
    max_images: int,
    timeout_seconds: float,
) -> list[GeminiImage]:
    images: list[GeminiImage] = []
    if not urls:
        return images

    async with httpx.AsyncClient(timeout=timeout_seconds, follow_redirects=True) as client:
        for url in urls[:max_images]:
            response = await client.get(url)
            response.raise_for_status()
            if len(response.content) > max_bytes:
                continue

            content_type = response.headers.get("content-type", "").split(";", maxsplit=1)[0].strip()
            mime_type = content_type if content_type.startswith("image/") else mimetypes.guess_type(url)[0]
            if not mime_type or not mime_type.startswith("image/"):
                continue

            images.append(GeminiImage(data=response.content, mime_type=mime_type, source_url=url))
    return images


async def _handle_human_case(settings, event: ChatEvent, reason: str, suggested_reply: str) -> None:
    data = {
        **_event_log_data(event),
        "reason": reason,
        "suggested_reply": suggested_reply,
    }
    log_human_case(settings, data)

    text = "\n".join(
        [
            "Shopee Bot can nguoi xu ly",
            f"Conversation: {event.conversation_id or '(unknown)'}",
            f"Customer: {event.customer_id or '(unknown)'}",
            f"Text: {event.text or '(khong co text)'}",
            f"Reason: {reason or '(khong ro)'}",
        ]
    )
    zalo_result = await ZaloClient(settings).send_message(text)
    log_chat_event(
        settings,
        "zalo_human_notice",
        {
            **_event_log_data(event),
            "sent": zalo_result.sent,
            "reason": zalo_result.reason,
            "status": zalo_result.response_status,
        },
    )


def _event_log_data(event: ChatEvent) -> dict[str, Any]:
    return {
        "conversation_id": event.conversation_id,
        "customer_id": event.customer_id,
        "message_id": event.message_id,
        "text": event.text,
        "image_urls": event.image_urls,
    }
