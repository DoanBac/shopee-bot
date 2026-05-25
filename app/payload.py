from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


_URL_RE = re.compile(r"^https?://", re.IGNORECASE)
_IMAGE_EXT_RE = re.compile(r"\.(jpg|jpeg|png|webp|gif|bmp)(\?|#|$)", re.IGNORECASE)


@dataclass(frozen=True)
class ChatEvent:
    raw: dict[str, Any]
    conversation_id: str
    customer_id: str
    message_id: str
    text: str
    image_urls: list[str]
    history: list[dict[str, str]]
    is_from_customer: bool


def parse_salework_payload(payload: dict[str, Any]) -> ChatEvent:
    payload = _with_column_values(payload)
    return ChatEvent(
        raw=payload,
        conversation_id=_to_str(
            _first_path(
                payload,
                (
                    "conversation_id",
                    "conversationId",
                    "conversation.id",
                    "chat.id",
                    "room.id",
                    "data.conversation_id",
                    "data.conversation.id",
                    "data.chat.id",
                    "data.room.id",
                ),
            )
            or _deep_find_first(payload, ("conversation_id", "conversationId", "thread_id", "room_id"))
        ),
        customer_id=_to_str(
            _first_path(
                payload,
                (
                    "customer_id",
                    "customerId",
                    "sender_id",
                    "sender.id",
                    "buyer_id",
                    "buyer.id",
                    "from.id",
                    "data.customer_id",
                    "data.sender_id",
                    "data.sender.id",
                    "data.buyer.id",
                    "data.from.id",
                ),
            )
            or _deep_find_first(payload, ("customer_id", "customerId", "sender_id", "buyer_id", "user_id"))
        ),
        message_id=_to_str(
            _first_path(
                payload,
                (
                    "message_id",
                    "messageId",
                    "msg_id",
                    "id",
                    "message.id",
                    "data.message_id",
                    "data.message.id",
                    "data.id",
                ),
            )
            or _deep_find_first(payload, ("message_id", "messageId", "msg_id"))
        ),
        text=_extract_text(payload),
        image_urls=_extract_image_urls(payload),
        history=_extract_history(payload),
        is_from_customer=_is_from_customer(payload),
    )


def _with_column_values(payload: dict[str, Any]) -> dict[str, Any]:
    columns = payload.get("columns")
    if not isinstance(columns, list):
        return payload

    mapped: dict[str, Any] = {}
    for item in columns:
        if not isinstance(item, dict):
            continue
        code = _to_str(item.get("columnCode") or item.get("code") or item.get("key") or item.get("name"))
        if not code:
            continue
        mapped[code] = item.get("value")

    if not mapped:
        return payload

    normalized = dict(payload)
    normalized.update(mapped)
    normalized["column_values"] = mapped
    return normalized


def _extract_text(payload: dict[str, Any]) -> str:
    value = _first_path(
        payload,
        (
            "text",
            "message",
            "content",
            "body",
            "message.text",
            "message.content",
            "data.text",
            "data.message",
            "data.content",
            "data.body",
            "data.message.text",
            "data.message.content",
            "event.message.text",
            "event.message.content",
            "last_message",
            "lastMessage",
            "message_content",
            "messageContent",
            "customer_message",
            "customerMessage",
        ),
    )
    if isinstance(value, dict):
        value = _first_path(value, ("text", "content", "body"))
    if value is None:
        value = _deep_find_first(payload, ("text", "content", "body"))
    return _to_str(value)


def _extract_history(payload: dict[str, Any]) -> list[dict[str, str]]:
    raw_history = _first_path(payload, ("history", "messages", "data.history", "data.messages", "conversation.messages"))
    if not isinstance(raw_history, list):
        return []

    history: list[dict[str, str]] = []
    for item in raw_history[-10:]:
        if not isinstance(item, dict):
            continue
        text = _to_str(_first_path(item, ("text", "content", "body", "message.text", "message.content")))
        if not text:
            continue
        role = _to_str(_first_path(item, ("role", "sender_type", "sender.type", "from.type"))) or "unknown"
        history.append({"role": role, "text": text})
    return history


