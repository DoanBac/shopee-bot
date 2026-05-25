from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv


def _bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    return int(value)


def _float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    return float(value)


@dataclass(frozen=True)
class Settings:
    gemini_api_key: str
    gemini_model: str
    gemini_temperature: float

    salework_token: str
    salework_reply_url: str
    salework_reply_mode: str
    salework_webhook_reply_field: str
    salework_auth_header: str
    salework_auth_scheme: str
    salework_webhook_secret: str

    zalo_token: str
    zalo_message_url: str
    zalo_recipient_id: str
    zalo_auth_header: str
    zalo_auth_scheme: str

    data_dir: Path
    timezone: str
    daily_report_time: str
    auto_reply_enabled: bool
    send_fallback_on_human_needed: bool
    human_fallback_message: str
    image_max_bytes: int
    max_images_per_message: int
    request_timeout_seconds: float

    bot_shop_profile: str
    bot_known_policy: str


@lru_cache
def get_settings() -> Settings:
    load_dotenv()

    data_dir = Path(os.getenv("DATA_DIR", "data")).resolve()

    return Settings(
        gemini_api_key=os.getenv("GEMINI_API_KEY", "").strip(),
        gemini_model=os.getenv("GEMINI_MODEL", "gemini-1.5-flash").strip(),
        gemini_temperature=_float("GEMINI_TEMPERATURE", 0.2),
        salework_token=os.getenv("SALEWORK_TOKEN", "").strip(),
        salework_reply_url=os.getenv("SALEWORK_REPLY_URL", "").strip(),
        salework_reply_mode=os.getenv("SALEWORK_REPLY_MODE", "api").strip().lower(),
        salework_webhook_reply_field=os.getenv("SALEWORK_WEBHOOK_REPLY_FIELD", "reply").strip(),
        salework_auth_header=os.getenv("SALEWORK_AUTH_HEADER", "Authorization").strip(),
        salework_auth_scheme=os.getenv("SALEWORK_AUTH_SCHEME", "Bearer").strip(),
        salework_webhook_secret=os.getenv("SALEWORK_WEBHOOK_SECRET", "").strip(),
        zalo_token=os.getenv("ZALO_TOKEN", "").strip(),
        zalo_message_url=os.getenv("ZALO_MESSAGE_URL", "").strip(),
        zalo_recipient_id=os.getenv("ZALO_RECIPIENT_ID", "").strip(),
        zalo_auth_header=os.getenv("ZALO_AUTH_HEADER", "access_token").strip(),
        zalo_auth_scheme=os.getenv("ZALO_AUTH_SCHEME", "").strip(),
        data_dir=data_dir,
        timezone=os.getenv("TIMEZONE", "Asia/Ho_Chi_Minh").strip(),
        daily_report_time=os.getenv("DAILY_REPORT_TIME", "23:00").strip(),
        auto_reply_enabled=_bool("AUTO_REPLY_ENABLED", True),
        send_fallback_on_human_needed=_bool("SEND_FALLBACK_ON_HUMAN_NEEDED", False),
        human_fallback_message=os.getenv(
            "HUMAN_FALLBACK_MESSAGE",
            "Shop da nhan duoc tin nhan va se kiem tra them roi phan hoi anh/chi som.",
        ).strip(),
        image_max_bytes=_int("IMAGE_MAX_BYTES", 5_000_000),
        max_images_per_message=_int("MAX_IMAGES_PER_MESSAGE", 3),
        request_timeout_seconds=_float("REQUEST_TIMEOUT_SECONDS", 20.0),
        bot_shop_profile=os.getenv(
            "BOT_SHOP_PROFILE",
            "Shop ban hang tren Shopee. Tra loi ngan gon, lich su, dung tieng Viet.",
        ).strip(),
        bot_known_policy=os.getenv(
            "BOT_KNOWN_POLICY",
            "Neu khong chac ve gia, ton kho, phi ship, trang thai don hoac chinh sach doi tra, hay danh dau can nguoi xu ly.",
        ).strip(),
    )
