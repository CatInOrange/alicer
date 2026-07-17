from __future__ import annotations

import time

from ..db import Database, uuid_like
from .consistency_service import reconcile_after_life_facts_changed
from .life_fact_service import audit_life_facts, normalize_fact_patch
from .llm_service import LlmService
from .prompt_service import merge_settings


async def create_manual_life_fact(db: Database, llm: LlmService, payload: dict) -> dict:
    patch = normalize_fact_patch(payload)
    fact_type = patch.pop("fact_type", "schedule_commitment")
    status = patch.pop("status", "candidate")
    title = str(patch.pop("title", payload.get("title", "")) or "").strip()
    summary = str(patch.pop("summary", payload.get("summary", title)) or title).strip()
    if not title and not summary:
        raise ValueError("title or summary is required")
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
    return await _fact_mutation_result(
        db,
        llm,
        payload=payload,
        fact=fact,
        reason="manual_life_fact_create",
    )


async def update_manual_life_fact(db: Database, llm: LlmService, fact_id: str, payload: dict) -> dict | None:
    patch = normalize_fact_patch(payload)
    if not patch:
        fact = db.get_life_fact(fact_id)
        return {"fact": fact} if fact is not None else None
    fact = db.update_life_fact(fact_id, **patch)
    if fact is None:
        return None
    return await _fact_mutation_result(
        db,
        llm,
        payload=payload,
        fact=fact,
        reason="manual_life_fact_update",
    )


async def cancel_manual_life_fact(db: Database, llm: LlmService, fact_id: str, payload: dict) -> dict | None:
    return await _status_mutation(
        db,
        llm,
        fact_id=fact_id,
        payload=payload,
        status="cancelled",
        metadata={"cancelledAt": time.time(), **(payload.get("metadata") or {})},
        reason="manual_life_fact_cancel",
    )


async def complete_manual_life_fact(db: Database, llm: LlmService, fact_id: str, payload: dict) -> dict | None:
    return await _status_mutation(
        db,
        llm,
        fact_id=fact_id,
        payload=payload,
        status="completed",
        metadata={"completedAt": time.time(), **(payload.get("metadata") or {})},
        reason="manual_life_fact_complete",
    )


async def supersede_manual_life_fact(db: Database, llm: LlmService, fact_id: str, payload: dict) -> dict | None:
    replacement_id = str(payload.get("replacementFactId") or payload.get("supersededBy") or "")
    return await _status_mutation(
        db,
        llm,
        fact_id=fact_id,
        payload=payload,
        status="superseded",
        metadata={"supersededAt": time.time(), "supersededBy": replacement_id},
        reason="manual_life_fact_supersede",
        supersedes_id=replacement_id,
    )


async def _status_mutation(
    db: Database,
    llm: LlmService,
    *,
    fact_id: str,
    payload: dict,
    status: str,
    metadata: dict,
    reason: str,
    supersedes_id: str | None = None,
) -> dict | None:
    fact = db.update_life_fact_status(
        fact_id,
        status=status,
        metadata=metadata,
        supersedes_id=supersedes_id,
    )
    if fact is None:
        return None
    return await _fact_mutation_result(db, llm, payload=payload, fact=fact, reason=reason)


async def _fact_mutation_result(
    db: Database,
    llm: LlmService,
    *,
    payload: dict,
    fact: dict,
    reason: str,
) -> dict:
    consistency = await reconcile_after_life_facts_changed(
        db,
        llm,
        settings=merge_settings(payload.get("settings") or db.get_settings()),
        facts=[fact],
        reason=reason,
    )
    return {"fact": fact, "audit": audit_life_facts(db), "consistency": consistency}
