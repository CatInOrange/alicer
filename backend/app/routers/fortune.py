from __future__ import annotations

import datetime as dt

from fastapi import APIRouter

from ..db import Database
from ..services.fortune_service import build_daily_fortune_context
from ..services.prompt_service import merge_settings


def create_fortune_router(db: Database) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["fortune"])

    @router.get("/fortune/today")
    def get_today_fortune() -> dict:
        settings = merge_settings(db.get_settings())
        return {"fortune": build_daily_fortune_context(settings)}

    @router.post("/fortune/preview")
    def preview_fortune(payload: dict) -> dict:
        settings = merge_settings(payload.get("settings") or db.get_settings())
        target_date = _parse_date(str(payload.get("date") or ""))
        return {"fortune": build_daily_fortune_context(settings, date=target_date)}

    return router


def _parse_date(value: str) -> dt.date | None:
    if not value.strip():
        return None
    try:
        return dt.date.fromisoformat(value.strip())
    except ValueError:
        return None
