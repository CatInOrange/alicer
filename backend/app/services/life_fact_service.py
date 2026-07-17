from __future__ import annotations

import asyncio
import datetime as dt
import json
import re
from zoneinfo import ZoneInfo

from ..db import Database, uuid_like
from .llm_service import LlmService
from .prompt_service import merge_settings


TZ = ZoneInfo("Asia/Shanghai")
USER_DAY_BOUNDARY_HOUR = 4
ACTIVE_STATUSES = ("candidate", "planned", "active")
VISIBLE_STATUSES = ("candidate", "planned", "active", "completed", "cancelled", "superseded", "expired", "archived")
FACT_TYPES = {
    "schedule_commitment",
    "relationship_commitment",
    "current_state",
    "profile_fact",
    "life_event_hint",
    "moment_posted",
}
VALUE_SIGNALS = re.compile(
    r"(明天|后天|今晚|今天|下周|周末|早上|中午|下午|晚上|凌晨|[0-2]?\d[:：点])"
    r"|航班|机场|出差|上班|加班|下班|请假|休假|约会|见朋友|回家|搬家|旅行|拍照|自拍|照片|记住|别忘|答应|说好",
    re.IGNORECASE,
)
RELATIVE_TIME_RE = re.compile(r"(今天|明天|后天|今晚|下周|周末)")
EXPLICIT_CLOCK_RE = re.compile(
    r"(?P<hour>[0-2]?\d)(?:[:：](?P<minute>\d{1,2})|点(?P<half>半)?(?:(?P<minute_cn>\d{1,2})分?)?)"
)


def schedule_fact_extraction(
    db: Database,
    llm: LlmService,
    *,
    settings: dict,
    user_message: dict,
    assistant_message: dict,
    life_context: dict | None = None,
) -> None:
    if not _should_extract(user_message, assistant_message):
        return
    asyncio.create_task(
        extract_life_facts(
            db,
            llm,
            settings=settings,
            user_message=user_message,
            assistant_message=assistant_message,
            life_context=life_context or {},
        )
    )


async def extract_life_facts(
    db: Database,
    llm: LlmService,
    *,
    settings: dict,
    user_message: dict,
    assistant_message: dict,
    life_context: dict | None = None,
) -> list[dict]:
    merged = merge_settings(settings or db.get_settings())
    cleanup_life_facts(db)
    existing = build_world_context(db, merged)
    companion = str(((merged.get("companion") or {}).get("name") or "Alice")).strip() or "Alice"
    extracted_at = dt.datetime.now(TZ)
    conversation_time = _message_datetime(user_message, fallback=extracted_at)
    life_day = _life_day(conversation_time)
    prompt = [
        {
            "role": "system",
            "content": (
                "你是 Alicer 的生活事实抽取器。只输出合法 JSON，不输出解释。"
                f"你要从一轮聊天中提取关于{companion}自己的生活、未来安排、当前状态、关系承诺的事实候选。"
                "不要抽取普通寒暄、情绪安慰、比喻、玩笑、用户自己的经历。"
                "只抽会影响后续聊天、生活模拟、朋友圈或承诺兑现的一致性事实。"
                "每条 facts 字段：type,title,summary,startsAt,endsAt,expiresAt,confidence,importance,status。"
                "type 只能是 schedule_commitment/relationship_commitment/current_state/profile_fact/life_event_hint。"
                "时间必须用 Asia/Shanghai 的 ISO8601；不确定可留空。"
                "所有相对时间必须以 userMessage.createdAt 为锚点，不以抽取执行时间为锚点。"
                "用户生活日以凌晨4点为界：00:00-03:59 仍算前一生活日；例如凌晨2点说“明天”指日历上的今天。"
                "title 和 summary 不得保留“今天/明天/后天/今晚/下周/周末”等相对日期词，必须改写成绝对日期或具体时间。"
                "只抽 Alicer 自己的事实，或 Alicer 对用户/关系作出的承诺；用户自己的行程、经历、计划不得变成 Alicer 的事实。"
                "如果无法确定 actor，丢弃；如果无法确定时间但事实重要，status 用 candidate 且 confidence 不超过 0.6。"
                "如果新事实修正或替代 activeFacts 中旧事实，在 summary 里说明修正点，并尽量给出 supersedesId。"
                "status 通常 planned 或 candidate，正在发生用 active。"
                "profile_fact 只用于稳定设定变化，必须高置信。"
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "now": extracted_at.isoformat(),
                    "extractedAt": extracted_at.isoformat(),
                    "conversationTime": conversation_time.isoformat(),
                    "userLifeDay": life_day.isoformat(),
                    "relativeTimeRule": "以 userMessage.createdAt 为锚点；先减去4小时得到用户生活日，再解析今天/明天/后天。",
                    "userMessage": {
                        "id": user_message.get("id"),
                        "createdAt": conversation_time.isoformat(),
                        "content": str(user_message.get("content") or "")[:1600],
                    },
                    "assistantMessage": {
                        "id": assistant_message.get("id"),
                        "createdAt": _message_datetime(assistant_message, fallback=conversation_time).isoformat(),
                        "content": str(assistant_message.get("content") or "")[:2000],
                    },
                    "currentLifeState": (life_context or {}).get("state") or {},
                    "activeFacts": existing.get("activeFacts") or [],
                },
                ensure_ascii=False,
            ),
        },
    ]
    try:
        raw = await llm.complete(messages=prompt, model_settings=merged.get("model") or {})
        parsed = json.loads(raw[raw.find("{") : raw.rfind("}") + 1])
    except Exception:
        return []
    facts = parsed.get("facts") if isinstance(parsed, dict) else None
    if not isinstance(facts, list):
        return []
    saved: list[dict] = []
    for item in facts[:8]:
        if not isinstance(item, dict):
            continue
        normalized = _normalize_fact(
            item,
            user_message=user_message,
            assistant_message=assistant_message,
            anchor_time=conversation_time,
            extracted_at=extracted_at,
        )
        if normalized is None:
            continue
        _supersede_conflicts(db, normalized)
        saved.append(db.upsert_life_fact(**normalized))
    return saved


