from __future__ import annotations

import asyncio
import datetime as dt
import json
import random
from zoneinfo import ZoneInfo

from ..db import Database, uuid_like
from .llm_service import LlmService
from .prompt_service import merge_settings


TZ = ZoneInfo("Asia/Shanghai")


async def run_life_scheduler(db: Database, llm: LlmService) -> None:
    await advance_life_until_now(db, llm)
    while True:
        now = dt.datetime.now(TZ)
        next_run = (now.replace(minute=0, second=0, microsecond=0) + dt.timedelta(hours=1))
        await asyncio.sleep(max(1.0, (next_run - now).total_seconds()))
        await advance_life_until_now(db, llm)


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
    return {
        "enabled": True,
        "profile": stored.get("profile") or _derive_profile_from_memories(db, merged)[0],
        "state": stored.get("state") or _default_state(merged),
        "plan": stored.get("plan") or {},
        "planDate": stored.get("planDate") or "",
        "profileUpdatedAt": stored.get("profileUpdatedAt"),
        "recentEvents": recent,
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
    plan = await _ensure_daily_plan(db, llm, settings=settings, profile=profile, slot=slot, stored=stored)
    previous_state = stored.get("state") or _default_state(settings)
    recent_events = list(reversed(db.list_life_events(limit=8)))
    event = await _generate_life_event(
        llm,
        settings=settings,
        profile=profile,
        plan=plan,
        previous_state=previous_state,
        recent_events=recent_events,
        slot=slot,
    )
    normalized = _normalize_event(event, profile=profile, previous_state=previous_state, slot=slot)
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
                "today's events should follow the daily plan unless a small surprise is justified",
                "hourly events may vary but must not rewrite stable facts",
            ],
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
    slot: dt.datetime,
) -> dict:
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
    if stored_profile and profile_age < refresh_hours * 3600:
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
    if stored.get("planDate") == day and existing:
        return existing
    recent_events = list(reversed(db.list_life_events(limit=12)))
    plan = await _generate_daily_plan(
        llm,
        settings=settings,
        profile=profile,
        slot=slot,
        recent_events=recent_events,
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
                    "recentEvents": recent_text or "暂无",
                },
                ensure_ascii=False,
            ),
        },
    ]
    try:
        raw = await llm.complete(messages=prompt, model_settings=settings.get("model") or {})
        parsed = json.loads(raw[raw.find("{") : raw.rfind("}") + 1])
        if isinstance(parsed, dict):
            return _normalize_plan(parsed, profile=profile, slot=slot, source="llm")
    except Exception:
        pass
    return _fallback_plan(profile=profile, slot=slot)


def _normalize_plan(plan: dict, *, profile: dict, slot: dt.datetime, source: str) -> dict:
    events = []
    for item in plan.get("plannedEvents") or []:
        if not isinstance(item, dict):
            continue
        location = str(item.get("location") or profile.get("homeBase") or "家").strip()[:80]
        if not _location_allowed(location, profile):
            location = str(profile.get("homeBase") or "家")
        events.append(
            {
                "timeRange": str(item.get("timeRange") or "").strip()[:40],
                "activity": str(item.get("activity") or "普通日常").strip()[:80],
                "location": location,
                "intent": str(item.get("intent") or "").strip()[:160],
            }
        )
    fallback = _fallback_plan(profile=profile, slot=slot)
    return {
        "date": slot.date().isoformat(),
        "dayTheme": str(plan.get("dayTheme") or fallback["dayTheme"]).strip()[:120],
        "plannedEvents": events[:8] or fallback["plannedEvents"],
        "possibleSurprises": [
            str(item).strip()[:80]
            for item in (plan.get("possibleSurprises") or fallback["possibleSurprises"])
            if str(item).strip()
        ][:5],
        "constraints": [
            str(item).strip()[:120]
            for item in (plan.get("constraints") or fallback["constraints"])
            if str(item).strip()
        ][:6],
        "source": source,
    }


