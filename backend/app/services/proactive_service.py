from __future__ import annotations

import asyncio
import datetime as dt
import random
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from zoneinfo import ZoneInfo

from ..db import Database
from .chat_photo_service import build_chat_photo_context
from .life_fact_service import build_world_context
from .life_service import advance_life_until_now, build_life_context
from .llm_service import LlmService
from .memory_service import recall_memories
from .prompt_service import merge_settings, render_prompt
from .user_timeline_service import build_user_timeline_context


TZ = ZoneInfo("Asia/Shanghai")
MomentGenerator = Callable[[Database, LlmService, dict, str], Awaitable[dict]]


@dataclass
class ProactiveCandidate:
    event_type: str
    intent: str
    source_key: str
    score: float
    reason: str
    prompt: str
    metadata: dict = field(default_factory=dict)


async def run_proactive_scheduler(
    db: Database,
    llm: LlmService,
    *,
    moment_generator: MomentGenerator | None = None,
) -> None:
    await asyncio.sleep(8)
    await _safe_run_proactive_once(db, llm, moment_generator=moment_generator)
    while True:
        settings = merge_settings(db.get_settings())
        proactive = settings.get("proactive") or {}
        interval_minutes = _clamp_int(proactive.get("intervalMinutes"), default=20, minimum=5, maximum=180)
        await asyncio.sleep(interval_minutes * 60)
        await _safe_run_proactive_once(db, llm, moment_generator=moment_generator)


async def _safe_run_proactive_once(
    db: Database,
    llm: LlmService,
    *,
    moment_generator: MomentGenerator | None,
) -> None:
    try:
        await run_proactive_once(db, llm, moment_generator=moment_generator)
    except Exception as exc:
        db.add_proactive_event(
            event_id=f"pro_{uuid.uuid4().hex}",
            event_type="system",
            status="error",
            intent="scheduler",
            reason=str(exc)[:500],
            metadata={"errorType": type(exc).__name__},
            decided=True,
        )


async def run_proactive_once(
    db: Database,
    llm: LlmService,
    *,
    settings: dict | None = None,
    force: bool = False,
    moment_generator: MomentGenerator | None = None,
) -> dict:
    settings = merge_settings(settings or db.get_settings())
    proactive = settings.get("proactive") or {}
    if proactive.get("enabled") is False:
        return {"created": False, "reason": "disabled", "candidates": []}

    now = dt.datetime.now(TZ)
    recent_messages = db.list_messages(limit=300)
    recent_moments = db.list_moments(limit=80)
    recent_proactive = db.list_proactive_events(limit=120, since=(now - dt.timedelta(days=2)).timestamp())
    life_result = await advance_life_until_now(db, llm, settings=settings)
    life_context = life_result.get("context") or build_life_context(db, settings)
    user_context = build_user_timeline_context(db, settings)
    world_context = build_world_context(db, settings)
    candidates = _build_candidates(
        settings=settings,
        now=now,
        recent_messages=recent_messages,
        recent_moments=recent_moments,
        recent_proactive=recent_proactive,
        life_context=life_context,
        user_context=user_context,
        allow_moments=moment_generator is not None,
    )
    if not candidates:
        return {"created": False, "reason": "no_candidates", "candidates": []}
    scored = sorted(candidates, key=lambda item: item.score, reverse=True)
    selected = scored[0]
    threshold = _threshold(settings, selected.event_type)
    decision_payload = {
        "selected": _candidate_public(selected),
        "topCandidates": [_candidate_public(item) for item in scored[:5]],
        "threshold": threshold,
        "force": force,
    }
    if not force and selected.score < threshold:
        db.add_proactive_event(
            event_id=f"pro_{uuid.uuid4().hex}",
            event_type=selected.event_type,
            status="skipped",
            intent=selected.intent,
            source_key=selected.source_key,
            score=selected.score,
            reason=f"below_threshold:{threshold:.2f}",
            metadata=decision_payload,
            decided=True,
        )
        return {"created": False, "reason": "below_threshold", **decision_payload}

    if selected.event_type == "moment":
        if moment_generator is None:
            return {"created": False, "reason": "moment_generator_unavailable", **decision_payload}
        return await _deliver_moment(
            db,
            llm,
            settings=settings,
            candidate=selected,
            decision_payload=decision_payload,
            moment_generator=moment_generator,
        )
    return await _deliver_chat(
        db,
        llm,
        settings=settings,
        recent_messages=recent_messages,
        candidate=selected,
        decision_payload=decision_payload,
        life_context=life_context,
        user_context=user_context,
        world_context=world_context,
    )