async def refresh_life_facts_from_recent_chat(
    db: Database,
    llm: LlmService,
    *,
    settings: dict | None = None,
    limit: int = 40,
) -> dict:
    merged = merge_settings(settings or db.get_settings())
    pre_cleanup = cleanup_life_facts(db)
    messages = db.list_messages(limit=max(2, min(limit, 120)))
    pairs: list[tuple[dict, dict]] = []
    pending_user: dict | None = None
    for message in messages:
        if message.get("role") == "user":
            pending_user = message
        elif message.get("role") == "assistant" and pending_user is not None:
            if _should_extract(pending_user, message):
                pairs.append((pending_user, message))
            pending_user = None
    saved: list[dict] = []
    for user_message, assistant_message in pairs[-12:]:
        saved.extend(
            await extract_life_facts(
                db,
                llm,
                settings=merged,
                user_message=user_message,
                assistant_message=assistant_message,
                life_context={},
            )
        )
    cleanup = cleanup_life_facts(db)
    return {
        "scannedMessages": len(messages),
        "candidatePairs": len(pairs),
        "savedFacts": saved,
        "cleanup": {"before": pre_cleanup, "after": cleanup},
        "world": build_world_context(db, merged),
        "audit": audit_life_facts(db),
    }


def build_world_context(db: Database, settings: dict | None = None) -> dict:
    merged = merge_settings(settings or db.get_settings())
    cleanup_life_facts(db)
    facts = db.list_life_facts(statuses=ACTIVE_STATUSES, limit=36)
    now = dt.datetime.now(TZ)
    today = now.date()
    tomorrow = today + dt.timedelta(days=1)
    current: list[dict] = []
    upcoming: list[dict] = []
    stable: list[dict] = []
    for item in facts:
        starts_at = _from_timestamp(item.get("startsAt"))
        ends_at = _from_timestamp(item.get("endsAt"))
        fact_type = str(item.get("type") or "")
        if fact_type == "profile_fact":
            stable.append(item)
        elif _is_current(starts_at, ends_at, now) or item.get("status") == "active":
            current.append(item)
        elif starts_at is None or starts_at.date() in {today, tomorrow} or starts_at <= now + dt.timedelta(days=3):
            upcoming.append(item)
    return {
        "enabled": True,
        "activeFacts": [_public_fact(item) for item in facts[:20]],
        "current": [_public_fact(item) for item in current[:8]],
        "upcoming": [_public_fact(item) for item in upcoming[:12]],
        "stable": [_public_fact(item) for item in stable[:8]],
        "prompt": _format_world_prompt(current=current, upcoming=upcoming, stable=stable),
        "audit": audit_life_facts(db),
    }


