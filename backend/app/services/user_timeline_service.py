from __future__ import annotations

import datetime as dt
import math
import time
import uuid

import httpx

from ..config import get_settings
from ..db import Database
from .prompt_service import merge_settings


LOCATION_STALE_SECONDS = 90 * 60
PLACE_MATCH_RADIUS_METERS = 220.0
MAX_REMEMBERED_PLACES = 16


def build_user_timeline_context(db: Database, settings: dict | None = None) -> dict:
    merged = merge_settings(settings)
    config = merged.get("userTimeline") or {}
    if config.get("enabled") is False:
        return {"enabled": False, "state": {}, "recentEvents": []}
    state_row = db.get_user_timeline_state() or {}
    events = _prompt_events(db.list_user_timeline_events(limit=30))
    state = state_row.get("state") or {}
    return {
        "enabled": True,
        "state": state,
        "updatedAt": state_row.get("updatedAt"),
        "recentEvents": list(reversed(events[:12])),
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
    previous_state = (db.get_user_timeline_state() or {}).get("state") or {}
    for raw in events[:100]:
        event = _normalize_event(raw)
        if event is None:
            continue
        if str(event["event_type"]).startswith("location_"):
            _enrich_location_event(event, previous_state=previous_state)
        accepted.append(db.add_user_timeline_event(**event))

    retention = _clamp_int(config.get("retentionDays"), default=2, minimum=1, maximum=2)
    db.prune_user_timeline_events(retention_days=retention)
    state = _summarize_state(db, previous_state=previous_state)
    db.save_user_timeline_state(state)
    return {
        "accepted": len(accepted),
        "events": accepted,
        "state": build_user_timeline_context(db, merged),
    }


def _normalize_event(raw: dict) -> dict | None:
    event_type = str(raw.get("eventType") or raw.get("type") or "").strip()
    source = str(raw.get("source") or "android").strip()
    if not event_type or event_type == "device_battery":
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
        "metadata": dict(metadata),
    }


def _summarize_state(db: Database, *, previous_state: dict) -> dict:
    events = db.list_user_timeline_events(limit=120)
    places = _update_places(events=events, previous_places=previous_state.get("places") or [])
    location = _latest_location(events)
    music = _latest_music(events)
    motion = _latest_motion(events)
    headset = _latest_device(events, "headset")
    location_state = _location_state(location, places, previous_state=previous_state)
    movement = _movement_state(location=location, motion=motion)
    music_text = music.get("summary") if music else ""
    activity = _infer_activity(
        location_state=location_state,
        music=music,
        movement=movement,
    )
    availability = _availability_state(movement=movement, music=music, location_state=location_state)
    cue = _relationship_cue(
        location_state=location_state,
        music=music,
        movement=movement,
        availability=availability,
    )
    summary = _join_filled(
        [
            location_state.get("changeSummary", ""),
            location_state.get("label", ""),
            movement.get("summary", ""),
            music_text,
        ],
        "；",
    )
    return {
        "activity": activity,
        "scene": location_state.get("scene", "未知"),
        "availability": availability,
        "locationLabel": location_state.get("label", ""),
        "placeKind": location_state.get("placeKind", ""),
        "placeId": location_state.get("placeId", ""),
        "city": location_state.get("city", ""),
        "district": location_state.get("district", ""),
        "addressHint": location_state.get("addressHint", ""),
        "locationAgeMinutes": location_state.get("ageMinutes"),
        "locationConfidence": location_state.get("confidence"),
        "locationStale": location_state.get("stale", True),
        "placeChanged": location_state.get("placeChanged", False),
        "cityChanged": location_state.get("cityChanged", False),
        "cityChange": location_state.get("cityChange", {}),
        "music": music_text,
        "currentMusicTitle": _metadata_value(music, "title") if music else "",
        "currentMusicArtist": _metadata_value(music, "artist") if music else "",
        "motion": movement.get("summary", ""),
        "headset": headset.get("summary") if headset else "",
        "summary": summary,
        "relationshipCue": cue,
        "attentionState": _attention_state(events),
        "places": places,
        "updatedAt": time.time(),
    }


