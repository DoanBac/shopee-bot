from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import random
import re
import shutil
import subprocess
import sys
import time
import traceback
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[1]
PROMPT_PATH = ROOT / "data" / "salework_ai_prompt.txt"
LOG_DIR = ROOT / "openclaw-logs"
STATE_PATH = LOG_DIR / "salework_gemini_bot_state.json"
URL = "https://chat.salework.net/conversations"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

SHOP_PREFIXES = (
    "trang:",
    "shop tago xin chao",
    "cam on ban da quan tam",
)

SYSTEM_PREVIEWS = {
    "[Sticker]",
    "[Hình ảnh]",
    "[Sản phẩm]",
    "[Đơn hàng]",
    "[Tệp tin]",
    "[Video]",
    "[Voice]",
    "[Thu âm]",
    "[Ghi âm]",
    "[GIF]",
}

# Patterns that should NEVER appear in a sent reply. They indicate the bot
# either leaked a banned topic, made a commitment only a human can make, or
# asked for info Salework already shows. Keep the list aggressive on the
# outbound side; we filter the inbound side with PREVIEW_SKIP_PATTERNS.
HARD_BLOCK_PATTERNS = (
    r"\bstk\b",
    r"so tai khoan",
    r"số tài khoản",
    r"chuyen khoan",
    r"chuyển khoản",
    r"\bbank\b",
    r"\bqr\b",
    r"\bzalo\b",
    r"\bfacebook\b",
    r"\btiktok\b",
    r"\bsdt\b",
    r"so dien thoai",
    r"số điện thoại",
    r"dat coc",
    r"đặt cọc",
    r"ngoai san",
    r"ngoài sàn",
    r"ship ngoai",
    r"ship ngoài",
    r"gui bu",
    r"gửi bù",
    r"ho tro lai.*chi phi",
    r"hỗ trợ lại.*chi phí",
    r"\bphi\b.*\bho tro\b",
    r"\bphí\b.*\bhỗ trợ\b",
    r"se ho tro.*(phi|chi phi|tien|ship|van chuyen|gui|bo sung|hoan|doi|den bu)",
    r"(ben em|shop) se ho tro.*(phi|chi phi|tien|ship|van chuyen|gui|bo sung|hoan|doi|den bu)",
    r"se co gang gui",
    r"sẽ cố gắng gửi",
    r"gui don oc",
    r"gửi đơn ốc",
    r"hoan lai",
    r"hoàn lại",
    r"cho em xin.*ma",
    r"gui.*ma.*san pham",
    r"ma san pham cu the",
    r"ma mau dang chon",
    # Hard refunds/commitments we must never auto-promise.
    r"hoan tien (cho|lai|cho ban|cho minh)",
    r"den bu",
    r"đền bù",
    r"boi thuong",
    r"bồi thường",
    r"giam gia.*phan",
    r"giảm giá.*phần",
)

# Preview-side patterns. If the latest customer line matches any of these,
# the bot will NOT open the conversation. Opening clears the unread badge
# and steals the message from a human's queue. These are "human-only" cases.
PREVIEW_SKIP_PATTERNS = (
    # Direct demands or threats that need a real human
    r"\bboi thuong\b",
    r"\bden bu\b",
    r"\btra lai tien\b",
    r"\bhoan tien ngay\b",
    r"\bhoan het\b",
    r"\bbao cao\b",
    r"\bto cao\b",
    r"\bkhoi kien\b",
    r"\bphap luat\b",
    r"\bcong an\b",
    r"\b1 sao\b",
    r"\bdanh gia xau\b",
    r"\bdanh gia 1\b",
    r"\bdanh gia tieu cuc\b",
    r"\bbom hang\b",
    # Personal contact / off-platform request
    r"\bso dien thoai shop\b",
    r"\bsdt shop\b",
    r"\bzalo shop\b",
    r"\bfacebook shop\b",
    # Custom modifications outside policy
    r"\bduc lo\b",
    r"\bkhoan them\b",
    r"\btuy chinh\b",
    r"\bdat rieng\b",
    r"\blam them\b.*\b(cho|giup)\b",
    # Cancel / address change after dispatch — must escalate
    r"\bhuy don\b",
    r"\bhuy giup\b",
    r"\bdoi dia chi.*sau\b",
    # Specific compensation amount
    r"\bgiam\s*\d+\s*%",
    r"\bgiam\s*\d+\s*k\b",
    r"\bden bu\s*\d+\b",
)

# Patterns that mark a preview as definitely outside the bot's safe scope.
# We still classify with quick_decision (it routes payment-info to the
# standard Shopee-only reply), but we never *promise* anything from these.
PREVIEW_HARD_CASE_HINTS = (
    "khong nhan duoc",
    "chua nhan hang",
    "chua giao",
    "shipper bom",
    "shipper khong giao",
    "hang loi",
    "hang vo",
    "hang gay",
    "thieu hang",
    "thieu oc",
    "khong co oc",
    "khong thay oc",
    "khong hai long",
    "buc",
    "que",
    "tuc",
    "vo van",
    "lam an",
)

