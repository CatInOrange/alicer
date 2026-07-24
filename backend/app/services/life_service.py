from __future__ import annotations

import asyncio
import datetime as dt
import hashlib
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
        return {"enabled": False, "state": {}, "profile": {}, "plan": {}, "weekPlan": {}, "recentEvents": []}
    stored = db.get_life_state() or {}
    recent = list(reversed(db.list_life_events(limit=12)))
    fact_constraints = fact_constraints_for_life(db, merged)
    today = dt.datetime.now(TZ).date()
    life_constraints = resolve_life_constraints_for_day(db, today, merged)
    profile = stored.get("profile") or _derive_profile_from_memories(db, merged)[0]
    profile = _effective_profile(profile, life_constraints=life_constraints)
    week_plan = _build_week_plan(
        db,
        settings=merged,
        profile=profile,
        start_day=today,
        recent_events=recent,
        stored_plan=stored.get("plan") or {},
    )
    return {
        "enabled": True,
        "profile": profile,
        "state": stored.get("state") or _default_state(merged),
        "plan": stored.get("plan") or {},
        "planDate": stored.get("planDate") or "",
        "weekPlan": week_plan,
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
        if item.get("canPostMoment") and not item.get("usedMomentId") and not _draft_aviation_event(item):
            return item
    events = db.list_life_events(limit=6)
    return next((item for item in events if not item.get("usedMomentId") and not _draft_aviation_event(item)), None)


def _draft_aviation_event(event: dict) -> bool:
    metadata = event.get("metadata") or {}
    plan_block = metadata.get("planBlock") or {}
    certainty = str(plan_block.get("certainty") or event.get("certainty") or "").strip()
    text = " ".join(
        str(item or "")
        for item in (
            event.get("activity"),
            event.get("location"),
            event.get("summary"),
            plan_block.get("activity"),
            plan_block.get("location"),
        )
    )
    return certainty == "draft" and any(word in text for word in ("执飞", "航班", "机场", "备勤", "航站楼", "机组"))


async def _advance_one_slot(
    db: Database,
    llm: LlmService,
    *,
    settings: dict,
    slot: dt.datetime,
) -> dict:
    existing = _life_event_at_slot(db, slot)
    if existing is not None:
        return existing
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
    plan_block = _current_plan_block(plan, slot=slot)
    if str((plan_block or {}).get("certainty") or "") == "draft":
        text = f"{normalized.get('activity') or ''} {normalized.get('location') or ''} {normalized.get('summary') or ''}"
        if any(word in text for word in ("执飞", "航班", "机场", "备勤")):
            normalized["canPostMoment"] = False
        normalized["continuity"] = (
            f"{normalized.get('continuity') or ''}；当前片段参考周草稿，未锁定。"
        ).strip("；")
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
            "planBlock": plan_block or {},
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
            "certainty": str((plan_block or {}).get("certainty") or normalized.get("source") or ""),
            "source": str((plan_block or {}).get("source") or normalized.get("source") or ""),
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
                "todayPlan 中 certainty=draft 的安排只是草稿倾向，不能说成已确认航班、已确认执飞或硬日程。"
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
    weekly_draft = _build_weekly_draft(profile=profile, start_day=slot.date(), recent_events=recent_events, days=7)
    today_draft = _draft_day_for_date(weekly_draft, slot.date())
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
                "weeklyDraft 是未锁定生活草稿，只能作为倾向；不得把草稿说成已确认航班或已确认工作。"
                "不要写成用户的行程。字段：dayTheme, plannedEvents, possibleSurprises, constraints。"
                "plannedEvents 每项包含 timeRange, activity, location, intent, certainty, source。"
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
                    "openLoops": life_constraints.get("openLoops") or [],
                    "draftBlocks": (today_draft or {}).get("draftBlocks") or [],
                    "weeklyDraft": today_draft or {},
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
            return _normalize_plan(parsed, profile=profile, slot=slot, source="llm", life_constraints=life_constraints, weekly_draft=weekly_draft)
    except Exception:
        pass
    return _normalize_plan(_fallback_plan(profile=profile, slot=slot, recent_events=recent_events), profile=profile, slot=slot, source="fallback", life_constraints=life_constraints, weekly_draft=weekly_draft)


def _normalize_plan(
    plan: dict,
    *,
    profile: dict,
    slot: dt.datetime,
    source: str,
    life_constraints: dict | None = None,
    weekly_draft: dict | None = None,
) -> dict:
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
    events = _apply_open_loop_blocks(events, life_constraints=life_constraints)
    events = _apply_draft_blocks(events, life_constraints=life_constraints, weekly_draft=weekly_draft, day=slot.date())
    events = _apply_hard_blocks(events, life_constraints=life_constraints)
    events, blocked_soft = _annotate_capacity_and_blocked_soft_events(events, life_constraints=life_constraints)
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
        "openLoops": life_constraints.get("openLoops") or [],
        "blockedSoftEvents": blocked_soft,
        "source": source,
        "generatedAt": dt.datetime.now(TZ).isoformat(),
        "hardBlocks": life_constraints.get("hardBlocks") or [],
        "draftBlocks": (_draft_day_for_date(weekly_draft or {}, slot.date()) or {}).get("draftBlocks") or [],
        "weeklyDraft": weekly_draft or {},
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


def _build_week_plan(
    db: Database,
    *,
    settings: dict,
    profile: dict,
    start_day: dt.date,
    recent_events: list[dict],
    stored_plan: dict | None = None,
    days: int = 7,
) -> dict:
    routine = profile.get("routine") or _routine_for_profile(profile)
    generated_at = dt.datetime.now(TZ).isoformat()
    draft = _current_weekly_draft(profile=profile, start_day=start_day, recent_events=recent_events, stored_plan=stored_plan, days=days)
    weekly_intention = _weekly_intention(profile=profile, routine=routine, recent_events=recent_events, start_day=start_day)
    items = []
    used_summaries: set[str] = set()
    for offset in range(max(1, min(days, 14))):
        day = start_day + dt.timedelta(days=offset)
        slot = dt.datetime.combine(day, dt.time(9, 0), tzinfo=TZ)
        constraints = resolve_life_constraints_for_day(db, day, settings)
        calendar = _calendar_state_from_events(recent_events, slot=slot)
        hard_blocks = [
            _week_hard_block_summary(item)
            for item in (constraints.get("hardBlocks") or [])[:6]
            if isinstance(item, dict)
        ]
        draft_day = _draft_day_for_date(draft, day)
        draft_blocks = [
            _week_draft_block_summary(item)
            for item in ((draft_day or {}).get("draftBlocks") or [])[:4]
            if isinstance(item, dict)
        ]
        soft_blocks = _soft_blocks_from_constraints(constraints)
        open_loops = _open_loops_from_constraints(constraints)
        day_type, confidence, basis = _routine_day_projection(
            routine=routine,
            slot=slot,
            calendar=calendar,
            hard_blocks=hard_blocks,
            draft_day=draft_day,
            soft_blocks=soft_blocks,
        )
        if constraints.get("conditionalCommitments"):
            basis.append("有条件承诺")
        if constraints.get("conflicts"):
            basis.append("存在冲突需复核")
        budgets = _day_budgets(day_type=day_type, confidence=confidence, calendar=calendar, hard_blocks=hard_blocks, soft_blocks=soft_blocks)
        summary = _week_day_summary(
            label=_relative_day_label(day, start_day=start_day),
            day_type=day_type,
            confidence=confidence,
            hard_blocks=hard_blocks,
            soft_blocks=soft_blocks,
            draft_blocks=draft_blocks,
            open_loops=open_loops,
            budgets=budgets,
            used=used_summaries,
        )
        used_summaries.add(summary)
        reasons = _week_day_reasons(basis=basis, hard_blocks=hard_blocks, soft_blocks=soft_blocks, open_loops=open_loops, calendar=calendar)
        items.append(
            {
                "date": day.isoformat(),
                "weekday": "一二三四五六日"[day.weekday()],
                "label": _relative_day_label(day, start_day=start_day),
                "dayType": day_type,
                "confidence": confidence,
                "basis": basis[:5],
                "summary": summary,
                "energyBudget": budgets["energyBudget"],
                "socialBudget": budgets["socialBudget"],
                "workLoad": budgets["workLoad"],
                "hardBlocks": hard_blocks,
                "draftBlocks": draft_blocks,
                "softBlocks": soft_blocks[:3],
                "openLoops": open_loops[:3],
                "reasons": reasons[:5],
                "risks": _week_day_risks(confidence=confidence, hard_blocks=hard_blocks, soft_blocks=soft_blocks, open_loops=open_loops, conflicts=constraints.get("conflicts") or [])[:4],
                "certainty": _week_day_certainty(confidence),
            }
        )
    return {
        "startDate": start_day.isoformat(),
        "days": items,
        "routine": routine,
        "weeklyIntention": weekly_intention,
        "draft": draft,
        "source": "facts+weekly_draft+routine",
        "generatedAt": generated_at,
        "rules": [
            "硬日程和事实账本优先于长期节律",
            "周草稿只表达可变倾向，可被事实账本随时覆盖",
            "固定工作制可按周内/周末回答上不上班",
            "排班制可生成备勤/培训/执飞倾向草稿，但不能编造航班号、航线或把草稿说成已确认",
        ],
    }


def _week_hard_block_summary(item: dict) -> dict:
    return {
        "timeRange": str(item.get("timeRange") or "").strip()[:40],
        "activity": str(item.get("activity") or item.get("title") or "已确定安排").strip()[:80],
        "location": str(item.get("location") or "").strip()[:80],
        "intent": str(item.get("intent") or item.get("summary") or "").strip()[:140],
        "source": str(item.get("source") or "fact").strip()[:40],
    }


def _week_draft_block_summary(item: dict) -> dict:
    return {
        "timeRange": str(item.get("timeRange") or "").strip()[:40],
        "activity": str(item.get("activity") or "生活草稿").strip()[:80],
        "location": str(item.get("location") or "").strip()[:80],
        "intent": str(item.get("intent") or "").strip()[:160],
        "certainty": "draft",
        "source": str(item.get("source") or "weekly_draft").strip()[:40],
    }


def _routine_day_projection(
    *,
    routine: dict,
    slot: dt.datetime,
    calendar: dict,
    hard_blocks: list[dict],
    draft_day: dict | None = None,
    soft_blocks: list[dict] | None = None,
) -> tuple[str, str, list[str]]:
    hard_text = " ".join(
        f"{item.get('activity') or ''} {item.get('location') or ''}"
        for item in hard_blocks
    )
    if hard_blocks:
        if any(word in hard_text for word in ("执飞", "航班", "机上", "机场", "上班", "工作", "培训", "备勤", "课程", "上课")):
            return "work", "hard", ["事实账本有硬日程"]
        if any(word in hard_text for word in ("休息", "调休", "放假", "请假")):
            return "rest", "hard", ["事实账本有休息安排"]
        return "scheduled", "hard", ["事实账本有已确定安排"]

    if soft_blocks:
        text = " ".join(f"{item.get('activity') or ''} {item.get('location') or ''}" for item in soft_blocks)
        if any(word in text for word in ("休息", "调休", "放假")):
            return "rest", "planned", ["事实账本有软安排"]
        if any(word in text for word in ("机场", "航班", "备勤", "培训", "上班", "工作", "太古里", "购物", "见面")):
            return "scheduled", "planned", ["事实账本有软安排"]
        return "scheduled", "planned", ["事实账本有软提示"]

    routine_type = str(routine.get("type") or "")
    if routine_type in {"weekday_office", "campus"}:
        if slot.weekday() < 5:
            label = "校园周内节律" if routine_type == "campus" else "工作日办公室节律"
            return "work", "routine", [label]
        return "rest", "routine", ["周末默认休息"]
    if routine_type == "flexible":
        if slot.weekday() < 5:
            return "flexible_work", "routine", ["弹性工作周内倾向"]
        return "flexible_rest", "routine", ["弹性工作周末倾向休息或个人安排"]
    if routine_type == "roster":
        if draft_day:
            draft_type = str(draft_day.get("dayType") or "")
            basis = [str(item) for item in draft_day.get("basis") or [] if str(item).strip()]
            return draft_type or "roster_draft", "draft", (basis or ["排班制周草稿"])[:4]
        if _routine_is_rest_day(routine, slot, calendar):
            return "rest", "routine", ["排班制且近期疲劳偏高，倾向恢复"]
        return "roster_unknown", "tentative", ["排班制未见硬航班事实"]
    if slot.weekday() < 5:
        return "work", "routine", ["默认工作日节律"]
    return "rest", "routine", ["默认周末休息"]


def _current_weekly_draft(
    *,
    profile: dict,
    start_day: dt.date,
    recent_events: list[dict],
    stored_plan: dict | None,
    days: int,
) -> dict:
    existing = (stored_plan or {}).get("weeklyDraft") or {}
    if _weekly_draft_usable(existing, profile=profile, start_day=start_day, days=days):
        return existing
    return _build_weekly_draft(profile=profile, start_day=start_day, recent_events=recent_events, days=days)


def _weekly_draft_usable(existing: dict, *, profile: dict, start_day: dt.date, days: int) -> bool:
    if not isinstance(existing, dict):
        return False
    if existing.get("startDate") != start_day.isoformat():
        return False
    if existing.get("profileKey") != _profile_draft_key(profile):
        return False
    existing_days = [item for item in existing.get("days") or [] if isinstance(item, dict)]
    return len(existing_days) >= max(1, min(days, 14))


def _build_weekly_draft(*, profile: dict, start_day: dt.date, recent_events: list[dict], days: int = 7) -> dict:
    routine = profile.get("routine") or _routine_for_profile(profile)
    count = max(1, min(days, 14))
    if str(routine.get("type") or "") != "roster":
        return {
            "startDate": start_day.isoformat(),
            "days": [],
            "profileKey": _profile_draft_key(profile),
            "certainty": "routine",
            "source": "routine",
            "generatedAt": dt.datetime.now(TZ).isoformat(),
            "rules": ["非排班制按长期节律投影，不生成周草稿班表"],
        }

    rng = random.Random(_stable_seed(f"{_profile_draft_key(profile)}:{start_day.isoformat()}"))
    fatigue = float(_calendar_state_from_events(recent_events, slot=dt.datetime.combine(start_day, dt.time(9), tzinfo=TZ)).get("fatigueLevel") or 0.35)
    monthly_range = _workday_range(routine.get("workDaysPerMonth"))
    target_work_days = max(2, min(count - 1, round(((monthly_range[0] + monthly_range[1]) / 2) / 30 * count)))
    if fatigue >= 0.72:
        target_work_days = max(1, target_work_days - 1)
    max_consecutive = _clamp_int(routine.get("maxConsecutiveWorkDays"), default=4, minimum=2, maximum=6)
    possible = [str(item) for item in routine.get("possibleDuties") or []]
    items: list[dict] = []
    consecutive_work = 0
    work_count = 0
    used_activity_counts: dict[str, int] = {}
    for offset in range(count):
        day = start_day + dt.timedelta(days=offset)
        remaining_days = count - offset
        remaining_work = max(0, target_work_days - work_count)
        must_work = remaining_work >= remaining_days
        should_rest = consecutive_work >= max_consecutive or (offset == 0 and fatigue >= 0.72)
        weekend_rest_bias = day.weekday() >= 5 and rng.random() < 0.35
        work_probability = 0.55 if remaining_work else 0.0
        if day.weekday() in {1, 2, 3}:
            work_probability += 0.08
        should_work = (must_work or rng.random() < work_probability) and not should_rest and not weekend_rest_bias
        if should_work:
            duty = _draft_roster_duty(rng, possible=possible, consecutive_work=consecutive_work)
            work_count += 1
            consecutive_work += 1
            items.append(
                _roster_draft_day(
                    day,
                    duty=duty,
                    confidence=_draft_confidence(offset),
                    rng=rng,
                    used_activity_counts=used_activity_counts,
                    consecutive_work=consecutive_work,
                    fatigue=fatigue,
                )
            )
        else:
            consecutive_work = 0
            items.append(
                _roster_rest_draft_day(
                    day,
                    fatigue=fatigue,
                    rng=rng,
                    confidence=_draft_confidence(offset),
                    used_activity_counts=used_activity_counts,
                )
            )
    return {
        "startDate": start_day.isoformat(),
        "days": items,
        "profileKey": _profile_draft_key(profile),
        "targetWorkDays": target_work_days,
        "certainty": "draft",
        "source": "routine_seeded_draft",
        "generatedAt": dt.datetime.now(TZ).isoformat(),
        "rules": [
            "草稿根据排班制节律、近期疲劳和稳定随机种子生成",
            "草稿不是事实；硬日程、聊天承诺和新事实随时覆盖它",
            "草稿不生成航班号、航线或不可更改的机场时间",
        ],
    }


def _draft_roster_duty(rng: random.Random, *, possible: list[str], consecutive_work: int) -> str:
    duties = [item for item in possible if item in {"执飞", "备勤", "培训"}]
    if not duties:
        duties = ["备勤", "培训", "执飞"]
    weights = []
    for duty in duties:
        if duty == "执飞":
            weights.append(0.46 if consecutive_work < 2 else 0.34)
        elif duty == "备勤":
            weights.append(0.34)
        else:
            weights.append(0.2)
    return rng.choices(duties, weights=weights, k=1)[0]


def _roster_draft_day(
    day: dt.date,
    *,
    duty: str,
    confidence: str,
    rng: random.Random,
    used_activity_counts: dict[str, int],
    consecutive_work: int,
    fatigue: float,
) -> dict:
    if duty == "执飞":
        day_type = "roster_flight_draft"
        variants = [
            ("06:30-12:30", "可能早班航班任务", "机场/航站楼", "早班倾向，需要前一晚早睡；未锁定航线和航班号", "flight:airport:morning"),
            ("09:30-15:30", "可能短途航班任务", "机场/机组准备区", "白天短途倾向，只代表排班可能，不等于确认执飞", "flight:airport:day"),
            ("13:30-18:30", "可能下午航班任务", "机场/航站楼", "下午飞行窗口草稿，未锁定航线和航班号", "flight:airport:afternoon"),
            ("16:00-22:00", "可能晚班航班任务", "机场/机上", "晚班倾向，晚间需要留恢复空间", "flight:airport:evening"),
            ("11:00-19:30", "可能航前准备加飞行任务", "机场/机组休息室", "偏完整工作日负荷，后续安排要轻", "flight:airport:full"),
        ]
        basis = ["排班制周草稿", "月工作天数节律", "未见硬航班事实"]
    elif duty == "培训":
        day_type = "roster_training_draft"
        variants = [
            ("09:30-12:00", "可能线上课程或资料复习", "家", "轻量培训草稿，适合留出下午弹性", "training:home:morning"),
            ("10:00-16:00", "可能培训或资质复训", "培训点/机场附近", "排班制草稿，可被新事实覆盖", "training:site:day"),
            ("14:00-17:30", "可能整理资质材料和制服", "家/附近打印店", "偏事务型培训准备，不是确认出勤", "training:errand:afternoon"),
            ("13:30-18:00", "可能参加复训安排", "培训点", "下午复训倾向，晚上不适合重安排", "training:site:afternoon"),
        ]
        basis = ["排班制周草稿", "培训可选职责", "未锁定"]
    else:
        day_type = "roster_standby_draft"
        variants = [
            ("08:30-10:00", "查看排班并整理飞行包", "家", "早上先等排班消息，后续保持机动", "standby:home:morning"),
            ("09:30-15:30", "可能居家备勤", "家", "居家等待排班确认，不等于确认出勤", "standby:home:day"),
            ("12:30-18:00", "可能机场附近备勤", "机场/备勤点", "下午留机场附近机动窗口，未锁定任务", "standby:airport:afternoon"),
            ("15:00-20:30", "可能晚间备勤窗口", "家/备勤点", "晚间机动倾向，适合减少远距离个人安排", "standby:mixed:evening"),
        ]
        basis = ["排班制周草稿", "备勤倾向", "未锁定"]
    block = _pick_roster_variant(rng, variants, used_activity_counts)
    if consecutive_work >= 3:
        basis.append("连续工作后需留恢复余量")
    if fatigue >= 0.62:
        basis.append("近期疲劳偏高")
    return {
        "date": day.isoformat(),
        "weekday": "一二三四五六日"[day.weekday()],
        "dayType": day_type,
        "confidence": confidence,
        "basis": basis,
        "summary": _draft_block_sentence(day_type, block),
        "reasons": basis,
        "draftBlocks": [{**block, "certainty": "draft", "source": "weekly_draft"}],
    }


def _roster_rest_draft_day(
    day: dt.date,
    *,
    fatigue: float,
    rng: random.Random,
    confidence: str,
    used_activity_counts: dict[str, int],
) -> dict:
    personal = rng.random() < 0.42 and fatigue < 0.72
    if personal:
        variants = [
            ("10:30-12:00", "处理房间整理和洗衣", "家", "把排班间隙里的生活小事补上", "personal:home:morning"),
            ("14:00-17:30", "可能个人安排或轻量兼职", "家/附近街区", "草稿窗口，可被排班或承诺覆盖", "personal:nearby:afternoon"),
            ("15:00-18:00", "可能去商场处理小采购", "商场/附近街区", "适合处理一次性 errands，不自动铺满全天", "personal:mall:afternoon"),
            ("19:00-21:30", "晚间轻量社交或散步", "附近街区", "保留一点生活感，但不压过恢复", "personal:nearby:evening"),
        ]
        block = _pick_roster_variant(rng, variants, used_activity_counts)
        return {
            "date": day.isoformat(),
            "weekday": "一二三四五六日"[day.weekday()],
            "dayType": "personal_draft",
            "confidence": confidence,
            "basis": ["排班制周草稿", "个人安排/兼职窗口", "未锁定"],
            "summary": _draft_block_sentence("personal_draft", block),
            "reasons": ["排班制周草稿", "个人安排/兼职窗口", "未锁定"],
            "draftBlocks": [{**block, "certainty": "draft", "source": "weekly_draft"}],
        }
    variants = [
        ("08:30-11:00", "补觉和慢慢恢复", "家", "排班间隙先恢复体力", "rest:home:morning"),
        ("10:00-13:00", "做饭、洗衣和房间整理", "家", "把生活维护放在休息日白天", "rest:home:late_morning"),
        ("14:30-17:00", "轻量散步或附近采购", "附近街区", "只安排低负荷活动，避免像全天任务", "rest:nearby:afternoon"),
        ("19:00-22:00", "晚间恢复和早睡准备", "家", "为后续可能排班留体力", "rest:home:evening"),
    ]
    block = _pick_roster_variant(rng, variants, used_activity_counts)
    basis = ["排班制周草稿", "恢复/调休倾向", "未锁定"]
    if fatigue >= 0.72:
        basis.append("近期疲劳高，优先恢复")
    return {
        "date": day.isoformat(),
        "weekday": "一二三四五六日"[day.weekday()],
        "dayType": "roster_rest_draft",
        "confidence": confidence,
        "basis": basis,
        "summary": _draft_block_sentence("roster_rest_draft", block),
        "reasons": basis,
        "draftBlocks": [{**block, "certainty": "draft", "source": "weekly_draft"}],
    }


def _pick_roster_variant(rng: random.Random, variants: list[tuple[str, str, str, str, str]], used: dict[str, int]) -> dict:
    has_unused = any(used.get(key, 0) == 0 for *_prefix, key in variants)
    weights = [
        0.0 if has_unused and used.get(key, 0) > 0 else 1.0 / (1 + used.get(key, 0) * 2.5)
        for *_prefix, key in variants
    ]
    time_range, activity, location, intent, key = rng.choices(variants, weights=weights, k=1)[0]
    used[key] = used.get(key, 0) + 1
    return {
        "timeRange": time_range,
        "activity": activity,
        "location": location,
        "intent": intent,
        "activityKey": key,
    }


def _draft_block_sentence(day_type: str, block: dict) -> str:
    if day_type.startswith("roster_flight"):
        return f"{block.get('timeRange')} 留给可能的航班任务，仍等正式排班。"
    if day_type.startswith("roster_standby"):
        return f"{block.get('timeRange')} 偏备勤机动，地点按排班消息收紧。"
    if day_type.startswith("roster_training"):
        return f"{block.get('timeRange')} 可能处理培训/资质事项，尚未锁定。"
    if day_type == "personal_draft":
        return f"{block.get('timeRange')} 适合放一个个人小安排，不是全天计划。"
    return f"{block.get('timeRange')} 以恢复为主，给后续排班留余量。"


def _draft_confidence(offset: int) -> str:
    if offset <= 1:
        return "draft_high"
    if offset <= 3:
        return "draft_medium"
    return "draft_low"


def _workday_range(value: object) -> tuple[int, int]:
    match = re.search(r"(?P<low>\d{1,2})\D+(?P<high>\d{1,2})", str(value or "14-18"))
    if match:
        low = int(match.group("low"))
        high = int(match.group("high"))
        return max(1, min(low, high)), max(low, high)
    return 14, 18


def _profile_draft_key(profile: dict) -> str:
    parts = [
        str(profile.get("occupation") or ""),
        str(profile.get("workStyle") or ""),
        str(profile.get("homeBase") or ""),
        str((profile.get("routine") or {}).get("type") or ""),
    ]
    return hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()[:12]


def _stable_seed(value: str) -> int:
    return int(hashlib.sha1(value.encode("utf-8")).hexdigest()[:12], 16)


def _draft_day_for_date(weekly_draft: dict, day: dt.date) -> dict | None:
    if not isinstance(weekly_draft, dict):
        return None
    day_text = day.isoformat()
    for item in weekly_draft.get("days") or []:
        if isinstance(item, dict) and item.get("date") == day_text:
            return item
    return None


def _soft_blocks_from_constraints(constraints: dict) -> list[dict]:
    blocks = []
    for item in [*(constraints.get("conditionalCommitments") or []), *(constraints.get("softHints") or [])]:
        if not isinstance(item, dict):
            continue
        time_range = _soft_fact_time_range(item)
        location = _location_from_fact_public(item)
        if not _soft_fact_is_schedule_like(item, time_range=time_range, location=location):
            continue
        blocks.append(
            {
                "timeRange": time_range,
                "activity": str(item.get("title") or "软安排").strip()[:80],
                "location": location,
                "intent": str(item.get("summary") or "").strip()[:160],
                "certainty": "planned" if str(item.get("status") or "") in {"planned", "active"} else "tentative",
                "source": str(item.get("source") or "life_fact").strip()[:40],
            }
        )
    return blocks


def _open_loops_from_constraints(constraints: dict) -> list[dict]:
    loops = []
    for item in constraints.get("openLoops") or []:
        if not isinstance(item, dict):
            continue
        loops.append(
            {
                "id": item.get("id"),
                "title": str(item.get("title") or "待兑现事项").strip()[:80],
                "summary": str(item.get("summary") or "").strip()[:160],
                "timeHint": str(item.get("timeHint") or "").strip()[:40],
                "timeRange": str(item.get("timeRange") or "").strip()[:40],
                "certainty": str(item.get("certainty") or "planned").strip()[:20],
                "whyToday": str(item.get("whyToday") or "来自聊天承诺，今天需要考虑。").strip()[:180],
            }
        )
    return loops


def _apply_open_loop_blocks(events: list[dict], *, life_constraints: dict) -> list[dict]:
    loops = _open_loops_from_constraints(life_constraints)
    if not loops:
        return events
    kept = list(events)
    for loop in loops:
        time_range = str(loop.get("timeRange") or _time_range_from_hint(loop.get("timeHint")) or "14:00-17:30")
        if any(_same_open_loop(event, loop) for event in kept):
            continue
        if any(_time_ranges_overlap(str(event.get("timeRange") or ""), time_range) and str(event.get("certainty") or "") == "hard" for event in kept):
            continue
        kept.append(
            {
                "timeRange": time_range,
                "activity": str(loop.get("title") or "兑现聊天承诺")[:80],
                "location": _location_from_open_loop(loop),
                "intent": str(loop.get("summary") or loop.get("whyToday") or "聊天里答应过的事，安排一次即可。")[:180],
                "certainty": str(loop.get("certainty") or "planned")[:20],
                "source": "open_loop",
                "sourceFactId": loop.get("id"),
            }
        )
    return sorted(kept, key=lambda item: _time_range_start_minutes(str(item.get("timeRange") or "")))


def _time_range_from_hint(value: object) -> str:
    hint = str(value or "").lower()
    if "morning" in hint or "上午" in hint:
        return "09:30-12:00"
    if "night" in hint or "evening" in hint or "晚上" in hint:
        return "19:00-21:30"
    if "afternoon" in hint or "下午" in hint:
        return "14:00-17:30"
    return ""


def _same_open_loop(event: dict, loop: dict) -> bool:
    source_id = str(loop.get("id") or "")
    if source_id and str(event.get("sourceFactId") or "") == source_id:
        return True
    return _text_overlap(str(event.get("activity") or ""), str(loop.get("title") or "")) >= 3


def _location_from_open_loop(loop: dict) -> str:
    text = f"{loop.get('title') or ''} {loop.get('summary') or ''}"
    for location in ("太古里", "商场", "机场", "航站楼", "公司", "学校", "家", "餐厅", "公园", "附近街区"):
        if location in text:
            return location
    return "附近街区"


def _annotate_capacity_and_blocked_soft_events(events: list[dict], *, life_constraints: dict) -> tuple[list[dict], list[dict]]:
    hard_ranges = [str(block.get("timeRange") or "") for block in life_constraints.get("hardBlocks") or []]
    conflicts = life_constraints.get("conflicts") or []
    blocked: list[dict] = []
    result: list[dict] = []
    for event in events:
        event_range = str(event.get("timeRange") or "")
        is_soft = str(event.get("source") or "") in {"open_loop", "life_fact"} or str(event.get("certainty") or "") in {"planned", "tentative"}
        if is_soft and hard_ranges and any(_time_ranges_overlap(event_range, hard_range) for hard_range in hard_ranges):
            blocked.append(
                {
                    "activity": event.get("activity"),
                    "timeRange": event_range,
                    "sourceFactId": event.get("sourceFactId"),
                    "reason": "被硬日程阻断，需要改期或在聊天里及时解释。",
                }
            )
            continue
        result.append(event)
    for conflict in conflicts[:8]:
        blocked.append(
            {
                "sourceFactId": conflict.get("factId"),
                "timeRange": "",
                "activity": "聊天承诺冲突",
                "reason": str(conflict.get("message") or "")[:180],
            }
        )
    for loop in _open_loops_from_constraints(life_constraints):
        loop_range = str(loop.get("timeRange") or _time_range_from_hint(loop.get("timeHint")) or "")
        if not loop_range or not hard_ranges:
            continue
        if any(_time_ranges_overlap(loop_range, hard_range) for hard_range in hard_ranges):
            blocked.append(
                {
                    "sourceFactId": loop.get("id"),
                    "timeRange": loop_range,
                    "activity": loop.get("title"),
                    "reason": "聊天承诺的时间窗撞上硬日程，需要主动说明改期或换轻量兑现方式。",
                }
            )
    return result[:10], blocked[:8]


def _weekly_intention(*, profile: dict, routine: dict, recent_events: list[dict], start_day: dt.date) -> dict:
    calendar = _calendar_state_from_events(recent_events, slot=dt.datetime.combine(start_day, dt.time(9), tzinfo=TZ))
    routine_type = str(routine.get("type") or "")
    fatigue = float(calendar.get("fatigueLevel") or 0.35)
    if routine_type == "roster":
        theme = "排班不确定的一周，先保留机动窗口，再把承诺和恢复安排进去。"
        needs = {"work": 0.65, "rest": 0.72 if fatigue >= 0.62 else 0.52, "relationship": 0.55, "errands": 0.42}
    elif routine_type in {"weekday_office", "campus"}:
        theme = "稳定工作/学习周，周内先保证核心义务，周末再承接个人安排。"
        needs = {"work": 0.8, "rest": 0.45, "relationship": 0.45, "errands": 0.35}
    else:
        theme = "弹性生活周，工作推进和个人事务都要留出可调整空间。"
        needs = {"work": 0.58, "rest": 0.5, "relationship": 0.5, "errands": 0.45}
    return {
        "theme": theme,
        "anchors": [str(profile.get("occupation") or ""), str(profile.get("homeBase") or "")],
        "needs": needs,
        "openLoopsPolicy": "聊天承诺按一次性待办处理；完成或被阻断后必须反馈，不自动铺满多天。",
    }


def _day_budgets(*, day_type: str, confidence: str, calendar: dict, hard_blocks: list[dict], soft_blocks: list[dict]) -> dict:
    fatigue = float(calendar.get("fatigueLevel") or 0.35)
    is_work = day_type in {"work", "roster_flight_draft", "roster_standby_draft", "roster_training_draft", "flexible_work"}
    hard_load = min(0.35, len(hard_blocks) * 0.14)
    soft_load = min(0.24, len(soft_blocks) * 0.08)
    work_load = 0.72 if is_work else 0.18
    if confidence == "hard":
        work_load = max(work_load, 0.82)
    energy = max(0.18, min(1.0, 0.82 - fatigue * 0.35 - hard_load - soft_load))
    social = max(0.12, min(0.9, 0.62 - work_load * 0.28 - fatigue * 0.2))
    return {
        "energyBudget": round(energy, 2),
        "socialBudget": round(social, 2),
        "workLoad": round(work_load, 2),
    }


def _week_day_summary(
    *,
    label: str,
    day_type: str,
    confidence: str,
    hard_blocks: list[dict],
    soft_blocks: list[dict],
    draft_blocks: list[dict],
    open_loops: list[dict],
    budgets: dict,
    used: set[str],
) -> str:
    if hard_blocks:
        main = f"{label}被硬日程锁住，重点是{hard_blocks[0].get('activity')}"
    elif open_loops:
        main = f"{label}适合兑现“{open_loops[0].get('title')}”，安排一次就够"
    elif soft_blocks:
        main = f"{label}有软安排，先给{soft_blocks[0].get('activity')}留窗口"
    elif draft_blocks:
        main = f"{label}{_draft_block_sentence(day_type, draft_blocks[0])}"
    elif day_type in {"work", "flexible_work"}:
        main = f"{label}按稳定工作节律推进，晚上留给恢复"
    else:
        main = f"{label}偏休息和生活维护，不塞重安排"
    suffix = "体力偏紧" if float(budgets.get("energyBudget") or 0) < 0.42 else "节奏可调整"
    summary = f"{main}。{suffix}。"
    if summary not in used:
        return summary
    return f"{main}，但换一个时间/地点处理，避免连续重复。{suffix}。"


def _week_day_reasons(*, basis: list[str], hard_blocks: list[dict], soft_blocks: list[dict], open_loops: list[dict], calendar: dict) -> list[str]:
    reasons = list(basis)
    if hard_blocks:
        reasons.append("硬事实优先，其他安排不得覆盖")
    if open_loops:
        reasons.append("聊天承诺进入待兑现事项")
    if soft_blocks:
        reasons.append("软计划只安排一次，未完成再改期")
    if float(calendar.get("fatigueLevel") or 0) >= 0.62:
        reasons.append("近期疲劳偏高")
    return list(dict.fromkeys(item for item in reasons if item))


def _week_day_risks(*, confidence: str, hard_blocks: list[dict], soft_blocks: list[dict], open_loops: list[dict], conflicts: list[dict]) -> list[str]:
    risks = []
    if confidence.startswith("draft"):
        risks.append("草稿不能说成已确认")
    if hard_blocks and (soft_blocks or open_loops):
        risks.append("软安排可能被硬日程挤掉")
    for conflict in conflicts[:2]:
        message = str(conflict.get("message") or "").strip()
        if message:
            risks.append(message[:120])
    return risks


def _soft_fact_is_schedule_like(item: dict, *, time_range: str, location: str) -> bool:
    fact_type = str(item.get("type") or "")
    status = str(item.get("status") or "")
    if fact_type not in {"schedule_commitment", "relationship_commitment", "current_state", "life_event_hint"}:
        return False
    try:
        importance = float(item.get("importance") or 0)
    except (TypeError, ValueError):
        importance = 0
    metadata = item.get("metadata") or {}
    has_target = bool(metadata.get("targetDate") or item.get("startsAt") or item.get("endsAt"))
    if fact_type == "life_event_hint" and (status == "candidate" or importance < 0.5):
        return False
    if has_target:
        return True
    if time_range or location:
        return fact_type in {"schedule_commitment", "relationship_commitment", "current_state"}
    return False


def _soft_fact_time_range(item: dict) -> str:
    start = _ts_to_dt(item.get("startsAt"))
    end = _ts_to_dt(item.get("endsAt"))
    if start and end:
        return f"{start.strftime('%H:%M')}-{end.strftime('%H:%M')}"
    if start:
        return start.strftime("%H:%M")
    metadata = item.get("metadata") or {}
    hint = str(metadata.get("timeHint") or "").lower()
    if "morning" in hint or "上午" in hint:
        return "09:30-12:00"
    if "night" in hint or "evening" in hint or "晚上" in hint:
        return "19:00-21:30"
    if "afternoon" in hint or "下午" in hint:
        return "14:00-17:30"
    return ""


def _location_from_fact_public(item: dict) -> str:
    text = f"{item.get('title') or ''} {item.get('summary') or ''}"
    for location in ("太古里", "机场", "航站楼", "公司", "学校", "家", "商场", "餐厅", "公园", "附近街区"):
        if location in text:
            return location
    return ""


def _week_day_certainty(confidence: str) -> str:
    if confidence == "hard":
        return "hard"
    if confidence == "planned":
        return "planned"
    if confidence.startswith("draft"):
        return "draft"
    if confidence == "routine":
        return "routine"
    return "tentative"


def _relative_day_label(day: dt.date, *, start_day: dt.date) -> str:
    delta = (day - start_day).days
    if delta == 0:
        return "今天"
    if delta == 1:
        return "明天"
    if delta == 2:
        return "后天"
    return f"周{'一二三四五六日'[day.weekday()]}"


def _normalize_plan_certainty(value: object, *, default: str) -> str:
    text = str(value or default or "planned").strip().lower()
    if text in {"hard", "planned", "routine", "tentative", "draft"}:
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
    if any(word in combined for word in ("现职业空乘", "当前职业空乘", "空乘", "空姐")) or any(
        word in hard_text for word in ("航班", "执飞", "机组", "机场")
    ):
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


def _current_plan_block(plan: dict, *, slot: dt.datetime) -> dict | None:
    minute = slot.hour * 60 + slot.minute
    for item in plan.get("plannedEvents") or []:
        if not isinstance(item, dict):
            continue
        parsed = _parse_time_range_minutes(str(item.get("timeRange") or ""))
        if parsed is None:
            continue
        start, end = parsed
        current = minute
        if end > 24 * 60 and current < start:
            current += 24 * 60
        if start <= current < end:
            return item
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


def _apply_draft_blocks(
    events: list[dict],
    *,
    life_constraints: dict,
    weekly_draft: dict | None,
    day: dt.date,
) -> list[dict]:
    if life_constraints.get("hardBlocks"):
        return events
    draft_day = _draft_day_for_date(weekly_draft or {}, day)
    draft_blocks = [
        _week_draft_block_summary(item)
        for item in ((draft_day or {}).get("draftBlocks") or [])
        if isinstance(item, dict)
    ]
    if not draft_blocks:
        return events
    kept = list(events)
    for block in draft_blocks:
        block_range = str(block.get("timeRange") or "")
        if block_range and any(_time_ranges_overlap(str(event.get("timeRange") or ""), block_range) for event in kept):
            continue
        kept.append(
            {
                "timeRange": block_range,
                "activity": str(block.get("activity") or "生活草稿")[:80],
                "location": str(block.get("location") or "家/附近街区")[:80],
                "intent": str(block.get("intent") or "周草稿倾向，未锁定。")[:180],
                "certainty": "draft",
                "source": "weekly_draft",
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


def _life_event_at_slot(db: Database, slot: dt.datetime) -> dict | None:
    return db.life_event_at_time(slot.timestamp())


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


def _text_overlap(left: str, right: str) -> int:
    left_words = {item for item in re.split(r"\W+", left.lower()) if len(item) >= 2}
    right_words = {item for item in re.split(r"\W+", right.lower()) if len(item) >= 2}
    if left_words and right_words:
        return len(left_words & right_words)
    left_chars = set(left)
    right_chars = set(right)
    return len({item for item in left_chars & right_chars if not item.isspace()})


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
