from __future__ import annotations

import asyncio
import datetime as dt
import json
import logging
import random
import re
from zoneinfo import ZoneInfo

from ..db import Database, uuid_like
from .life_fact_service import fact_constraints_for_life, resolve_life_constraints_for_day
from .llm_service import LlmService
from .prompt_service import merge_settings


TZ = ZoneInfo("Asia/Shanghai")
logger = logging.getLogger(__name__)


async def run_life_scheduler(db: Database, llm: LlmService) -> None:
    await _safe_scheduler_advance(db, llm, source="startup")
    while True:
        now = dt.datetime.now(TZ)
        next_run = (now.replace(minute=0, second=0, microsecond=0) + dt.timedelta(hours=1))
        await asyncio.sleep(max(1.0, (next_run - now).total_seconds()))
        await _safe_scheduler_advance(db, llm, source="hourly")


async def _safe_scheduler_advance(db: Database, llm: LlmService, *, source: str) -> None:
    started_at = dt.datetime.now(TZ).isoformat()
    try:
        result = await advance_life_until_now(db, llm)
        created = result.get("created") or []
        payload = {
            "ok": True,
            "source": source,
            "startedAt": started_at,
            "finishedAt": dt.datetime.now(TZ).isoformat(),
            "advanced": bool(result.get("advanced")),
            "reason": result.get("reason") or "",
            "createdCount": len(created) if isinstance(created, list) else 0,
            "latestStateAt": _state_updated_at_text(result.get("context") or {}),
        }
        db.upsert_scheduled_job(job_key="life:advance:last", result=payload)
    except asyncio.CancelledError:
        raise
    except Exception as exc:  # noqa: BLE001
        payload = {
            "ok": False,
            "source": source,
            "startedAt": started_at,
            "failedAt": dt.datetime.now(TZ).isoformat(),
            "errorType": type(exc).__name__,
            "error": str(exc)[:500],
        }
        db.upsert_scheduled_job(job_key="life:advance:error", result=payload)
        db.upsert_scheduled_job(job_key="life:advance:last", result=payload)
        logger.exception("life scheduler advance failed")


async def advance_life_until_now(
    db: Database,
    llm: LlmService,
    *,
    settings: dict | None = None,
    force: bool = False,
) -> dict:
    merged = merge_settings(settings or db.get_settings())
    life_settings = merged.get("life") or {}
    if life_settings.get("enabled") is False:
        return {"advanced": False, "reason": "disabled", "context": build_life_context(db, merged)}

    now = dt.datetime.now(TZ).replace(minute=0, second=0, microsecond=0)
    latest = db.latest_life_event_before(now.timestamp())
    if latest and not force:
        interval = _clamp_int(life_settings.get("updateIntervalHours"), default=1, minimum=1, maximum=6)
        latest_time = dt.datetime.fromtimestamp(float(latest["eventTime"]), tz=TZ)
        if now - latest_time < dt.timedelta(hours=interval):
            return {"advanced": False, "reason": "not_due", "context": build_life_context(db, merged)}

    slots = _due_slots(latest, now, force=force)
    created = []
    for slot in slots:
        created.append(await _advance_one_slot(db, llm, settings=merged, slot=slot))
    return {
        "advanced": bool(created),
        "created": created,
        "context": build_life_context(db, merged),
    }


def build_life_context(db: Database, settings: dict | None = None) -> dict:
    merged = merge_settings(settings or db.get_settings())
    if (merged.get("life") or {}).get("enabled") is False:
        return {"enabled": False, "state": {}, "profile": {}, "plan": {}, "recentEvents": []}
    stored = db.get_life_state() or {}
    recent = list(reversed(db.list_life_events(limit=12)))
    fact_constraints = fact_constraints_for_life(db, merged)
    life_constraints = resolve_life_constraints_for_day(db, dt.datetime.now(TZ).date(), merged)
    profile = stored.get("profile") or _derive_profile_from_memories(db, merged)[0]
    profile = _effective_profile(profile, life_constraints=life_constraints)
    return {
        "enabled": True,
        "profile": profile,
        "state": stored.get("state") or _default_state(merged),
        "plan": stored.get("plan") or {},
        "planDate": stored.get("planDate") or "",
        "updatedAt": stored.get("updatedAt"),
        "profileUpdatedAt": stored.get("profileUpdatedAt"),
        "recentEvents": recent,
        "factConstraints": fact_constraints,
        "lifeConstraints": life_constraints,
        "routine": profile.get("routine") or {},
    }


async def refresh_life_plan(
    db: Database,
    llm: LlmService,
    *,
    settings: dict | None = None,
    force_profile: bool = False,
) -> dict:
    merged = merge_settings(settings or db.get_settings())
    life_settings = merged.get("life") or {}
    if life_settings.get("enabled") is False:
        return {"refreshed": False, "reason": "disabled", "context": build_life_context(db, merged)}
    slot = dt.datetime.now(TZ).replace(minute=0, second=0, microsecond=0)
    stored = db.get_life_state() or {}
    life_constraints = resolve_life_constraints_for_day(db, slot.date(), merged)
    if force_profile:
        profile, memory_ids = _derive_profile_from_memories(db, merged)
        profile_updated_at = dt.datetime.now(TZ).timestamp()
        profile["memoryIds"] = memory_ids
        profile["profileUpdatedAt"] = profile_updated_at
    else:
        profile, memory_ids, profile_updated_at = _current_profile(db, merged, stored)
    profile = _effective_profile(profile, life_constraints=life_constraints)
    plan = await _generate_daily_plan(
        llm,
        settings=merged,
        profile=profile,
        slot=slot,
        recent_events=list(reversed(db.list_life_events(limit=12))),
        fact_constraints=fact_constraints_for_life(db, merged),
        life_constraints=life_constraints,
    )
    plan["date"] = slot.date().isoformat()
    state = stored.get("state") or _default_state(merged)
    db.save_life_state(
        profile=profile,
        state=state,
        plan=plan,
        profile_updated_at=profile_updated_at,
        plan_date=slot.date().isoformat(),
    )
    return {
        "refreshed": True,
        "profileMemoryIds": memory_ids,
        "plan": plan,
        "context": build_life_context(db, merged),
    }