def fact_constraints_for_life(db: Database, settings: dict | None = None) -> dict:
    context = build_world_context(db, settings)
    facts = [*context.get("current", []), *context.get("upcoming", []), *context.get("stable", [])]
    return {
        "facts": facts[:16],
        "summary": _format_fact_lines(facts[:16]) or "暂无需要强制遵守的生活事实。",
    }


def cleanup_life_facts(db: Database, *, now: float | None = None) -> dict:
    value = now or dt.datetime.now(TZ).timestamp()
    expired = db.expire_life_facts(now=value)
    activated = 0
    archived = 0
    completed = 0
    for fact in db.list_life_facts(statuses=["active"], limit=120, include_expired=True):
        ends_at = fact.get("endsAt")
        if ends_at is None:
            continue
        if value > float(ends_at) + 2 * 3600:
            if db.update_life_fact_status(str(fact["id"]), status="completed", metadata={"autoCompletedAt": value}):
                completed += 1
    for fact in db.list_life_facts(statuses=["planned"], limit=120, include_expired=True):
        starts_at = fact.get("startsAt")
        ends_at = fact.get("endsAt")
        if starts_at is None:
            continue
        if float(starts_at) <= value and (ends_at is None or value <= float(ends_at) + 2 * 3600):
            if db.update_life_fact_status(str(fact["id"]), status="active", metadata={"autoActivatedAt": value}):
                activated += 1
    for fact in db.list_life_facts(statuses=["candidate"], limit=120, include_expired=True):
        expires_at = fact.get("expiresAt")
        updated_at = fact.get("updatedAt")
        stale = False
        if expires_at is not None and float(expires_at) < value:
            stale = True
        elif updated_at is not None and value - float(updated_at) > 7 * 86400:
            stale = True
        if stale and db.update_life_fact_status(str(fact["id"]), status="archived", metadata={"autoArchivedAt": value}):
            archived += 1
    superseded = _dedupe_life_facts(db, now=value)
    return {
        "expired": expired,
        "activated": activated,
        "completed": completed,
        "archived": archived,
        "supersededDuplicates": superseded,
    }


def audit_life_facts(db: Database) -> dict:
    facts = db.list_life_facts(statuses=VISIBLE_STATUSES, limit=120, include_expired=True)
    counts: dict[str, int] = {}
    warnings = []
    now = dt.datetime.now(TZ).timestamp()
    activeish = [item for item in facts if item.get("status") in ACTIVE_STATUSES]
    for item in facts:
        status = str(item.get("status") or "")
        counts[status] = counts.get(status, 0) + 1
        if item.get("status") in ACTIVE_STATUSES and item.get("expiresAt") and float(item["expiresAt"]) < now:
            warnings.append({"factId": item.get("id"), "type": "expired_visible", "message": "事实已过期但仍在活跃状态。"})
        if item.get("confidence") is not None and float(item.get("confidence") or 0) < 0.55:
            warnings.append({"factId": item.get("id"), "type": "low_confidence", "message": "低置信事实需要谨慎使用。"})
    for index, left in enumerate(activeish):
        for right in activeish[index + 1 :]:
            if left.get("type") != right.get("type"):
                continue
            if _facts_overlap(left, right) and _text_overlap(str(left.get("title") or ""), str(right.get("title") or "")) >= 2:
                warnings.append(
                    {
                        "factId": left.get("id"),
                        "otherFactId": right.get("id"),
                        "type": "possible_conflict",
                        "message": "同类型同时间附近的事实可能冲突。",
                    }
                )
    return {"counts": counts, "warnings": warnings[:24]}


def normalize_fact_patch(body: dict) -> dict:
    result: dict = {}
    if "type" in body:
        fact_type = str(body.get("type") or "").strip()
        if fact_type in FACT_TYPES:
            result["fact_type"] = fact_type
    if "status" in body:
        status = str(body.get("status") or "").strip()
        if status in VISIBLE_STATUSES:
            result["status"] = status
    for key in ("title", "summary"):
        if key in body:
            result[key] = " ".join(str(body.get(key) or "").split())
    for source, target in (("startsAt", "starts_at"), ("endsAt", "ends_at"), ("expiresAt", "expires_at")):
        if source in body:
            result[target] = _parse_time(body.get(source))
    for key in ("confidence", "importance"):
        if key in body:
            result[key] = _clamp_float(body.get(key), default=0.7 if key == "confidence" else 0.5)
    if isinstance(body.get("related"), dict):
        result["related"] = body["related"]
    if isinstance(body.get("metadata"), dict):
        result["metadata"] = body["metadata"]
    if "supersedesId" in body:
        result["supersedes_id"] = str(body.get("supersedesId") or "")
    return result


