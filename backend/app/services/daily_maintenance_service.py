from __future__ import annotations

import asyncio
import calendar
import datetime as dt
import logging
from zoneinfo import ZoneInfo

from ..db import Database
from ..routers.diary import generate_entry
from .life_fact_service import cleanup_life_facts, reflect_life_fact_retention
from .life_service import advance_life_until_now, build_life_context
from .llm_service import LlmService
from .memory_service import maybe_process_memory_queue
from .prompt_service import merge_settings


TZ = ZoneInfo("Asia/Shanghai")
JOB_LAST = "daily_maintenance:last"
JOB_ERROR = "daily_maintenance:error"
JOB_CONSISTENCY_LAST = "daily_maintenance:consistency:last"
logger = logging.getLogger(__name__)


def get_daily_maintenance_status(db: Database) -> dict:
    return {
        "lastRun": db.get_scheduled_job(JOB_LAST),
        "lastConsistency": db.get_scheduled_job(JOB_CONSISTENCY_LAST),
        "lastError": db.get_scheduled_job(JOB_ERROR),
    }


async def run_daily_maintenance_scheduler(db: Database, llm: LlmService) -> None:
    await _catch_up(db, llm)
    while True:
        settings = merge_settings(db.get_settings())
        config = _config(settings)
        if not config["enabled"]:
            await asyncio.sleep(30 * 60)
            continue
        next_run = _next_run(config["runTime"])
        await asyncio.sleep(
            max(1.0, (next_run - dt.datetime.now(TZ)).total_seconds())
        )
        await run_daily_maintenance_once(db, llm, settings=settings, source="scheduled")


async def run_daily_maintenance_once(
    db: Database,
    llm: LlmService,
    *,
    settings: dict | None = None,
    source: str = "manual",
) -> dict:
    merged = merge_settings(settings or db.get_settings())
    config = _config(merged)
    started_at = dt.datetime.now(TZ)
    if not config["enabled"] and source != "manual":
        result = {
            "ok": True,
            "processed": False,
            "reason": "disabled",
            "source": source,
            "startedAt": started_at.isoformat(),
            "finishedAt": dt.datetime.now(TZ).isoformat(),
        }
        db.upsert_scheduled_job(job_key=JOB_LAST, result=result)
        return result

    target_day = _target_day(started_at, config["target"])
    result: dict = {
        "ok": True,
        "processed": True,
        "source": source,
        "targetDay": target_day.isoformat(),
        "startedAt": started_at.isoformat(),
        "steps": {},
    }
    try:
        if config["advanceLife"]:
            result["steps"]["life"] = await _run_life_step(db, llm, merged)
        if config["cleanupFacts"]:
            facts = cleanup_life_facts(db)
            result["steps"]["facts"] = facts
            retention = (
                facts.get("retention") if isinstance(facts.get("retention"), dict) else None
            )
            result["steps"]["factRetention"] = (
                retention
                if retention and retention.get("processed") is not False
                else reflect_life_fact_retention(db, force=True)
            )
        if config["processMemory"]:
            result["steps"]["memory"] = await maybe_process_memory_queue(
                db,
                llm,
                settings=merged,
                force=True,
            )
        if config["generateDiary"]:
            result["steps"]["diary"] = await _run_diary_step(db, llm, target_day=target_day)
        if config["consistencyCheck"]:
            result["steps"]["consistency"] = _run_consistency_check(
                db,
                merged,
                target_day=target_day,
                now=dt.datetime.now(TZ),
            )
        result["finishedAt"] = dt.datetime.now(TZ).isoformat()
        result["health"] = _build_health_summary(db, merged)
        db.upsert_scheduled_job(job_key=JOB_LAST, result=result)
        return result
    except asyncio.CancelledError:
        raise
    except Exception as exc:  # noqa: BLE001
        result.update(
            {
                "ok": False,
                "failedAt": dt.datetime.now(TZ).isoformat(),
                "errorType": type(exc).__name__,
                "error": str(exc)[:500],
            }
        )
        db.upsert_scheduled_job(job_key=JOB_ERROR, result=result)
        db.upsert_scheduled_job(job_key=JOB_LAST, result=result)
        logger.exception("daily maintenance failed")
        return result