def _prompt_events(events: list[dict]) -> list[dict]:
    high_signal = []
    for event in events:
        event_type = str(event.get("eventType") or "")
        if event_type == "app_foreground" or event_type == "device_headset":
            continue
        high_signal.append(event)
    return high_signal


def _enrich_location_event(event: dict, *, previous_state: dict) -> None:
    metadata = event["metadata"]
    lat = _float_or_none(metadata.get("latitude"))
    lon = _float_or_none(metadata.get("longitude"))
    if lat is not None and lon is not None:
        metadata["latitude"] = round(lat, 5)
        metadata["longitude"] = round(lon, 5)
    if lat is not None and lon is not None and not _metadata_has_place(metadata):
        metadata.update(_reverse_geocode(lat=lat, lon=lon))
    label = _location_label(metadata)
    previous_city = str(previous_state.get("city") or "").strip()
    city = str(metadata.get("city") or "").strip()
    city_changed = bool(previous_city and city and previous_city != city)
    metadata["semanticLabel"] = label
    metadata["cityChanged"] = city_changed
    event["title"] = "城市变化" if city_changed else "位置快照"
    event["summary"] = (
        f"城市从{previous_city}变化到{city}，当前位置在{label}"
        if city_changed
        else f"位置更新到{label}"
    )
    event["metadata"] = metadata


def _reverse_geocode(*, lat: float, lon: float) -> dict:
    settings = get_settings()
    if not settings.amap_key:
        return {}
    try:
        params = {
            "key": settings.amap_key,
            "location": f"{lon},{lat}",
            "extensions": "all",
            "roadlevel": 0,
        }
        with httpx.Client(timeout=4) as client:
            response = client.get("https://restapi.amap.com/v3/geocode/regeo", params=params)
            response.raise_for_status()
            data = response.json()
        if str(data.get("status")) != "1":
            return {}
        regeocode = data.get("regeocode") or {}
        component = regeocode.get("addressComponent") or {}
        city = component.get("city")
        if isinstance(city, list):
            city = ""
        pois = regeocode.get("pois") or []
        poi_name = ""
        if pois and isinstance(pois[0], dict):
            poi_name = str(pois[0].get("name") or "").strip()
        return {
            "province": str(component.get("province") or "").strip(),
            "city": str(city or component.get("province") or "").strip(),
            "district": str(component.get("district") or "").strip(),
            "township": str(component.get("township") or "").strip(),
            "address": str(regeocode.get("formatted_address") or "").strip(),
            "poi": poi_name,
        }
    except Exception:
        return {}


def _metadata_has_place(metadata: dict) -> bool:
    return any(str(metadata.get(key) or "").strip() for key in ("city", "district", "address", "poi"))


def _update_places(*, events: list[dict], previous_places: list[dict]) -> list[dict]:
    places = [_normalize_place(item) for item in previous_places if isinstance(item, dict)]
    places = [item for item in places if item]
    for event in sorted(events, key=lambda item: float(item.get("eventTime") or 0)):
        if not str(event.get("eventType") or "").startswith("location_"):
            continue
        metadata = event.get("metadata") if isinstance(event.get("metadata"), dict) else {}
        lat = _float_or_none(metadata.get("latitude"))
        lon = _float_or_none(metadata.get("longitude"))
        if lat is None or lon is None:
            continue
        place = _match_place(places, lat=lat, lon=lon)
        if place is None:
            place = {
                "id": f"place_{uuid.uuid4().hex[:8]}",
                "kind": "unknown",
                "label": _location_label(metadata),
                "latitude": lat,
                "longitude": lon,
                "radiusMeters": PLACE_MATCH_RADIUS_METERS,
                "visits": 0,
                "nightHits": 0,
                "weekdayDayHits": 0,
                "seenEventIds": [],
                "firstSeen": event.get("eventTime"),
                "lastSeen": event.get("eventTime"),
                "city": str(metadata.get("city") or "").strip(),
                "district": str(metadata.get("district") or "").strip(),
                "addressHint": _address_hint(metadata),
            }
            places.append(place)
        event_id = str(event.get("id") or "")
        if event_id and event_id in set(place.get("seenEventIds") or []):
            continue
        _update_place(place, event=event, lat=lat, lon=lon, metadata=metadata)
    places.sort(key=lambda item: (float(item.get("lastSeen") or 0), int(item.get("visits") or 0)), reverse=True)
    return places[:MAX_REMEMBERED_PLACES]