def choose_moment_life_event(db: Database) -> dict | None:
    for item in db.list_life_events(limit=18):
        if item.get("canPostMoment") and not item.get("usedMomentId"):
            return item
    events = db.list_life_events(limit=6)
    return next((item for item in events if not item.get("usedMomentId")), None)


async def _advance_one_slot(
    db: Database,
    llm: LlmService,
    *,
    settings: dict,
    slot: dt.datetime,
) -> dict:
    stored = db.get_life_state() or {}
    profile, memory_ids, profile_updated_at = _current_profile(db, settings, stored)
    life_constraints = resolve_life_constraints_for_day(db, slot.date(), settings)
    profile = _effective_profile(profile, life_constraints=life_constraints)
    plan = await _ensure_daily_plan(db, llm, settings=settings, profile=profile, slot=slot, stored=stored)
    previous_state = stored.get("state") or _default_state(settings)
    recent_events = list(reversed(db.list_life_events(limit=8)))
    fact_constraints = fact_constraints_for_life(db, settings)
    event = await _generate_life_event(
        llm,
        settings=settings,
        profile=profile,
        plan=plan,
        previous_state=previous_state,
        recent_events=recent_events,
        fact_constraints=fact_constraints,
        life_constraints=life_constraints,
        slot=slot,
    )
    normalized = _normalize_event(event, profile=profile, previous_state=previous_state, slot=slot, life_constraints=life_constraints)
    event_id = f"life_{int(slot.timestamp())}_{uuid_like()}"
    saved = db.add_life_event(
        event_id=event_id,
        event_time=slot.timestamp(),
        activity=normalized["activity"],
        location=normalized["location"],
        mood=normalized["mood"],
        energy=normalized["energy"],
        summary=normalized["summary"],
        details=normalized["details"],
        continuity=normalized["continuity"],
        can_post_moment=normalized["canPostMoment"],
        metadata={
            "source": normalized["source"],
            "profile": profile,
            "memoryIds": memory_ids,
            "plan": plan,
            "stabilityRules": [
                "occupation/location/habits are derived from memories and settings",
                "chat-derived life facts and commitments override random daily variation",
                "today's events should follow the daily plan unless a small surprise is justified",
                "hourly events may vary but must not rewrite stable facts",
            ],
            "factConstraints": fact_constraints,
            "lifeConstraints": life_constraints,
            "routine": profile.get("routine") or {},
        },
    )
    db.save_life_state(
        profile=profile,
        state={
            "activity": saved["activity"],
            "location": saved["location"],
            "mood": saved["mood"],
            "energy": saved["energy"],
            "summary": saved["summary"],
            "occupation": profile.get("occupation") or "",
            "updatedAt": saved["eventTime"],
            "eventId": saved["id"],
        },
        plan=plan,
        profile_updated_at=profile_updated_at,
        plan_date=slot.date().isoformat(),
    )
    _maybe_store_life_observation(db, profile=profile)
    return saved


async def _generate_life_event(
    llm: LlmService,
    *,
    settings: dict,
    profile: dict,
    plan: dict,
    previous_state: dict,
    recent_events: list[dict],
    fact_constraints: dict,
    life_constraints: dict,
    slot: dt.datetime,
) -> dict:
    hard_event = _event_from_hard_block(life_constraints, slot=slot)
    if hard_event is not None:
        return hard_event
    companion = str(((settings.get("companion") or {}).get("name") or "Alice")).strip() or "Alice"
    recent_text = "\n".join(
        f"- {item.get('timeLabel')}: {item.get('location')} / {item.get('activity')} / {item.get('summary')}"
        for item in recent_events[-8:]
    )
    prompt = [
        {
            "role": "system",
            "content": (
                f"你是 Alicer 的生活模拟器，负责推进{companion}自己的生活轨迹。"
                "你只输出合法 JSON，不输出解释。"
                "稳定事实必须来自 profile 和记忆，不要临时改职业、住处、长期习惯。"
                "今天的活动应优先服从 todayPlan；可以偏离，但必须在 continuity 中说明合理原因。"
                "可以有随机性：临时加班、摸鱼、散步、买东西、心情波动、和朋友联系等，但必须能从上一小时自然延续。"
                "字段：activity, location, mood, energy, summary, details, continuity, canPostMoment。"
                "energy 是 0 到 1；canPostMoment 表示这件事是否适合自然生成朋友圈。"
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "time": slot.strftime("%Y-%m-%d %H:%M"),
                    "weekday": "一二三四五六日"[slot.weekday()],
                    "profile": profile,
                    "todayPlan": plan or "暂无",
                    "lifeFactConstraints": fact_constraints.get("summary") or "暂无",
                    "lifeHardConstraints": life_constraints.get("summary") or "暂无",
                    "previousState": previous_state,
                    "recentEvents": recent_text or "暂无",
                    "randomness": (settings.get("life") or {}).get("randomness", 0.62),
                },
                ensure_ascii=False,
            ),
        },
    ]
    try:
        raw = await llm.complete(messages=prompt, model_settings=settings.get("model") or {})
        parsed = json.loads(raw[raw.find("{") : raw.rfind("}") + 1])
        if isinstance(parsed, dict):
            parsed["source"] = "llm"
            return parsed
    except Exception:
        pass
    fallback = _fallback_event(profile=profile, previous_state=previous_state, slot=slot)
    fallback["source"] = "fallback"
    return fallback


