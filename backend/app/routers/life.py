from __future__ import annotations

import time

from fastapi import APIRouter, HTTPException

from ..db import Database, uuid_like
from ..services.life_fact_service import (
    audit_life_facts,
    build_world_context,
    cleanup_life_facts,
    normalize_fact_patch,
)
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

    @router.post("/life/facts")
    def create_life_fact(body: dict | None = None) -> dict:
        payload = body or {}
        patch = normalize_fact_patch(payload)
        fact_type = patch.pop("fact_type", "schedule_commitment")
        status = patch.pop("status", "candidate")
        title = str(patch.pop("title", payload.get("title", "")) or "").strip()
        summary = str(patch.pop("summary", payload.get("summary", title)) or title).strip()
        if not title and not summary:
            raise HTTPException(status_code=400, detail="title or summary is required")
        fact = db.upsert_life_fact(
            fact_id=str(payload.get("id") or f"fact_{uuid_like()}"),
            fact_type=fact_type,
            status=status,
            title=title or summary[:80],
            summary=summary or title,
            source=str(payload.get("source") or "manual"),
            source_message_id=str(payload.get("sourceMessageId") or ""),
            **patch,
        )
        return {"fact": fact, "audit": audit_life_facts(db)}

    @router.patch("/life/facts/{fact_id}")
    def update_life_fact(fact_id: str, body: dict | None = None) -> dict:
        patch = normalize_fact_patch(body or {})
        if not patch:
            fact = db.get_life_fact(fact_id)
            if fact is None:
                raise HTTPException(status_code=404, detail="fact not found")
            return {"fact": fact}
        fact = db.update_life_fact(fact_id, **patch)
        if fact is None:
            raise HTTPException(status_code=404, detail="fact not found")
        return {"fact": fact, "audit": audit_life_facts(db)}

    @router.post("/life/facts/{fact_id}/cancel")
    def cancel_life_fact(fact_id: str, body: dict | None = None) -> dict:
        fact = db.update_life_fact_status(
            fact_id,
            status="cancelled",
            metadata={"cancelledAt": time.time(), **((body or {}).get("metadata") or {})},
        )
        if fact is None:
            raise HTTPException(status_code=404, detail="fact not found")
        return {"fact": fact, "audit": audit_life_facts(db)}

    @router.post("/life/facts/{fact_id}/complete")
    def complete_life_fact(fact_id: str, body: dict | None = None) -> dict:
        fact = db.update_life_fact_status(
            fact_id,
            status="completed",
            metadata={"completedAt": time.time(), **((body or {}).get("metadata") or {})},
        )
        if fact is None:
            raise HTTPException(status_code=404, detail="fact not found")
        return {"fact": fact, "audit": audit_life_facts(db)}

    @router.post("/life/facts/{fact_id}/supersede")
    def supersede_life_fact(fact_id: str, body: dict | None = None) -> dict:
        payload = body or {}
        replacement_id = str(payload.get("replacementFactId") or payload.get("supersededBy") or "")
        fact = db.update_life_fact_status(
            fact_id,
            status="superseded",
            supersedes_id=replacement_id,
            metadata={"supersededAt": time.time(), "supersededBy": replacement_id},
        )
        if fact is None:
            raise HTTPException(status_code=404, detail="fact not found")
        return {"fact": fact, "audit": audit_life_facts(db)}

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
