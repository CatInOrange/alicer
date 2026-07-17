from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..db import Database
from ..services.life_fact_app_service import (
    cancel_manual_life_fact,
    complete_manual_life_fact,
    create_manual_life_fact,
    supersede_manual_life_fact,
    update_manual_life_fact,
)
from ..services.life_fact_service import (
    audit_life_facts,
    build_world_context,
    cleanup_life_facts,
    refresh_life_facts_from_recent_chat,
)
from ..services.life_service import advance_life_until_now, build_life_context, refresh_life_plan
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

    @router.get("/life/facts")
    def list_life_facts(status: str = "active", limit: int = 40) -> dict:
        settings = merge_settings(db.get_settings())
        cleanup = cleanup_life_facts(db)
        statuses = _status_filter(status)
        return {
            "facts": db.list_life_facts(
                statuses=statuses,
                limit=limit,
                include_expired=status in {"all", "history"},
            ),
            "world": build_world_context(db, settings),
            "audit": audit_life_facts(db),
            "cleanup": cleanup,
        }

    @router.get("/life/world-context")
    def get_world_context() -> dict:
        settings = merge_settings(db.get_settings())
        cleanup_life_facts(db)
        return {"world": build_world_context(db, settings), "audit": audit_life_facts(db)}

    @router.post("/life/facts/cleanup")
    def cleanup_facts() -> dict:
        result = cleanup_life_facts(db)
        return {"cleanup": result, "audit": audit_life_facts(db)}

    @router.post("/life/facts/refresh")
    async def refresh_facts(body: dict | None = None) -> dict:
        payload = body or {}
        settings = merge_settings(payload.get("settings") or db.get_settings())
        limit = int(payload.get("limit") or 40)
        return await refresh_life_facts_from_recent_chat(db, llm, settings=settings, limit=limit)

    @router.post("/life/facts")
    async def create_life_fact(body: dict | None = None) -> dict:
        payload = body or {}
        try:
            return await create_manual_life_fact(db, llm, payload)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="title or summary is required") from exc

    @router.patch("/life/facts/{fact_id}")
    async def update_life_fact(fact_id: str, body: dict | None = None) -> dict:
        result = await update_manual_life_fact(db, llm, fact_id, body or {})
        if result is None:
            raise HTTPException(status_code=404, detail="fact not found")
        return result

    @router.post("/life/facts/{fact_id}/cancel")
    async def cancel_life_fact(fact_id: str, body: dict | None = None) -> dict:
        result = await cancel_manual_life_fact(db, llm, fact_id, body or {})
        if result is None:
            raise HTTPException(status_code=404, detail="fact not found")
        return result

    @router.post("/life/facts/{fact_id}/complete")
    async def complete_life_fact(fact_id: str, body: dict | None = None) -> dict:
        result = await complete_manual_life_fact(db, llm, fact_id, body or {})
        if result is None:
            raise HTTPException(status_code=404, detail="fact not found")
        return result

    @router.post("/life/facts/{fact_id}/supersede")
    async def supersede_life_fact(fact_id: str, body: dict | None = None) -> dict:
        result = await supersede_manual_life_fact(db, llm, fact_id, body or {})
        if result is None:
            raise HTTPException(status_code=404, detail="fact not found")
        return result

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

    @router.post("/life/plan/refresh")
    async def refresh_plan(body: dict | None = None) -> dict:
        payload = body or {}
        settings = merge_settings(payload.get("settings") or db.get_settings())
        return await refresh_life_plan(
            db,
            llm,
            settings=settings,
            force_profile=payload.get("forceProfile") is True,
        )

    return router


def _status_filter(value: str) -> list[str]:
    status = str(value or "active").strip()
    if status == "all":
        return ["candidate", "planned", "active", "completed", "cancelled", "superseded", "expired", "archived"]
    if status == "history":
        return ["completed", "cancelled", "superseded", "expired", "archived"]
    if status == "active":
        return ["candidate", "planned", "active"]
    allowed = {"candidate", "planned", "active", "completed", "cancelled", "superseded", "expired", "archived"}
    selected = [item.strip() for item in status.split(",") if item.strip() in allowed]
    return selected or ["candidate", "planned", "active"]
