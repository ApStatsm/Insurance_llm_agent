from __future__ import annotations

import re
from typing import Any


def to_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def unique_texts(items: list[Any]) -> list[str]:
    return list(dict.fromkeys([to_text(item) for item in items if to_text(item)]))


def format_file_size(size_bytes: int | None) -> str:
    if not size_bytes:
        return "크기 확인 중"
    if size_bytes < 1024:
        return f"{size_bytes}B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f}KB"
    return f"{size_bytes / (1024 * 1024):.1f}MB"


def mask_display_value(value: Any, *, kind: str = "") -> str:
    text = to_text(value)
    if not text:
        return "확인 필요"
    if kind == "name":
        if len(text) == 2:
            return f"{text[0]}*"
        if len(text) > 2:
            return f"{text[0]}*{text[-1]}"
    if kind == "vehicle" and len(text) > 3:
        return f"{text[:3]}****"
    return text


def mask_customer_id(value: Any) -> str:
    text = to_text(value)
    if len(text) <= 4:
        return text
    return f"{text[:4]}***{text[-2:]}"


def strip_source_markers(value: Any) -> str:
    text = to_text(value)
    text = re.sub(r"\s*\[(?:출처|근거):[^\]]+\]", "", text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