def _build_candidates(
    *,
    settings: dict,
    now: dt.datetime,
    recent_messages: list[dict],
    recent_moments: list[dict],
    recent_proactive: list[dict],
    life_context: dict,
    user_context: dict,
    allow_moments: bool,
) -> list[ProactiveCandidate]:
    proactive = settings.get("proactive") or {}
    candidates: list[ProactiveCandidate] = []
    if _is_quiet_hour(now, proactive):
        return candidates

    last_message = recent_messages[-1] if recent_messages else None
    last_user_message = next((item for item in reversed(recent_messages) if item.get("role") == "user"), None)
    chat_cooldown_hours = _clamp_float(proactive.get("minHoursBetweenChat"), default=3.0, minimum=0.5, maximum=24.0)
    moment_cooldown_hours = _clamp_float(proactive.get("minHoursBetweenMoments"), default=8.0, minimum=1.0, maximum=48.0)

    if _delivered_count(recent_proactive, event_type="chat", since=_day_start(now)) < _daily_limit(proactive, "maxChatPerDay", 3):
        last_chat = _latest_delivered(recent_proactive, event_type="chat")
        if _hours_since_event(last_chat, now) >= chat_cooldown_hours:
            if last_message:
                idle_hours = _hours_since_ts(last_message.get("createdAt"), now)
                min_quiet = _clamp_float(proactive.get("minIdleHoursBeforeChat"), default=5.0, minimum=0.5, maximum=72.0)
                last_meta = last_message.get("metadata") or {}
                if idle_hours >= min_quiet and last_meta.get("source") != "proactive":
                    candidates.append(
                        ProactiveCandidate(
                            event_type="chat",
                            intent="check_in",
                            source_key=str((last_user_message or last_message).get("id") or "idle"),
                            score=min(0.92, 0.48 + idle_hours * 0.045),
                            reason=f"用户已经约 {idle_hours:.1f} 小时没有继续聊天",
                            prompt="用户有一段时间没出现。主动发一条很短的关心或轻轻找话题，不要催回复。",
                            metadata={"idleHours": idle_hours},
                        )
                    )
            follow_up = _follow_up_candidate(now=now, recent_messages=recent_messages, recent_proactive=recent_proactive)
            if follow_up is not None:
                candidates.append(follow_up)
            life_share = _life_share_candidate(now=now, life_context=life_context, recent_proactive=recent_proactive)
            if life_share is not None:
                candidates.append(life_share)

    if allow_moments and _delivered_count(recent_proactive, event_type="moment", since=_day_start(now)) < _daily_limit(proactive, "maxMomentsPerDay", 2):
        last_moment_event = _latest_delivered(recent_proactive, event_type="moment")
        latest_moment = recent_moments[0] if recent_moments else None
        if _hours_since_event(last_moment_event, now) >= moment_cooldown_hours and _hours_since_ts((latest_moment or {}).get("createdAt"), now) >= moment_cooldown_hours:
            moment_candidate = _moment_candidate(life_context=life_context)
            if moment_candidate is not None:
                candidates.append(moment_candidate)

    return _suppress_duplicates(candidates, recent_proactive)


def _follow_up_candidate(
    *,
    now: dt.datetime,
    recent_messages: list[dict],
    recent_proactive: list[dict],
) -> ProactiveCandidate | None:
    used_sources = {str(item.get("sourceKey") or "") for item in recent_proactive if item.get("status") == "delivered"}
    keyword_groups = [
        ("support", ("累", "压力", "烦", "难受", "焦虑", "崩", "不舒服", "睡不着")),
        ("follow_up", ("开会", "考试", "面试", "出门", "航班", "飞", "赶路", "到机场", "加班")),
    ]
    for item in reversed(recent_messages[-80:]):
        if item.get("role") != "user":
            continue
        source_key = str(item.get("id") or "")
        if source_key in used_sources:
            continue
        content = str(item.get("content") or "")
        age_hours = _hours_since_ts(item.get("createdAt"), now)
        if age_hours < 1.0 or age_hours > 24.0:
            continue
        for intent, keywords in keyword_groups:
            if any(word in content for word in keywords):
                score = 0.74 if intent == "support" else 0.68
                if 2 <= age_hours <= 8:
                    score += 0.08
                return ProactiveCandidate(
                    event_type="chat",
                    intent=intent,
                    source_key=source_key,
                    score=min(score, 0.95),
                    reason=f"追踪用户先前提到的事项：{content[:80]}",
                    prompt=(
                        "用户之前提到过压力/身体/重要安排。主动 follow-up 一句，"
                        "语气自然、具体、有分寸，不要像提醒机器人。"
                    ),
                    metadata={"sourceMessage": item, "ageHours": age_hours},
                )
    return None