def _current_profile(db: Database, settings: dict, stored: dict) -> tuple[dict, list[str], float]:
    life_settings = settings.get("life") or {}
    refresh_hours = _clamp_int(life_settings.get("profileRefreshHours"), default=24, minimum=6, maximum=168)
    now = dt.datetime.now(TZ).timestamp()
    stored_profile = stored.get("profile") or {}
    profile_updated_at = stored.get("profileUpdatedAt")
    try:
        profile_age = now - float(profile_updated_at or 0)
    except (TypeError, ValueError):
        profile_age = refresh_hours * 3600 + 1
    if stored_profile and profile_age < refresh_hours * 3600 and not _has_new_profile_facts(db, profile_updated_at):
        return stored_profile, [str(item) for item in stored_profile.get("memoryIds") or []], float(profile_updated_at or now)
    profile, memory_ids = _derive_profile_from_memories(db, settings)
    profile["memoryIds"] = memory_ids
    profile["profileUpdatedAt"] = now
    return profile, memory_ids, now


async def _ensure_daily_plan(
    db: Database,
    llm: LlmService,
    *,
    settings: dict,
    profile: dict,
    slot: dt.datetime,
    stored: dict,
) -> dict:
    day = slot.date().isoformat()
    existing = stored.get("plan") or {}
    life_constraints = resolve_life_constraints_for_day(db, slot.date(), settings)
    if stored.get("planDate") == day and existing and _plan_satisfies_constraints(existing, life_constraints):
        return existing
    recent_events = list(reversed(db.list_life_events(limit=12)))
    plan = await _generate_daily_plan(
        llm,
        settings=settings,
        profile=profile,
        slot=slot,
        recent_events=recent_events,
        fact_constraints=fact_constraints_for_life(db, settings),
        life_constraints=life_constraints,
    )
    plan["date"] = day
    return plan


async def _generate_daily_plan(
    llm: LlmService,
    *,
    settings: dict,
    profile: dict,
    slot: dt.datetime,
    recent_events: list[dict],
    fact_constraints: dict,
    life_constraints: dict,
) -> dict:
    companion = str(((settings.get("companion") or {}).get("name") or "Alice")).strip() or "Alice"
    recent_text = "\n".join(
        f"- {item.get('timeLabel')}: {item.get('location')} / {item.get('activity')} / {item.get('summary')}"
        for item in recent_events[-10:]
    )
    prompt = [
        {
            "role": "system",
            "content": (
                f"你是 Alicer 的日计划器，给{companion}生成今天的生活骨架。"
                "只输出合法 JSON。计划必须服从 profile 中的职业、住处、作息和常去地点。"
                "同时必须服从 lifeFactConstraints 中来自聊天和记忆的未来安排、承诺和当前事实。"
                "不要写成用户的行程。字段：dayTheme, plannedEvents, possibleSurprises, constraints。"
                "plannedEvents 每项包含 timeRange, activity, location, intent。"
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "date": slot.date().isoformat(),
                    "weekday": "一二三四五六日"[slot.weekday()],
                    "profile": profile,
                    "routine": profile.get("routine") or {},
                    "hardBlocks": life_constraints.get("hardBlocks") or [],
                    "conditionalCommitments": life_constraints.get("conditionalCommitments") or [],
                    "conflicts": life_constraints.get("conflicts") or [],
                    "recentEvents": recent_text or "暂无",
                    "lifeFactConstraints": fact_constraints.get("summary") or "暂无",
                    "lifeConstraintSummary": life_constraints.get("summary") or "暂无",
                },
                ensure_ascii=False,
            ),
        },
    ]
    try:
        raw = await llm.complete(messages=prompt, model_settings=settings.get("model") or {})
        parsed = json.loads(raw[raw.find("{") : raw.rfind("}") + 1])
        if isinstance(parsed, dict):
            return _normalize_plan(parsed, profile=profile, slot=slot, source="llm", life_constraints=life_constraints)
    except Exception:
        pass
    return _normalize_plan(_fallback_plan(profile=profile, slot=slot, recent_events=recent_events), profile=profile, slot=slot, source="fallback", life_constraints=life_constraints)


