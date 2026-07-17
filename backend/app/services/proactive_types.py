from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from zoneinfo import ZoneInfo

from ..db import Database
from .llm_service import LlmService


TZ = ZoneInfo("Asia/Shanghai")
MomentGenerator = Callable[[Database, LlmService, dict, str], Awaitable[dict]]


@dataclass
class ProactiveCandidate:
    event_type: str
    intent: str
    source_key: str
    score: float
    reason: str
    prompt: str
    metadata: dict = field(default_factory=dict)