def _fallback_plan(*, profile: dict, slot: dt.datetime) -> dict:
    home = str(profile.get("homeBase") or "家")
    work_style = str(profile.get("workStyle") or "office")
    work_place = home if work_style == "flexible" else ("学校" if work_style == "campus" else "公司")
    return {
        "date": slot.date().isoformat(),
        "dayTheme": "按稳定作息推进普通但完整的一天。",
        "plannedEvents": [
            {"timeRange": "07:30-09:00", "activity": "起床整理", "location": home, "intent": "进入白天节奏"},
            {"timeRange": "09:00-12:00", "activity": "处理主要事务", "location": work_place, "intent": "推进工作或学习"},
            {"timeRange": "12:00-14:00", "activity": "午饭和短暂休息", "location": work_place, "intent": "恢复精力"},
            {"timeRange": "14:00-18:00", "activity": "继续处理事务", "location": work_place, "intent": "收束白天任务"},
            {"timeRange": "18:00-22:30", "activity": "回到个人生活", "location": home, "intent": "放松和整理心情"},
        ],
        "possibleSurprises": ["临时加班", "朋友发来消息", "路上遇到天气变化", "给自己买点小东西"],
        "constraints": ["不改写职业、住处、长期习惯", "地点变化要符合常去地点和时间距离"],
        "source": "fallback",
    }


def _derive_profile_from_memories(db: Database, settings: dict) -> tuple[dict, list[str]]:
    memories = db.list_memories(status="active", limit=120)
    companion = str(((settings.get("companion") or {}).get("name") or "Alice")).strip() or "Alice"
    relevant = []
    for item in memories:
        kind = item.get("kind")
        subject = item.get("subject")
        content = str(item.get("content") or "")
        if kind == "self_life":
            relevant.append(item)
            continue
        if subject == "companion" and kind in {"state", "fact", "preference"}:
            relevant.append(item)
            continue
        if subject == "relationship" and companion.lower() in content.lower() and kind in {"state", "fact"}:
            relevant.append(item)
    text = "\n".join(str(item.get("content") or "") for item in relevant).lower()
    occupation = _infer_occupation(text)
    profile = {
        "name": companion,
        "occupation": occupation,
        "workStyle": _infer_work_style(text, occupation),
        "homeBase": _infer_home_base(text),
        "usualPlaces": _infer_places(text),
        "sleepWindow": _infer_sleep_window(text),
        "source": "memories" if relevant else "defaults",
    }
    return profile, [str(item.get("id")) for item in relevant[:16] if item.get("id")]


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
            "source": "defaults",
        },
        [],
    )


def _fallback_event(*, profile: dict, previous_state: dict, slot: dt.datetime) -> dict:
    hour = slot.hour
    work_style = profile.get("workStyle") or "office"
    home = str(profile.get("homeBase") or "家")
    if hour < 7:
        return _event("睡觉", home, "安静", 0.28, "还在睡，房间很安静。", "延续夜间休息。", False)
    if hour < 9:
        return _event("起床整理", home, "清醒中", 0.55, "慢慢醒来，整理今天要做的事。", "从睡眠切到早晨节奏。", False)
    if 9 <= hour < 12:
        if work_style == "flexible":
            return _event("处理工作", home, "专注", 0.68, "在自己的工作节奏里处理任务。", "延续当前职业节奏。", False)
        return _event("上班", "公司", "认真", 0.72, "在工作，偶尔有一点走神。", "工作日上午的稳定安排。", False)
    if 12 <= hour < 14:
        return _event("吃午饭", random.choice([home, "公司附近", "附近街区"]), "放松", 0.62, "午饭时间，短暂从事情里抽身。", "承接上午安排。", True)
    if 14 <= hour < 18:
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


def _normalize_event(event: dict, *, profile: dict, previous_state: dict, slot: dt.datetime) -> dict:
    fallback = _fallback_event(profile=profile, previous_state=previous_state, slot=slot)
    activity = str(event.get("activity") or fallback["activity"]).strip()[:80]
    location = str(event.get("location") or fallback["location"]).strip()[:80]
    mood = str(event.get("mood") or fallback["mood"]).strip()[:40]
    summary = str(event.get("summary") or fallback["summary"]).strip()[:300]
    details = str(event.get("details") or summary).strip()[:800]
    continuity = str(event.get("continuity") or fallback["continuity"]).strip()[:300]
    if not _location_allowed(location, profile):
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


def _location_allowed(location: str, profile: dict) -> bool:
    if not location:
        return True
    usual = [str(item) for item in profile.get("usualPlaces") or []]
    broad = ["家", "公司", "学校", "路上", "附近", "街区", "商场", "餐厅", "公园", "饮品店", "工作室"]
    return any(item and item in location for item in usual + broad)


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


def _clamp_float(value: object, default: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = default
    return max(0.0, min(1.0, parsed))