def _life_share_candidate(
    *,
    now: dt.datetime,
    life_context: dict,
    recent_proactive: list[dict],
) -> ProactiveCandidate | None:
    state = life_context.get("state") or {}
    activity = str(state.get("activity") or "").strip()
    summary = str(state.get("summary") or "").strip()
    if not activity and not summary:
        return None
    latest = _latest_delivered(recent_proactive, event_type="chat")
    if _hours_since_event(latest, now) < 5:
        return None
    current_text = " / ".join(item for item in (activity, str(state.get("location") or ""), summary) if item)
    score = 0.58
    if any(word in current_text for word in ("下班", "午饭", "晚间", "休息", "机场", "航班", "路上")):
        score += 0.08
    return ProactiveCandidate(
        event_type="chat",
        intent="share_life",
        source_key=f"life:{activity}:{state.get('location') or ''}",
        score=score,
        reason=f"Alicer 当前生活片段适合自然分享：{current_text[:120]}",
        prompt="Alicer 想主动分享自己此刻的小片段。写得像真实伴侣随手发来的消息，不要长篇汇报。",
        metadata={"lifeState": state},
    )


def _moment_candidate(*, life_context: dict) -> ProactiveCandidate | None:
    recent_events = life_context.get("recentEvents") or []
    event = next(
        (
            item
            for item in reversed(recent_events[-8:])
            if item.get("canPostMoment") and not item.get("usedMomentId")
        ),
        None,
    )
    if event is None:
        return None
    text = " / ".join(
        str(item or "").strip()
        for item in (event.get("timeLabel"), event.get("location"), event.get("activity"), event.get("summary"))
        if str(item or "").strip()
    )
    score = 0.62
    if any(word in text for word in ("午饭", "下班", "晚间", "放松", "休息", "街区", "机场")):
        score += 0.08
    return ProactiveCandidate(
        event_type="moment",
        intent="share_life",
        source_key=str(event.get("id") or f"life_event:{text[:40]}"),
        score=min(score + random.uniform(0, 0.06), 0.86),
        reason=f"生活事件适合发布朋友圈：{text[:140]}",
        prompt="从当前生活事件自然长出一条朋友圈。",
        metadata={"lifeEvent": event},
    )


async def _deliver_chat(
    db: Database,
    llm: LlmService,
    *,
    settings: dict,
    recent_messages: list[dict],
    candidate: ProactiveCandidate,
    decision_payload: dict,
    life_context: dict,
    user_context: dict,
    world_context: dict,
) -> dict:
    memories = recall_memories(db, text=f"{candidate.intent} {candidate.reason}", limit=20)
    messages, prompt_debug = render_prompt(
        settings=settings,
        recent_messages=recent_messages,
        memories=memories,
        environment={},
        life_context=life_context,
        user_context=user_context,
        photo_context=build_chat_photo_context(db, settings),
        world_context=world_context,
    )
    messages.append(
        {
            "role": "user",
            "content": (
                "这是一次 Alicer 主动联系用户，不是回复用户刚刚发来的消息。\n"
                f"主动意图：{candidate.intent}\n"
                f"触发原因：{candidate.reason}\n"
                f"写作要求：{candidate.prompt}\n"
                "只输出将要发送给用户的一条聊天消息，1 到 3 句，短、自然、具体。"
                "不要说你是系统自动触发，不要解释策略、分数、后台、时间线。"
            ),
        }
    )
    content = (await llm.complete(messages=messages, model_settings=settings.get("model") or {})).strip()
    if not content:
        content = _fallback_proactive_text(candidate)
    message = db.add_message(
        message_id=f"msg_{uuid.uuid4().hex}",
        role="assistant",
        content=content[:900],
        metadata={
            "source": "proactive",
            "proactive": _candidate_public(candidate),
            "promptDebug": prompt_debug,
        },
    )
    event = db.add_proactive_event(
        event_id=f"pro_{uuid.uuid4().hex}",
        event_type="chat",
        status="delivered",
        intent=candidate.intent,
        source_key=candidate.source_key,
        score=candidate.score,
        reason=candidate.reason,
        message_id=str(message.get("id") or ""),
        metadata={**decision_payload, "message": message},
        decided=True,
        delivered=True,
    )
    return {"created": True, "type": "chat", "message": message, "event": event, **decision_payload}


async def _deliver_moment(
    db: Database,
    llm: LlmService,
    *,
    settings: dict,
    candidate: ProactiveCandidate,
    decision_payload: dict,
    moment_generator: MomentGenerator,
) -> dict:
    moment = await moment_generator(db, llm, settings, "proactive_life")
    event = db.add_proactive_event(
        event_id=f"pro_{uuid.uuid4().hex}",
        event_type="moment",
        status="delivered",
        intent=candidate.intent,
        source_key=candidate.source_key,
        score=candidate.score,
        reason=candidate.reason,
        moment_id=str(moment.get("id") or ""),
        metadata={**decision_payload, "moment": moment},
        decided=True,
        delivered=True,
    )
    return {"created": True, "type": "moment", "moment": moment, "event": event, **decision_payload}


