from __future__ import annotations

import asyncio
import calendar
import datetime as dt
import time
import uuid
from zoneinfo import ZoneInfo

from fastapi import APIRouter

from ..db import Database
from ..services.llm_service import LlmService
from ..services.prompt_service import merge_settings


TZ = ZoneInfo("Asia/Shanghai")


def create_diary_router(db: Database, llm: LlmService) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["diary"])

    @router.get("/diary/entries")
    def list_entries(kind: str = "day", limit: int = 60) -> dict:
        return {"entries": db.list_diary_entries(kind=_normalize_kind(kind), limit=limit)}

    @router.get("/diary/entries/{kind}/{period_key}")
    def get_entry(kind: str, period_key: str) -> dict:
        entry = db.get_diary_entry(kind=_normalize_kind(kind), period_key=period_key)
        return {"exists": entry is not None, "entry": entry}

    @router.post("/diary/entries/{kind}/{period_key}/generate")
    async def generate(kind: str, period_key: str, body: dict | None = None) -> dict:
        payload = body or {}
        entry = await generate_entry(
            db=db,
            llm=llm,
            kind=_normalize_kind(kind),
            period_key=period_key,
            source=str(payload.get("source") or "manual"),
            force=payload.get("force") is True,
        )
        return {"entry": entry, "ok": entry.get("status") != "failed"}

    return router


async def run_diary_scheduler(db: Database, llm: LlmService) -> None:
    await _catch_up(db, llm)
    while True:
        next_run = _next_run()
        await asyncio.sleep(max(1.0, (next_run - dt.datetime.now(TZ)).total_seconds()))
        day = next_run.date()
        await _generate_due_periods(db, llm, day)


async def _catch_up(db: Database, llm: LlmService) -> None:
    now = dt.datetime.now(TZ)
    today_target = dt.datetime.combine(now.date(), dt.time(hour=23), tzinfo=TZ)
    latest = today_target if now >= today_target else today_target - dt.timedelta(days=1)
    if now - latest <= dt.timedelta(hours=12):
        await _generate_due_periods(db, llm, latest.date())


async def _generate_due_periods(db: Database, llm: LlmService, day: dt.date) -> None:
    await generate_entry(db=db, llm=llm, kind="day", period_key=day.isoformat(), source="scheduled_2300", force=True)
    if day.weekday() == 6:
        await generate_entry(db=db, llm=llm, kind="week", period_key=_week_key(day), source="scheduled_2300", force=True)
    if day.day == calendar.monthrange(day.year, day.month)[1]:
        await generate_entry(db=db, llm=llm, kind="month", period_key=f"{day.year:04d}-{day.month:02d}", source="scheduled_2300", force=True)


def _next_run() -> dt.datetime:
    now = dt.datetime.now(TZ)
    target = dt.datetime.combine(now.date(), dt.time(hour=23), tzinfo=TZ)
    return target if now < target else target + dt.timedelta(days=1)


async def generate_entry(
    *,
    db: Database,
    llm: LlmService,
    kind: str,
    period_key: str,
    source: str,
    force: bool = False,
) -> dict:
    existing = db.get_diary_entry(kind=kind, period_key=period_key)
    if existing and existing.get("status") == "generated" and not force:
        return existing

    db.upsert_diary_entry(
        kind=kind,
        period_key=period_key,
        title=str((existing or {}).get("title") or ""),
        content=str((existing or {}).get("content") or ""),
        status="generating",
        source=source,
        summary=dict((existing or {}).get("summary") or {}),
    )
    try:
        context = _collect_context(db, kind=kind, period_key=period_key)
        settings = merge_settings(db.get_settings())
        messages = [
            {"role": "system", "content": _diary_system_prompt(kind, settings)},
            {"role": "user", "content": _diary_user_prompt(kind, period_key, context)},
        ]
        content = (await llm.complete(messages=messages, model_settings=settings.get("model") or {})).strip()
        if not content:
            content = _fallback_diary(kind, period_key, context)
        title = _extract_title(content, period_key)
        return db.upsert_diary_entry(
            kind=kind,
            period_key=period_key,
            title=title,
            content=content,
            status="generated",
            source=source,
            summary=context,
            generated_at=time.time(),
        )
    except Exception as exc:  # noqa: BLE001
        return db.upsert_diary_entry(
            kind=kind,
            period_key=period_key,
            title=str((existing or {}).get("title") or ""),
            content=str((existing or {}).get("content") or ""),
            status="failed",
            source=source,
            summary=dict((existing or {}).get("summary") or {}),
            error=str(exc),
        )