async def _catch_up(db: Database, llm: LlmService) -> None:
    settings = merge_settings(db.get_settings())
    config = _config(settings)
    if not config["enabled"]:
        return
    now = dt.datetime.now(TZ)
    today_run = _run_datetime(now.date(), config["runTime"])
    if now < today_run:
        return
    last = db.get_scheduled_job(JOB_LAST)
    last_day = str(((last or {}).get("result") or {}).get("targetDay") or "")
    if last_day == _target_day(now, config["target"]).isoformat():
        return
    await run_daily_maintenance_once(db, llm, settings=settings, source="startup_catch_up")


async def _run_life_step(db: Database, llm: LlmService, settings: dict) -> dict:
    life_result = await advance_life_until_now(db, llm, settings=settings)
    created = life_result.get("created") or []
    return {
        "advanced": bool(life_result.get("advanced")),
        "reason": life_result.get("reason") or "",
        "createdCount": len(created) if isinstance(created, list) else 0,
    }


async def _run_diary_step(db: Database, llm: LlmService, *, target_day: dt.date) -> dict:
    day = await generate_entry(
        db=db,
        llm=llm,
        kind="day",
        period_key=target_day.isoformat(),
        source="daily_maintenance",
        force=False,
    )
    result: dict = {"day": _entry_result(day)}
    if target_day.weekday() == 6:
        week = await generate_entry(
            db=db,
            llm=llm,
            kind="week",
            period_key=_week_key(target_day),
            source="daily_maintenance",
            force=False,
        )
        result["week"] = _entry_result(week)
    if target_day.day == calendar.monthrange(target_day.year, target_day.month)[1]:
        month = await generate_entry(
            db=db,
            llm=llm,
            kind="month",
            period_key=f"{target_day.year:04d}-{target_day.month:02d}",
            source="daily_maintenance",
            force=False,
        )
        result["month"] = _entry_result(month)
    return result


def _build_health_summary(db: Database, settings: dict) -> dict:
    life_context = build_life_context(db, settings)
    state = life_context.get("state") or {}
    state_updated_at = state.get("updatedAt") or life_context.get("updatedAt")
    return {
        "pendingMemoryQueue": db.count_pending_memory_queue(),
        "lifeStateUpdatedAt": _format_ts(state_updated_at),
        "latestLifeActivity": state.get("activity") or "",
    }