def _normalize_plan(plan: dict, *, profile: dict, slot: dt.datetime, source: str, life_constraints: dict | None = None) -> dict:
    events = []
    life_constraints = life_constraints or {}
    allowed_locations = set(str(item) for item in life_constraints.get("allowedLocations") or [])
    for item in plan.get("plannedEvents") or []:
        if not isinstance(item, dict):
            continue
        location = str(item.get("location") or profile.get("homeBase") or "家").strip()[:80]
        if not _location_allowed(location, profile, allowed_locations=allowed_locations):
            location = str(profile.get("homeBase") or "家")
        events.append(
            {
                "timeRange": str(item.get("timeRange") or "").strip()[:40],
                "activity": str(item.get("activity") or "普通日常").strip()[:80],
                "location": location,
                "intent": str(item.get("intent") or "").strip()[:160],
                "certainty": _normalize_plan_certainty(item.get("certainty"), default="planned"),
                "source": str(item.get("source") or source or "plan").strip()[:40],
            }
        )
    events = _apply_hard_blocks(events, life_constraints=life_constraints)
    fallback = _fallback_plan(profile=profile, slot=slot)
    return {
        "date": slot.date().isoformat(),
        "dayTheme": str(plan.get("dayTheme") or fallback["dayTheme"]).strip()[:120],
        "plannedEvents": events[:10] or fallback["plannedEvents"],
        "possibleSurprises": [
            str(item).strip()[:80]
            for item in (plan.get("possibleSurprises") or fallback["possibleSurprises"])
            if str(item).strip()
        ][:5],
        "constraints": [
            str(item).strip()[:120]
            for item in (plan.get("constraints") or fallback["constraints"])
            if str(item).strip()
        ][:6]
        + [str(item.get("message") or "")[:120] for item in (life_constraints.get("conflicts") or [])[:4] if item.get("message")],
        "source": source,
        "generatedAt": dt.datetime.now(TZ).isoformat(),
        "hardBlocks": life_constraints.get("hardBlocks") or [],
        "routine": profile.get("routine") or {},
    }


def _fallback_plan(*, profile: dict, slot: dt.datetime, recent_events: list[dict] | None = None) -> dict:
    home = str(profile.get("homeBase") or "家")
    work_style = str(profile.get("workStyle") or "office")
    routine = profile.get("routine") or _routine_for_profile(profile)
    calendar = _calendar_state_from_events(recent_events or [], slot=slot)
    if work_style in {"flexible", "roster"}:
        work_place = home if work_style == "flexible" else "机场/备勤点"
    else:
        work_place = "学校" if work_style == "campus" else "公司"
    planned_events = _routine_events(profile=profile, routine=routine, calendar=calendar, slot=slot, home=home, work_place=work_place)
    return {
        "date": slot.date().isoformat(),
        "dayTheme": _routine_day_theme(routine, slot, calendar),
        "plannedEvents": planned_events,
        "possibleSurprises": ["兼职或副业安排", "朋友发来消息", "路上遇到天气变化", "给自己买点小东西"],
        "constraints": ["不改写职业、住处、长期习惯", "硬事实优先于节律和偏好", "调休或周末可安排兼职/副业，但不能覆盖已确定日程"],
        "source": "fallback",
        "generatedAt": dt.datetime.now(TZ).isoformat(),
        "routine": routine,
    }


def _normalize_plan_certainty(value: object, *, default: str) -> str:
    text = str(value or default or "planned").strip().lower()
    if text in {"hard", "planned", "routine", "tentative"}:
        return text
    if text in {"soft", "maybe", "possible", "candidate"}:
        return "tentative"
    return default


def _derive_profile_from_memories(db: Database, settings: dict) -> tuple[dict, list[str]]:
    memories = db.list_memories(status="active", limit=120)
    profile_facts = [
        item for item in db.list_life_facts(statuses=("candidate", "planned", "active"), limit=80)
        if item.get("type") == "profile_fact"
    ]
    companion = str(((settings.get("companion") or {}).get("name") or "Alice")).strip() or "Alice"
    relevant = []
    for item in memories:
        kind = item.get("kind")
        subject = item.get("subject")
        content = str(item.get("content") or "")
        source = item.get("source") or {}
        if isinstance(source, dict) and source.get("type") == "life_simulator":
            continue
        if kind == "self_life":
            relevant.append(item)
            continue
        if subject == "companion" and kind in {"state", "fact", "preference"}:
            relevant.append(item)
            continue
        if subject == "relationship" and companion.lower() in content.lower() and kind in {"state", "fact"}:
            relevant.append(item)
    fact_text = "\n".join(f"{item.get('title') or ''} {item.get('summary') or ''}" for item in profile_facts)
    text = "\n".join([*(str(item.get("content") or "") for item in relevant), fact_text]).lower()
    occupation = _infer_occupation(text)
    profile = {
        "name": companion,
        "occupation": occupation,
        "workStyle": _infer_work_style(text, occupation),
        "homeBase": _infer_home_base(text),
        "usualPlaces": _infer_places(text),
        "sleepWindow": _infer_sleep_window(text),
        "routine": _routine_for_profile({"occupation": occupation, "workStyle": _infer_work_style(text, occupation)}),
        "source": "memories" if relevant else "defaults",
    }
    return profile, [
        *(str(item.get("id")) for item in relevant[:16] if item.get("id")),
        *(str(item.get("id")) for item in profile_facts[:8] if item.get("id")),
    ]


def _maybe_store_life_observation(db: Database, *, profile: dict) -> None:
    events = list(reversed(db.list_life_events(limit=18)))
    if len(events) < 6:
        return
    day_events = events[-12:]
    locations = _top_counts(str(item.get("location") or "") for item in day_events)
    activities = _top_counts(str(item.get("activity") or "") for item in day_events)
    if not locations and not activities:
        return
    location_text = "、".join(locations[:3]) or "常规地点"
    activity_text = "、".join(activities[:3]) or "普通日常"
    content = (
        f"最近的生活轨迹显示，{profile.get('name') or '她'}多在{location_text}活动，"
        f"主要状态是{activity_text}。这是近期状态，不代表永久设定。"
    )
    db.upsert_memory(
        memory_id="mem_life_recent_pattern",
        kind="self_life",
        subject="companion",
        content=content,
        summary=f"近期生活轨迹：{activity_text}",
        tags=["生活模拟", "近期状态"],
        confidence=0.68,
        importance=0.48,
        status="active",
        enabled=True,
        pinned=False,
        sensitive=False,
        source={
            "type": "life_simulator",
            "eventIds": [str(item.get("id")) for item in day_events[-8:] if item.get("id")],
            "createdAt": dt.datetime.now(TZ).isoformat(),
        },
        expires_at=dt.datetime.now(TZ).timestamp() + 7 * 86400,
    )