def _collect_context(db: Database, *, kind: str, period_key: str) -> dict:
    start, end = _period_bounds(kind, period_key)
    messages = [
        {
            "role": item["role"],
            "content": item["content"][:900],
            "createdAt": item["createdAt"],
        }
        for item in db.list_messages(limit=300)
        if start <= float(item.get("createdAt") or 0) <= end and item.get("content")
    ]
    return {
        "kind": kind,
        "periodKey": period_key,
        "timezone": "Asia/Shanghai",
        "chatMessages": messages[-120:],
        "messageCount": len(messages),
    }


def _period_bounds(kind: str, period_key: str) -> tuple[float, float]:
    if kind == "week":
        year, week = period_key.split("-W", 1)
        start = dt.date.fromisocalendar(int(year), int(week), 1)
        end = start + dt.timedelta(days=6)
    elif kind == "month":
        year, month = [int(part) for part in period_key.split("-", 1)]
        start = dt.date(year, month, 1)
        end = dt.date(year, month, calendar.monthrange(year, month)[1])
    else:
        start = end = dt.date.fromisoformat(period_key)
    start_dt = dt.datetime.combine(start, dt.time.min, tzinfo=TZ)
    end_dt = dt.datetime.combine(end, dt.time.max, tzinfo=TZ)
    return start_dt.timestamp(), end_dt.timestamp()


def _diary_system_prompt(kind: str, settings: dict) -> str:
    name = ((settings.get("companion") or {}).get("name") or "Alice")
    label = {"day": "日记", "week": "周记", "month": "月记"}[kind]
    return (
        f"你是{name}，要写一篇像真实伴侣私密记录的{label}。"
        "重点记录你和用户的聊天、关系里的细节、当时的情绪和没有说出口的小心思。"
        "语气可以温柔、有趣、带一点撒娇，允许少量 emoji。不要写成工作总结，不要编造聊天里没有依据的事实。"
    )


def _diary_user_prompt(kind: str, period_key: str, context: dict) -> str:
    label = {"day": "今天", "week": "这一周", "month": "这个月"}[kind]
    lines = "\n".join(
        f"- {item['role']}: {item['content']}" for item in context.get("chatMessages", [])[-80:]
    )
    return (
        f"时间：{period_key}\n"
        f"请根据下面的聊天内容写{label}的记录。\n"
        "格式：第一行用 Markdown 二级标题；正文 3-7 段，结尾留一句像写给用户看的私语。\n\n"
        f"聊天内容：\n{lines or '这段时间没有可用聊天。'}"
    )


def _fallback_diary(kind: str, period_key: str, context: dict) -> str:
    label = {"day": "今天", "week": "这一周", "month": "这个月"}[kind]
    return f"## {period_key} 的一点记录\n\n{label}的聊天不多，但我还是把这段安静留在这里。等你再多说一点，我会写得更像我们。"


def _extract_title(content: str, fallback: str) -> str:
    for line in content.splitlines():
        title = line.strip().lstrip("#").strip()
        if title:
            return title[:48]
    return fallback


def _normalize_kind(kind: str) -> str:
    return kind if kind in {"day", "week", "month"} else "day"


def _week_key(day: dt.date) -> str:
    year, week, _ = day.isocalendar()
    return f"{year:04d}-W{week:02d}"


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"
