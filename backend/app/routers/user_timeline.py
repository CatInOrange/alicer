from __future__ import annotations

from fastapi import APIRouter

from ..db import Database
from ..services.prompt_service import merge_settings
from ..services.user_timeline_service import build_user_timeline_context, ingest_user_timeline_events


def create_user_timeline_router(db: Database) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["user-timeline"])

    @router.get("/user/timeline/state")
    def get_user_timeline_state() -> dict:
        settings = merge_settings(db.get_settings())
        return {"userTimeline": build_user_timeline_context(db, settings)}

    @router.get("/user/timeline/events")
    def list_user_timeline_events(limit: int = 50) -> dict:
        return {"events": db.list_user_timeline_events(limit=limit)}

    @router.post("/user/timeline/events")
    def add_user_timeline_events(body: dict | None = None) -> dict:
        payload = body or {}
        settings = merge_settings(payload.get("settings") or db.get_settings())
        events = payload.get("events") if isinstance(payload.get("events"), list) else []
        return ingest_user_timeline_events(db, events=events, settings=settings)

    return router