def _top_counts(items) -> list[str]:
    counts: dict[str, int] = {}
    for item in items:
        value = item.strip()
        if not value:
            continue
        counts[value] = counts.get(value, 0) + 1
    return [
        item
        for item, _ in sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))
    ]


def _infer_occupation(text: str) -> str:
    candidates = [
        ("空乘", "空乘"),
        ("空姐", "空乘"),
        ("航班", "空乘"),
        ("执飞", "空乘"),
        ("机组", "空乘"),
        ("插画", "插画师"),
        ("画稿", "插画师"),
        ("设计", "设计相关工作"),
        ("学生", "学生"),
        ("老师", "教师"),
        ("医生", "医疗工作者"),
        ("程序", "程序员"),
        ("工程师", "工程师"),
        ("自由职业", "自由职业者"),
        ("上班", "普通上班族"),
        ("公司", "普通上班族"),
    ]
    for needle, value in candidates:
        if needle in text:
            return value
    return "普通上班族"


def _infer_work_style(text: str, occupation: str) -> str:
    if occupation == "空乘" or any(word in text for word in ("航班", "执飞", "机组", "备勤", "排班")):
        return "roster"
    if "自由职业" in text or occupation in {"插画师", "自由职业者"}:
        return "flexible"
    if "学生" in occupation:
        return "campus"
    return "office"


def _infer_home_base(text: str) -> str:
    if "合租" in text:
        return "合租住处"
    if "宿舍" in text:
        return "宿舍"
    return "家"


def _infer_places(text: str) -> list[str]:
    places = ["家", "附近街区"]
    if any(word in text for word in ("空乘", "空姐", "航班", "执飞", "机组", "机场")):
        places.extend(["机场", "航站楼", "机组休息室", "机上", "酒店"])
    if "公司" in text or "上班" in text:
        places.append("公司")
    if "学校" in text or "学生" in text:
        places.append("学校")
    if "健身" in text:
        places.append("健身房")
    if "图书馆" in text:
        places.append("图书馆")
    places.append("饮品店")
    return list(dict.fromkeys(places))


def _infer_sleep_window(text: str) -> str:
    if "熬夜" in text or "夜猫" in text:
        return "01:00-09:30"
    return "23:30-07:30"


def _default_state(settings: dict) -> dict:
    profile, _ = _derive_profile_from_memories_empty(settings)
    return {
        "activity": "普通日常",
        "location": profile["homeBase"],
        "mood": "平静",
        "energy": 0.65,
        "summary": "在按自己的节奏过一天。",
        "occupation": profile["occupation"],
    }


def _derive_profile_from_memories_empty(settings: dict) -> tuple[dict, list[str]]:
    companion = str(((settings.get("companion") or {}).get("name") or "Alice")).strip() or "Alice"
    return (
        {
            "name": companion,
            "occupation": "普通上班族",
            "workStyle": "office",
            "homeBase": "家",
            "usualPlaces": ["家", "公司", "附近街区", "饮品店"],
            "sleepWindow": "23:30-07:30",
            "routine": _routine_for_profile({"occupation": "普通上班族", "workStyle": "office"}),
            "source": "defaults",
        },
        [],
    )


def _fallback_event(*, profile: dict, previous_state: dict, slot: dt.datetime) -> dict:
    hour = slot.hour
    work_style = profile.get("workStyle") or "office"
    home = str(profile.get("homeBase") or "家")
    routine = profile.get("routine") or _routine_for_profile(profile)
    calendar = _calendar_state_from_events([], slot=slot)
    if hour < 7:
        return _event("睡觉", home, "安静", 0.28, "还在睡，房间很安静。", "延续夜间休息。", False)
    if hour < 9:
        return _event("起床整理", home, "清醒中", 0.55, "慢慢醒来，整理今天要做的事。", "从睡眠切到早晨节奏。", False)
    if 9 <= hour < 12:
        if _routine_is_rest_day(routine, slot, calendar):
            return _event("调休/休息", home, "放松", 0.58, "今天按生活节律偏休息，慢慢处理个人事务。", "长期节律判定为休息日，不强行安排正式工作。", True)
        if work_style == "roster":
            return _event("备勤或整理飞行用品", "家/机场", "清醒", 0.62, "查看排班和航班信息，整理制服、证件和随身物品。", "空乘排班制下，没有明确航班时以备勤、培训或休息为主。", False)
        if work_style == "flexible":
            return _event("处理工作", home, "专注", 0.68, "在自己的工作节奏里处理任务。", "延续当前职业节奏。", False)
        return _event("上班", "公司", "认真", 0.72, "在工作，偶尔有一点走神。", "工作日上午的稳定安排。", False)
    if 12 <= hour < 14:
        return _event("吃午饭", random.choice([home, "公司附近", "附近街区"]), "放松", 0.62, "午饭时间，短暂从事情里抽身。", "承接上午安排。", True)
    if 14 <= hour < 18:
        if _routine_is_rest_day(routine, slot, calendar):
            return _event("个人安排或兼职", random.choice([home, "附近街区", "工作室"]), "轻松", 0.55, "休息日不安排正式主业，留给个人计划、兼职或恢复精力。", "调休/周末节律下的轻量安排。", True)
        if work_style == "roster":
            return _event("备勤/培训/休息", random.choice([home, "机场", "机组休息室"]), "平稳", 0.55, "没有明确航班时，按排班制处理备勤、培训或休息。", "空乘不是每天执飞，按长期节律保持自洽。", False)
        place = home if work_style == "flexible" else "公司"
        return _event("继续工作", place, "专注", 0.58, "下午继续推进手头的事。", "上午任务自然延续到下午。", False)
    if 18 <= hour < 20:
        return _event("下班后的空档", random.choice([home, "附近街区"]), "松一口气", 0.5, "从白天的节奏里退出来，给自己留一点空白。", "从工作切换到个人生活。", True)
    if 20 <= hour < 23:
        return _event("晚间放松", home, "柔软", 0.45, "窝在自己的小空间里，做点轻松的事。", "晚间固定的恢复时间。", True)
    return _event("准备休息", home, "困倦", 0.3, "准备收尾今天，慢慢安静下来。", "自然进入睡前状态。", False)


