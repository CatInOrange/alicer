from __future__ import annotations

import uuid

from ..db import Database
from .proactive_candidates import candidate_public, threshold
from .proactive_types import ProactiveCandidate


def select_candidate(candidates: list[ProactiveCandidate], settings: dict, *, force: bool) -> dict:
    scored = sorted(candidates, key=lambda item: item.score, reverse=True)
    selected = scored[0]
    selected_threshold = threshold(settings, selected.event_type)
    return {
        "selected": selected,
        "payload": {
            "selected": candidate_public(selected),
            "topCandidates": [candidate_public(item) for item in scored[:5]],
            "threshold": selected_threshold,
            "force": force,
        },
        "passes": force or selected.score >= selected_threshold,
    }


def record_skip(db: Database, *, candidate: ProactiveCandidate, decision_payload: dict, reason: str) -> dict:
    event = db.add_proactive_event(
        event_id=f"pro_{uuid.uuid4().hex}",
        event_type=candidate.event_type,
        status="skipped",
        intent=candidate.intent,
        source_key=candidate.source_key,
        score=candidate.score,
        reason=reason,
        metadata=decision_payload,
        decided=True,
    )
    return {"created": False, "event": event, **decision_payload}
