from __future__ import annotations

import asyncio
import datetime as dt
import uuid

from ..db import Database
from .life_fact_service import build_world_context
from .life_service import advance_life_until_now, build_life_context
from .llm_service import LlmService
from .proactive_candidates import build_candidates as _build_candidates
from .proactive_candidates import candidate_public as _candidate_public
from .proactive_candidates import debug_candidates
from .proactive_delivery import deliver_chat, deliver_moment
from .proactive_policy import record_skip, select_candidate
from .proactive_types import TZ, MomentGenerator
from .prompt_service import merge_settings
from .user_timeline_service import build_user_timeline_context


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

    decision = select_candidate(candidates, settings, force=force)
    selected = decision["selected"]
    decision_payload = decision["payload"]
    if not decision["passes"]:
        threshold = float(decision_payload["threshold"])
        return {
            "reason": "below_threshold",
            **record_skip(
                db,
                candidate=selected,
                decision_payload=decision_payload,
                reason=f"below_threshold:{threshold:.2f}",
            ),
        }

    if selected.event_type == "moment":
        if moment_generator is None:
            return {"created": False, "reason": "moment_generator_unavailable", **decision_payload}
        return await deliver_moment(
            db,
            llm,
            settings=settings,
            candidate=selected,
            decision_payload=decision_payload,
            moment_generator=moment_generator,
        )
    return await deliver_chat(
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


def _clamp_int(value: object, *, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))
