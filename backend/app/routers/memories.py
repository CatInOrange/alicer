from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..db import Database, uuid_like
from ..services.llm_service import LlmService
from ..services.memory_service import process_memory_queue
from ..services.prompt_service import merge_settings


class MemoryPayload(BaseModel):
    kind: str = "fact"
    subject: str = "user"
    content: str
    summary: str = ""
    tags: list[str] = Field(default_factory=list)
    confidence: float = 0.85
    importance: float = 0.6
    status: str = "active"
    enabled: bool = True
    pinned: bool = False
    sensitive: bool = False
    expiresAt: float | None = None


class MemoryUpdatePayload(BaseModel):
    kind: str | None = None
    subject: str | None = None
    content: str | None = None
    summary: str | None = None
    tags: list[str] | None = None
    confidence: float | None = None
    importance: float | None = None
    status: str | None = None
    enabled: bool | None = None
    pinned: bool | None = None
    sensitive: bool | None = None
    expiresAt: float | None = None


def create_memories_router(db: Database, llm: LlmService) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["memories"])

    @router.get("/memories")
    def list_memories(
        kind: str | None = None,
        status: str = "active",
        query: str = "",
        limit: int = 80,
    ) -> dict:
        return {
            "memories": db.list_memories(
                kind=kind,
                status=status,
                query_text=query,
                include_disabled=status == "all",
                limit=limit,
            ),
            "pendingQueue": db.count_pending_memory_queue(),
        }

    @router.post("/memories")
    def create_memory(payload: MemoryPayload) -> dict:
        content = payload.content.strip()
        if not content:
            raise HTTPException(status_code=400, detail="content is required")
        item = db.upsert_memory(
            memory_id=f"mem_{uuid_like()}",
            kind=_normalize_kind(payload.kind),
            subject=_normalize_subject(payload.subject),
            content=content,
            summary=payload.summary.strip(),
            tags=[item.strip() for item in payload.tags if item.strip()],
            confidence=payload.confidence,
            importance=payload.importance,
            status=_normalize_status(payload.status),
            enabled=payload.enabled,
            pinned=payload.pinned,
            sensitive=payload.sensitive,
            source={"type": "manual"},
            expires_at=payload.expiresAt,
        )
        return {"memory": item}

    @router.put("/memories/{memory_id}")
    def update_memory(memory_id: str, payload: MemoryUpdatePayload) -> dict:
        raw = payload.model_dump() if hasattr(payload, "model_dump") else payload.dict()
        updates = {
            key: value
            for key, value in raw.items()
            if value is not None
        }
        if "kind" in updates:
            updates["kind"] = _normalize_kind(str(updates["kind"]))
        if "subject" in updates:
            updates["subject"] = _normalize_subject(str(updates["subject"]))
        if "status" in updates:
            updates["status"] = _normalize_status(str(updates["status"]))
        if "tags" in updates:
            updates["tags"] = [str(item).strip() for item in updates["tags"] if str(item).strip()]
        item = db.update_memory(memory_id, updates)
        if item is None:
            raise HTTPException(status_code=404, detail="memory not found")
        return {"memory": item}

    @router.delete("/memories/{memory_id}")
    def delete_memory(memory_id: str) -> dict:
        item = db.update_memory(memory_id, {"enabled": False, "status": "archived"})
        if item is None:
            raise HTTPException(status_code=404, detail="memory not found")
        return {"memory": item}

    @router.post("/memories/process")
    async def process_memories(payload: dict | None = None) -> dict:
        settings = merge_settings((payload or {}).get("settings") or db.get_settings())
        result = await process_memory_queue(db, llm, settings=settings, force=True)
        return result

    return router


def _normalize_kind(value: str) -> str:
    return value if value in {"fact", "preference", "relationship", "state", "self_life"} else "fact"


def _normalize_subject(value: str) -> str:
    return value if value in {"user", "companion", "relationship"} else "user"


def _normalize_status(value: str) -> str:
    return value if value in {"active", "pending", "archived"} else "active"
