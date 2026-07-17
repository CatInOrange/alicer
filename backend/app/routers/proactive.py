from __future__ import annotations

from fastapi import APIRouter

from ..db import Database
from ..services.llm_service import LlmService
from ..services.proactive_service import debug_candidates, run_proactive_once
from ..services.prompt_service import merge_settings
from .moments import generate_life_moment


def create_proactive_router(db: Database, llm: LlmService) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["proactive"])

    @router.get("/proactive/events")
    def list_events(limit: int = 50) -> dict:
        return {"events": db.list_proactive_events(limit=limit)}

    @router.get("/proactive/candidates")
    def list_candidates() -> dict:
        return debug_candidates(db)

    @router.post("/proactive/run")
    async def run_once(body: dict | None = None) -> dict:
        payload = body or {}
        settings = merge_settings(payload.get("settings") or db.get_settings())
        return await run_proactive_once(
            db,
            llm,
            settings=settings,
            force=payload.get("force") is True,
            moment_generator=generate_life_moment,
        )

    return router

