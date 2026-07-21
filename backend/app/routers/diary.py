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
        settings = merge_settings(db.get_settings())
        context = _collect_context(
            db,
            kind=kind,
            period_key=period_key,
            settings=settings,
        )
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


def _collect_context(
    db: Database,
    *,
    kind: str,
    period_key: str,
    settings: dict,
) -> dict:
    start, end = _period_bounds(kind, period_key)
    companion = _companion_name(settings)
    user_name = _user_name(settings)
    messages = [
        {
            "role": item["role"],
            "speaker": user_name if item["role"] == "user" else companion,
            "roleMeaning": (
                "用户发言，可作为用户事实"
                if item["role"] == "user"
                else "伴侣回复，只能作为伴侣视角/关系背景"
            ),
            "content": item["content"][:900],
            "createdAt": item["createdAt"],
            "timeText": _message_time(item.get("createdAt")),
        }
        for item in db.list_messages(limit=300)
        if start <= float(item.get("createdAt") or 0) <= end and item.get("content")
    ]
    return {
        "kind": kind,
        "periodKey": period_key,
        "periodLabel": _period_label(kind, period_key),
        "timezone": "Asia/Shanghai",
        "companionName": companion,
        "userName": user_name,
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
    name = _companion_name(settings)
    user_name = _user_name(settings)
    label = {"day": "日记", "week": "周记", "month": "月记"}[kind]
    return (
        f"你是{name}，正在以伴侣口吻为{user_name}写一篇偏生活档案的{label}。"
        f"叙述视角必须是{name}：第一人称“我”只能指{name}，不能指{user_name}；"
        f"写{user_name}时用“你”“{user_name}”“用户”或“他”，绝不能替{user_name}自述。"
        "核心目标是记录用户这段时间的生活、状态、安排、情绪、任务推进、习惯和重要决定；"
        "你的生活只能作为关系背景或陪伴视角的少量旁注，不能成为主线。"
        "阅读聊天时要严格区分：用户发言才是用户事实；伴侣回复里的“我”是伴侣自己，"
        "伴侣回复里的“你/主人”才是在称呼用户。"
        "只有标注为“用户发言”的内容能证明用户说过某句话、做过某个动作或表达过某个态度；"
        "标注为“伴侣回复”的内容不能改写成用户原话或用户动作。"
        "引用或转述用户发言时必须写成“你说/你问/你回/你表示”，"
        "并把用户原话里的第一人称“我”转换为“你”；不能写成“我说/我问/我表示”。"
        "只有转述伴侣回复时，才可以用“我说/我问/我当时”。"
        "只能基于聊天证据写，不要把你的模拟生活、朋友圈、航班、纹身或推测当成用户事实。"
        "语气自然亲密，但要像可靠的生活记录，不要写成伴侣自传、用户自传或工作总结。"
    )


def _diary_user_prompt(kind: str, period_key: str, context: dict) -> str:
    label = {"day": "今天", "week": "这一周", "month": "这个月"}[kind]
    companion = str(context.get("companionName") or "伴侣")
    user_name = str(context.get("userName") or "用户")
    user_lines = "\n".join(
        (
            f"- {item.get('timeText') or '时间未知'} "
            f"{item.get('speaker') or user_name}"
            f"（{item.get('roleMeaning') or '用户发言'}）: {item['content']}"
        )
        for item in context.get("chatMessages", [])[-80:]
        if item.get("role") == "user"
    )
    companion_lines = "\n".join(
        (
            f"- {item.get('timeText') or '时间未知'} "
            f"{item.get('speaker') or item['role']}"
            f"（{item.get('roleMeaning') or item['role']}）: {item['content']}"
        )
        for item in context.get("chatMessages", [])[-80:]
        if item.get("role") != "user"
    )
    return (
        f"时间：{context.get('periodLabel') or period_key}\n"
        f"作者/叙述者：{companion}；记录对象：{user_name}。\n"
        f"请根据下面的聊天内容，用{companion}写给/写关于{user_name}的伴侣口吻，写{label}的用户生活记录。\n"
        "标题和正文里的日期、星期必须以“时间”这一行和消息时间为准；"
        "聊天里提到的“周五/明天/今晚”等相对时间只能按消息时间换算，不能覆盖日记日期。"
        "写作重点按优先级：用户发生了什么、用户在忙什么、身体/情绪/习惯/任务状态、关系互动里能支持这些判断的细节。"
        "先读“用户发言”，它是用户事实的唯一直接来源；再读“伴侣回复”，它只补充伴侣当时如何回应、关系氛围和伴侣自己的经历。"
        "涉及时间时优先使用每条消息前的 Asia/Shanghai 时间，不要自行猜成上午/下午的其他钟点。"
        f"凡是引用“用户发言”里的话，都要转换为{companion}视角：用户原话里的“我”写成“你”，"
        f"例如用户说“我盯着呢”，日记里应写“你说你盯着呢”，不能写“我说我盯着呢”。"
        "不要把伴侣回复里的第一人称事件改写成用户事件；例如伴侣说“我下飞机/我纹身”，只能写成伴侣发生了这件事，"
        "用户最多是到场、安排、回应、关心或确认，不能写成用户下飞机/用户纹身。"
        "不要把伴侣回复里的玩笑、想象、动作描写或称呼改写成用户说过的话。"
        "如果聊天很少，就明确写“可用记录不多”，不要用伴侣自己的经历填充篇幅。"
        f"格式：第一行用 Markdown 二级标题；正文 3-7 段；全文保持{companion}视角；"
        f"结尾可以留一句对{user_name}说的短短陪伴私语，但不要把整篇写成情书。\n\n"
        f"用户发言（用户事实的直接来源）：\n{user_lines or '这段时间没有可用用户发言。'}\n\n"
        f"伴侣回复（只能作为伴侣视角/关系背景，不能当作用户事实）：\n{companion_lines or '这段时间没有可用伴侣回复。'}"
    )


def _fallback_diary(kind: str, period_key: str, context: dict) -> str:
    label = {"day": "今天", "week": "这一周", "month": "这个月"}[kind]
    return f"## {period_key} 的生活记录\n\n{label}可用的用户记录不多，暂时只能确认这段时间聊天很少。先把这段空白留好，等有更多真实线索时再补上用户的状态、安排和重要变化。"


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


def _period_label(kind: str, period_key: str) -> str:
    if kind == "day":
        day = dt.date.fromisoformat(period_key)
        weekday = "一二三四五六日"[day.weekday()]
        return f"{period_key} 星期{weekday}"
    return period_key


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def _companion_name(settings: dict) -> str:
    return str(((settings.get("companion") or {}).get("name") or "Alice")).strip() or "Alice"


def _user_name(settings: dict) -> str:
    return str(((settings.get("companion") or {}).get("userName") or "用户")).strip() or "用户"


def _message_time(value: object) -> str:
    try:
        timestamp = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return ""
    if timestamp <= 0:
        return ""
    return dt.datetime.fromtimestamp(timestamp, tz=TZ).strftime("%Y-%m-%d %H:%M")
