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
from urllib.parse import quote_plus

import httpx
from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[1]
PROMPT_PATH = ROOT / "data" / "salework_ai_prompt.txt"
LOG_DIR = ROOT / "openclaw-logs"
STATE_PATH = LOG_DIR / "salework_gemini_bot_state.json"
URL = "https://chat.salework.net/conversations"
MAX_REPLY_CHARS = 280
DEFAULT_LOOKUP_PROFILE = os.getenv("OPENCLAW_LOOKUP_BROWSER_PROFILE", "edgelookup")
YOUTUBE_GUIDE_URL = "https://www.youtube.com/@TagoFurniture2412"
LOOKUP_NEEDED_CATEGORIES = {
    "dimension_visible_but_unknown",
    "dimension_no_product_context",
    "product_info_lookup_needed",
}

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

ATTACHMENT_MARKERS = SYSTEM_PREVIEWS | {
    "[Image]",
    "[Photo]",
    "[Attachment]",
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
    # Cost/fee/payment amount conversations are human-only.
    r"\bphi\b",
    r"\bphí\b",
    r"\bchi phi\b",
    r"\bchi phí\b",
    r"\btiền\b",
    r"\bbao nhieu tien\b",
    r"\btien (hang|ship|van chuyen|hoan|gui|lai|mat)\b",
    r"\bbao gia\b",
    r"\bgia\b.*\b(bao nhieu|bn|sao|nao|sp|san pham|nay|ko|khong)\b",
    r"\bship\b.*\b(cao|dat|mac|phi|phí|tien|tiền)\b",
    r"\bvan chuyen\b.*\b(phi|phí|tien|tiền|bao nhieu)\b",
    r"\bphi\b.*\bho tro\b",
    r"\bphí\b.*\bhỗ trợ\b",
    r"se ho tro.*(phi|chi phi|tien|ship|van chuyen|gui|bo sung|hoan|doi|den bu)",
    r"(ben em|shop) se ho tro.*(phi|chi phi|tien|ship|van chuyen|gui|bo sung|hoan|doi|den bu)",
    r"se co gang gui",
    r"sẽ cố gắng gửi",
    # Any screw/accessory-related outbound message is human-only.
    r"\boc\b",
    r"\bốc\b",
    r"\bvit\b",
    r"\bvít\b",
    r"\btua vit\b",
    r"\btua vít\b",
    r"\blo khoan\b",
    r"\blỗ khoan\b",
    r"\bkhoan san\b",
    r"\bkhoan sẵn\b",
    r"\bphu kien\b",
    r"\bphụ kiện\b",
    r"\bgoi phu kien\b",
    r"\bgói phụ kiện\b",
    r"\bgoi oc\b",
    r"\bgói ốc\b",
    r"\bthieu phu kien\b",
    r"\bthiếu phụ kiện\b",
    # Missing panels/parts/items are human-only.
    r"\bthieu hang\b",
    r"\bthiếu hàng\b",
    r"\bthieu tam\b",
    r"\bthiếu tấm\b",
    r"\bthieu ngan\b",
    r"\bthiếu ngăn\b",
    r"\bthieu chi tiet\b",
    r"\bthiếu chi tiết\b",
    r"\bthieu bo phan\b",
    r"\bthiếu bộ phận\b",
    r"\bthieu mon\b",
    r"\bthiếu món\b",
    r"\bgiao thieu\b",
    r"\bgiao thiếu\b",
    r"gui don oc",
    r"gửi đơn ốc",
    # Return/refund cases are human-only. Do not let Gemini draft a Shopee
    # return/refund instruction after the case has been opened.
    r"\btra hang\b",
    r"\btrả hàng\b",
    r"\bhoan hang\b",
    r"\bhoàn hàng\b",
    r"\bhoan tien\b",
    r"\bhoàn tiền\b",
    r"\bdoi tra\b",
    r"\bđổi trả\b",
    r"\btra hoan\b",
    r"\btrả hoàn\b",
    r"\brefund\b",
    r"\breturn\b",
    r"hoan lai",
    r"hoàn lại",
    r"cho em xin.*ma",
    r"gui.*ma.*san pham",
    r"ma san pham cu the",
    r"ma mau dang chon",
    # Do not push product lookup work back to the customer. The bot must use
    # visible Salework product context or skip for a human to check.
    r"xem.*mo ta",
    r"phan mo ta",
    r"muc mo ta",
    r"mo ta san pham",
    r"tham khao.*mo ta",
    r"xem chi tiet.*(san pham|shopee|app)",
    r"xem.*live",
    r"live cua shop",
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
    "product_corner": [
        "Dạ mẫu bàn này cạnh xử lý nhẵn, dạng góc vuông chứ không bo tròn lớn ạ.",
        "Dạ mẫu này là góc vuông, cạnh được xử lý nhẵn để dùng đỡ sắc tay ạ.",
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
    "material_wood": [
        "Dạ sản phẩm bên em là gỗ MDF phủ Melamine, bề mặt sạch và dễ lau ạ.",
        "Dạ mẫu này dùng gỗ MDF phủ Melamine, phù hợp nhu cầu sinh hoạt cơ bản ạ.",
    ],
    "self_assembly": [
        f"Dạ sản phẩm là dạng tự lắp ạ. Mình xem video hướng dẫn của shop ở đây giúp em nha: {YOUTUBE_GUIDE_URL}",
        f"Dạ bên em có video hướng dẫn lắp trên kênh YouTube của shop ạ: {YOUTUBE_GUIDE_URL}",
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
        data = self.evaluate(
            f"() => {{ const name={json.dumps(row.name, ensure_ascii=False)}; const preview={json.dumps(row.preview, ensure_ascii=False)}; "
            "const nodes=Array.from(document.querySelectorAll('div')); const matches=[]; "
            "for (const el of nodes) { const text=(el.innerText||'').trim(); const rect=el.getBoundingClientRect(); "
            "if (!text || rect.left>520 || rect.top<120 || rect.width<250 || rect.width>460 || rect.height<45 || rect.height>150) continue; "
            "if (text.includes(name) && text.includes(preview)) matches.push({el,rect,score:rect.height*10-rect.left}); } "
            "matches.sort((a,b)=>b.score-a.score); if (!matches.length) return {ok:false}; "
            "const target=matches[0].el; target.scrollIntoView({block:'center'}); "
            "const r=target.getBoundingClientRect(); return {ok:true,x:Math.round(r.left+r.width/2),y:Math.round(r.top+r.height/2)}; }"
        )
        if isinstance(data, dict) and data.get("ok"):
            self.run("click-coords", str(int(data.get("x", row.x))), str(int(data.get("y", row.y))), timeout=20)
        else:
            self.run("click-coords", str(row.x), str(row.y), timeout=20)
        time.sleep(0.7)

    def active_chat(self) -> ActiveChat:
        data = self.evaluate(
            "() => { const ta=document.querySelector('textarea'); const box=(ta && ta.closest('.chat-box')) || document.body; "
            "const ava=box && box.querySelector('img[alt=ava]'); const name=(ava && ava.parentElement && ava.parentElement.innerText) || ''; "
            "return {name:name,text:((box && box.innerText) || '').slice(-15000),draft:(ta && ta.value) || ''}; }"
        )
        return ActiveChat(
            name=str(data.get("name", "")).strip(),
            text=str(data.get("text", "")),
            draft=str(data.get("draft", "")),
        )

    def active_product_urls(self) -> list[str]:
        data = self.evaluate(
            "() => { const ta=document.querySelector('textarea'); const box=(ta && ta.closest('.chat-box')) || document.body; "
            "return Array.from(box.querySelectorAll('a[href]')).map(a=>a.href).filter(h=>/shopee\\.vn/i.test(h)).slice(-8); }"
        )
        if not isinstance(data, list):
            return []
        seen: set[str] = set()
        urls: list[str] = []
        for item in data:
            url = str(item)
            if url and url not in seen:
                seen.add(url)
                urls.append(url)
        return urls

    def mark_unread_current_chat(self) -> bool:
        js = (
            "() => {"
            "const normalize=(value)=>(value||'').toString().normalize('NFD').replace(/[\\u0300-\\u036f]/g,'').toLowerCase().replace(/đ/g,'d').replace(/\\s+/g,' ').trim();"
            "const visible=(el)=>{const rect=el.getBoundingClientRect();const style=window.getComputedStyle(el);return rect.width>0&&rect.height>0&&style.visibility!=='hidden'&&style.display!=='none';};"
            "const fireClick=(el)=>{if(typeof el.click==='function'){el.click();}else{el.dispatchEvent(new MouseEvent('click',{bubbles:true,cancelable:true,view:window}));}};"
            "const textOf=(el)=>normalize([el.innerText,el.textContent,el.getAttribute('aria-label'),el.getAttribute('title'),el.getAttribute('data-title'),el.getAttribute('data-tooltip'),el.className&&el.className.toString(),el.parentElement&&el.parentElement.getAttribute('aria-label'),el.parentElement&&el.parentElement.getAttribute('title'),el.parentElement&&el.parentElement.innerText].filter(Boolean).join(' '));"
            "const clickableFor=(el)=>el.closest('button,[role=\"button\"],.ant-btn,[class*=\"button\"],[class*=\"icon\"]')||el;"
            "const nodes=Array.from(document.querySelectorAll('button,[role=\"button\"],[aria-label],[title],[data-title],[data-tooltip],svg,i,span,div'));"
            "const matches=[];const seen=new Set();"
            "for(const node of nodes){const clickable=clickableFor(node);if(!clickable||seen.has(clickable)||!visible(clickable))continue;seen.add(clickable);const rect=clickable.getBoundingClientRect();if(rect.top<55||rect.top>190||rect.left<window.innerWidth*0.45)continue;const label=textOf(node)+' '+textOf(clickable);const explicit=label.includes('danh dau la chua doc')||label.includes('danh dau chua doc')||label.includes('chua doc')||label.includes('mark as unread')||label.includes('unread');if(explicit){matches.push({el:clickable,score:1000+rect.left,label});continue;}const maybeEye=(label.includes('eye')||label.includes('visibility')||label.includes('unread'))&&rect.left>window.innerWidth-360&&rect.width<=72&&rect.height<=72;if(maybeEye)matches.push({el:clickable,score:200+rect.left,label});}"
            "matches.sort((a,b)=>b.score-a.score);if(matches.length){fireClick(matches[0].el);return {ok:true,method:'label',label:matches[0].label.slice(0,160)};}"
            "const fallback=Array.from(document.querySelectorAll('button,[role=\"button\"],.ant-btn,[class*=\"icon\"]')).map((el)=>({el,rect:el.getBoundingClientRect(),label:textOf(el)})).filter(({el,rect})=>visible(el)&&rect.top>=55&&rect.top<=175&&rect.left>=window.innerWidth-320&&rect.width<=72&&rect.height<=72).sort((a,b)=>b.rect.left-a.rect.left);"
            "if(fallback.length){fireClick(fallback[0].el);return {ok:true,method:'top-right-fallback',label:fallback[0].label.slice(0,160)};}"
            "return {ok:false,method:'not-found'};"
            "}"
        )
        data = self.evaluate(js)
        if isinstance(data, dict) and data.get("ok"):
            time.sleep(0.3)
            return True
        return False

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


def restart_openclaw_gateway() -> None:
    executable = find_openclaw()
    subprocess.run(
        [executable, "gateway", "restart"],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=120,
    )
    time.sleep(5.0)


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


def is_video_request(text: str) -> bool:
    t = norm(text)
    return any(
        word in t
        for word in (
            "video",
            "clip",
            "huong dan",
            "huong dan lap",
            "huong dan rap",
            "huong dan su dung",
            "hdsd",
            "hd lap",
            "hd rap",
            "cach lap",
            "cach rap",
            "day lap",
            "day rap",
            "video hd",
            "xin vd",
            "xem cach lap",
            "lap nhu the nao",
            "lap nhu nao",
            "lap tu",
            "lap ke",
            "lap ban",
            "rap tu",
            "rap ke",
            "rap ban",
        )
    ) and not any(block in t for block in ("khong lap", "ko lap"))


def is_send_reference_request(text: str) -> bool:
    """Customer is likely saying "send it here" after a previous request.

    This is only a permission to open the conversation and inspect recent
    context; quick_decision still requires recent video/assembly context before
    sending anything.
    """
    t = norm(text)
    if not t:
        return False
    blocked_context = (
        "gap",
        "don",
        "hang",
        "ship",
        "giao",
        "tien",
        "phi",
        "gia",
        "oc",
        "vit",
        "phu kien",
        "thieu",
        "loi",
        "vo",
        "gay",
        "hong",
        "tra",
        "hoan",
        "bu",
        "stk",
        "tai khoan",
        "zalo",
        "sdt",
    )
    if any(re.search(rf"\b{re.escape(block)}\b", t) for block in blocked_context):
        return False
    patterns = (
        r"\b(b|ban|shop)\s+gui\s+(minh|em|e|cho minh|cho em|qua day)\b",
        r"\bgui\s+(minh|em|e|cho minh|cho em|qua day)\b",
        r"\bgui\s+qua\s+day\b",
        r"\bcho\s+(minh|em|e)\s+xin\s+(link|video|clip)?\b",
        r"\bshop\s+gui\s+qua\b",
        r"\bshop\s+gui\s+cho\s+(minh|em|e)\b",
    )
    return any(re.search(pattern, t) for pattern in patterns)


def is_short_followup_request(text: str) -> bool:
    """Short nudge after a previous message, e.g. "shop ơiiii" or "gấp giúp em".

    This only permits opening the chat to inspect recent context. The bot still
    sends only if the recent context contains a video/assembly request.
    """
    t = norm(text)
    if not t or len(t) > 45:
        return False
    blocked_words = (
        "don",
        "hang",
        "ship",
        "giao",
        "tien",
        "phi",
        "gia",
        "oc",
        "vit",
        "phu kien",
        "thieu",
        "loi",
        "vo",
        "gay",
        "hong",
        "tra",
        "hoan",
        "bu",
        "stk",
        "tai khoan",
        "zalo",
        "sdt",
    )
    if any(re.search(rf"\b{re.escape(word)}\b", t) for word in blocked_words):
        return False
    patterns = (
        r"\bshop o+i{2,}\b",
        r"\balo{2,}\b",
        r"\brep\s+(em|e|minh)\b",
        r"\btra loi\s+(em|e|minh)\b",
        r"\bgap giup\s+(em|e|minh)\b",
        r"\bgiup\s+(em|e|minh)\s*(a|voi|nha)?\b",
    )
    return any(re.search(pattern, t) for pattern in patterns)


def recent_chat_context(text: str, line_limit: int = 20) -> str:
    lines = [line.strip() for line in fix_mojibake(text).splitlines() if line.strip()]
    return "\n".join(lines[-line_limit:])


def is_dimension_question(text: str) -> bool:
    t = norm(text)
    return any(
        word in t
        for word in (
            "kich thuoc",
            "size",
            "so do",
            "chieu dai",
            "dai bao nhieu",
            "chieu rong",
            "rong bao nhieu",
            "chieu cao",
            "cao bao nhieu",
            "cao bn",
            "chieu sau",
            "sau bao nhieu",
            "do day",
            "day bao nhieu",
            "day mat",
            "mat ban day",
            "nang bao nhieu",
            "bao nhieu kg",
        )
    )


def is_product_info_request(text: str) -> bool:
    t = norm(text)
    if is_video_request(t) or is_dimension_question(t):
        return True
    return any(
        word in t
        for word in (
            "go gi",
            "chat lieu",
            "lam tu go",
            "go loai",
            "mdf",
            "melamine",
            "mau gi",
            "mau nao",
            "co mau",
            "f hau",
            "f.hau",
            "kin lung",
            "co hau",
            "hau lung",
            "may tang",
            "bao nhieu tang",
            "may ngan",
            "bao nhieu ngan",
            "tai trong",
            "chiu luc",
            "bo tron",
            "goc",
            "nhon",
            "tu lap",
            "tu rap",
            "lap rap",
            "lap san",
        )
    )


def is_shop_preview(preview: str) -> bool:
    p = norm(preview)
    return any(p.startswith(prefix) for prefix in SHOP_PREFIXES)


def load_processed() -> set[str]:
    return load_state_set("processed")


def load_human_only() -> set[str]:
    return load_state_set("human_only")


def load_state_set(key: str) -> set[str]:
    if not STATE_PATH.exists():
        return set()
    try:
        data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return set()
    return set(data.get(key, []))


def save_state(processed: set[str], human_only: set[str]) -> None:
    LOG_DIR.mkdir(exist_ok=True)
    STATE_PATH.write_text(
        json.dumps(
            {
                "processed": sorted(processed)[-1000:],
                "human_only": sorted(human_only)[-1000:],
            },
            ensure_ascii=False,
            indent=2,
        ),
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
    missing_reason = missing_item_reason(text)
    if missing_reason:
        return missing_reason
    if len(reply) > MAX_REPLY_CHARS:
        return "reply too long"
    if not text.startswith(("da", "minh", "em", "co")):
        return "reply does not match shop style"
    return None


def attachment_related_reason(text: str) -> str | None:
    fixed = fix_mojibake(text)
    normalized = norm(fixed)
    if any(marker in fixed for marker in ATTACHMENT_MARKERS):
        return "image/attachment case: human only"
    if re.search(r"\[(hinh anh|image|photo|attachment|tep tin|file|voice|gif)\]", normalized):
        return "image/attachment case: human only"
    return None


def private_payment_reason(text: str) -> str | None:
    normalized = norm(text)
    patterns = (
        r"\bstk\b",
        r"\bso tai khoan\b",
        r"\bchuyen khoan\b",
        r"\bbank\b",
        r"\bqr\b",
        r"\bzalo\b",
        r"\bfacebook\b",
        r"\bsdt\b",
        r"\bso dien thoai\b",
        r"\bngoai san\b",
        r"\bship ngoai\b",
    )
    for pattern in patterns:
        if re.search(pattern, normalized):
            return "private payment/contact case: human only"
    return None


def complaint_or_defect_reason(text: str) -> str | None:
    normalized = norm(text)
    patterns = (
        r"\bsai mau\b",
        r"\bkhac mau\b",
        r"\bmau khac\b",
        r"\bgiao mau khac\b",
        r"\bshop giao mau khac\b",
        r"\bkhong dung mau\b",
        r"\bk dung mau\b",
        r"\bko dung mau\b",
        r"\bdoi tra\b",
        r"\bthat vong\b",
        r"\buong tien\b",
        r"\bqua met\b",
        r"\bmet qua\b",
        r"\bchat luong\b.*\b(kem|thap|te)\b",
        r"\bdo hoan thien\b.*\b(kem|thap|te)\b",
        r"\bsut\b",
        r"\bvo\b",
        r"\bme\b",
        r"\bnut\b",
        r"\bgay\b",
        r"\bhong\b",
        r"\bloi\b",
        r"\bye?u\b",
        r"\bchan tu ye?u\b",
        r"\bkeo ra\b.*\b(kho|khong duoc|k duoc|ko duoc)\b",
        r"\bday vao\b.*\b(kho|khong duoc|k duoc|ko duoc)\b",
        r"\bkhong keo ra\b",
        r"\bk keo ra\b",
        r"\bko keo ra\b",
        r"\bshop gui hang co ktra\b",
        r"\bco ktra k\b",
        r"\bco kiem tra k\b",
    )
    for pattern in patterns:
        if re.search(pattern, normalized):
            return "complaint/defect case: human only"
    return None


def preview_skip_reason(preview: str) -> str | None:
    """If the preview alone signals a case the bot must not auto-touch,
    return the reason. The caller will skip *without* clicking — that keeps
    the unread badge intact for a human."""
    if not preview:
        return None
    attachment_reason = attachment_related_reason(preview)
    if attachment_reason:
        return attachment_reason
    text = norm(preview)
    private_reason = private_payment_reason(text)
    if private_reason:
        return private_reason
    cost_reason = cost_related_reason(text)
    if cost_reason:
        return cost_reason
    return_reason = return_related_reason(text)
    if return_reason:
        return return_reason
    complaint_reason = complaint_or_defect_reason(text)
    if complaint_reason:
        return complaint_reason
    missing_reason = missing_item_reason(text)
    if missing_reason:
        return missing_reason
    screw_reason = screw_related_reason(text)
    if screw_reason:
        return screw_reason
    for pattern in PREVIEW_SKIP_PATTERNS:
        if re.search(pattern, text):
            return f"preview skip: {pattern}"
    if is_send_reference_request(text) or is_short_followup_request(text):
        return None
    if not is_product_info_request(text):
        return "outside product-info scope"
    return None


def cost_related_reason(text: str) -> str | None:
    normalized = norm(text)
    cost_patterns = (
        r"\bphi\b",
        r"\bchi phi\b",
        r"\bphu phi\b",
        r"\bphi hu\b",
        r"\bbao nhieu tien\b",
        r"\btien hang\b",
        r"\btien ship\b",
        r"\btien van chuyen\b",
        r"\bbao gia\b",
        r"\bgia\b.*\b(bao nhieu|bn|sao|nao|sp|san pham|nay|a|ko|khong)\b",
        r"\b(bao nhieu|bn)\b.*\bgia\b",
        r"\bton bao nhieu\b",
        r"\bmat bao nhieu\b",
        r"\bmat phi\b",
        r"\bship cao\b",
        r"\bship dat\b",
        r"\bphi ship\b",
        r"\bphi van chuyen\b",
        r"\bho tro phi\b",
        r"\bho tro chi phi\b",
        r"\bden bu\b",
        r"\bboi thuong\b",
    )
    for pattern in cost_patterns:
        if re.search(pattern, normalized):
            return "cost/fee case: human only"
    return None


def return_related_reason(text: str) -> str | None:
    normalized = norm(text)
    return_patterns = (
        r"\btra hang\b",
        r"\bhoan hang\b",
        r"\bhoan tien\b",
        r"\bdoi tra\b",
        r"\btra hoan\b",
        r"\bye?u cau.*\bhoan\b",
        r"\bye?u cau.*\btra\b",
        r"\bkhieu nai.*\bhoan\b",
        r"\brefund\b",
        r"\breturn\b",
    )
    for pattern in return_patterns:
        if re.search(pattern, normalized):
            return "return/refund case: human only"
    return None


def missing_item_reason(text: str) -> str | None:
    normalized = norm(text)
    part_words = (
        "tam ngan",
        "bo phan",
        "chi tiet",
        "mat ban",
        "canh tu",
        "chan ban",
        "tam",
        "ngan",
        "van",
        "mieng",
        "thanh",
        "hang",
        "do",
        "mon",
        "cai",
        "canh",
        "chan",
        "mat",
        "hau",
        "lung",
        "ke",
        "tu",
        "go",
        "mdf",
    )
    part_pattern = "|".join(re.escape(word) for word in part_words)
    missing_patterns = (
        rf"\bthieu(?:\s+\w+){{0,4}}\s+({part_pattern})\b",
        rf"\bbi thieu(?:\s+\w+){{0,4}}\s+({part_pattern})\b",
        rf"\bgiao thieu(?:\s+\w+){{0,4}}\s+({part_pattern})\b",
        rf"\bshop gui thieu(?:\s+\w+){{0,4}}\s+({part_pattern})\b",
        rf"\bkhong thay(?:\s+\w+){{0,4}}\s+({part_pattern})\b",
        rf"\bkhong co(?:\s+\w+){{0,4}}\s+({part_pattern})\b",
        rf"\bko thay(?:\s+\w+){{0,4}}\s+({part_pattern})\b",
        rf"\bko co(?:\s+\w+){{0,4}}\s+({part_pattern})\b",
    )
    for pattern in missing_patterns:
        if re.search(pattern, normalized):
            return "missing item/part case: human only"
    return None


def screw_related_reason(text: str) -> str | None:
    normalized = norm(text)
    screw_patterns = (
        r"\boc\b",
        r"\bvit\b",
        r"\btua vit\b",
        r"\blo vit\b",
        r"\blo khoan\b",
        r"\bkhoan san\b",
        r"\bphu kien\b",
        r"\bgoi phu kien\b",
        r"\bthieu phu kien\b",
        r"\bbu long\b",
        r"\bbulong\b",
        r"\bdinh\b",
        r"\bgoi oc\b",
        r"\bthieu oc\b",
        r"\boc vit\b",
    )
    for pattern in screw_patterns:
        if re.search(pattern, normalized):
            return "screw-related case: human only"
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
        return (
            "Salework khong hien ro san pham trong ngu canh dang doc. "
            "Khong bat khach tu xem mo ta san pham; neu can thong tin san pham chinh xac thi action=skip."
        )
    code = f" Ma san pham thay duoc: {product.code}." if product.code else ""
    return (
        f"Salework dang hien thi san pham: {product.name}.{code} "
        "Tu dung thong tin san pham nay de tra loi. "
        "Khong hoi khach gui lai ma/ten san pham va khong bao khach tu xem mo ta/live neu thong tin nay da co trong ngu canh."
    )


def shorten_reply(reply: str, max_chars: int = MAX_REPLY_CHARS) -> str:
    text = " ".join(fix_mojibake(reply).split()).strip()
    if len(text) <= max_chars:
        return text
    parts = re.split(r"(?<=[.!?ạ])\s+", text)
    candidate = " ".join(parts[:2]).strip()
    if candidate and len(candidate) <= max_chars:
        return candidate
    cut = text[:max_chars].rsplit(" ", 1)[0].rstrip(" ,.;")
    if not cut.endswith(("ạ", "nha", "nhé", ".", "!", "?")):
        cut += " ạ"
    return cut


def clean_description_line(line: str) -> str:
    line = " ".join(fix_mojibake(line).split()).strip(" -:|")
    return line[:220].strip()


def line_has_price_or_policy(line: str) -> bool:
    normalized = norm(line)
    return any(
        word in normalized
        for word in (
            "gia",
            "phi",
            "voucher",
            "freeship",
            "hoan tien",
            "tra hang",
            "bao hanh",
            "lien he",
            "zalo",
            "facebook",
            "sdt",
        )
    )


def extract_dimension_answer(description_text: str, question: str = "") -> str | None:
    fixed = fix_mojibake(description_text)
    q = norm(question)
    lines = [clean_description_line(line) for line in fixed.splitlines()]
    lines = [line for line in lines if line and not line_has_price_or_policy(line)]
    scope = "\n".join(lines)

    if "cao" in q:
        match = re.search(r"(?:cao|chiều cao|chieu cao)\s*[:\-]?\s*([0-9]+(?:[,.][0-9]+)?\s*(?:cm|mm|m))", scope, flags=re.IGNORECASE)
        if match:
            return f"Dạ mẫu này cao khoảng {match.group(1).replace(' ', '')} ạ."
    if "rong" in q:
        match = re.search(r"(?:rộng|rong|chiều rộng|chieu rong)\s*[:\-]?\s*([0-9]+(?:[,.][0-9]+)?\s*(?:cm|mm|m))", scope, flags=re.IGNORECASE)
        if match:
            return f"Dạ mẫu này rộng khoảng {match.group(1).replace(' ', '')} ạ."
    if "dai" in q:
        match = re.search(r"(?:dài|dai|chiều dài|chieu dai)\s*[:\-]?\s*([0-9]+(?:[,.][0-9]+)?\s*(?:cm|mm|m))", scope, flags=re.IGNORECASE)
        if match:
            return f"Dạ mẫu này dài khoảng {match.group(1).replace(' ', '')} ạ."
    if "sau" in q:
        match = re.search(r"(?:sâu|sau|chiều sâu|chieu sau)\s*[:\-]?\s*([0-9]+(?:[,.][0-9]+)?\s*(?:cm|mm|m))", scope, flags=re.IGNORECASE)
        if match:
            return f"Dạ mẫu này sâu khoảng {match.group(1).replace(' ', '')} ạ."
    if "day" in q:
        match = re.search(r"(?:dày|day|độ dày|do day)\s*[:\-]?\s*([0-9]+(?:[,.][0-9]+)?\s*(?:cm|mm|m))", scope, flags=re.IGNORECASE)
        if match:
            return f"Dạ mẫu này dày khoảng {match.group(1).replace(' ', '')} ạ."
    if "kg" in q or "nang" in q:
        match = re.search(r"(?:nặng|nang|khối lượng|khoi luong)\s*[:\-]?\s*([0-9]+(?:[,.][0-9]+)?(?:\s*[-–]\s*[0-9]+(?:[,.][0-9]+)?)?\s*kg)", scope, flags=re.IGNORECASE)
        if match:
            return f"Dạ mẫu này nặng khoảng {match.group(1).replace(' ', '')} ạ."

    size_patterns = (
        r"(?:kích thước|kich thuoc|size|kt)\s*[:\-]?\s*([0-9]+(?:[,.][0-9]+)?\s*(?:cm|mm|m)?\s*[x×]\s*[0-9]+(?:[,.][0-9]+)?\s*(?:cm|mm|m)?(?:\s*[x×]\s*[0-9]+(?:[,.][0-9]+)?\s*(?:cm|mm|m)?)?)",
        r"\b([0-9]+(?:[,.][0-9]+)?\s*(?:cm|mm|m)\s*[x×]\s*[0-9]+(?:[,.][0-9]+)?\s*(?:cm|mm|m)(?:\s*[x×]\s*[0-9]+(?:[,.][0-9]+)?\s*(?:cm|mm|m))?)\b",
        r"\b([0-9]+m[0-9]?\s*[x×]\s*[0-9]+(?:[,.][0-9]+)?\s*cm(?:\s*[x×]\s*[0-9]+(?:[,.][0-9]+)?\s*cm)?)\b",
    )
    for pattern in size_patterns:
        match = re.search(pattern, scope, flags=re.IGNORECASE)
        if match:
            value = " ".join(match.group(1).split())
            return f"Dạ kích thước mẫu này khoảng {value} ạ."
    return None


def extract_description_fact_answer(description_text: str, question: str) -> str | None:
    q = norm(question)
    fixed = fix_mojibake(description_text)
    lines = [clean_description_line(line) for line in fixed.splitlines()]
    lines = [line for line in lines if line and not line_has_price_or_policy(line)]

    topic_terms: tuple[str, ...]
    if any(term in q for term in ("chat lieu", "go gi", "go loai", "mdf", "melamine")):
        topic_terms = ("chất liệu", "chat lieu", "mdf", "melamine", "gỗ", "go")
    elif any(term in q for term in ("mau", "màu")):
        topic_terms = ("màu", "mau", "trắng", "den", "đen", "vân", "van")
    elif any(term in q for term in ("hau", "kin lung", "f hau", "f.hau")):
        topic_terms = ("hậu", "hau", "lưng", "lung", "kín lưng", "kin lung")
    elif any(term in q for term in ("tang", "ngan")):
        topic_terms = ("tầng", "tang", "ngăn", "ngan")
    elif any(term in q for term in ("tai trong", "chiu luc")):
        topic_terms = ("tải trọng", "tai trong", "chịu lực", "chiu luc")
    elif any(term in q for term in ("goc", "bo tron", "nhon")):
        topic_terms = ("góc", "goc", "bo", "cạnh", "canh")
    else:
        return None

    for line in lines:
        normalized = norm(line)
        if any(norm(term) in normalized for term in topic_terms) and len(line) <= 180:
            return shorten_reply(f"Dạ theo thông tin sản phẩm, {line[0].lower() + line[1:] if line else line} ạ.")
    return None


def answer_from_product_description(description_text: str, question: str) -> str | None:
    if is_dimension_question(question):
        answer = extract_dimension_answer(description_text, question)
        if answer:
            return shorten_reply(answer)
    answer = extract_description_fact_answer(description_text, question)
    if answer:
        return shorten_reply(answer)
    return None


def read_shopee_page(claw: OpenClaw, url: str) -> dict[str, Any]:
    claw.run("open", url, timeout=45)
    time.sleep(5.0)
    data = claw.evaluate(
        "() => { const links=Array.from(document.querySelectorAll('a[href]')).map(a=>a.href)"
        ".filter(h=>/shopee\\.vn/i.test(h)).slice(0,30); "
        "return {url:location.href,title:document.title,text:(document.body && document.body.innerText || '').slice(0,60000),links}; }"
    )
    return data if isinstance(data, dict) else {"url": url, "title": "", "text": "", "links": []}


def lookup_product_answer(
    lookup_claw: OpenClaw | None,
    product: ProductContext,
    question: str,
    product_urls: list[str],
) -> str | None:
    if lookup_claw is None:
        return None
    urls = [url for url in product_urls if "shopee.vn" in url]
    if not urls and (product.name or product.code):
        query = " ".join(part for part in (product.code, product.name) if part).strip()
        urls.append("https://shopee.vn/search?keyword=" + quote_plus(query))
    if not urls:
        return None

    for url in urls[:3]:
        try:
            page = read_shopee_page(lookup_claw, url)
            text = str(page.get("text", ""))
            normalized = norm(text[:2000])
            if any(word in normalized for word in ("captcha", "xac minh", "verify", "robot")):
                continue
            answer = answer_from_product_description(text, question)
            if answer:
                return answer
            if "/search" in str(page.get("url", "")):
                links = [str(link) for link in page.get("links", []) if "/product/" in str(link) or "-i." in str(link)]
                for link in links[:3]:
                    page = read_shopee_page(lookup_claw, link)
                    answer = answer_from_product_description(str(page.get("text", "")), question)
                    if answer:
                        return answer
        except Exception as exc:
            log(f"WARN lookup failed for {url}: {exc}")
            continue
    return None


def quick_decision(
    customer_text: str,
    chat_text: str,
    seed: str | None = None,
) -> Decision | None:
    """Pattern-based classifier. Returns a Decision the safety filter will
    accept, or None if no rule applied. The seed parameter selects which
    phrasing variant to use (per-customer-per-day stability)."""
    t = norm(customer_text)
    code = extract_product_code(chat_text)
    product = extract_product_context(chat_text)
    product_name = norm(product.name)
    s = seed or customer_text

    recent_context = recent_chat_context(chat_text)
    recent_scope = f"{customer_text}\n{recent_context}"
    attachment_reason = attachment_related_reason(recent_scope)
    if attachment_reason:
        return Decision("skip", "", "attachment", attachment_reason, 1.0)

    private_reason = private_payment_reason(customer_text)
    if private_reason:
        return Decision("skip", "", "private_payment", private_reason, 1.0)

    return_reason = return_related_reason(customer_text)
    if return_reason:
        return Decision("skip", "", "return_refund", return_reason, 1.0)

    complaint_reason = complaint_or_defect_reason(recent_scope)
    if complaint_reason:
        return Decision("skip", "", "complaint_defect", complaint_reason, 1.0)

    cost_reason = cost_related_reason(customer_text)
    if cost_reason:
        return Decision("skip", "", "cost_fee", cost_reason, 1.0)

    missing_reason = missing_item_reason(recent_scope)
    if missing_reason:
        return Decision("skip", "", "missing_item", missing_reason, 1.0)

    screw_reason = screw_related_reason(recent_scope)
    if screw_reason:
        return Decision("skip", "", "screw_related", screw_reason, 1.0)

    context_video_request = is_video_request(recent_context)
    if is_video_request(t) or (
        (is_send_reference_request(t) or is_short_followup_request(t)) and context_video_request
    ):
        if code:
            reply = (
                f"Dạ mẫu này mã {code}, mình xem video hướng dẫn của shop ở đây giúp em nha: {YOUTUBE_GUIDE_URL}"
            )
        else:
            reply = f"Dạ mình xem video hướng dẫn của shop ở đây giúp em nha: {YOUTUBE_GUIDE_URL}"
        return Decision("send", reply, "assembly_video", "assembly/video request", 0.9)

    if is_send_reference_request(t):
        return Decision(
            "skip",
            "",
            "ambiguous_send_reference",
            "send-reference message without recent video/assembly context",
            0.0,
        )

    if is_short_followup_request(t):
        return Decision(
            "skip",
            "",
            "ambiguous_short_followup",
            "short follow-up without recent video/assembly context",
            0.0,
        )

    if any(word in t for word in ["go gi", "chat lieu gi", "lam tu go gi", "go loai gi", "go mdf chua", "co ben khong"]):
        return Decision("send", pick_variant("material_wood", s), "material_wood", "material question", 0.85)

    if any(word in t for word in ["tu lap", "tu rap", "lap san chua", "co lap san chua", "co lap san khong", "co lap san k"]):
        return Decision("send", pick_variant("self_assembly", s), "self_assembly", "self-assembly question", 0.85)

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

    if is_dimension_question(t):
        if product.name:
            return Decision(
                "skip",
                "",
                "dimension_visible_but_unknown",
                f"visible product but no trusted dimension rule: {product.name}",
                0.0,
            )
        return Decision("skip", "", "dimension_no_product_context", "no visible product context", 0.0)

    if is_product_info_request(t):
        return Decision(
            "skip",
            "",
            "product_info_lookup_needed",
            "product info question needs Shopee description lookup",
            0.0,
        )

    return Decision("skip", "", "outside_product_info_scope", "only product video/dimensions/description info allowed", 0.0)


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
                        "Chi duoc action='send' cho 3 nhom: xin video huong dan/san pham, hoi kich thuoc, hoi thong tin co trong mo ta san pham. "
                        "Moi case khac deu action='skip'. Tra loi ngan toi da 1-2 cau, duoi 240 ky tu. "
                        "TUYET DOI khong nhac so tai khoan, QR, chuyen khoan, Zalo, Facebook, sdt, ngoai san, ngoai Shopee. "
                        "TUYET DOI khong hua hoan tien, gui bu, den bu, giam gia, tang qua, ho tro chi phi, ho tro phi ship. "
                        "Khong dung cum 'phi ho tro', 'ho tro lai chi phi', 'gui bu', 'gui don oc', 'hoan lai'. "
                        "Khong yeu cau hoac goi y khach huy don. "
                        "Truong hop khach noi tra hang, hoan hang, hoan tien, doi tra, tra hoan: action='skip', khong nhan tin. "
                        "Truong hop nao co lien quan oc, vit, tua vit, lo khoan, khoan san, phu kien: action='skip', khong nhan tin. "
                        "Truong hop nao khach bao thieu tam, thieu ngan, thieu chi tiet, thieu hang, giao thieu bat ky mon nao: action='skip', khong nhan tin. "
                        "Truong hop khach gui hinh anh/tep/clip hoac can xem anh: action='skip', khong nhan tin. "
                        "Truong hop nhac phi, chi phi, phi hu, tien, gia, den bu, boi thuong: action='skip', khong nhan tin. "
                        "Khong xin lai ma san pham/ma mau neu Salework da hien ro san pham. "
                        "Khong bao khach tu xem mo ta san pham, xem live, hoac tu check thong tin san pham; phai tu doc san pham trong Salework. "
                        "Neu khong co so do/thong tin san pham chac chan, action='skip' de nguoi shop kiem tra. "
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

Chi action=send neu la case hoi video huong dan/san pham, kich thuoc, hoac thong tin co trong mo ta san pham. Cau tra loi ngan gon toi da 1-2 cau.
Moi case khac action=skip, khong tra loi buoc dau.
Neu khach noi ve tra hang/hoan hang/hoan tien/doi tra/tra hoan/refund/return, action=skip. Khong tu gui bat ky tin nhan nao cho case nay.
Neu khach hoac lich su chat co noi ve oc/vit/tua vit/lo khoan/khoan san/phu kien/goi phu kien/thieu phu kien, action=skip. Khong tu gui bat ky tin nhan nao cho case nay.
Neu khach hoac lich su chat co noi ve thieu tam/thieu ngan/thieu chi tiet/thieu hang/giao thieu/khong thay mon nao do trong kien hang, action=skip. Khong tu gui bat ky tin nhan nao cho case nay.
Neu khach gui hinh anh/tep/clip, hoac noi can xem anh/loi qua anh, action=skip. Khong tu gui bat ky tin nhan nao.
Neu khach nhac phi/chi phi/phi hu/tien/gia/den bu/boi thuong, action=skip. Khong tu gui bat ky tin nhan nao.
Neu Salework da hien san pham, tu dung ma/ten/boi canh san pham dang hien thi; khong hoi khach gui lai ma san pham/ma mau/anh mau.
Tuyet doi khong viet cac cau kieu "minh xem phan mo ta", "tham khao mo ta", "xem chi tiet tren Shopee", "xem live cua shop" de day viec check san pham cho khach.
Neu khach hoi kich thuoc/do day/chieu cao va khong co so lieu chac chan trong Salework/luat co san, action=skip; khong tra loi doan va khong bat khach tu check.
Neu can quyet dinh den bu/gui bu/hoan tien/doi tra/huy don/thong tin rieng/khong chac so do, action=skip.
""".strip()
                    }
                ],
            }
        ],
        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": 220,
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


def is_handleable_candidate(row: Row, processed: set[str], human_only: set[str]) -> tuple[bool, str]:
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
    if key_for(row) in human_only:
        return False, "human-only already flagged"
    reason = preview_skip_reason(row.preview)
    if reason:
        return False, reason
    return True, ""


def find_row_by_name(rows: list[Row], name: str) -> Row | None:
    for row in rows:
        if row.name == name:
            return row
    return None


def mark_unread_for_manual_check(claw: OpenClaw, row: Row, reason: str, dry_run: bool) -> None:
    if dry_run:
        return
    try:
        marked = claw.mark_unread_current_chat()
    except Exception as exc:
        log(f"WARN_MARK_UNREAD {row.name}: failed after {reason}: {exc}")
        return
    if marked:
        log(f"MARK_UNREAD {row.name}: ok | {reason}")
    else:
        log(f"WARN_MARK_UNREAD {row.name}: button not found | {reason}")


async def process_once(
    claw: OpenClaw,
    lookup_claw: OpenClaw | None,
    prompt_text: str,
    processed: set[str],
    human_only: set[str],
    args: argparse.Namespace,
) -> int:
    sent = 0
    rows = claw.rows()
    candidates: list[Row] = []
    skipped_no_click = 0
    state_dirty = False
    for row in rows:
        row_key = key_for(row)
        ok, reason = is_handleable_candidate(row, processed, human_only)
        if not ok:
            if reason and reason not in {
                "already processed",
                "human-only already flagged",
                "shop's own message",
            }:
                skipped_no_click += 1
                log(f"SKIP_NOCLICK {row.name}: {reason}")
                if not args.dry_run and reason != "outside product-info scope":
                    human_only.add(row_key)
                    state_dirty = True
            continue
        candidates.append(row)

    log(f"visible_rows={len(rows)} candidates={len(candidates)} skipped_no_click={skipped_no_click}")
    if state_dirty and not args.dry_run:
        save_state(processed, human_only)
        state_dirty = False

    for row in candidates[: args.max_candidates]:
        if sent >= args.max_send:
            break

        # Refresh row coordinates — the chat list re-orders after every send,
        # so the (x,y) we captured at the start may now point to a different
        # conversation. Look the row up again by name before clicking.
        fresh_rows = claw.rows()
        fresh_row = find_row_by_name(fresh_rows, row.name)
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
            mark_unread_for_manual_check(claw, row, "active chat mismatch", args.dry_run)
            continue
        if active.draft.strip():
            log(f"SKIP {row.name}: textarea already has draft")
            mark_unread_for_manual_check(claw, row, "textarea already has draft", args.dry_run)
            continue

        active_recent_scope = f"{row.preview}\n{recent_chat_context(active.text)}"
        attachment_reason = attachment_related_reason(active_recent_scope)
        if attachment_reason:
            log(f"FLAG_HUMAN {row.name}: {attachment_reason}")
            if not args.dry_run:
                human_only.add(row_key)
                state_dirty = True
            mark_unread_for_manual_check(claw, row, attachment_reason, args.dry_run)
            continue

        private_reason = private_payment_reason(row.preview)
        if private_reason:
            log(f"FLAG_HUMAN {row.name}: {private_reason}")
            if not args.dry_run:
                human_only.add(row_key)
                state_dirty = True
            mark_unread_for_manual_check(claw, row, private_reason, args.dry_run)
            continue

        complaint_reason = complaint_or_defect_reason(active_recent_scope)
        if complaint_reason:
            log(f"FLAG_HUMAN {row.name}: {complaint_reason}")
            if not args.dry_run:
                human_only.add(row_key)
                state_dirty = True
            mark_unread_for_manual_check(claw, row, complaint_reason, args.dry_run)
            continue

        cost_reason = cost_related_reason(row.preview)
        if cost_reason:
            log(f"FLAG_HUMAN {row.name}: {cost_reason}")
            if not args.dry_run:
                human_only.add(row_key)
                state_dirty = True
            mark_unread_for_manual_check(claw, row, cost_reason, args.dry_run)
            continue

        return_reason = return_related_reason(active_recent_scope)
        if return_reason:
            log(f"FLAG_HUMAN {row.name}: {return_reason}")
            if not args.dry_run:
                human_only.add(row_key)
                state_dirty = True
            mark_unread_for_manual_check(claw, row, return_reason, args.dry_run)
            continue

        missing_reason = missing_item_reason(active_recent_scope)
        if missing_reason:
            log(f"FLAG_HUMAN {row.name}: {missing_reason}")
            if not args.dry_run:
                human_only.add(row_key)
                state_dirty = True
            mark_unread_for_manual_check(claw, row, missing_reason, args.dry_run)
            continue

        screw_reason = screw_related_reason(active_recent_scope)
        if screw_reason:
            log(f"FLAG_HUMAN {row.name}: {screw_reason}")
            if not args.dry_run:
                human_only.add(row_key)
                state_dirty = True
            mark_unread_for_manual_check(claw, row, screw_reason, args.dry_run)
            continue

        seed = variant_seed(row.name)
        decision = await decide(row.preview, active.text, prompt_text, args.use_gemini, seed=seed)
        decision = Decision(
            action=decision.action,
            reply=shorten_reply(decision.reply),
            category=decision.category,
            reason=decision.reason,
            confidence=decision.confidence,
        )
        if decision.action != "send" and decision.category in LOOKUP_NEEDED_CATEGORIES:
            product = extract_product_context(active.text)
            urls = claw.active_product_urls()
            lookup_reply = lookup_product_answer(lookup_claw, product, row.preview, urls)
            if lookup_reply:
                decision = Decision(
                    "send",
                    shorten_reply(lookup_reply),
                    "product_description_lookup",
                    "answered from Shopee product description",
                    0.82,
                )
            else:
                log(f"FLAG_HUMAN {row.name}: product description lookup failed | {decision.reason}")
                if not args.dry_run:
                    human_only.add(row_key)
                    state_dirty = True
                mark_unread_for_manual_check(claw, row, decision.reason, args.dry_run)
                continue

        if decision.action != "send" or not decision.reply:
            log(f"SKIP {row.name}: {decision.category} | {decision.reason}")
            # Only mark as processed when the decision is *definitive* (no
            # rule applies / outside scope), not when it's a transient
            # Gemini/network failure — otherwise we'd silently drop a chat
            # we could later answer.
            transient = decision.category in {"gemini", "config"} and "HTTP" in (decision.reason or "")
            transient = transient or decision.reason == "missing Gemini API key"
            human_only_decision = decision.category in {
                "return_refund",
                "missing_item",
                "screw_related",
                "cost_fee",
                "attachment",
                "private_payment",
                "complaint_defect",
            }
            if not args.dry_run:
                if not transient:
                    if human_only_decision:
                        human_only.add(row_key)
                    else:
                        processed.add(row_key)
                    state_dirty = True
                mark_unread_for_manual_check(claw, row, decision.reason or decision.category, args.dry_run)
            continue

        block = safety_block_reason(decision.reply)
        if block:
            log(f"FLAG_HUMAN {row.name}: safety block {block} | reply={decision.reply!r}")
            if not args.dry_run:
                human_only.add(row_key)
                state_dirty = True
            mark_unread_for_manual_check(claw, row, block, args.dry_run)
            continue

        if args.dry_run:
            log(f"DRY {row.name}: {decision.category} | {decision.reply}")
            sent += 1
            continue

        try:
            value = claw.set_message(decision.reply)
            if value.strip() != decision.reply.strip():
                log(f"SKIP {row.name}: textarea value mismatch")
                try:
                    claw.clear_message()
                except Exception:
                    pass
                mark_unread_for_manual_check(claw, row, "textarea value mismatch", args.dry_run)
                continue
            # Final safety re-check on the actual textarea contents.
            final_block = safety_block_reason(value)
            if final_block:
                log(f"FLAG_HUMAN {row.name}: textarea safety block {final_block}")
                try:
                    claw.clear_message()
                except Exception:
                    pass
                human_only.add(row_key)
                state_dirty = True
                mark_unread_for_manual_check(claw, row, final_block, args.dry_run)
                continue
            claw.send_enter()
        except Exception as exc:
            log(f"SKIP {row.name}: send failed: {exc}")
            mark_unread_for_manual_check(claw, row, f"send failed: {exc}", args.dry_run)
            continue

        sent += 1
        processed.add(row_key)
        state_dirty = True
        log(f"SENT {row.name}: {decision.category} | {decision.reply}")
        # Human-like jitter between sends so the cadence doesn't look robotic.
        base = max(0.3, args.after_send_delay)
        time.sleep(base + random.uniform(0, base))

    if state_dirty and not args.dry_run:
        save_state(processed, human_only)
    return sent


async def main() -> int:
    parser = argparse.ArgumentParser(description="Run Gemini-powered Salework UI auto reply bot.")
    parser.add_argument("--profile", default=os.getenv("OPENCLAW_BROWSER_PROFILE", "edgeremote"))
    parser.add_argument("--lookup-profile", default=DEFAULT_LOOKUP_PROFILE)
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
    human_only = load_human_only()
    claw = OpenClaw(args.profile)
    lookup_claw = OpenClaw(args.lookup_profile) if args.lookup_profile else None
    claw.open_chat()

    total_sent = 0
    consecutive_errors = 0
    loops = 0
    log(
        f"START profile={args.profile} lookup_profile={args.lookup_profile} max_send={args.max_send} once={args.once} "
        f"dry_run={args.dry_run} gemini={args.use_gemini}"
    )
    while total_sent < args.max_send:
        loops += 1
        try:
            sent = await process_once(claw, lookup_claw, prompt_text, processed, human_only, args)
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
                    log("WARN restart OpenClaw gateway after repeated browser errors")
                    restart_openclaw_gateway()
                except Exception as gateway_exc:
                    log(f"ERROR gateway restart failed: {gateway_exc}")
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