def _should_extract(user_message: dict, assistant_message: dict) -> bool:
    text = f"{user_message.get('content') or ''}\n{assistant_message.get('content') or ''}"
    if len(text.strip()) < 8:
        return False
    return bool(VALUE_SIGNALS.search(text))


def _normalize_fact(
    item: dict,
    *,
    user_message: dict,
    assistant_message: dict,
    anchor_time: dt.datetime | None = None,
    extracted_at: dt.datetime | None = None,
) -> dict | None:
    fact_type = str(item.get("type") or "").strip()
    if fact_type not in FACT_TYPES:
        return None
    anchor = anchor_time or _message_datetime(user_message)
    extracted = extracted_at or dt.datetime.now(TZ)
    raw_title = " ".join(str(item.get("title") or "").split())
    raw_summary = " ".join(str(item.get("summary") or raw_title).split())
    title = _rewrite_relative_time_text(raw_title, anchor)[:200]
    summary = _rewrite_relative_time_text(raw_summary or title, anchor)[:1000]
    if not title and not summary:
        return None
    confidence = _clamp_float(item.get("confidence"), default=0.65)
    importance = _clamp_float(item.get("importance"), default=0.55)
    if confidence < 0.5 and importance < 0.7:
        return None
    starts_at = _parse_time(item.get("startsAt")) or _infer_relative_start(raw_title, raw_summary, anchor)
    ends_at = _parse_time(item.get("endsAt"))
    expires_at = _parse_time(item.get("expiresAt"))
    expires_at = expires_at or _default_expiry(fact_type, starts_at, ends_at, anchor=anchor)
    status = str(item.get("status") or "").strip() or ("planned" if starts_at else "candidate")
    if status not in {"candidate", "planned", "active", "completed", "cancelled"}:
        status = "candidate"
    return {
        "fact_id": f"fact_{uuid_like()}",
        "fact_type": fact_type,
        "status": status,
        "title": title or summary[:80],
        "summary": summary or title,
        "starts_at": starts_at,
        "ends_at": ends_at,
        "expires_at": expires_at,
        "confidence": confidence,
        "importance": importance,
        "source": "chat",
        "source_message_id": str(user_message.get("id") or ""),
        "related": {
            "userMessageId": user_message.get("id"),
            "assistantMessageId": assistant_message.get("id"),
        },
        "metadata": {
            "extractor": "life_fact_service",
            "rawType": item.get("type"),
            "timeAnchor": anchor.isoformat(),
            "userLifeDay": _life_day(anchor).isoformat(),
            "extractedAt": extracted.isoformat(),
            "rawTitle": raw_title,
            "rawSummary": raw_summary,
        },
    }


def _supersede_conflicts(db: Database, fact: dict) -> None:
    new_type = fact.get("fact_type")
    new_starts = fact.get("starts_at")
    new_title = str(fact.get("title") or "")
    for existing in db.list_life_facts(statuses=ACTIVE_STATUSES, limit=80):
        if existing.get("type") != new_type:
            continue
        existing_starts = existing.get("startsAt")
        if new_starts and existing_starts and abs(float(new_starts) - float(existing_starts)) > 18 * 3600:
            continue
        overlap = _text_overlap(new_title, str(existing.get("title") or ""))
        if overlap >= 2:
            db.update_life_fact_status(
                str(existing["id"]),
                status="superseded",
                metadata={"supersededBy": fact["fact_id"]},
                supersedes_id=fact["fact_id"],
            )


