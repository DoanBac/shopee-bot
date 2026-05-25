from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from app.config import Settings


CHAT_LOG = "chat_events.jsonl"
HUMAN_LOG = "human_cases.jsonl"


def log_chat_event(settings: Settings, event_type: str, data: dict[str, Any]) -> None:
    _append_jsonl(settings.data_dir / CHAT_LOG, _record(settings, event_type, data))


def log_human_case(settings: Settings, data: dict[str, Any]) -> None:
    _append_jsonl(settings.data_dir / HUMAN_LOG, _record(settings, "human_needed", data))


def load_chat_events(settings: Settings, report_date: date) -> list[dict[str, Any]]:
    return [
        record
        for record in _read_jsonl(settings.data_dir / CHAT_LOG)
        if _record_date(record, settings) == report_date
    ]


def load_human_cases(settings: Settings, report_date: date) -> list[dict[str, Any]]:
    return [
        record
        for record in _read_jsonl(settings.data_dir / HUMAN_LOG)
        if _record_date(record, settings) == report_date
    ]


def _record(settings: Settings, event_type: str, data: dict[str, Any]) -> dict[str, Any]:
    now = datetime.now(_timezone(settings))
    return {
        "created_at": now.isoformat(),
        "event_type": event_type,
        "data": data,
    }


def _append_jsonl(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(record, ensure_ascii=False) + "\n")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []

    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as file:
        for line in file:
            stripped = line.strip()
            if not stripped:
                continue
            try:
                records.append(json.loads(stripped))
            except json.JSONDecodeError:
                continue
    return records


def _record_date(record: dict[str, Any], settings: Settings) -> date | None:
    created_at = record.get("created_at")
    if not isinstance(created_at, str):
        return None
    try:
        return datetime.fromisoformat(created_at).astimezone(_timezone(settings)).date()
    except ValueError:
        return None


def _timezone(settings: Settings) -> ZoneInfo:
    try:
        return ZoneInfo(settings.timezone)
    except Exception:
        return ZoneInfo("Asia/Ho_Chi_Minh")