def _candidate_public(candidate: ProactiveCandidate) -> dict:
    return {
        "eventType": candidate.event_type,
        "intent": candidate.intent,
        "sourceKey": candidate.source_key,
        "score": round(candidate.score, 4),
        "reason": candidate.reason,
        "metadata": candidate.metadata,
    }


def _fallback_proactive_text(candidate: ProactiveCandidate) -> str:
    if candidate.intent == "support":
        return "我刚才又想起你说的那件事了。先不用回我，别一个人硬撑就好。"
    if candidate.intent == "share_life":
        return "我这边刚从自己的节奏里抬头，忽然有点想把这一小段发给你。"
    return "我来轻轻敲一下你。忙的话不用急着回，我只是有点想你了。"


def _suppress_duplicates(candidates: list[ProactiveCandidate], recent_proactive: list[dict]) -> list[ProactiveCandidate]:
    delivered_sources = {
        (str(item.get("eventType") or ""), str(item.get("sourceKey") or ""))
        for item in recent_proactive
        if item.get("status") == "delivered"
    }
    result = []
    for item in candidates:
        if (item.event_type, item.source_key) in delivered_sources:
            continue
        result.append(item)
    return result


def _threshold(settings: dict, event_type: str) -> float:
    proactive = settings.get("proactive") or {}
    key = "momentThreshold" if event_type == "moment" else "chatThreshold"
    return _clamp_float(proactive.get(key), default=0.66 if event_type == "chat" else 0.68, minimum=0.2, maximum=0.98)


def _is_quiet_hour(now: dt.datetime, proactive: dict) -> bool:
    quiet = proactive.get("quietHours") or {}
    start = str(quiet.get("start") or "23:30")
    end = str(quiet.get("end") or "08:00")
    start_minutes = _parse_clock_minutes(start, default=23 * 60 + 30)
    end_minutes = _parse_clock_minutes(end, default=8 * 60)
    current = now.hour * 60 + now.minute
    if start_minutes <= end_minutes:
        return start_minutes <= current < end_minutes
    return current >= start_minutes or current < end_minutes


def _parse_clock_minutes(value: str, *, default: int) -> int:
    try:
        hour_text, minute_text = value.split(":", 1)
        hour = int(hour_text)
        minute = int(minute_text[:2])
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return hour * 60 + minute
    except Exception:
        pass
    return default


def _latest_delivered(events: list[dict], *, event_type: str) -> dict | None:
    return next(
        (
            item
            for item in events
            if item.get("eventType") == event_type and item.get("status") == "delivered"
        ),
        None,
    )


def _delivered_count(events: list[dict], *, event_type: str, since: dt.datetime) -> int:
    start = since.timestamp()
    return sum(
        1
        for item in events
        if item.get("eventType") == event_type
        and item.get("status") == "delivered"
        and float(item.get("deliveredAt") or item.get("createdAt") or 0) >= start
    )


def _hours_since_event(event: dict | None, now: dt.datetime) -> float:
    if not event:
        return 999.0
    return _hours_since_ts(event.get("deliveredAt") or event.get("createdAt"), now)


def _hours_since_ts(value: object, now: dt.datetime) -> float:
    try:
        timestamp = float(value or 0)
    except (TypeError, ValueError):
        timestamp = 0
    if timestamp <= 0:
        return 999.0
    return max(0.0, (now.timestamp() - timestamp) / 3600)


def _day_start(now: dt.datetime) -> dt.datetime:
    boundary = now.replace(hour=4, minute=0, second=0, microsecond=0)
    return boundary if now >= boundary else boundary - dt.timedelta(days=1)


def _daily_limit(proactive: dict, key: str, default: int) -> int:
    return _clamp_int(proactive.get(key), default=default, minimum=0, maximum=12)


def _clamp_int(value: object, *, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


def _clamp_float(value: object, *, default: float, minimum: float, maximum: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


def debug_candidates(db: Database, settings: dict | None = None) -> dict:
    merged = merge_settings(settings or db.get_settings())
    now = dt.datetime.now(TZ)
    life_context = build_life_context(db, merged)
    candidates = _build_candidates(
        settings=merged,
        now=now,
        recent_messages=db.list_messages(limit=300),
        recent_moments=db.list_moments(limit=80),
        recent_proactive=db.list_proactive_events(limit=120, since=(now - dt.timedelta(days=2)).timestamp()),
        life_context=life_context,
        user_context=build_user_timeline_context(db, merged),
        allow_moments=True,
    )
    return {
        "now": now.isoformat(),
        "candidates": [_candidate_public(item) for item in sorted(candidates, key=lambda item: item.score, reverse=True)],
    }