def _event(activity: str, location: str, mood: str, energy: float, summary: str, continuity: str, can_post: bool) -> dict:
    return {
        "activity": activity,
        "location": location,
        "mood": mood,
        "energy": energy,
        "summary": summary,
        "details": summary,
        "continuity": continuity,
        "canPostMoment": can_post,
    }


def _normalize_event(event: dict, *, profile: dict, previous_state: dict, slot: dt.datetime, life_constraints: dict | None = None) -> dict:
    fallback = _fallback_event(profile=profile, previous_state=previous_state, slot=slot)
    activity = str(event.get("activity") or fallback["activity"]).strip()[:80]
    location = str(event.get("location") or fallback["location"]).strip()[:80]
    mood = str(event.get("mood") or fallback["mood"]).strip()[:40]
    summary = str(event.get("summary") or fallback["summary"]).strip()[:300]
    details = str(event.get("details") or summary).strip()[:800]
    continuity = str(event.get("continuity") or fallback["continuity"]).strip()[:300]
    allowed_locations = set(str(item) for item in (life_constraints or {}).get("allowedLocations") or [])
    if not _location_allowed(location, profile, allowed_locations=allowed_locations):
        location = str(previous_state.get("location") or profile.get("homeBase") or "家")
        continuity = f"{continuity}；地点按已有生活画像校正。".strip("；")
    return {
        "activity": activity or fallback["activity"],
        "location": location or fallback["location"],
        "mood": mood or fallback["mood"],
        "energy": _clamp_float(event.get("energy"), fallback["energy"]),
        "summary": summary or fallback["summary"],
        "details": details or summary or fallback["details"],
        "continuity": continuity or fallback["continuity"],
        "canPostMoment": bool(event.get("canPostMoment", fallback["canPostMoment"])),
        "source": str(event.get("source") or "llm"),
    }


def _location_allowed(location: str, profile: dict, *, allowed_locations: set[str] | None = None) -> bool:
    if not location:
        return True
    usual = [str(item) for item in profile.get("usualPlaces") or []]
    broad = ["家", "公司", "学校", "路上", "附近", "街区", "商场", "餐厅", "公园", "饮品店", "工作室", "兼职", "机场", "航站楼", "机上", "机组", "酒店", "大连", "北京", "广州", "上海", "温泉镇", "马连洼"]
    allowed = list(allowed_locations or set())
    return any(item and item in location for item in usual + broad + allowed)


def _has_new_profile_facts(db: Database, profile_updated_at: object) -> bool:
    try:
        updated_after = float(profile_updated_at or 0)
    except (TypeError, ValueError):
        updated_after = 0
    for fact in db.list_life_facts(statuses=("candidate", "planned", "active"), limit=80):
        if fact.get("type") == "profile_fact" and float(fact.get("updatedAt") or 0) > updated_after:
            return True
    return False


def _effective_profile(profile: dict, *, life_constraints: dict) -> dict:
    result = dict(profile or {})
    result["routine"] = result.get("routine") or _routine_for_profile(result)
    hard_text = " ".join(
        f"{item.get('activity') or ''} {item.get('location') or ''} {item.get('intent') or ''}"
        for item in life_constraints.get("hardBlocks") or []
    )
    profile_text = " ".join(
        f"{item.get('title') or ''} {item.get('summary') or ''}"
        for item in life_constraints.get("profileFacts") or []
    )
    combined = f"{hard_text} {profile_text}"
    if any(word in combined for word in ("航班", "执飞", "机组", "空乘", "空姐", "机场")):
        result["occupation"] = "空乘"
        result["workStyle"] = "roster"
        result["routine"] = _routine_for_profile(result)
        places = [*(result.get("usualPlaces") or []), "机场", "航站楼", "机组休息室", "机上", "酒店"]
        result["usualPlaces"] = list(dict.fromkeys(str(item) for item in places if str(item).strip()))
    allowed = [str(item) for item in life_constraints.get("allowedLocations") or []]
    if allowed:
        result["usualPlaces"] = list(dict.fromkeys([*(str(item) for item in result.get("usualPlaces") or []), *allowed]))
    result["effectiveSource"] = "profile+life_constraints"
    return result


