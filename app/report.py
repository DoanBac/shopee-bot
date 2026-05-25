from __future__ import annotations

import asyncio
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.config import Settings
from app.storage import load_chat_events, load_human_cases, log_chat_event
from app.zalo import ZaloClient, ZaloResult


async def send_daily_report(settings: Settings, report_date: date | None = None) -> ZaloResult:
    tz = _timezone(settings)
    target_date = report_date or datetime.now(tz).date()
    text = build_daily_report(settings, target_date)
    result = await ZaloClient(settings).send_message(text)
    log_chat_event(
        settings,
        "daily_report",
        {
            "date": target_date.isoformat(),
            "zalo_sent": result.sent,
            "zalo_reason": result.reason,
            "zalo_status": result.response_status,
        },
    )
    return result


def build_daily_report(settings: Settings, report_date: date) -> str:
    events = load_chat_events(settings, report_date)
    human_cases = load_human_cases(settings, report_date)

    incoming = [event for event in events if event.get("event_type") == "incoming"]
    replies = [event for event in events if event.get("event_type") == "reply_sent" and event.get("data", {}).get("sent")]
    errors = [event for event in events if event.get("event_type") == "error"]
    conversations = {
        str(event.get("data", {}).get("conversation_id") or "")
        for event in incoming
        if event.get("data", {}).get("conversation_id")
    }

    lines = [
        f"Bao cao Shopee Bot ngay {report_date.isoformat()}",
        f"- Tin nhan khach: {len(incoming)}",
        f"- Hoi thoai: {len(conversations)}",
        f"- Da tra loi tu dong: {len(replies)}",
        f"- Can nguoi xu ly: {len(human_cases)}",
        f"- Loi he thong: {len(errors)}",
    ]

    if human_cases:
        lines.append("")
        lines.append("Case can xem:")
        for index, case in enumerate(human_cases[-5:], start=1):
            data = case.get("data", {})
            text = str(data.get("text") or "(khong co text)").replace("\n", " ")
            reason = str(data.get("reason") or "").replace("\n", " ")
            conversation_id = str(data.get("conversation_id") or "")
            lines.append(f"{index}. {conversation_id}: {text[:80]} | {reason[:80]}")

    return "\n".join(lines)


async def daily_report_loop(settings: Settings) -> None:
    while True:
        now = datetime.now(_timezone(settings))
        next_run = _next_run_at(now, settings.daily_report_time)
        await asyncio.sleep(max(1.0, (next_run - now).total_seconds()))
        await send_daily_report(settings, next_run.date())


def _next_run_at(now: datetime, report_time: str) -> datetime:
    hour, minute = _parse_report_time(report_time)
    target = datetime.combine(now.date(), time(hour=hour, minute=minute), tzinfo=now.tzinfo)
    if target <= now:
        target += timedelta(days=1)
    return target


def _parse_report_time(value: str) -> tuple[int, int]:
    try:
        hour_text, minute_text = value.split(":", maxsplit=1)
        hour = int(hour_text)
        minute = int(minute_text)
    except ValueError:
        return 23, 0
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        return 23, 0
    return hour, minute


def _timezone(settings: Settings) -> ZoneInfo:
    try:
        return ZoneInfo(settings.timezone)
    except Exception:
        return ZoneInfo("Asia/Ho_Chi_Minh")