def _run_consistency_check(
    db: Database,
    settings: dict,
    *,
    target_day: dt.date,
    now: dt.datetime,
) -> dict:
    checks: list[dict] = []
    life_context = build_life_context(db, settings)
    state = life_context.get("state") or {}
    state_updated_at = _to_float(state.get("updatedAt"))
    outer_updated_at = _to_float(life_context.get("updatedAt"))
    latest_event = db.latest_life_event_before(now.timestamp())
    latest_event_time = _to_float((latest_event or {}).get("eventTime"))
    interval_hours = _clamp_int(
        ((settings.get("life") or {}).get("updateIntervalHours")),
        1,
        1,
        6,
    )
    stale_after = dt.timedelta(hours=interval_hours, minutes=30)

    if state_updated_at is None:
        checks.append(_check("life_state_timestamp", "error", "生活状态缺少 state.updatedAt。"))
    else:
        age_seconds = now.timestamp() - state_updated_at
        if age_seconds > stale_after.total_seconds():
            checks.append(
                _check(
                    "life_state_freshness",
                    "warning",
                    f"生活状态已落后 {_duration_text(age_seconds)}，超过更新间隔加宽限。",
                )
            )

    if outer_updated_at and state_updated_at and outer_updated_at - state_updated_at > 30 * 60:
        checks.append(
            _check(
                "life_state_mixed_freshness",
                "warning",
                "life_state 外层更新时间明显晚于 state.updatedAt，存在混合新鲜度。",
            )
        )

    if latest_event_time and state_updated_at and abs(latest_event_time - state_updated_at) > 60:
        checks.append(
            _check(
                "life_event_state_mismatch",
                "warning",
                "最新 life_event 时间与当前 life_state.state.updatedAt 不一致。",
            )
        )

    event_id = str(state.get("eventId") or "")
    latest_event_id = str((latest_event or {}).get("id") or "")
    if event_id and latest_event_id and event_id != latest_event_id:
        checks.append(
            _check(
                "life_event_id_mismatch",
                "warning",
                "life_state.state.eventId 不是当前最新 life_event。",
            )
        )

    diary = db.get_diary_entry(kind="day", period_key=target_day.isoformat())
    if not diary:
        checks.append(_check("diary_day_missing", "warning", f"{target_day.isoformat()} 日记不存在。"))
    elif diary.get("status") == "failed":
        checks.append(_check("diary_day_failed", "error", f"{target_day.isoformat()} 日记生成失败。"))

    pending_memory = db.count_pending_memory_queue()
    if pending_memory >= 30:
        checks.append(
            _check(
                "memory_queue_backlog",
                "warning",
                f"记忆队列仍有 {pending_memory} 条待处理，达到自动整理阈值。",
            )
        )

    for job_key, max_age_hours in (
        ("life:advance:last", interval_hours + 2),
        ("memory:auto:last", 28),
        ("life_facts:retention:last", 52),
    ):
        job = db.get_scheduled_job(job_key)
        if not job:
            checks.append(_check("scheduled_job_missing", "info", f"{job_key} 尚无运行记录。"))
            continue
        age = now.timestamp() - float(job.get("ranAt") or 0)
        if age > max_age_hours * 3600:
            checks.append(
                _check(
                    "scheduled_job_stale",
                    "warning",
                    f"{job_key} 已 {_duration_text(age)} 未更新。",
                )
            )

    for job_key in ("life:advance:error", "daily_maintenance:error"):
        job = db.get_scheduled_job(job_key)
        if job and now.timestamp() - float(job.get("ranAt") or 0) <= 24 * 3600:
            checks.append(_check("recent_job_error", "error", f"{job_key} 最近 24 小时有错误记录。"))

    checks.extend(_plan_fact_conflict_checks(db, life_context, target_day=target_day))
    severity = "error" if any(item["severity"] == "error" for item in checks) else (
        "warning" if any(item["severity"] == "warning" for item in checks) else "ok"
    )
    result = {
        "processed": True,
        "severity": severity,
        "issueCount": len([item for item in checks if item["severity"] in {"warning", "error"}]),
        "checks": checks[:40],
        "metrics": {
            "targetDay": target_day.isoformat(),
            "pendingMemoryQueue": pending_memory,
            "lifeStateUpdatedAt": _format_ts(state_updated_at),
            "lifeStateOuterUpdatedAt": _format_ts(outer_updated_at),
            "latestLifeEventAt": _format_ts(latest_event_time),
            "latestLifeActivity": (latest_event or {}).get("activity") or "",
        },
    }
    db.upsert_scheduled_job(job_key=JOB_CONSISTENCY_LAST, result=result)
    return result


def _entry_result(entry: dict) -> dict:
    return {
        "id": entry.get("id") or "",
        "status": entry.get("status") or "",
        "periodKey": entry.get("periodKey") or "",
        "source": entry.get("source") or "",
    }


def _config(settings: dict) -> dict:
    raw = settings.get("dailyMaintenance") or {}
    return {
        "enabled": raw.get("enabled") is not False,
        "runTime": _normalize_clock(str(raw.get("runTime") or "03:30")),
        "target": str(raw.get("target") or "yesterday"),
        "generateDiary": raw.get("generateDiary") is not False,
        "cleanupFacts": raw.get("cleanupFacts") is not False,
        "processMemory": raw.get("processMemory") is not False,
        "advanceLife": raw.get("advanceLife") is not False,
        "consistencyCheck": raw.get("consistencyCheck") is not False,
    }


def _next_run(run_time: str) -> dt.datetime:
    now = dt.datetime.now(TZ)
    target = _run_datetime(now.date(), run_time)
    return target if now < target else target + dt.timedelta(days=1)


def _run_datetime(day: dt.date, run_time: str) -> dt.datetime:
    hour, minute = [int(part) for part in run_time.split(":", 1)]
    return dt.datetime.combine(day, dt.time(hour=hour, minute=minute), tzinfo=TZ)


def _target_day(now: dt.datetime, target: str) -> dt.date:
    if target == "today":
        return now.date()
    return (now - dt.timedelta(days=1)).date()