def _routine_for_profile(profile: dict) -> dict:
    occupation = str(profile.get("occupation") or "")
    work_style = str(profile.get("workStyle") or "")
    if occupation == "空乘" or work_style == "roster":
        return {
            "type": "roster",
            "workDaysPerMonth": "14-18",
            "maxConsecutiveWorkDays": 4,
            "minRestAfterFlightHours": 12,
            "possibleDuties": ["执飞", "备勤", "培训", "调休", "个人安排/兼职"],
        }
    if work_style == "flexible" or occupation in {"插画师", "自由职业者"}:
        return {
            "type": "flexible",
            "workDays": "弹性",
            "coreHours": "10:00-17:00",
            "restDays": "按项目节奏",
            "possibleDuties": ["项目工作", "接稿/兼职", "外出采风", "休息"],
        }
    if work_style == "campus" or occupation == "学生":
        return {
            "type": "campus",
            "workDays": "周一-周五",
            "coreHours": "08:30-17:30",
            "weekendDefault": "休息/自习",
            "possibleDuties": ["上课", "自习", "社交", "兼职"],
        }
    return {
        "type": "weekday_office",
        "workDays": "周一-周五",
        "workHours": "09:00-18:00",
        "weekendDefault": "休息",
        "overtimeProbability": "low",
        "possibleDuties": ["上班", "通勤", "休息", "兼职/副业"],
    }


def _calendar_state_from_events(recent_events: list[dict], *, slot: dt.datetime) -> dict:
    latest_flight_end = None
    work_days: set[str] = set()
    rest_days: set[str] = set()
    for item in recent_events[-30:]:
        text = f"{item.get('activity') or ''} {item.get('location') or ''} {item.get('summary') or ''}"
        event_time = item.get("eventTime")
        try:
            event_dt = dt.datetime.fromtimestamp(float(event_time), tz=TZ)
        except (TypeError, ValueError, OSError):
            continue
        if any(word in text for word in ("执飞", "航班", "机上", "机场", "上班", "工作")):
            work_days.add(event_dt.date().isoformat())
        if any(word in text for word in ("休息", "调休", "睡觉", "放松")):
            rest_days.add(event_dt.date().isoformat())
        if any(word in text for word in ("执飞", "航班", "落地")):
            latest_flight_end = event_dt
    fatigue = 0.35
    if latest_flight_end is not None:
        hours = (slot - latest_flight_end).total_seconds() / 3600
        if hours < 12:
            fatigue = 0.8
        elif hours < 24:
            fatigue = 0.62
    return {
        "recentWorkDays": len(work_days),
        "recentRestDays": len(rest_days),
        "lastFlightAt": latest_flight_end.isoformat() if latest_flight_end else "",
        "fatigueLevel": fatigue,
    }


def _routine_is_rest_day(routine: dict, slot: dt.datetime, calendar: dict) -> bool:
    routine_type = str(routine.get("type") or "")
    if routine_type == "weekday_office":
        return slot.weekday() >= 5
    if routine_type == "roster":
        return float(calendar.get("fatigueLevel") or 0) >= 0.72
    return False


def _routine_day_theme(routine: dict, slot: dt.datetime, calendar: dict) -> str:
    routine_type = str(routine.get("type") or "")
    if _routine_is_rest_day(routine, slot, calendar):
        return "按长期节律调休/休息，留出恢复和个人安排。"
    if routine_type == "roster":
        return "按排班制维持备勤、培训或休息节奏，明确航班由事实账本决定。"
    if routine_type == "weekday_office":
        return "按工作日办公室节律推进，周末默认休息。"
    if routine_type == "flexible":
        return "按弹性工作节奏推进项目，也允许副业和个人安排。"
    return "按稳定生活节律推进普通但完整的一天。"


def _routine_events(*, profile: dict, routine: dict, calendar: dict, slot: dt.datetime, home: str, work_place: str) -> list[dict]:
    if _routine_is_rest_day(routine, slot, calendar):
        return [
            {"timeRange": "08:30-10:00", "activity": "自然醒和慢慢整理", "location": home, "intent": "调休/周末以恢复状态为主", "certainty": "routine", "source": "routine"},
            {"timeRange": "10:00-12:00", "activity": "个人事务或轻量副业", "location": home, "intent": "休息日可安排兼职/副业，但不压过硬事实", "certainty": "routine", "source": "routine"},
            {"timeRange": "12:00-14:00", "activity": "午饭和休息", "location": home, "intent": "补充体力", "certainty": "routine", "source": "routine"},
            {"timeRange": "14:00-17:30", "activity": "外出散步、见朋友或继续兼职", "location": "附近街区", "intent": "保持生活感和弹性安排", "certainty": "routine", "source": "routine"},
            {"timeRange": "18:00-22:30", "activity": "晚间放松", "location": home, "intent": "收束一天", "certainty": "routine", "source": "routine"},
        ]
    routine_type = str(routine.get("type") or "")
    if routine_type == "roster":
        return [
            {"timeRange": "08:00-09:30", "activity": "起床整理并查看排班", "location": home, "intent": "确认当天是否执飞、备勤或培训", "certainty": "routine", "source": "routine"},
            {"timeRange": "09:30-12:00", "activity": "备勤/培训准备或整理飞行用品", "location": "家/机场", "intent": "空乘排班制下的常规准备", "certainty": "routine", "source": "routine"},
            {"timeRange": "12:00-14:00", "activity": "午饭和短暂休息", "location": home, "intent": "保持体力", "certainty": "routine", "source": "routine"},
            {"timeRange": "14:00-17:30", "activity": "备勤、培训、个人安排或兼职", "location": "家/机场/附近街区", "intent": "没有明确航班时不强行执飞", "certainty": "routine", "source": "routine"},
            {"timeRange": "18:00-22:30", "activity": "晚间恢复和个人生活", "location": home, "intent": "给排班制工作留恢复空间", "certainty": "routine", "source": "routine"},
        ]
    return [
        {"timeRange": "07:30-09:00", "activity": "起床整理", "location": home, "intent": "进入白天节奏", "certainty": "routine", "source": "routine"},
        {"timeRange": "09:00-12:00", "activity": "处理主要事务", "location": work_place, "intent": "推进工作或学习", "certainty": "routine", "source": "routine"},
        {"timeRange": "12:00-14:00", "activity": "午饭和短暂休息", "location": work_place, "intent": "恢复精力", "certainty": "routine", "source": "routine"},
        {"timeRange": "14:00-18:00", "activity": "继续处理事务", "location": work_place, "intent": "收束白天任务", "certainty": "routine", "source": "routine"},
        {"timeRange": "18:00-22:30", "activity": "回到个人生活", "location": home, "intent": "放松和整理心情", "certainty": "routine", "source": "routine"},
    ]


