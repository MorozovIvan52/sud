"""Маскировка секретов в строках для логов (URL с apikey, токены)."""
from __future__ import annotations

import re


def redact_secrets(text: str, max_len: int = 400) -> str:
    if not text:
        return text
    t = str(text)[:max_len]
    t = re.sub(r"(?i)(apikey|api_key|token|password|secret)=([^&\s\"']+)", r"\1=***", t)
    t = re.sub(r"(?i)(Bearer\s+)([A-Za-z0-9._\-]+)", r"\1***", t)
    return t
