from __future__ import annotations

from fastapi import APIRouter

from ..db import Database
from ..services.life_service import advance_life_until_now, build_life_context
from ..services.llm_service import LlmService
from ..services.prompt_service import merge_settings


def create_life_router(db: Database, llm: LlmService) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["life"])

    @router.get("/life/state")
    def get_life_state() -> dict:
        settings = merge_settings(db.get_settings())
        return {"life": build_life_context(db, settings)}

    @router.get("/life/events")
    def list_life_events(limit: int = 24) -> dict:
        return {"events": db.list_life_events(limit=limit)}

    @router.post("/life/advance")
    async def advance_life(body: dict | None = None) -> dict:
        payload = body or {}
        settings = merge_settings(payload.get("settings") or db.get_settings())
        return await advance_life_until_now(
            db,
            llm,
            settings=settings,
            force=payload.get("force") is True,
        )

    return router