# Reply variation pools. Picked deterministically from a customer-day seed so
# the same conversation gets a consistent voice within a day, but different
# customers see different phrasings — looks less like a template and helps
# avoid pattern-based moderation.
REPLY_VARIATIONS: dict[str, list[str]] = {
    "thanks": [
        "Dạ em cảm ơn mình nhiều ạ ❤️",
        "Dạ vâng ạ, em cảm ơn mình nha ❤️",
        "Dạ em cảm ơn mình đã ủng hộ shop ạ ❤️",
    ],
    "greeting": [
        "Dạ em chào mình ạ. Mình cần em hỗ trợ gì không ạ?",
        "Dạ em đây mình ơi, mình cần em hỗ trợ gì ạ?",
        "Dạ vâng ạ, em đang lắng nghe. Mình có vấn đề gì cần em hỗ trợ ạ?",
    ],
    "policy_payment": [
        "Dạ để đúng quy định Shopee, phần hỗ trợ mình thao tác trực tiếp trong đơn trên Shopee giúp em nha. Shop không xử lý qua kênh riêng trong chat ạ, có gì vướng mình nhắn em hỗ trợ tiếp nha.",
        "Dạ theo quy định của Shopee, mọi hỗ trợ mình thao tác trong đơn trên Shopee giúp em ạ. Bên em không nhận xử lý qua kênh riêng đâu nha, có gì mình nhắn em hỗ trợ tiếp ạ.",
        "Dạ phần này mình thao tác trên Shopee giúp em theo đúng quy định của sàn nha. Shop không hỗ trợ qua kênh riêng trong chat ạ, mình cần gì cứ nhắn vào đây em hỗ trợ tiếp ạ.",
    ],
    "missing_screws_first": [
        "Dạ em xin lỗi mình ạ. Mình kiểm tra kỹ giúp em trong thùng, bọc xốp và các khe của tấm gỗ xem túi ốc có bị lẫn không nha, túi này nhỏ nên đôi khi dễ sót ạ. Nếu vẫn không thấy, mình chụp giúp em ảnh phần hàng/phụ kiện nhận được để em kiểm tra hỗ trợ cho mình nhé.",
        "Dạ em xin lỗi mình nhiều ạ. Túi ốc nhỏ nên hay bị lẫn trong bọc xốp hoặc các khe của tấm gỗ, mình kiểm tra kỹ lại một lần giúp em nha. Trường hợp vẫn không tìm thấy, mình chụp giúp em phần hàng và phụ kiện đang có để em kiểm tra hỗ trợ cho mình ạ.",
        "Dạ em xin lỗi mình ạ. Mình kiểm tra kỹ một lần nữa giúp em trong thùng và các bọc xốp nha, túi ốc khá nhỏ nên đôi khi bị lẫn ạ. Nếu vẫn không thấy, mình chụp giúp em ảnh hiện trạng để em ghi nhận và kiểm tra hỗ trợ cho mình ạ.",
    ],
    "missing_screws_confirmed": [
        "Dạ em xin lỗi mình nhiều ạ. Vậy em ghi nhận là mình đã kiểm tra kỹ nhưng không thấy gói ốc, em sẽ note lại thiếu phụ kiện để kiểm tra với kho và hướng hỗ trợ cho mình. Mình giữ giúp em thùng/bọc hàng và ảnh phần phụ kiện hiện có nha.",
        "Dạ em xin lỗi mình ạ. Vậy em note lại trường hợp thiếu phụ kiện này để kiểm tra lại với kho và hỗ trợ cho mình ạ. Mình giữ giúp em phần thùng và bọc hàng, kèm ảnh phụ kiện đang có để em đối chiếu nha.",
    ],
    "tight_screws": [
        "Dạ mình dùng tua vít bake đầu chữ + đúng size, đặt vít thẳng, ấn mạnh tay rồi vặn từ từ giúp em nha. Bên em làm lỗ nhỏ để vít ăn gỗ chắc hơn nên lúc đầu sẽ hơi cứng; mình có thể xoáy thử 1-2 vòng rồi vặn lại, hoặc chà nhẹ đầu vít vào xà phòng/sáp nến cho trơn hơn ạ.",
        "Dạ mình dùng tua vít bake (đầu chữ +) đúng size, đặt vít thẳng và vặn từ từ là vào được ạ. Bên em làm lỗ nhỏ để vít bám chắc nên ban đầu sẽ hơi cứng; mình có thể xoáy thử 1-2 vòng cho mòn lỗ, hoặc chà nhẹ đầu vít vào sáp nến/xà phòng cho trơn hơn nha.",
    ],
    "defect_first_step": [
        "Dạ em xin lỗi mình nhiều ạ. Mình chụp hoặc quay giúp em rõ tình trạng sản phẩm và toàn cảnh phần hàng đang gặp vấn đề, kèm ảnh thùng/tem vận chuyển nếu còn giữ. Em kiểm tra lại để hỗ trợ hướng xử lý cho mình nha.",
        "Dạ em xin lỗi mình ạ. Mình quay hoặc chụp giúp em một đoạn rõ tình trạng sản phẩm, toàn cảnh phần hàng đang gặp vấn đề và phần thùng/tem vận chuyển nếu còn giữ giúp em ạ. Em sẽ kiểm tra và hướng hỗ trợ tiếp cho mình nha.",
        "Dạ em xin lỗi mình nha. Mình chụp giúp em ảnh rõ phần hàng đang gặp vấn đề, kèm ảnh thùng và tem vận chuyển nếu vẫn còn giúp em ạ. Em ghi nhận lại và kiểm tra hướng hỗ trợ cho mình ngay nha.",
    ],
    "shipping_in_transit": [
        "Dạ em xin lỗi mình nha. Đơn đang ở trạng thái giao/bên vận chuyển xử lý, em sẽ báo sàn kiểm tra lại phía vận chuyển cho mình. Mình giúp em để ý điện thoại, có cập nhật mới em báo lại ngay ạ.",
        "Dạ em xin lỗi mình nhiều ạ. Đơn hiện đang được bên vận chuyển xử lý, em sẽ note lại để báo sàn rà phía vận chuyển cho mình. Mình để ý điện thoại giúp em, có thông tin mới em cập nhật ngay nha.",
    ],
    "shipping_no_status": [
        "Dạ em xin lỗi mình nha. Mình chụp giúp em trạng thái đơn trên Shopee hoặc gửi mã đơn để em kiểm tra lại và hối bên vận chuyển/kho cho mình ạ.",
        "Dạ em xin lỗi mình ạ. Mình giúp em chụp trạng thái đơn hoặc nhắn em mã đơn để em kiểm tra lại và hối phía kho/vận chuyển hỗ trợ mình sớm nha.",
    ],
    "product_corner": [
        "Dạ mẫu bàn này thiết kế góc vuông, cạnh được xử lý nhẵn nên không sắc tay, nhưng không phải kiểu bo tròn lớn hẳn ạ. Nếu nhà có bé nhỏ thì mình có thể gắn thêm miếng bo silicon bên ngoài cho an toàn hơn nha.",
        "Dạ mẫu bàn này phần cạnh được xử lý nhẵn nên cầm không bị sắc tay, nhưng vẫn là dạng góc vuông chứ không bo tròn lớn ạ. Nếu nhà có em bé, mình có thể gắn thêm miếng bo silicon bên ngoài cho yên tâm hơn nha.",
    ],
    "thickness_table": [
        "Dạ mẫu bàn này mặt MDF dày 15mm ạ. Mình dùng học tập, làm việc, để laptop/màn hình và đồ sinh hoạt bình thường là ổn nha.",
        "Dạ mặt bàn mẫu này là MDF 15mm ạ. Đặt laptop, màn hình hay đồ sinh hoạt bình thường thì rất ổn nha mình.",
    ],
    "thickness_shelf": [
        "Dạ mẫu kệ/tủ này phần gỗ MDF dày khoảng 11mm, phù hợp nhu cầu để đồ sinh hoạt cơ bản và decor gọn gàng ạ.",
        "Dạ kệ bên em phần gỗ MDF khoảng 11mm, phù hợp cho nhu cầu để đồ sinh hoạt cơ bản và bày trí gọn gàng ạ.",
    ],
    "height_table": [
        "Dạ mẫu bàn làm việc/gaming này cao khoảng 75cm ạ.",
        "Dạ mẫu này cao tầm 75cm ạ, là chiều cao tiêu chuẩn của bàn làm việc/gaming bên em nha.",
    ],
    "weight_table_1m2": [
        "Dạ mẫu bàn kích thước 1m2 x 60cm nặng tầm 6-7kg ạ.",
        "Dạ bàn 1m2 x 60cm bên em nặng khoảng 6-7kg ạ.",
    ],
    "delivery_time": [
        "Dạ thời gian giao hệ thống Shopee sẽ hiển thị theo địa chỉ của mình ạ. Bên em đóng gói kỹ và bàn giao đơn vị vận chuyển sớm nhất nha mình.",
        "Dạ thời gian giao hàng hệ thống Shopee tính theo địa chỉ của mình ạ, mình xem dự kiến giao trong app nha. Bên em luôn cố gắng đóng gói kỹ và gửi đơn vị vận chuyển sớm nhất ạ.",
    ],
    "shipping_fee": [
        "Dạ phí vận chuyển bên Shopee tính tự động theo địa chỉ của mình ạ. Mình tham khảo thêm gói Shopee VIP (khoảng 29k/tháng), thường có nhiều voucher freeship cho đơn cồng kềnh, đơn giá trị cao còn được giảm thêm nữa nha.",
        "Dạ phí vận chuyển bên Shopee sẽ tính theo địa chỉ giao của mình ạ. Mình tham khảo gói Shopee VIP để nhận thêm voucher freeship cho đơn cồng kềnh nha.",
    ],
    "material_wood": [
        "Dạ các mẫu nội thất bên em đều làm từ gỗ MDF chất lượng tốt, có lớp chống ẩm và chống trầy ạ. Gỗ dày dặn, chắc chắn, mình dùng thoải mái nha.",
        "Dạ sản phẩm bên em là gỗ MDF chất lượng, có phủ lớp chống ẩm và chống trầy nên rất bền và sạch ạ. Mình yên tâm sử dụng nha.",
    ],
    "self_assembly": [
        "Dạ khi nhận hàng mình tự lắp ráp giúp em nha. Bên em có video hướng dẫn từng bước, xem một chút là mình tự lắp được ngay, rất đơn giản ạ.",
        "Dạ sản phẩm bên em là dạng lắp ráp, mình tự hoàn thiện khi nhận hàng giúp em nha. Bên em có video hướng dẫn từng bước trên kênh YouTube của shop, mình xem theo là làm được ngay ạ.",
    ],
    "screwdriver": [
        "Dạ bên em đã khoan sẵn lỗ và tặng kèm ốc vít rồi ạ, mình chỉ cần chuẩn bị một chiếc tua vít là lắp được nha.",
        "Dạ phần ốc vít và lỗ khoan bên em đã chuẩn bị sẵn rồi ạ, mình chỉ cần một chiếc tua vít là có thể lắp ráp dễ dàng nha.",
    ],
    "no_inspect": [
        "Dạ do quy định trước giờ của sàn rồi ạ, nhưng mình yên tâm, nhận có gì không đúng, bên em hỗ trợ đầy đủ theo chính sách của Shopee, quyền lợi của mình vẫn được đảm bảo đầu tiên ạ.",
    ],
}


