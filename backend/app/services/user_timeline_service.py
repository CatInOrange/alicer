from __future__ import annotations

import time
import uuid

from ..db import Database
from .prompt_service import merge_settings


def build_user_timeline_context(db: Database, settings: dict | None = None) -> dict:
    merged = merge_settings(settings)
    config = merged.get("userTimeline") or {}
    if config.get("enabled") is False:
        return {"enabled": False, "state": {}, "recentEvents": []}
    state_row = db.get_user_timeline_state() or {}
    events = list(reversed(db.list_user_timeline_events(limit=12)))
    state = state_row.get("state") or {}
    return {
        "enabled": True,
        "state": state,
        "updatedAt": state_row.get("updatedAt"),
        "recentEvents": events,
    }


def ingest_user_timeline_events(
    db: Database,
    *,
    events: list[dict],
    settings: dict | None = None,
) -> dict:
    merged = merge_settings(settings)
    config = merged.get("userTimeline") or {}
    if config.get("enabled") is False:
        return {"accepted": 0, "state": build_user_timeline_context(db, merged)}

    accepted = []
    for raw in events[:100]:
        event = _normalize_event(raw)
        if event is None:
            continue
        accepted.append(db.add_user_timeline_event(**event))

    retention = _clamp_int(config.get("retentionDays"), default=2, minimum=1, maximum=2)
    db.prune_user_timeline_events(retention_days=retention)
    state = _summarize_state(db)
    db.save_user_timeline_state(state)
    return {
        "accepted": len(accepted),
        "events": accepted,
        "state": build_user_timeline_context(db, merged),
    }


def _normalize_event(raw: dict) -> dict | None:
    event_type = str(raw.get("eventType") or raw.get("type") or "").strip()
    source = str(raw.get("source") or "android").strip()
    if not event_type:
        return None
    if event_type == "device_battery":
        return None
    metadata = raw.get("metadata") if isinstance(raw.get("metadata"), dict) else {}
    event_time = _float_or_now(raw.get("eventTime"))
    title = str(raw.get("title") or _title_for(event_type, metadata)).strip()
    summary = str(raw.get("summary") or _summary_for(event_type, metadata)).strip()
    if not title and not summary:
        return None
    return {
        "event_id": str(raw.get("id") or f"user_{int(event_time)}_{uuid.uuid4().hex[:8]}"),
        "event_time": event_time,
        "source": source,
        "event_type": event_type,
        "title": title or event_type,
        "summary": summary or title or event_type,
        "confidence": _clamp_float(raw.get("confidence"), default=0.65),
        "privacy_level": str(raw.get("privacyLevel") or "context"),
        "metadata": metadata,
    }


def _summarize_state(db: Database) -> dict:
    events = db.list_user_timeline_events(limit=80)
    latest_by_type: dict[str, dict] = {}
    for event in events:
        event_type = str(event.get("eventType") or "")
        if event_type and event_type not in latest_by_type:
            latest_by_type[event_type] = event

    location = _latest_location(events)
    music = _latest_music(events)
    motion = _latest_motion(events)
    headset = _latest_device(events, "headset")
    activity = _infer_activity(location=location, music=music, motion=motion)
    summary = _join_filled(
        [
            location.get("summary") if location else "",
            motion.get("summary") if motion else "",
            music.get("summary") if music else "",
        ],
        "；",
    )
    return {
        "activity": activity,
        "locationLabel": _metadata_value(location, "label") if location else "",
        "music": music.get("summary") if music else "",
        "motion": motion.get("summary") if motion else "",
        "headset": headset.get("summary") if headset else "",
        "summary": summary,
        "attentionState": _attention_state(events),
        "updatedAt": time.time(),
    }


def _latest_location(events: list[dict]) -> dict | None:
    return next((item for item in events if str(item.get("eventType") or "").startswith("location_")), None)


def _latest_music(events: list[dict]) -> dict | None:
    return next((item for item in events if str(item.get("eventType") or "").startswith("music_")), None)


def _latest_motion(events: list[dict]) -> dict | None:
    return next((item for item in events if str(item.get("eventType") or "").startswith("motion_")), None)


def _latest_device(events: list[dict], kind: str) -> dict | None:
    return next(
        (
            item
            for item in events
            if str(item.get("eventType") or "").startswith(f"device_{kind}")
        ),
        None,
    )


def _infer_activity(*, location: dict | None, music: dict | None, motion: dict | None) -> str:
    motion_type = _metadata_value(motion, "activity")
    if motion_type in {"in_vehicle", "on_bicycle"}:
        return "可能在通勤或移动中"
    if motion_type == "walking":
        return "可能在步行"
    if music:
        return "正在听音乐" if not location else f"在{_metadata_value(location, 'label') or '当前位置'}听音乐"
    return "普通日常状态"


def _attention_state(events: list[dict]) -> str:
    if not events:
        return "未知"
    latest = events[0]
    age = time.time() - float(latest.get("eventTime") or 0)
    if age < 20 * 60:
        return "刚有新动态"
    if age < 2 * 3600:
        return "近期有动态"
    return "暂无近期手机动态"


def _title_for(event_type: str, metadata: dict) -> str:
    return {
        "location_snapshot": "读取当前位置",
        "location_changed": "位置变化",
        "music_playing": "正在听音乐",
        "music_paused": "音乐暂停",
        "motion_detected": "运动状态变化",
        "device_headset": "耳机状态",
        "app_foreground": "打开 Alicer",
    }.get(event_type, event_type)


def _summary_for(event_type: str, metadata: dict) -> str:
    if event_type.startswith("location"):
        label = str(metadata.get("label") or "当前位置").strip()
        return f"手机位置更新到{label}"
    if event_type == "music_playing":
        title = str(metadata.get("title") or "").strip()
        artist = str(metadata.get("artist") or "").strip()
        return _join_filled(["正在听歌", title, artist], " · ")
    if event_type == "device_headset":
        connected = metadata.get("connected") is True
        return "耳机已连接" if connected else "耳机未连接"
    if event_type == "motion_detected":
        return f"运动状态：{metadata.get('activity') or '未知'}"
    return str(metadata.get("summary") or "").strip()


def _metadata_value(event: dict | None, key: str) -> str:
    metadata = event.get("metadata") if event else {}
    if not isinstance(metadata, dict):
        return ""
    value = metadata.get(key)
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value or "").strip()


def _join_filled(items: list[str], separator: str) -> str:
    return separator.join(item for item in (value.strip() for value in items) if item)


def _float_or_now(value: object) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return time.time()


def _clamp_float(value: object, *, default: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = default
    return max(0.0, min(1.0, parsed))


def _clamp_int(value: object, *, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))
