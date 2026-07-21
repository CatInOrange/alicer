from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

from ..db import Database
from .llm_service import LlmService
from .prompt_service import merge_settings


TZ = ZoneInfo("Asia/Shanghai")
PLAN_AFFECTING_TYPES = {
    "schedule_commitment",
    "relationship_commitment",
    "current_state",
    "profile_fact",
    "life_event_hint",
}
PLAN_AFFECTING_STATUSES = {"candidate", "planned", "active", "completed", "cancelled", "superseded", "expired"}


async def reconcile_after_life_facts_changed(
    db: Database,
    llm: LlmService,
    *,
    settings: dict | None = None,
    facts: list[dict],
    reason: str,
) -> dict:
    """Refresh projections after facts that can change Alicer's near-future reality.

    This service is intentionally deterministic except for the life plan generator
    it may call after a fact is already accepted. Context composition itself must
    stay LLM-free on the synchronous chat path.
    """

    merged = merge_settings(settings or db.get_settings())
    affected = [fact for fact in facts if _affects_life_projection(fact)]
    if not affected:
        result = {
            "reconciled": False,
            "reason": "no_projection_affecting_facts",
            "sourceReason": reason,
            "factIds": [str(fact.get("id") or "") for fact in facts if fact.get("id")],
        }
        db.upsert_scheduled_job(job_key="consistency:life_projection:last", result=result)
        return result

    today = dt.datetime.now(TZ).date()
    dates = _affected_dates(affected)
    should_refresh_today = not dates or today in dates
    result: dict = {
        "reconciled": True,
        "sourceReason": reason,
        "factIds": [str(fact.get("id") or "") for fact in affected if fact.get("id")],
        "affectedDates": sorted(date.isoformat() for date in dates),
        "refreshedTodayPlan": False,
    }
    if should_refresh_today:
        from .life_service import refresh_life_plan

        refreshed = await refresh_life_plan(db, llm, settings=merged, force_profile=_has_profile_fact(affected))
        result["refreshedTodayPlan"] = bool(refreshed.get("refreshed"))
        result["planSource"] = ((refreshed.get("plan") or {}).get("source") or "")
        result["planGeneratedAt"] = ((refreshed.get("plan") or {}).get("generatedAt") or "")
    else:
        result["reason"] = "affected_date_not_today"
    db.upsert_scheduled_job(job_key="consistency:life_projection:last", result=result)
    return result


def _affects_life_projection(fact: dict) -> bool:
    fact_type = str(fact.get("type") or fact.get("fact_type") or "")
    status = str(fact.get("status") or "")
    if fact_type not in PLAN_AFFECTING_TYPES:
        return False
    if status and status not in PLAN_AFFECTING_STATUSES:
        return False
    if fact_type == "current_state":
        return True
    if fact_type == "profile_fact":
        return True
    metadata = fact.get("metadata") or {}
    if (
        fact_type in {"schedule_commitment", "relationship_commitment", "life_event_hint"}
        and metadata.get("targetDate")
        and str(metadata.get("commitmentStrength") or "") in {"accepted", "planned", "confirmed"}
        and float(fact.get("importance") or 0) >= 0.5
    ):
        return True
    return bool(fact.get("startsAt") or fact.get("starts_at") or fact.get("endsAt") or fact.get("ends_at"))


def _affected_dates(facts: list[dict]) -> set[dt.date]:
    dates: set[dt.date] = set()
    for fact in facts:
        start = _from_timestamp(fact.get("startsAt") or fact.get("starts_at"))
        end = _from_timestamp(fact.get("endsAt") or fact.get("ends_at"))
        if start is None and end is None:
            metadata = fact.get("metadata") or {}
            target_date = _parse_date(metadata.get("targetDate"))
            if target_date is not None:
                dates.add(target_date)
            continue
        if start is None:
            start = end
        if end is None:
            end = start
        if start is None or end is None:
            continue
        current = start.date()
        final = end.date()
        while current <= final:
            dates.add(current)
            current += dt.timedelta(days=1)
    return dates


def _has_profile_fact(facts: list[dict]) -> bool:
    return any(str(fact.get("type") or fact.get("fact_type") or "") == "profile_fact" for fact in facts)


def _from_timestamp(value: object) -> dt.datetime | None:
    try:
        if value is None:
            return None
        return dt.datetime.fromtimestamp(float(value), tz=TZ)
    except (TypeError, ValueError, OSError):
        return None


def _parse_date(value: object) -> dt.date | None:
    if value is None:
        return None
    try:
        return dt.date.fromisoformat(str(value)[:10])
    except ValueError:
        return None
