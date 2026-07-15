from __future__ import annotations

import datetime as dt
import json
import re
import time
from typing import Any

from ..db import Database, uuid_like
from .llm_service import LlmService
from .prompt_service import merge_settings


EXPLICIT_MEMORY_RE = re.compile(
    r"(记住|记一下|以后(别|不要|要)|我喜欢|我不喜欢|我讨厌|我的生日|我叫|称呼我|不要叫我|偏好|雷点|忌口)",
    re.IGNORECASE,
)

AUTO_BATCH_SIZE = 30
AUTO_BATCH_SECONDS = 3 * 60 * 60


def memory_trigger_type(text: str) -> str:
    return "explicit" if EXPLICIT_MEMORY_RE.search(text) else "batch"


def should_process_memory_queue(db: Database, *, force: bool = False) -> bool:
    if force:
        return True
    pending = db.count_pending_memory_queue()
    if pending >= AUTO_BATCH_SIZE:
        return True
    last = db.get_scheduled_job("memory:auto:last")
    if not last:
        return False
    return pending > 0 and time.time() - float(last.get("ranAt") or 0) >= AUTO_BATCH_SECONDS


async def maybe_process_memory_queue(
    db: Database,
    llm: LlmService,
    *,
    settings: dict | None = None,
    force: bool = False,
) -> dict:
    merged = merge_settings(settings or db.get_settings())
    memory_settings = merged.get("memory") or {}
    if memory_settings.get("autoExtract") is False:
        return {"processed": False, "reason": "auto_extract_disabled"}
    if not should_process_memory_queue(db, force=force):
        return {"processed": False, "reason": "not_due", "pending": db.count_pending_memory_queue()}
    return await process_memory_queue(db, llm, settings=merged, force=force)


async def process_memory_queue(
    db: Database,
    llm: LlmService,
    *,
    settings: dict | None = None,
    force: bool = False,
) -> dict:
    merged = merge_settings(settings or db.get_settings())
    queue = db.list_pending_memory_queue(limit=80 if force else 50)
    if not queue:
        return {"processed": True, "created": 0, "pending": 0}
    existing = db.list_memories(status="all", include_disabled=True, limit=120)
    review = bool((merged.get("memory") or {}).get("reviewBeforeSave", True))
    candidates = await _extract_memory_candidates(llm, settings=merged, queue=queue, existing=existing)
    created = []
    for candidate in candidates:
        normalized = _normalize_candidate(candidate)
        if not normalized["content"]:
            continue
        duplicate = _find_duplicate(existing + created, normalized["content"])
        status = normalized["status"]
        if status == "active" and review and not _is_explicit_queue(queue):
            status = "pending"
        if duplicate:
            merged_item = db.update_memory(
                duplicate["id"],
                {
                    "content": _merge_content(duplicate["content"], normalized["content"]),
                    "summary": normalized["summary"] or duplicate.get("summary", ""),
                    "tags": sorted(set((duplicate.get("tags") or []) + normalized["tags"])),
                    "confidence": max(float(duplicate.get("confidence") or 0), normalized["confidence"]),
                    "importance": max(float(duplicate.get("importance") or 0), normalized["importance"]),
                    "status": "active" if duplicate.get("status") == "active" else status,
                    "source": normalized["source"],
                    "expiresAt": normalized["expiresAt"],
                },
            )
            if merged_item:
                created.append(merged_item)
            continue
        created.append(
            db.upsert_memory(
                memory_id=f"mem_{uuid_like()}_{len(created)}",
                kind=normalized["kind"],
                subject=normalized["subject"],
                content=normalized["content"],
                summary=normalized["summary"],
                tags=normalized["tags"],
                confidence=normalized["confidence"],
                importance=normalized["importance"],
                status=status,
                enabled=True,
                pinned=normalized["pinned"],
                sensitive=normalized["sensitive"],
                source=normalized["source"],
                expires_at=normalized["expiresAt"],
            )
        )
    db.mark_memory_queue_processed([item["messageId"] for item in queue])
    result = {
        "processed": True,
        "created": len(created),
        "pending": db.count_pending_memory_queue(),
        "memories": created,
    }
    db.upsert_scheduled_job(job_key="memory:auto:last", result=result)
    return result


def recall_memories(db: Database, *, text: str = "", limit: int = 24) -> list[dict]:
    memories = db.list_memories(status="active", limit=120)
    now = time.time()
    keywords = _keywords(text)
    scored = []
    for item in memories:
        expires_at = item.get("expiresAt")
        if expires_at is not None and float(expires_at) < now:
            continue
        haystack = " ".join(
            [
                str(item.get("content") or ""),
                str(item.get("summary") or ""),
                " ".join(str(tag) for tag in item.get("tags") or []),
            ]
        ).lower()
        lexical = sum(1 for word in keywords if word and word in haystack)
        recency = 1.0 / max(1.0, (now - float(item.get("updatedAt") or now)) / 86400)
        score = (
            (2.0 if item.get("pinned") else 0.0)
            + float(item.get("importance") or 0.5) * 2.0
            + float(item.get("confidence") or 0.7)
            + lexical * 0.8
            + min(recency, 1.0) * 0.2
        )
        scored.append((score, item))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    selected = [item for _, item in scored[:limit]]
    db.mark_memories_used([item["id"] for item in selected])
    return selected