def _normalize_place(item: dict) -> dict | None:
    lat = _float_or_none(item.get("latitude"))
    lon = _float_or_none(item.get("longitude"))
    if lat is None or lon is None:
        return None
    return {
        "id": str(item.get("id") or f"place_{uuid.uuid4().hex[:8]}"),
        "kind": str(item.get("kind") or "unknown"),
        "label": str(item.get("label") or "常去地点").strip(),
        "latitude": lat,
        "longitude": lon,
        "radiusMeters": _positive_float(item.get("radiusMeters"), default=PLACE_MATCH_RADIUS_METERS),
        "visits": int(item.get("visits") or 0),
        "nightHits": int(item.get("nightHits") or 0),
        "weekdayDayHits": int(item.get("weekdayDayHits") or 0),
        "seenEventIds": [
            str(value)
            for value in (item.get("seenEventIds") or [])
            if str(value).strip()
        ][-80:],
        "firstSeen": _float_or_now(item.get("firstSeen")),
        "lastSeen": _float_or_now(item.get("lastSeen")),
        "city": str(item.get("city") or "").strip(),
        "district": str(item.get("district") or "").strip(),
        "addressHint": str(item.get("addressHint") or "").strip(),
    }


def _match_place(places: list[dict], *, lat: float, lon: float) -> dict | None:
    candidates = []
    for place in places:
        distance = _distance_meters(lat, lon, float(place["latitude"]), float(place["longitude"]))
        radius = float(place.get("radiusMeters") or PLACE_MATCH_RADIUS_METERS)
        if distance <= max(radius, PLACE_MATCH_RADIUS_METERS):
            candidates.append((distance, place))
    if not candidates:
        return None
    candidates.sort(key=lambda pair: pair[0])
    return candidates[0][1]


def _update_place(place: dict, *, event: dict, lat: float, lon: float, metadata: dict) -> None:
    seen = [
        str(value)
        for value in (place.get("seenEventIds") or [])
        if str(value).strip()
    ]
    event_id = str(event.get("id") or "")
    if event_id:
        seen.append(event_id)
    place["seenEventIds"] = seen[-80:]
    visits = int(place.get("visits") or 0) + 1
    place["latitude"] = (float(place["latitude"]) * (visits - 1) + lat) / visits
    place["longitude"] = (float(place["longitude"]) * (visits - 1) + lon) / visits
    place["visits"] = visits
    place["lastSeen"] = event.get("eventTime")
    place["city"] = str(metadata.get("city") or place.get("city") or "").strip()
    place["district"] = str(metadata.get("district") or place.get("district") or "").strip()
    place["addressHint"] = _address_hint(metadata) or str(place.get("addressHint") or "")
    hour = dt.datetime.fromtimestamp(float(event.get("eventTime") or time.time())).astimezone().hour
    weekday = dt.datetime.fromtimestamp(float(event.get("eventTime") or time.time())).astimezone().weekday()
    if hour >= 22 or hour < 7:
        place["nightHits"] = int(place.get("nightHits") or 0) + 1
    if weekday < 5 and 9 <= hour <= 18:
        place["weekdayDayHits"] = int(place.get("weekdayDayHits") or 0) + 1
    if int(place.get("nightHits") or 0) >= 2 and visits >= 2:
        place["kind"] = "home"
        place["label"] = "家"
    elif int(place.get("weekdayDayHits") or 0) >= 3 and visits >= 3 and place.get("kind") != "home":
        place["kind"] = "work"
        place["label"] = "公司/工作地"
    elif visits >= 2 and place.get("kind") == "unknown":
        place["kind"] = "frequent"
        place["label"] = _location_label(metadata)


