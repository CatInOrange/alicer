from __future__ import annotations

from fastapi import APIRouter

from ..db import Database
from ..services.chat_photo_service import build_chat_photo_context
from ..services.daily_maintenance_service import get_daily_maintenance_status
from ..services.life_fact_service import build_world_context
from ..services.life_service import build_life_context
from ..services.prompt_service import merge_settings, render_prompt
from ..services.user_timeline_service import build_user_timeline_context


def create_settings_router(db: Database) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["settings"])

    @router.get("/settings")
    def get_settings() -> dict:
        return {"settings": merge_settings(db.get_settings())}

    @router.put("/settings")
    def put_settings(payload: dict) -> dict:
        saved = db.save_settings(merge_settings(payload))
        return {"settings": saved}

    @router.get("/daily-maintenance/status")
    def daily_maintenance_status() -> dict:
        return get_daily_maintenance_status(db)

    @router.post("/prompt/preview")
    def preview(payload: dict) -> dict:
        settings = merge_settings(payload.get("settings") or db.get_settings())
        messages = db.list_messages(limit=300)
        memories = db.list_memories(limit=30)
        prompt_messages, debug = render_prompt(
            settings=settings,
            recent_messages=messages,
            memories=memories,
            environment=payload.get("environment") or {},
            life_context=build_life_context(db, settings),
            user_context=build_user_timeline_context(db, settings),
            photo_context=build_chat_photo_context(db, settings),
            world_context=build_world_context(db, settings),
        )
        return {"messages": prompt_messages, "debug": debug}

    return router