def _normalize_clock(value: str) -> str:
    try:
        hour_text, minute_text = value.split(":", 1)
        hour = max(0, min(23, int(hour_text)))
        minute = max(0, min(59, int(minute_text)))
    except (TypeError, ValueError):
        hour, minute = 3, 30
    return f"{hour:02d}:{minute:02d}"


def _week_key(day: dt.date) -> str:
    year, week, _ = day.isocalendar()
    return f"{year:04d}-W{week:02d}"


def _format_ts(value: object) -> str:
    timestamp = _to_float(value)
    if timestamp is None:
        return ""
    return dt.datetime.fromtimestamp(timestamp, tz=TZ).isoformat()


def _to_float(value: object) -> float | None:
    try:
        timestamp = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return timestamp if timestamp > 0 else None


def _clamp_int(value: object, fallback: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        parsed = fallback
    return max(minimum, min(maximum, parsed))


def _check(check_id: str, severity: str, message: str) -> dict:
    return {"id": check_id, "severity": severity, "message": message}


def _duration_text(seconds: float) -> str:
    minutes = max(0, int(seconds // 60))
    if minutes < 90:
        return f"{minutes} 分钟"
    return f"{minutes / 60:.1f} 小时"


def _plan_fact_conflict_checks(db: Database, life_context: dict, *, target_day: dt.date) -> list[dict]:
    plan = life_context.get("plan") or {}
    events = [
        item
        for item in plan.get("plannedEvents") or []
        if isinstance(item, dict) and item.get("timeRange")
    ]
    if not events:
        return []
    checks: list[dict] = []
    facts = db.list_life_facts(statuses=("active", "planned"), limit=120)
    for fact in facts:
        fact_start = _to_float(fact.get("startsAt"))
        fact_end = _to_float(fact.get("endsAt"))
        if fact_start is None or fact_end is None:
            continue
        fact_start_dt = dt.datetime.fromtimestamp(fact_start, tz=TZ)
        fact_end_dt = dt.datetime.fromtimestamp(fact_end, tz=TZ)
        if fact_start_dt.date() != target_day and fact_end_dt.date() != target_day:
            continue
        for event in events:
            bounds = _event_bounds(target_day, str(event.get("timeRange") or ""))
            if bounds is None:
                continue
            event_start, event_end = bounds
            if not _overlaps(fact_start_dt, fact_end_dt, event_start, event_end):
                continue
            fact_text = f"{fact.get('title') or ''} {fact.get('summary') or ''}"
            event_text = f"{event.get('activity') or ''} {event.get('location') or ''} {event.get('intent') or ''}"
            if not _looks_compatible(fact_text, event_text):
                checks.append(
                    _check(
                        "life_fact_plan_overlap",
                        "warning",
                        f"事实“{fact.get('title') or fact.get('id')}”与计划“{event.get('timeRange')} {event.get('activity')}”时间重叠但语义不明显一致。",
                    )
                )
                break
    return checks[:12]


def _event_bounds(day: dt.date, time_range: str) -> tuple[dt.datetime, dt.datetime] | None:
    try:
        start_text, end_text = [part.strip() for part in time_range.split("-", 1)]
        start_hour, start_minute = [int(part) for part in start_text.split(":", 1)]
        end_hour, end_minute = [int(part) for part in end_text.split(":", 1)]
        start = dt.datetime.combine(day, dt.time(start_hour, start_minute), tzinfo=TZ)
        end = dt.datetime.combine(day, dt.time(end_hour, end_minute), tzinfo=TZ)
        if end <= start:
            end += dt.timedelta(days=1)
        return start, end
    except (TypeError, ValueError):
        return None


def _overlaps(
    left_start: dt.datetime,
    left_end: dt.datetime,
    right_start: dt.datetime,
    right_end: dt.datetime,
) -> bool:
    return left_start < right_end and right_start < left_end


def _looks_compatible(left: str, right: str) -> bool:
    keywords = (
        "航班",
        "执飞",
        "机场",
        "机上",
        "飞",
        "酒店",
        "睡",
        "休息",
        "通勤",
        "吃",
        "早餐",
        "纹身",
        "约",
        "工作",
        "会议",
    )
    return any(keyword in left and keyword in right for keyword in keywords)