@dataclass(frozen=True)
class Row:
    name: str
    preview: str
    x: int
    y: int
    unread: int
    raw_text: str


@dataclass(frozen=True)
class ActiveChat:
    name: str
    text: str
    draft: str


@dataclass(frozen=True)
class Decision:
    action: str
    reply: str
    category: str
    reason: str
    confidence: float


@dataclass(frozen=True)
class ProductContext:
    name: str = ""
    code: str = ""


class OpenClaw:
    def __init__(self, profile: str, timeout: int = 30) -> None:
        self.profile = profile
        self.timeout = timeout
        self.executable = find_openclaw()

    def run(self, *args: str, timeout: int | None = None) -> str:
        cmd = [self.executable, "browser", "--browser-profile", self.profile, *args]
        result = subprocess.run(
            cmd,
            cwd=ROOT,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=timeout or self.timeout,
        )
        if result.returncode != 0:
            raise RuntimeError((result.stderr or result.stdout).strip())
        return result.stdout.strip()

    def open_chat(self) -> None:
        self.run("open", URL, timeout=45)
        time.sleep(1.0)

    def rows(self) -> list[Row]:
        data = self.evaluate(
            "() => { const rows=[]; const nodes=Array.from(document.querySelectorAll('div')); "
            "for (const el of nodes) { const text=(el.innerText||'').trim(); const rect=el.getBoundingClientRect(); "
            "if (!text || rect.left>520 || rect.top<120) continue; "
            "if (rect.width<250 || rect.width>420 || rect.height<70 || rect.height>120) continue; "
            "if (!text.includes('Decor')) continue; "
            "const lines=text.split('\\n').map(s=>s.trim()).filter(Boolean); "
            "const name=lines[0]||''; const preview=lines[lines.length-1]||''; if (!name || !preview) continue; "
            "const unreadLine=lines.find(s=>/^[1-9][0-9]*$/.test(s)); const unread=unreadLine?Number(unreadLine):0; "
            "rows.push({name,preview,unread,x:Math.round(rect.left+Math.min(rect.width*0.45,160)),"
            "y:Math.round(rect.top+rect.height/2),h:Math.round(rect.height),text:text.slice(0,700)}); } "
            "const best=new Map(); for (const row of rows) { const key=row.name+'\\n'+row.preview; const old=best.get(key); "
            "if (!old || row.h>old.h) best.set(key,row); } return Array.from(best.values()).slice(0,30); }"
        )
        return [
            Row(
                name=str(item.get("name", "")).strip(),
                preview=str(item.get("preview", "")).strip(),
                x=int(item.get("x", 0)),
                y=int(item.get("y", 0)),
                unread=int(item.get("unread") or 0),
                raw_text=str(item.get("text", "")),
            )
            for item in data
            if item.get("name") and item.get("preview")
        ]

    def click_row(self, row: Row) -> None:
        self.run("click-coords", str(row.x), str(row.y), timeout=20)
        time.sleep(0.7)

    def active_chat(self) -> ActiveChat:
        data = self.evaluate(
            "() => { const ta=document.querySelector('textarea'); const box=(ta && ta.closest('.chat-box')) || document.body; "
            "const ava=box && box.querySelector('img[alt=ava]'); const name=(ava && ava.parentElement && ava.parentElement.innerText) || ''; "
            "return {name:name,text:((box && box.innerText) || '').slice(-5000),draft:(ta && ta.value) || ''}; }"
        )
        return ActiveChat(
            name=str(data.get("name", "")).strip(),
            text=str(data.get("text", "")),
            draft=str(data.get("draft", "")),
        )

    def set_message(self, message: str) -> str:
        data = self.evaluate(
            f"() => {{ const msg={json.dumps(message, ensure_ascii=False)}; const ta=document.querySelector('textarea'); "
            "if (!ta) return {ok:false,value:''}; const setter=Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype,'value').set; "
            "ta.focus(); setter.call(ta,msg); ta.dispatchEvent(new Event('input',{bubbles:true})); return {ok:true,value:ta.value}; }"
        )
        if not data.get("ok"):
            raise RuntimeError("Textarea not found")
        return str(data.get("value", ""))

    def clear_message(self) -> None:
        self.evaluate(
            "() => { const ta=document.querySelector('textarea'); if (!ta) return false; "
            "const setter=Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype,'value').set; "
            "setter.call(ta,''); ta.dispatchEvent(new Event('input',{bubbles:true})); return true; }"
        )

    def send_enter(self) -> None:
        self.run("press", "Enter", timeout=20)

    def evaluate(self, fn: str) -> Any:
        output = self.run("evaluate", "--fn", fn, timeout=30)
        try:
            return json.loads(output)
        except json.JSONDecodeError:
            return output