def _location_state(location: dict | None, places: list[dict], *, previous_state: dict) -> dict:
    if not location:
        return {"label": "", "scene": "未知", "stale": True, "confidence": 0.0}
    metadata = location.get("metadata") if isinstance(location.get("metadata"), dict) else {}
    lat = _float_or_none(metadata.get("latitude"))
    lon = _float_or_none(metadata.get("longitude"))
    place = _match_place(places, lat=lat, lon=lon) if lat is not None and lon is not None else None
    raw_age = _float_or_none(metadata.get("locationAgeSeconds"))
    age = raw_age if raw_age is not None else max(0.0, time.time() - float(location.get("eventTime") or 0))
    stale = age > LOCATION_STALE_SECONDS
    city = str(metadata.get("city") or (place or {}).get("city") or "").strip()
    district = str(metadata.get("district") or (place or {}).get("district") or "").strip()
    place_kind = str((place or {}).get("kind") or "unknown")
    place_label = _place_label(place, metadata)
    previous_city = str(previous_state.get("city") or "").strip()
    previous_place = str(previous_state.get("placeId") or "").strip()
    place_id = str((place or {}).get("id") or "")
    city_change = _recent_city_change(previous_state, current_city=city)
    city_changed = bool(previous_city and city and previous_city != city)
    if city_changed:
        city_change = {"from": previous_city, "to": city, "changedAt": time.time()}
    city_changed_recently = bool(city_change)
    place_changed = bool(previous_place and place_id and previous_place != place_id)
    scene = _scene_for(place_kind=place_kind, city_changed=city_changed_recently, stale=stale)
    confidence = float(location.get("confidence") or 0.6)
    if stale:
        confidence *= 0.55
    if place_kind in {"home", "work", "frequent"}:
        confidence = min(0.98, confidence + 0.18)
    change_summary = ""
    if city_changed:
        change_summary = f"城市从{previous_city}变为{city}"
    elif city_change:
        change_summary = f"近期城市从{city_change.get('from')}变为{city_change.get('to')}"
    elif place_changed:
        change_summary = f"地点切换到{place_label}"
    return {
        "label": place_label,
        "scene": scene,
        "placeKind": place_kind,
        "placeId": place_id,
        "city": city,
        "district": district,
        "addressHint": _address_hint(metadata) or str((place or {}).get("addressHint") or ""),
        "ageMinutes": round(age / 60),
        "confidence": round(confidence, 2),
        "stale": stale,
        "cityChanged": city_changed_recently,
        "cityChange": city_change,
        "placeChanged": place_changed,
        "changeSummary": change_summary,
    }


def _recent_city_change(previous_state: dict, *, current_city: str) -> dict:
    change = previous_state.get("cityChange")
    if not isinstance(change, dict):
        return {}
    changed_at = _float_or_none(change.get("changedAt"))
    target = str(change.get("to") or "").strip()
    if changed_at is None or time.time() - changed_at > 12 * 3600:
        return {}
    if current_city and target and current_city != target:
        return {}
    return {
        "from": str(change.get("from") or "").strip(),
        "to": target,
        "changedAt": changed_at,
    }


def _movement_state(*, location: dict | None, motion: dict | None) -> dict:
    motion_type = _metadata_value(motion, "activity")
    if motion_type in {"in_vehicle", "on_bicycle"}:
        return {"kind": "moving", "summary": "可能在路上或通勤中"}
    if motion_type == "walking":
        return {"kind": "walking", "summary": "可能在步行或外出移动"}
    if location and not _location_state(location, [], previous_state={}).get("stale"):
        return {"kind": "still", "summary": "当前位置近期较稳定"}
    return {"kind": "unknown", "summary": ""}


def _infer_activity(*, location_state: dict, music: dict | None, movement: dict) -> str:
    if location_state.get("cityChanged"):
        return "可能到了新的城市"
    if movement.get("kind") == "moving":
        return "可能在通勤或移动中"
    if movement.get("kind") == "walking":
        return "可能在外面走动"
    label = str(location_state.get("label") or "").strip()
    if music and label:
        return f"在{label}听音乐"
    if music:
        return "正在听音乐"
    if label:
        return f"可能在{label}"
    return "普通日常状态"