def _dedupe_life_facts(db: Database, *, now: float) -> int:
    facts = db.list_life_facts(statuses=ACTIVE_STATUSES, limit=160, include_expired=True)
    superseded = 0
    for index, left in enumerate(facts):
        if left.get("status") not in ACTIVE_STATUSES:
            continue
        for right in facts[index + 1 :]:
            if right.get("status") not in ACTIVE_STATUSES:
                continue
            if left.get("id") == right.get("id") or left.get("type") != right.get("type"):
                continue
            same_source = bool(left.get("sourceMessageId")) and left.get("sourceMessageId") == right.get("sourceMessageId")
            if not same_source and not _facts_overlap(left, right):
                continue
            overlap = _text_overlap(
                f"{left.get('title') or ''} {left.get('summary') or ''}",
                f"{right.get('title') or ''} {right.get('summary') or ''}",
            )
            if not same_source and overlap < 4:
                continue
            keep, drop = _preferred_fact(left, right)
            updated = db.update_life_fact_status(
                str(drop["id"]),
                status="superseded",
                metadata={"autoSupersededDuplicateAt": now, "supersededBy": keep.get("id")},
                supersedes_id=str(keep.get("id") or ""),
            )
            if updated is not None:
                drop["status"] = "superseded"
                superseded += 1
    return superseded


def _preferred_fact(left: dict, right: dict) -> tuple[dict, dict]:
    status_rank = {"active": 3, "planned": 2, "candidate": 1}

    def score(item: dict) -> tuple[float, float, float, float]:
        return (
            float(status_rank.get(str(item.get("status") or ""), 0)),
            float(item.get("importance") or 0),
            float(item.get("confidence") or 0),
            float(item.get("updatedAt") or 0),
        )

    if score(left) >= score(right):
        return left, right
    return right, left


def _facts_overlap(left: dict, right: dict) -> bool:
    left_start = left.get("startsAt")
    right_start = right.get("startsAt")
    if left_start is None or right_start is None:
        return True
    return abs(float(left_start) - float(right_start)) <= 18 * 3600


def _format_world_prompt(*, current: list[dict], upcoming: list[dict], stable: list[dict]) -> str:
    lines = []
    if stable:
        lines.append("稳定生活事实：")
        lines.extend(f"  - {item.get('title')}: {item.get('summary')}" for item in stable[:6])
    if current:
        lines.append("当前必须保持一致的事实：")
        lines.extend(f"  - {_time_window(item)} {item.get('title')}: {item.get('summary')}".strip() for item in current[:8])
    if upcoming:
        lines.append("未完成/即将发生的承诺与计划：")
        lines.extend(f"  - {_time_window(item)} {item.get('title')}: {item.get('summary')}".strip() for item in upcoming[:10])
    if not lines:
        return "暂无额外生活事实约束；仍需遵守稳定人设、生活模拟和长期记忆。"
    lines.append("一致性规则：聊天、朋友圈和生活模拟都必须优先服从这些事实；不要安排冲突的地点、工作、行程或承诺。")
    lines.append("如果事实低置信或时间已过，只能含蓄处理，不要编成确定发生。")
    return "\n".join(lines)


def _format_fact_lines(facts: list[dict]) -> str:
    return "\n".join(
        f"- {_time_window(item)} {item.get('title')}: {item.get('summary')}".strip()
        for item in facts
        if item.get("title") or item.get("summary")
    )


def _public_fact(item: dict) -> dict:
    return {
        "id": item.get("id"),
        "type": item.get("type"),
        "status": item.get("status"),
        "title": item.get("title"),
        "summary": item.get("summary"),
        "startsAt": item.get("startsAt"),
        "endsAt": item.get("endsAt"),
        "expiresAt": item.get("expiresAt"),
        "confidence": item.get("confidence"),
        "importance": item.get("importance"),
        "timeWindow": _time_window(item),
    }


def _time_window(item: dict) -> str:
    start = _from_timestamp(item.get("startsAt"))
    end = _from_timestamp(item.get("endsAt"))
    if start and end:
        return f"{start.strftime('%m-%d %H:%M')}-{end.strftime('%H:%M')}"
    if start:
        return start.strftime("%m-%d %H:%M")
    return ""


def _message_datetime(message: dict, *, fallback: dt.datetime | None = None) -> dt.datetime:
    fallback_value = fallback or dt.datetime.now(TZ)
    value = message.get("createdAt") or message.get("created_at")
    if isinstance(value, (int, float)):
        try:
            return dt.datetime.fromtimestamp(float(value), tz=TZ)
        except (ValueError, OSError):
            return fallback_value
    if isinstance(value, str) and value.strip():
        parsed = _parse_datetime(value)
        if parsed is not None:
            return parsed
    return fallback_value


def _life_day(anchor: dt.datetime) -> dt.date:
    return (anchor.astimezone(TZ) - dt.timedelta(hours=USER_DAY_BOUNDARY_HOUR)).date()


