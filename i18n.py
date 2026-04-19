"""
Localized strings and Telegram custom emoji helpers.

Premium / custom emoji: Bot API HTML
  <tg-emoji emoji-id="NUMERIC_ID">fallback</tg-emoji>
Placeholders: {{e:sparkle}} → from _emoji + _emoji_char.

Inline buttons: optional Bot API style (primary / success / danger) and
icon_custom_emoji_id via ibutton() + _button_emoji / _button_style in en.json.

sc() = optional Unicode small-caps for dynamic snippets (country names stay normal for readability).
"""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Dict

logger = logging.getLogger(__name__)

_DIR = os.path.dirname(os.path.abspath(__file__))
_EN_PATH = os.path.join(_DIR, "en.json")

_data: Dict[str, Any] = {}
_emoji_ids: Dict[str, str] = {}
_emoji_chars: Dict[str, str] = {}
_btn_emoji: Dict[str, str] = {}
_btn_style: Dict[str, str] = {}

# Latin letters → Unicode small caps (ᴛᴇʟᴇɢʀᴀᴍ aesthetic)
_SC_MAP = {
    "a": "ᴀ",
    "b": "ʙ",
    "c": "ᴄ",
    "d": "ᴅ",
    "e": "ᴇ",
    "f": "ғ",
    "g": "ɢ",
    "h": "ʜ",
    "i": "ɪ",
    "j": "ᴊ",
    "k": "ᴋ",
    "l": "ʟ",
    "m": "ᴍ",
    "n": "ɴ",
    "o": "ᴏ",
    "p": "ᴘ",
    "q": "ǫ",
    "r": "ʀ",
    "s": "ꜱ",
    "t": "ᴛ",
    "u": "ᴜ",
    "v": "ᴠ",
    "w": "ᴡ",
    "x": "x",
    "y": "ʏ",
    "z": "ᴢ",
}


def sc(text: str) -> str:
    """Optional small caps for dynamic UI fragments (ASCII letters only)."""
    if not text:
        return text
    out = []
    for c in text:
        if c.isascii() and c.isalpha():
            out.append(_SC_MAP.get(c.lower(), c))
        else:
            out.append(c)
    return "".join(out)


def _load() -> None:
    global _data, _emoji_ids, _emoji_chars, _btn_emoji, _btn_style
    try:
        with open(_EN_PATH, encoding="utf-8") as f:
            _data = json.load(f)
    except FileNotFoundError:
        logger.error("en.json not found at %s", _EN_PATH)
        _data = {}
    _emoji_ids = dict(_data.get("_emoji") or {})
    _emoji_chars = dict(_data.get("_emoji_char") or {})
    _btn_emoji = dict(_data.get("_button_emoji") or {})
    _btn_style = dict(_data.get("_button_style") or {})


_load()


def reload_strings() -> None:
    _load()


def _get_nested(key: str) -> Any:
    cur: Any = _data
    for part in key.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


_EMOJI_PLACEHOLDER = re.compile(r"\{\{e:(\w+)\}\}")


def _emoji_html(name: str) -> str:
    eid = _emoji_ids.get(name, "").strip()
    ch = _emoji_chars.get(name, "·")
    if not eid:
        return ch
    return f'<tg-emoji emoji-id="{eid}">{ch}</tg-emoji>'


def apply_custom_emoji_html(text: str) -> str:
    if not text:
        return text

    def repl(m: re.Match) -> str:
        return _emoji_html(m.group(1))

    return _EMOJI_PLACEHOLDER.sub(repl, text)


def apply_custom_emoji_plain(text: str) -> str:
    if not text:
        return text

    def repl(m: re.Match) -> str:
        return _emoji_chars.get(m.group(1), "·")

    return _EMOJI_PLACEHOLDER.sub(repl, text)


def t(key: str, **kwargs: Any) -> str:
    val = _get_nested(key)
    if val is None:
        logger.warning("i18n missing key: %s", key)
        return key
    if not isinstance(val, str):
        logger.warning("i18n key %s is not a string", key)
        return key
    s = apply_custom_emoji_html(val)
    try:
        return s.format(**kwargs) if kwargs else s
    except KeyError as e:
        logger.error("i18n format error for %s: %s", key, e)
        return s


def t_plain(key: str, **kwargs: Any) -> str:
    val = _get_nested(key)
    if val is None:
        logger.warning("i18n missing key: %s", key)
        return key
    if not isinstance(val, str):
        return key
    s = apply_custom_emoji_plain(val)
    try:
        return s.format(**kwargs) if kwargs else s
    except KeyError:
        return s


def welcome_default_template() -> str:
    val = _get_nested("welcome.default")
    if isinstance(val, str) and val.strip():
        return val
    return (
        "<b>{{e:sparkle}} ᴡᴇʟᴄᴏᴍᴇ {user_name}</b>\n"
        "<b>━━━━━━━━━━━━━━━━━━━━</b>\n"
        "<b>ᴘʀᴇᴍɪᴜᴍ ᴠᴇʀɪꜰɪᴇᴅ ɴᴜᴍʙᴇʀꜱ</b>\n"
        "<b>ᴛᴀᴘ ᴀ ʙᴜᴛᴛᴏɴ ʙᴇʟᴏᴡ ᴛᴏ ᴄᴏɴᴛɪɴᴜᴇ.</b>"
    )


def _icon_id_for_slot(slot: str | None) -> str | None:
    if not slot:
        return None
    eid = str(_emoji_ids.get(slot, "") or "").strip()
    return eid or None


def ibutton(
    key: str,
    *,
    callback_data: str | None = None,
    url: str | None = None,
    icon_slot: str | None = None,
    style: str | None = None,
    **fmt: Any,
) -> "InlineKeyboardButton":
    """Inline button with optional premium icon (icon_custom_emoji_id) + style from en.json."""
    from telegram import InlineKeyboardButton

    text = t_plain(key, **fmt)
    slot = icon_slot if icon_slot is not None else _btn_emoji.get(key)
    eid = _icon_id_for_slot(slot)
    st = style if style is not None else _btn_style.get(key)
    if st not in (None, "danger", "success", "primary"):
        st = None
    kw: Dict[str, Any] = {"text": text}
    if eid:
        kw["icon_custom_emoji_id"] = eid
    if st:
        kw["style"] = st
    if url is not None:
        kw["url"] = url
        return InlineKeyboardButton(**kw)
    if callback_data is not None:
        kw["callback_data"] = callback_data
        return InlineKeyboardButton(**kw)
    raise ValueError("ibutton requires url or callback_data")


def ibutton_raw(
    text: str,
    *,
    callback_data: str | None = None,
    url: str | None = None,
    icon_slot: str | None = None,
    style: str | None = None,
) -> "InlineKeyboardButton":
    """Same as ibutton but raw label (for dynamic text). icon_slot names _emoji keys."""
    from telegram import InlineKeyboardButton

    eid = _icon_id_for_slot(icon_slot)
    st = style if style in ("danger", "success", "primary") else None
    kw: Dict[str, Any] = {"text": text}
    if eid:
        kw["icon_custom_emoji_id"] = eid
    if st:
        kw["style"] = st
    if url is not None:
        kw["url"] = url
        return InlineKeyboardButton(**kw)
    if callback_data is not None:
        kw["callback_data"] = callback_data
        return InlineKeyboardButton(**kw)
    raise ValueError("ibutton_raw requires url or callback_data")