def _availability_state(*, movement: dict, music: dict | None, location_state: dict) -> str:
    if location_state.get("cityChanged") or movement.get("kind") == "moving":
        return "可能不适合长聊，适合短句关心"
    if location_state.get("placeKind") == "work":
        return "可能在忙，适合轻量关心"
    if location_state.get("placeKind") == "home":
        return "可能较放松，可以更亲密自然"
    if music:
        return "可能在放松或专注，适合顺着情绪聊天"
    return "不确定，正常聊天"


def _relationship_cue(*, location_state: dict, music: dict | None, movement: dict, availability: str) -> str:
    parts = [availability]
    if location_state.get("cityChanged"):
        parts.append("城市变化是强信号，可以自然关心路程、出差或旅行，但不要说出精确定位。")
    elif location_state.get("placeChanged"):
        parts.append("地点刚变化，可以轻轻关心是不是刚到一个地方。")
    elif location_state.get("placeKind") == "work":
        parts.append("可以自然关心工作节奏、有没有休息。")
    elif location_state.get("placeKind") == "home":
        parts.append("可以用更放松亲近的语气。")
    if music:
        parts.append("如果聊天气氛合适，可以顺带接住正在听的歌和情绪。")
    if movement.get("kind") in {"moving", "walking"}:
        parts.append("回复尽量短，不要长篇。")
    return "；".join(parts)


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
        "location_snapshot": "位置快照",
        "location_changed": "位置变化",
        "music_playing": "正在听音乐",
        "music_paused": "音乐暂停",
        "motion_detected": "运动状态变化",
        "device_headset": "耳机状态",
        "app_foreground": "打开 Alicer",
    }.get(event_type, event_type)


def _summary_for(event_type: str, metadata: dict) -> str:
    if event_type.startswith("location"):
        return f"位置更新到{_location_label(metadata)}"
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


def _location_label(metadata: dict) -> str:
    if str(metadata.get("semanticLabel") or "").strip():
        return str(metadata["semanticLabel"]).strip()
    parts = [
        str(metadata.get("city") or "").strip(),
        str(metadata.get("district") or "").strip(),
        str(metadata.get("township") or "").strip(),
        str(metadata.get("poi") or "").strip(),
    ]
    label = " · ".join(item for item in parts if item)
    return label or str(metadata.get("label") or "当前位置").strip()


def _place_label(place: dict | None, metadata: dict) -> str:
    if place:
        kind = str(place.get("kind") or "")
        base = str(place.get("label") or "").strip()
        if kind in {"home", "work"}:
            district = str(place.get("district") or "").strip()
            return f"{base}附近" if not district else f"{district} · {base}附近"
        if kind == "frequent" and base:
            return f"常去地：{base}"
    return _location_label(metadata)


def _scene_for(*, place_kind: str, city_changed: bool, stale: bool) -> str:
    if stale:
        return "旧位置线索"
    if city_changed:
        return "城市变化"
    return {
        "home": "在家附近",
        "work": "在公司/工作地附近",
        "frequent": "在常去地点附近",
    }.get(place_kind, "外出或未知地点")


def _address_hint(metadata: dict) -> str:
    address = str(metadata.get("address") or "").strip()
    poi = str(metadata.get("poi") or "").strip()
    if poi:
        return poi
    if address:
        return address[-32:]
    return ""


def _metadata_value(event: dict | None, key: str) -> str:
    metadata = event.get("metadata") if event else {}
    if not isinstance(metadata, dict):
        return ""
    value = metadata.get(key)
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value or "").strip()


def _join_filled(items: list[str], separator: str) -> str:
    return separator.join(item for item in (value.strip() for value in items if isinstance(value, str)) if item)


def _distance_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371000.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return radius * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _float_or_now(value: object) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return time.time()


def _float_or_none(value: object) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(parsed) or math.isinf(parsed):
        return None
    return parsed


def _positive_float(value: object, *, default: float) -> float:
    parsed = _float_or_none(value)
    if parsed is None or parsed <= 0:
        return default
    return parsed


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