def _rewrite_relative_time_text(text: str, anchor: dt.datetime) -> str:
    if not text:
        return text
    life_day = _life_day(anchor)

    def replacement(match: re.Match[str]) -> str:
        token = match.group(1)
        target = _relative_target_date(token, life_day)
        if token == "今晚":
            return f"{target.strftime('%m-%d')} 晚上"
        return target.strftime("%m-%d")

    return RELATIVE_TIME_RE.sub(replacement, text)


def _infer_relative_start(title: str, summary: str, anchor: dt.datetime) -> float | None:
    text = f"{title}\n{summary}"
    match = RELATIVE_TIME_RE.search(text)
    if match is None:
        return None
    target_date = _relative_target_date(match.group(1), _life_day(anchor))
    hour, minute = _infer_clock(text, default_token=match.group(1))
    return dt.datetime(
        target_date.year,
        target_date.month,
        target_date.day,
        hour,
        minute,
        tzinfo=TZ,
    ).timestamp()


def _relative_target_date(token: str, life_day: dt.date) -> dt.date:
    if token in {"今天", "今晚"}:
        return life_day
    if token == "明天":
        return life_day + dt.timedelta(days=1)
    if token == "后天":
        return life_day + dt.timedelta(days=2)
    if token == "下周":
        return life_day + dt.timedelta(days=7)
    if token == "周末":
        days_until_saturday = (5 - life_day.weekday()) % 7
        if days_until_saturday == 0:
            days_until_saturday = 7
        return life_day + dt.timedelta(days=days_until_saturday)
    return life_day


def _infer_clock(text: str, *, default_token: str) -> tuple[int, int]:
    match = EXPLICIT_CLOCK_RE.search(text)
    if match is not None:
        hour = max(0, min(23, int(match.group("hour"))))
        minute_text = match.group("minute") or match.group("minute_cn")
        minute = 30 if match.group("half") else int(minute_text or 0)
        minute = max(0, min(59, minute))
        prefix = text[max(0, match.start() - 4) : match.start()]
        if any(word in prefix for word in ("下午", "晚上", "今晚")) and hour < 12:
            hour += 12
        if "中午" in prefix and hour < 11:
            hour += 12
        if "凌晨" in prefix and hour == 12:
            hour = 0
        return hour, minute
    if default_token == "今晚" or "晚上" in text:
        return 20, 0
    if "凌晨" in text:
        return 2, 0
    if "中午" in text:
        return 12, 0
    if "下午" in text:
        return 15, 0
    if "早上" in text or "上午" in text:
        return 9, 0
    return 9, 0


def _parse_time(value: object) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    parsed = _parse_datetime(text)
    return parsed.timestamp() if parsed is not None else None


def _parse_datetime(value: str) -> dt.datetime | None:
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=TZ)
    return parsed.astimezone(TZ)


def _from_timestamp(value: object) -> dt.datetime | None:
    try:
        if value is None:
            return None
        return dt.datetime.fromtimestamp(float(value), tz=TZ)
    except (TypeError, ValueError, OSError):
        return None


def _default_expiry(
    fact_type: str,
    starts_at: float | None,
    ends_at: float | None,
    *,
    anchor: dt.datetime | None = None,
) -> float | None:
    now = anchor or dt.datetime.now(TZ)
    if fact_type == "profile_fact":
        return None
    if ends_at:
        return ends_at + 12 * 3600
    if starts_at:
        return starts_at + (48 if fact_type == "schedule_commitment" else 12) * 3600
    hours = 8 if fact_type == "current_state" else 72
    return (now + dt.timedelta(hours=hours)).timestamp()


def _is_current(start: dt.datetime | None, end: dt.datetime | None, now: dt.datetime) -> bool:
    if start and end:
        return start <= now <= end
    if start:
        return abs((now - start).total_seconds()) <= 2 * 3600
    return False


def _clamp_float(value: object, *, default: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = default
    return max(0.0, min(1.0, parsed))


def _text_overlap(left: str, right: str) -> int:
    left_words = {item for item in re.split(r"\W+", left.lower()) if len(item) >= 2}
    right_words = {item for item in re.split(r"\W+", right.lower()) if len(item) >= 2}
    if left_words and right_words:
        return len(left_words & right_words)
    left_chars = set(left)
    right_chars = set(right)
    return len({item for item in left_chars & right_chars if not item.isspace()})