def _extract_image_urls(payload: dict[str, Any]) -> list[str]:
    urls: list[str] = []
    seen: set[str] = set()

    def add(url: str) -> None:
        normalized = url.strip()
        if normalized and normalized not in seen:
            seen.add(normalized)
            urls.append(normalized)

    def walk(value: Any, image_context: bool = False) -> None:
        if isinstance(value, dict):
            local_image_context = image_context or _dict_has_image_hint(value)
            for key, child in value.items():
                key_norm = _norm_key(key)
                child_image_context = local_image_context or _key_has_image_hint(key_norm)
                if isinstance(child, str) and _is_url(child):
                    if child_image_context or _key_has_url_hint(key_norm) and _looks_like_image_url(child):
                        add(child)
                else:
                    walk(child, child_image_context)
            return

        if isinstance(value, list):
            for child in value:
                walk(child, image_context)
            return

        if isinstance(value, str) and image_context and _is_url(value):
            add(value)

    walk(payload)
    return urls


def _is_from_customer(payload: dict[str, Any]) -> bool:
    from_me = _first_path(
        payload,
        (
            "from_me",
            "fromMe",
            "is_from_me",
            "isFromMe",
            "sent_by_shop",
            "sentByShop",
            "data.from_me",
            "data.message.from_me",
            "message.from_me",
        ),
    )
    if isinstance(from_me, bool):
        return not from_me

    sender_type = _to_str(
        _first_path(
            payload,
            (
                "sender_type",
                "sender.type",
                "from.type",
                "data.sender_type",
                "data.sender.type",
                "data.from.type",
                "message.sender_type",
            ),
        )
    ).lower()
    if sender_type in {"shop", "seller", "admin", "agent", "staff", "bot"}:
        return False
    if sender_type in {"customer", "buyer", "user", "client"}:
        return True
    return True


def _first_path(data: Any, paths: tuple[str, ...]) -> Any:
    for path in paths:
        value = _get_path(data, path)
        if value not in (None, ""):
            return value
    return None


def _get_path(data: Any, path: str) -> Any:
    value = data
    for part in path.split("."):
        if isinstance(value, dict) and part in value:
            value = value[part]
            continue
        return None
    return value


def _deep_find_first(data: Any, candidate_keys: tuple[str, ...]) -> Any:
    normalized = {_norm_key(key) for key in candidate_keys}
    if isinstance(data, dict):
        for key, value in data.items():
            if _norm_key(key) in normalized and value not in (None, ""):
                return value
        for value in data.values():
            found = _deep_find_first(value, candidate_keys)
            if found not in (None, ""):
                return found
    elif isinstance(data, list):
        for item in data:
            found = _deep_find_first(item, candidate_keys)
            if found not in (None, ""):
                return found
    return None


def _dict_has_image_hint(data: dict[str, Any]) -> bool:
    for key, value in data.items():
        key_norm = _norm_key(key)
        if _key_has_image_hint(key_norm):
            return True
        if key_norm in {"type", "mimetype", "contenttype", "filetype"} and "image" in _to_str(value).lower():
            return True
    return False


def _key_has_image_hint(key_norm: str) -> bool:
    return any(hint in key_norm for hint in ("image", "img", "photo", "picture", "thumbnail", "attachment"))


def _key_has_url_hint(key_norm: str) -> bool:
    return key_norm in {"url", "link", "href", "src", "fileurl", "mediaurl"} or key_norm.endswith("url")


def _looks_like_image_url(value: str) -> bool:
    return bool(_IMAGE_EXT_RE.search(value)) or "image" in value.lower()


def _is_url(value: str) -> bool:
    return bool(_URL_RE.match(value.strip()))


def _norm_key(key: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(key).lower())


def _to_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()