async def _extract_memory_candidates(
    llm: LlmService,
    *,
    settings: dict,
    queue: list[dict],
    existing: list[dict],
) -> list[dict]:
    transcript = "\n".join(
        f"[{item['messageId']}] {item['role']}: {item['content'][:700]}" for item in queue
    )
    known = "\n".join(
        f"- {item['kind']}/{item['subject']}: {item['content'][:180]}" for item in existing[:40]
    )
    messages = [
        {
            "role": "system",
            "content": (
                "你是 Alicer 的记忆整理器。只提取对伴侣陪伴长期有用、可复用、相对稳定的信息。"
                "不要记录普通寒暄、一次性玩笑、无关细节、未经确认的敏感猜测。"
                "如果用户明确说“记住/以后/别/喜欢/讨厌”，优先提取。"
                "输出严格 JSON 数组，每项字段：kind, subject, content, summary, tags, confidence, importance, status, sensitive, expiresInDays。"
                "kind 只能是 fact/preference/relationship/state/self_life；subject 只能是 user/companion/relationship。"
                "status 通常 active；不确定或敏感用 pending。confidence/importance 为 0 到 1。"
            ),
        },
        {
            "role": "user",
            "content": f"已有记忆：\n{known or '暂无'}\n\n待整理聊天：\n{transcript}",
        },
    ]
    try:
        raw = await llm.complete(messages=messages, model_settings=settings.get("model") or {})
        parsed = json.loads(raw[raw.find("[") : raw.rfind("]") + 1])
        if isinstance(parsed, list):
            return [item for item in parsed if isinstance(item, dict)]
    except Exception:
        pass
    return _heuristic_candidates(queue)


def _heuristic_candidates(queue: list[dict]) -> list[dict]:
    candidates = []
    for item in queue:
        if item.get("triggerType") != "explicit":
            continue
        content = str(item.get("content") or "").strip()
        if not content:
            continue
        candidates.append(
            {
                "kind": "preference" if "喜欢" in content or "讨厌" in content or "别" in content else "fact",
                "subject": "user",
                "content": content[:240],
                "summary": content[:80],
                "tags": ["用户明确要求"],
                "confidence": 0.82,
                "importance": 0.72,
                "status": "active",
                "sensitive": False,
            }
        )
    return candidates


def _normalize_candidate(candidate: dict[str, Any]) -> dict:
    kind = str(candidate.get("kind") or "fact").strip()
    if kind not in {"fact", "preference", "relationship", "state", "self_life"}:
        kind = "fact"
    subject = str(candidate.get("subject") or "user").strip()
    if subject not in {"user", "companion", "relationship"}:
        subject = "user"
    content = str(candidate.get("content") or "").strip()
    summary = str(candidate.get("summary") or "").strip()[:160]
    tags = [str(item).strip()[:24] for item in (candidate.get("tags") or []) if str(item).strip()]
    status = str(candidate.get("status") or "active").strip()
    if status not in {"active", "pending", "archived"}:
        status = "pending"
    expires_at = None
    expires_days = candidate.get("expiresInDays")
    if expires_days is not None:
        try:
            expires_at = time.time() + max(1.0, float(expires_days)) * 86400
        except (TypeError, ValueError):
            expires_at = None
    if kind == "state" and expires_at is None:
        expires_at = time.time() + 14 * 86400
    return {
        "kind": kind,
        "subject": subject,
        "content": content[:500],
        "summary": summary,
        "tags": tags[:8],
        "confidence": _clamp_float(candidate.get("confidence"), 0.7),
        "importance": _clamp_float(candidate.get("importance"), 0.5),
        "status": status,
        "pinned": bool(candidate.get("pinned", False)),
        "sensitive": bool(candidate.get("sensitive", False)),
        "source": {
            "type": "auto_extract",
            "createdAt": dt.datetime.now().astimezone().isoformat(),
        },
        "expiresAt": expires_at,
    }


def _find_duplicate(memories: list[dict], content: str) -> dict | None:
    normalized = _normalize_text(content)
    if len(normalized) < 8:
        return None
    for item in memories:
        if _normalize_text(str(item.get("content") or "")) == normalized:
            return item
    return None


def _merge_content(current: str, incoming: str) -> str:
    if incoming in current:
        return current
    if current in incoming:
        return incoming
    return f"{current}\n{incoming}"[:500]


def _is_explicit_queue(queue: list[dict]) -> bool:
    return any(item.get("triggerType") == "explicit" for item in queue)


def _keywords(text: str) -> set[str]:
    raw = re.findall(r"[\w\u4e00-\u9fff]{2,}", text.lower())
    return {item for item in raw if len(item) >= 2}


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", "", text.strip().lower())


def _clamp_float(value: object, default: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = default
    return max(0.0, min(1.0, parsed))