def find_openclaw() -> str:
    for name in ("openclaw.cmd", "openclaw.exe", "openclaw"):
        path = shutil.which(name)
        if path:
            return path
    npm_path = Path.home() / "AppData" / "Roaming" / "npm" / "openclaw.cmd"
    if npm_path.exists():
        return str(npm_path)
    raise RuntimeError("openclaw executable not found in PATH")


def fix_mojibake(text: str) -> str:
    try:
        fixed = text.encode("latin1").decode("utf-8")
    except UnicodeError:
        return text
    if any(mark in fixed for mark in ("ạ", "ư", "đ", "Đ", "❤️")):
        return fixed
    return text


def strip_accents(text: str) -> str:
    text = fix_mojibake(text).replace("đ", "d").replace("Đ", "D")
    normalized = unicodedata.normalize("NFD", text)
    return "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")


def norm(text: str) -> str:
    return " ".join(strip_accents(text).lower().strip().split())


def is_shop_preview(preview: str) -> bool:
    p = norm(preview)
    return any(p.startswith(prefix) for prefix in SHOP_PREFIXES)


def load_processed() -> set[str]:
    if not STATE_PATH.exists():
        return set()
    try:
        data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return set()
    return set(data.get("processed", []))


def save_processed(processed: set[str]) -> None:
    LOG_DIR.mkdir(exist_ok=True)
    STATE_PATH.write_text(
        json.dumps({"processed": sorted(processed)[-1000:]}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def key_for(row: Row) -> str:
    return f"{row.name}|{row.preview}"


def safety_block_reason(reply: str) -> str | None:
    text = norm(reply)
    for pattern in HARD_BLOCK_PATTERNS:
        if re.search(pattern, text):
            if "youtube.com" in text or "youtu.be" in text:
                if pattern in {r"\bzalo\b", r"\bfacebook\b"}:
                    return f"blocked keyword: {pattern}"
            return f"blocked keyword: {pattern}"
    if len(reply) > 900:
        return "reply too long"
    if not text.startswith(("da", "minh", "em", "co")):
        return "reply does not match shop style"
    return None


def preview_skip_reason(preview: str) -> str | None:
    """If the preview alone signals a case the bot must not auto-touch,
    return the reason. The caller will skip *without* clicking — that keeps
    the unread badge intact for a human."""
    if not preview:
        return None
    text = norm(preview)
    for pattern in PREVIEW_SKIP_PATTERNS:
        if re.search(pattern, text):
            return f"preview skip: {pattern}"
    return None


def pick_variant(category: str, seed: str) -> str:
    options = REPLY_VARIATIONS.get(category) or []
    if not options:
        return ""
    digest = hashlib.md5(seed.encode("utf-8", errors="replace")).digest()
    index = int.from_bytes(digest[:4], "big") % len(options)
    return options[index]


def variant_seed(row_name: str) -> str:
    return f"{row_name}|{datetime.now().strftime('%Y%m%d')}"


def extract_product_code(text: str) -> str | None:
    match = re.search(r"\b(?:TAGO\s*)?(ND\d{1,3})\b", text, flags=re.IGNORECASE)
    if match:
        return match.group(1).upper()
    return None


def extract_product_context(text: str) -> ProductContext:
    fixed = fix_mojibake(text)
    lines = [line.strip() for line in fixed.splitlines() if line.strip()]
    candidates: list[str] = []

    for index, line in enumerate(lines):
        normalized = norm(line)
        if normalized not in {
            "thong tin don hang",
            "san pham goi y",
            "nguoi dung trao doi thong tin don hang",
        }:
            continue

        for candidate in lines[index + 1 : index + 8]:
            if looks_like_product_name(candidate):
                candidates.append(candidate)
                break

    if not candidates:
        for line in lines:
            if looks_like_product_name(line):
                candidates.append(line)

    if not candidates:
        return ProductContext()

    product_name = max(candidates, key=len)
    return ProductContext(name=product_name, code=extract_product_code(product_name) or "")


def looks_like_product_name(line: str) -> bool:
    normalized = norm(line)
    if len(normalized) < 12:
        return False
    if normalized.startswith(("ma:", "gia", "tago.furniture", "shop tago", "nguoi dung")):
        return False
    if normalized in {"dang giao", "dang dong goi", "thanh cong", "moi", "da huy"}:
        return False
    if re.match(r"^\d{2}/\d{2}/\d{4}", normalized):
        return False
    return any(word in normalized for word in ("ban", "ke", "tu", "go", "mdf", "nd"))


def product_note(chat_text: str) -> str:
    product = extract_product_context(chat_text)
    if not product.name:
        return "Salework khong hien ro san pham trong ngu canh dang doc."
    code = f" Ma san pham thay duoc: {product.code}." if product.code else ""
    return f"Salework dang hien thi san pham: {product.name}.{code} Khong hoi khach gui lai ma/ten san pham neu thong tin nay da co trong ngu canh."


def quick_decision(
    customer_text: str,
    chat_text: str,
    seed: str | None = None,
) -> Decision | None:
    """Pattern-based classifier. Returns a Decision the safety filter will
    accept, or None if no rule applied. The seed parameter selects which
    phrasing variant to use (per-customer-per-day stability)."""
    t = norm(customer_text)
    full = norm(chat_text)
    code = extract_product_code(chat_text)
    product = extract_product_context(chat_text)
    product_name = norm(product.name)
    s = seed or customer_text

    if any(word in t for word in ["stk", "so tai khoan", "qr", "chuyen khoan", "bank", "the ngan hang", "mb bank", "tk ngan hang"]):
        return Decision(
            "send",
            pick_variant("policy_payment", s),
            "policy_payment",
            "bank/private payment mention",
            0.95,
        )

    if any(word in t for word in ["cam on", "thank", "thanks", "tks", "tk em", "tk shop", " ok ", "okie", "okay", "vang a", " vang ", "da nhe"]) or t in {"ok", "okie", "okay", "vang"}:
        return Decision("send", pick_variant("thanks", s), "thanks", "simple thanks", 0.9)

    if t in {"hi", "hello", "alo", "shop oi", "shop oi shop", "shop", "em oi", "alo shop", "chao shop", "shop con day k", "shop co o do k"}:
        return Decision("send", pick_variant("greeting", s), "greeting", "greeting", 0.85)

    if any(word in t for word in ["video", "huong dan", "huong dan lap", "lap nhu the nao", "lap nhu nao", "cach lap"]) and not any(b in t for b in ["khong lap", "ko lap"]):
        if code:
            reply = (
                f"Dạ mẫu này mã {code}, mình vào YouTube tìm giúp em: TAGO {code} nha. "
                "Kênh hướng dẫn của shop đây ạ: https://www.youtube.com/@TagoFurniture2412 "
                "Mình xem đúng video theo mã sản phẩm là lắp được ạ."
            )
        else:
            reply = (
                "Dạ mình xem video hướng dẫn ở kênh này giúp em nha: https://www.youtube.com/@TagoFurniture2412 "
                "Mình vào YouTube rồi tìm theo TAGO + mã/tên sản phẩm để ra đúng mẫu mình đang lắp ạ."
            )
        return Decision("send", reply, "assembly_video", "assembly/video request", 0.9)

    if any(word in t for word in ["tua vit", "tua vít", "phu kien", "co tang oc", "co kem oc", "khoan san chua"]):
        return Decision("send", pick_variant("screwdriver", s), "screwdriver", "screwdriver/accessory question", 0.85)

    if any(word in t for word in ["go gi", "chat lieu gi", "lam tu go gi", "go loai gi", "go mdf chua", "co ben khong"]):
        return Decision("send", pick_variant("material_wood", s), "material_wood", "material question", 0.85)

    if any(word in t for word in ["tu lap", "tu rap", "lap san chua", "co lap san chua", "co lap san khong", "co lap san k"]):
        return Decision("send", pick_variant("self_assembly", s), "self_assembly", "self-assembly question", 0.85)

    if any(word in t for word in ["khi nao toi", "bao gio toi", "bao gio den", "khi nao den", "bao lau thi den", "may ngay thi nhan"]):
        return Decision("send", pick_variant("delivery_time", s), "delivery_time", "delivery ETA question", 0.85)

    if any(word in t for word in ["phi ship bao nhieu", "phi van chuyen bao nhieu", "ship cao qua", "phi giao cao", "ship dat the"]):
        return Decision("send", pick_variant("shipping_fee", s), "shipping_fee", "shipping fee question", 0.85)

    if any(word in t for word in ["co dc ktra hang khong", "co duoc ktra hang khong", "co duoc kiem tra hang", "duoc xem hang truoc khi nhan", "co dc xem hang khong"]):
        return Decision("send", pick_variant("no_inspect", s), "no_inspect", "inspect-before-receive question", 0.85)

    if any(word in t for word in ["khong thay goi oc", "ko thay goi oc", "khong co oc", "ko co oc", "thieu oc", "oc vit dau", "goi oc dau", "khong co goi oc"]):
        if any(word in t for word in ["tim may lan", "bo ban ra", "van khong thay", "kiem tra het roi", "ktra het roi", "tim mai khong thay"]):
            reply = pick_variant("missing_screws_confirmed", s)
        else:
            reply = pick_variant("missing_screws_first", s)
        return Decision("send", reply, "missing_screws", "missing screws", 0.9)

    if any(word in t for word in ["xoay oc", "van oc", "kco noi", "khong noi cai", "ko noi", "vit cung", "vit khong vao", "khong van duoc"]):
        return Decision(
            "send",
            pick_variant("tight_screws", s),
            "tight_screws",
            "screw tightening help",
            0.9,
        )

    if any(word in t for word in ["gay", "vo", "hu", "loi", "lech", "thieu hang", "khac phuc", "moc", "tray xuoc", "vet xuoc"]):
        return Decision(
            "send",
            pick_variant("defect_first_step", s),
            "defect_first_step",
            "defect/complaint safe first step",
            0.86,
        )

    if any(word in t for word in ["chua nhan", "khong nhan", "ko nhan", "giao hang", "giao hag", "van chuyen", "don vi", "shipper", "tra hoan", "lau qua", "cham qua", "sao chua giao"]):
        if "dang giao" in full:
            reply = pick_variant("shipping_in_transit", s)
        else:
            reply = pick_variant("shipping_no_status", s)
        return Decision("send", reply, "shipping_status", "shipping/not received", 0.86)

    if any(word in t for word in ["goc", "bo tron", "nhon"]):
        return Decision(
            "send",
            pick_variant("product_corner", s),
            "product_corner",
            "corner shape",
            0.82,
        )

    if any(word in t for word in ["do day", "day bao nhieu", "day mat", "mat ban day"]):
        if "ban" in product_name:
            return Decision(
                "send",
                pick_variant("thickness_table", s),
                "dimension_thickness_table",
                "visible table product, known MDF table thickness",
                0.88,
            )
        if any(word in product_name for word in ["ke", "tu"]):
            return Decision(
                "send",
                pick_variant("thickness_shelf", s),
                "dimension_thickness_shelf",
                "visible shelf/cabinet product, known MDF shelf thickness",
                0.84,
            )

    if "cao bao nhieu" in t or "cao bn" in t:
        if any(word in product_name for word in ["ban gaming", "ban lam viec", "ban hoc dai"]):
            return Decision(
                "send",
                pick_variant("height_table", s),
                "dimension_height_table",
                "visible work/gaming table product",
                0.86,
            )

    if "nang bao nhieu" in t or "bao nhieu kg" in t:
        if "ban" in product_name and any(size in t for size in ["1m2", "120", "1.2"]):
            return Decision(
                "send",
                pick_variant("weight_table_1m2", s),
                "dimension_weight_table",
                "visible table product and requested 1m2 x 60cm",
                0.84,
            )

    if any(word in t for word in ["cao bao nhieu", "cao bn", "kich thuoc", "nang bao nhieu", "bao nhieu kg"]):
        if product.name:
            return Decision(
                "skip",
                "",
                "dimension_visible_but_unknown",
                f"visible product but no trusted dimension rule: {product.name}",
                0.0,
            )
        return Decision("skip", "", "dimension_no_product_context", "no visible product context", 0.0)

    if any(word in t for word in ["huy", "doi dia chi"]):
        return Decision(
            "skip",
            "",
            "cancel_address",
            "cancel/address change needs human or Shopee-only wording",
            0.5,
        )

    return None


async def gemini_decision(customer_text: str, chat_text: str, prompt_text: str) -> Decision:
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or ""
    if not api_key.strip():
        return Decision("skip", "", "config", "missing Gemini API key", 0.0)

    primary_model = (os.getenv("GEMINI_MODEL") or "gemini-2.0-flash").strip() or "gemini-2.0-flash"
    fallback_model = (os.getenv("GEMINI_FALLBACK_MODEL") or "gemini-2.0-flash-lite").strip() or "gemini-2.0-flash-lite"
    temperature = float(os.getenv("GEMINI_TEMPERATURE", "0.2") or "0.2")
    body = {
        "systemInstruction": {
            "parts": [
                {
                    "text": (
                        "Ban la bo loc tra loi Shopee Chat cho shop noi that. "
                        "Chi tra ve JSON hop le. Neu khong chac, action='skip'. "
                        "TUYET DOI khong nhac so tai khoan, QR, chuyen khoan, Zalo, Facebook, sdt, ngoai san, ngoai Shopee. "
                        "TUYET DOI khong hua hoan tien, gui bu, den bu, giam gia, tang qua, ho tro chi phi, ho tro phi ship. "
                        "Khong dung cum 'phi ho tro', 'ho tro lai chi phi', 'gui bu', 'gui don oc', 'hoan lai'. "
                        "Khong yeu cau hoac goi y khach huy don. "
                        "Khong xin lai ma san pham/ma mau neu Salework da hien ro san pham. "
                        "Duoc gui link YouTube huong dan lap san pham cua shop neu khach hoi video/huong dan lap. "
                        "Cau tra loi phai mem, co 'Da', xung 'em', goi khach la 'minh' hoac 'anh/chi'."
                    )
                }
            ]
        },
        "contents": [
            {
                "role": "user",
                "parts": [
                    {
                        "text": f"""
Phong cach shop:
{prompt_text[:9000]}

Thong tin san pham doc duoc tu Salework:
{product_note(chat_text)}

Tin nhan moi nhat cua khach:
{customer_text}

Ngu canh chat gan day:
{chat_text[-3500:]}

Hay tra ve DUY NHAT JSON:
{{
  "action": "send" hoac "skip",
  "reply": "cau tra loi neu action=send",
  "category": "ten_case",
  "reason": "ly do ngan",
  "confidence": 0.0
}}

Chi action=send neu la case de hoac buoc dau an toan: xin loi, xin anh/video, huong dan trong Shopee, hoi lai thong tin, tra loi lap rap/phu kien/video/chat lieu chung.
Neu Salework da hien san pham, khong hoi khach gui lai ma san pham/ma mau/anh mau.
Neu can quyet dinh den bu/gui bu/hoan tien/doi tra/huy don/thong tin rieng/khong chac so do, action=skip.
""".strip()
                    }
                ],
            }
        ],
        "generationConfig": {
            "temperature": temperature,
            "responseMimeType": "application/json",
        },
    }

    models_to_try = [primary_model]
    if fallback_model and fallback_model != primary_model:
        models_to_try.append(fallback_model)

    last_err = "no model attempted"
    for model in models_to_try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        for attempt in range(3):
            try:
                async with httpx.AsyncClient(timeout=25) as client:
                    response = await client.post(url, params={"key": api_key}, json=body)
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code
                last_err = f"Gemini HTTP {status} for model {model}"
                if status in (429, 500, 502, 503, 504) and attempt < 2:
                    await asyncio.sleep(1.5 * (attempt + 1))
                    continue
                break
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_err = f"Gemini transport error for {model}: {exc}"
                if attempt < 2:
                    await asyncio.sleep(1.5 * (attempt + 1))
                    continue
                break

            text = extract_gemini_text(response.json())
            try:
                data = json.loads(extract_json(text))
            except json.JSONDecodeError:
                return Decision("skip", "", "gemini", "non-json response", 0.0)
            return Decision(
                action=str(data.get("action") or "skip").strip().lower(),
                reply=str(data.get("reply") or "").strip(),
                category=str(data.get("category") or "gemini").strip(),
                reason=str(data.get("reason") or "").strip(),
                confidence=safe_float(data.get("confidence"), 0.0),
            )

    return Decision("skip", "", "gemini", last_err, 0.0)


def extract_gemini_text(data: dict[str, Any]) -> str:
    candidates = data.get("candidates") or []
    parts = candidates[0].get("content", {}).get("parts", []) if candidates else []
    return "\n".join(str(part.get("text", "")) for part in parts if isinstance(part, dict)).strip()


def extract_json(text: str) -> str:
    match = re.search(r"```(?:json)?\s*(.*?)```", text, flags=re.DOTALL | re.IGNORECASE)
    if match:
        text = match.group(1)
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        return text[start : end + 1]
    return text


def safe_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def log(line: str) -> None:
    LOG_DIR.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    message = f"[{stamp}] {line}"
    try:
        print(message, flush=True)
    except UnicodeEncodeError:
        safe = message.encode(sys.stdout.encoding or "utf-8", errors="replace").decode(
            sys.stdout.encoding or "utf-8", errors="replace"
        )
        print(safe, flush=True)
    with (LOG_DIR / "salework_gemini_bot.log").open("a", encoding="utf-8") as fh:
        fh.write(message + "\n")


async def decide(
    customer_text: str,
    chat_text: str,
    prompt_text: str,
    use_gemini: bool,
    seed: str,
) -> Decision:
    quick = quick_decision(customer_text, chat_text, seed=seed)
    if quick is not None:
        return quick
    if not use_gemini:
        return Decision("skip", "", "no_rule", "no quick rule matched", 0.0)
    return await gemini_decision(customer_text, chat_text, prompt_text)


def is_handleable_candidate(row: Row, processed: set[str]) -> tuple[bool, str]:
    """Pre-screen from row preview only (NO click). Returns (handleable, reason).
    The bot must not open a chat it cannot reply to — opening clears the
    unread badge and steals the case from a human."""
    if is_shop_preview(row.preview):
        return False, "shop's own message"
    if row.preview in SYSTEM_PREVIEWS:
        return False, f"system attachment preview: {row.preview}"
    if row.preview.startswith("Trang:"):
        return False, "page header preview"
    if key_for(row) in processed:
        return False, "already processed"
    reason = preview_skip_reason(row.preview)
    if reason:
        return False, reason
    return True, ""


def find_row_by_name(rows: list[Row], name: str) -> Row | None:
    for row in rows:
        if row.name == name:
            return row
    return None


async def process_once(claw: OpenClaw, prompt_text: str, processed: set[str], args: argparse.Namespace) -> int:
    sent = 0
    rows = claw.rows()
    candidates: list[Row] = []
    skipped_no_click = 0
    for row in rows:
        ok, reason = is_handleable_candidate(row, processed)
        if not ok:
            if reason and reason != "already processed" and reason != "shop's own message":
                skipped_no_click += 1
                log(f"SKIP_NOCLICK {row.name}: {reason}")
            continue
        candidates.append(row)

    log(f"visible_rows={len(rows)} candidates={len(candidates)} skipped_no_click={skipped_no_click}")

    processed_dirty = False

    for row in candidates[: args.max_candidates]:
        if sent >= args.max_send:
            break

        # Refresh row coordinates — the chat list re-orders after every send,
        # so the (x,y) we captured at the start may now point to a different
        # conversation. Look the row up again by name before clicking.
        fresh_rows = claw.rows() if sent > 0 else rows
        fresh_row = find_row_by_name(fresh_rows, row.name) if sent > 0 else row
        if fresh_row is None:
            log(f"SKIP {row.name}: row no longer visible after reorder")
            continue
        row = fresh_row

        row_key = key_for(row)
        try:
            claw.click_row(row)
            active = claw.active_chat()
        except Exception as exc:
            log(f"SKIP {row.name}: click/read failed: {exc}")
            continue

        if active.name and row.name not in active.name:
            log(f"SKIP {row.name}: active chat mismatch -> {active.name!r}")
            continue
        if active.draft.strip():
            log(f"SKIP {row.name}: textarea already has draft")
            continue

        seed = variant_seed(row.name)
        decision = await decide(row.preview, active.text, prompt_text, args.use_gemini, seed=seed)
        decision = Decision(
            action=decision.action,
            reply=fix_mojibake(decision.reply).strip(),
            category=decision.category,
            reason=decision.reason,
            confidence=decision.confidence,
        )
        if decision.action != "send" or not decision.reply:
            log(f"SKIP {row.name}: {decision.category} | {decision.reason}")
            # Only mark as processed when the decision is *definitive* (no
            # rule applies / outside scope), not when it's a transient
            # Gemini/network failure — otherwise we'd silently drop a chat
            # we could later answer.
            transient = decision.category in {"gemini", "config"} and "HTTP" in (decision.reason or "")
            transient = transient or decision.reason == "missing Gemini API key"
            if not transient and not args.dry_run:
                processed.add(row_key)
                processed_dirty = True
            continue

        block = safety_block_reason(decision.reply)
        if block:
            log(f"SKIP {row.name}: safety block {block} | reply={decision.reply!r}")
            # Safety-blocked reply: don't send and don't mark processed.
            # We want the case to remain unread for a human to handle.
            continue

        if args.dry_run:
            log(f"DRY {row.name}: {decision.category} | {decision.reply}")
            sent += 1
            continue

        try:
            value = claw.set_message(decision.reply)
            if value.strip() != decision.reply.strip():
                log(f"SKIP {row.name}: textarea value mismatch")
                continue
            # Final safety re-check on the actual textarea contents.
            final_block = safety_block_reason(value)
            if final_block:
                log(f"SKIP {row.name}: textarea safety block {final_block}")
                try:
                    claw.clear_message()
                except Exception:
                    pass
                continue
            claw.send_enter()
        except Exception as exc:
            log(f"SKIP {row.name}: send failed: {exc}")
            continue

        sent += 1
        processed.add(row_key)
        processed_dirty = True
        log(f"SENT {row.name}: {decision.category} | {decision.reply}")
        # Human-like jitter between sends so the cadence doesn't look robotic.
        base = max(0.3, args.after_send_delay)
        time.sleep(base + random.uniform(0, base))

    if processed_dirty and not args.dry_run:
        save_processed(processed)
    return sent


async def main() -> int:
    parser = argparse.ArgumentParser(description="Run Gemini-powered Salework UI auto reply bot.")
    parser.add_argument("--profile", default=os.getenv("OPENCLAW_BROWSER_PROFILE", "edgeremote"))
    parser.add_argument("--max-send", type=int, default=int(os.getenv("SALEWORK_BOT_MAX_SEND", "30")))
    parser.add_argument("--max-candidates", type=int, default=int(os.getenv("SALEWORK_BOT_MAX_CANDIDATES", "12")))
    parser.add_argument("--poll-seconds", type=float, default=float(os.getenv("SALEWORK_BOT_POLL_SECONDS", "6")))
    parser.add_argument("--after-send-delay", type=float, default=float(os.getenv("SALEWORK_BOT_AFTER_SEND_DELAY", "1.2")))
    parser.add_argument("--reopen-every-loops", type=int, default=int(os.getenv("SALEWORK_BOT_REOPEN_EVERY", "200")))
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-gemini", dest="use_gemini", action="store_false")
    parser.set_defaults(use_gemini=True)
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")
    prompt_text = PROMPT_PATH.read_text(encoding="utf-8") if PROMPT_PATH.exists() else ""
    processed = load_processed()
    claw = OpenClaw(args.profile)
    claw.open_chat()

    total_sent = 0
    consecutive_errors = 0
    loops = 0
    log(
        f"START profile={args.profile} max_send={args.max_send} once={args.once} "
        f"dry_run={args.dry_run} gemini={args.use_gemini}"
    )
    while total_sent < args.max_send:
        loops += 1
        try:
            sent = await process_once(claw, prompt_text, processed, args)
            total_sent += sent
            consecutive_errors = 0
        except Exception as exc:
            consecutive_errors += 1
            log(f"ERROR loop ({consecutive_errors}): {exc}\n{traceback.format_exc()}")
            sent = 0
            # Exponential backoff on repeated errors so we don't hammer
            # a broken browser/gateway.
            backoff = min(60.0, 2.0 ** min(consecutive_errors, 6))
            time.sleep(backoff)
            if consecutive_errors >= 5:
                log("WARN reopen chat after repeated errors")
                try:
                    claw.open_chat()
                except Exception as reopen_exc:
                    log(f"ERROR reopen failed: {reopen_exc}")

        if args.once:
            break

        if args.reopen_every_loops > 0 and loops % args.reopen_every_loops == 0:
            log(f"INFO periodic chat refresh after {loops} loops")
            try:
                claw.open_chat()
            except Exception as exc:
                log(f"WARN periodic reopen failed: {exc}")

        if sent == 0:
            jitter = random.uniform(0, max(0.5, args.poll_seconds * 0.3))
            time.sleep(args.poll_seconds + jitter)

    log(f"STOP total_sent={total_sent}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except KeyboardInterrupt:
        log("STOP keyboard interrupt")
        raise SystemExit(130)