def _event_from_hard_block(life_constraints: dict, *, slot: dt.datetime) -> dict | None:
    for block in life_constraints.get("hardBlocks") or []:
        start = _ts_to_dt(block.get("startsAt"))
        end = _ts_to_dt(block.get("endsAt"))
        if start is None or end is None:
            continue
        if start <= slot < end:
            return {
                "activity": str(block.get("activity") or "已确定安排"),
                "location": str(block.get("location") or "按事实地点"),
                "mood": "专注",
                "energy": 0.58,
                "summary": str(block.get("intent") or block.get("activity") or "正在执行已确定日程。")[:300],
                "details": str(block.get("intent") or "")[:800],
                "continuity": f"当前时间命中硬日程 {block.get('timeRange')}，优先服从事实账本。",
                "canPostMoment": False,
                "source": "hard_constraint",
            }
    return None


def _apply_hard_blocks(events: list[dict], *, life_constraints: dict) -> list[dict]:
    hard_blocks = life_constraints.get("hardBlocks") or []
    if not hard_blocks:
        return events
    kept = []
    for event in events:
        event_range = str(event.get("timeRange") or "")
        if any(_time_ranges_overlap(event_range, str(block.get("timeRange") or "")) for block in hard_blocks):
            continue
        kept.append(event)
    for block in hard_blocks:
        kept.append(
            {
                "timeRange": str(block.get("timeRange") or ""),
                "activity": str(block.get("activity") or "已确定安排")[:80],
                "location": str(block.get("location") or "按事实地点")[:80],
                "intent": str(block.get("intent") or "硬事实锁定，不能被其他活动覆盖。")[:180],
                "certainty": "hard",
                "source": "fact",
            }
        )
    return sorted(kept, key=lambda item: _time_range_start_minutes(str(item.get("timeRange") or "")))


def _plan_satisfies_constraints(plan: dict, life_constraints: dict) -> bool:
    hard_blocks = life_constraints.get("hardBlocks") or []
    if not hard_blocks:
        return True
    events = plan.get("plannedEvents") or []
    for block in hard_blocks:
        block_range = str(block.get("timeRange") or "")
        block_activity = str(block.get("activity") or "")
        matched = False
        for event in events:
            event_range = str((event or {}).get("timeRange") or "")
            event_text = f"{(event or {}).get('activity') or ''} {(event or {}).get('location') or ''}"
            if _time_ranges_overlap(event_range, block_range) and (
                block_activity[:4] in event_text or any(word in event_text for word in ("航班", "执飞", "机场", "备勤", "上班"))
            ):
                matched = True
                break
        if not matched:
            return False
    return True


def _time_ranges_overlap(left: str, right: str) -> bool:
    left_range = _parse_time_range_minutes(left)
    right_range = _parse_time_range_minutes(right)
    if left_range is None or right_range is None:
        return False
    return left_range[0] < right_range[1] and right_range[0] < left_range[1]


def _time_range_start_minutes(value: str) -> int:
    parsed = _parse_time_range_minutes(value)
    return parsed[0] if parsed else 24 * 60


def _parse_time_range_minutes(value: str) -> tuple[int, int] | None:
    match = re.search(r"(?P<sh>\d{1,2}):(?P<sm>\d{2})\s*[-—~至]\s*(?P<eh>\d{1,2}):(?P<em>\d{2})", value)
    if match is None:
        return None
    start = int(match.group("sh")) * 60 + int(match.group("sm"))
    end = int(match.group("eh")) * 60 + int(match.group("em"))
    if end <= start:
        end += 24 * 60
    return start, end


def _ts_to_dt(value: object) -> dt.datetime | None:
    try:
        if value is None:
            return None
        return dt.datetime.fromtimestamp(float(value), tz=TZ)
    except (TypeError, ValueError, OSError):
        return None


def _due_slots(latest: dict | None, now: dt.datetime, *, force: bool) -> list[dt.datetime]:
    if force or not latest:
        return [now]
    latest_time = dt.datetime.fromtimestamp(float(latest["eventTime"]), tz=TZ).replace(minute=0, second=0, microsecond=0)
    slots = []
    cursor = latest_time + dt.timedelta(hours=1)
    while cursor <= now and len(slots) < 6:
        slots.append(cursor)
        cursor += dt.timedelta(hours=1)
    return slots or [now]


def _clamp_int(value: object, *, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


def _state_updated_at_text(context: dict) -> str:
    state = (context or {}).get("state") or {}
    try:
        raw = float(state.get("updatedAt") or 0)
    except (TypeError, ValueError):
        return ""
    if raw <= 0:
        return ""
    return dt.datetime.fromtimestamp(raw, tz=TZ).isoformat()


def _clamp_float(value: object, default: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = default
    return max(0.0, min(1.0, parsed))
