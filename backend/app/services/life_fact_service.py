from __future__ import annotations

import asyncio
import datetime as dt
import hashlib
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
RETENTION_STATUSES = ("completed", "cancelled", "superseded", "expired", "archived")
RETENTION_AGE_SECONDS = 48 * 3600
RETENTION_JOB_KEY = "life_facts:retention:last"
RETENTION_JOB_INTERVAL_SECONDS = 20 * 3600
FACT_TYPES = {
    "schedule_commitment",
    "relationship_commitment",
    "current_state",
    "profile_fact",
    "life_event_hint",
    "moment_posted",
}
HARD_SCHEDULE_KEYWORDS = (
    "航班",
    "执飞",
    "机场",
    "上班",
    "出差",
    "值机",
    "备勤",
    "培训",
    "约会",
    "考试",
    "入职",
    "面试",
)
CONDITIONAL_KEYWORDS = ("如果", "若", "假如", "要是", "否则", "没出现", "来接", "接机")
AVIATION_KEYWORDS = ("航班", "执飞", "机场", "机组", "空乘", "空姐", "值机", "落地", "登机", "备勤")
LONG_TERM_FACT_KEYWORDS = (
    "记住",
    "别忘",
    "以后",
    "喜欢",
    "不喜欢",
    "讨厌",
    "偏好",
    "习惯",
    "生日",
    "纪念日",
    "长期",
    "固定",
    "家",
    "工作",
    "职业",
    "排班",
    "住",
    "称呼",
)
VALUE_SIGNALS = re.compile(
    r"(明天|后天|今晚|今天|下周|周末|早上|中午|下午|晚上|凌晨|等会儿|一会儿|待会儿|稍后|回头|[0-2]?\d[:：点])"
    r"|航班|机场|出差|上班|加班|下班|请假|休假|约会|见朋友|回家|搬家|旅行|去买|挑|逛|试穿|下单|商场|太古里"
    r"|拍照|自拍|照片|拍给你看|记住|别忘|答应|说好",
    re.IGNORECASE,
)
ASSISTANT_COMMITMENT_SIGNALS = re.compile(
    r"(我|咱|我们).{0,12}(等会儿|一会儿|待会儿|稍后|回头|直接|会|去|给你|帮你|记着|拍|买|挑|试穿)",
    re.IGNORECASE,
)
SOFT_PLAN_SIGNALS = re.compile(
    r"(等会儿|一会儿|待会儿|稍后|回头|去买|挑|逛|试穿|下单|商场|太古里|拍给你看)",
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
            reconcile=True,
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
    reconcile: bool = False,
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
    if saved and reconcile:
        from .consistency_service import reconcile_after_life_facts_changed

        await reconcile_after_life_facts_changed(
            db,
            llm,
            settings=merged,
            facts=saved,
            reason="life_fact_extraction",
        )
    return saved


async def extract_life_facts_batch(
    db: Database,
    llm: LlmService,
    *,
    settings: dict,
    pairs: list[tuple[dict, dict]],
    life_context: dict | None = None,
    reconcile: bool = False,
) -> list[dict]:
    if not pairs:
        return []
    merged = merge_settings(settings or db.get_settings())
    cleanup_life_facts(db)
    existing = build_world_context(db, merged)
    companion = str(((merged.get("companion") or {}).get("name") or "Alice")).strip() or "Alice"
    extracted_at = dt.datetime.now(TZ)
    pair_lookup: dict[str, tuple[dict, dict, dt.datetime]] = {}
    conversation_pairs: list[dict] = []
    for index, (user_message, assistant_message) in enumerate(pairs[:10]):
        conversation_time = _message_datetime(user_message, fallback=extracted_at)
        pair_id = _pair_id(user_message, assistant_message, index=index)
        pair_lookup[pair_id] = (user_message, assistant_message, conversation_time)
        conversation_pairs.append(
            {
                "pairId": pair_id,
                "userMessageId": user_message.get("id"),
                "assistantMessageId": assistant_message.get("id"),
                "conversationTime": conversation_time.isoformat(),
                "userLifeDay": _life_day(conversation_time).isoformat(),
                "user": str(user_message.get("content") or "")[:1600],
                "assistant": str(assistant_message.get("content") or "")[:2000],
            }
        )
    prompt = [
        {
            "role": "system",
            "content": (
                "你是 Alicer 的生活事实批量抽取器。只输出合法 JSON，不输出解释。"
                f"你要从多轮聊天中提取关于{companion}自己的生活、未来安排、当前状态、关系承诺的事实候选。"
                "不要抽取普通寒暄、情绪安慰、比喻、玩笑、用户自己的经历。"
                "只抽会影响后续聊天、生活模拟、朋友圈或承诺兑现的一致性事实。"
                "每条 facts 字段：sourcePairId,type,title,summary,startsAt,endsAt,expiresAt,confidence,importance,status。"
                "type 只能是 schedule_commitment/relationship_commitment/current_state/profile_fact/life_event_hint。"
                "必须填写 sourcePairId，且必须来自输入 conversationPairs。"
                "时间必须用 Asia/Shanghai 的 ISO8601；不确定可留空。"
                "所有相对时间必须以对应 pair 的 conversationTime 为锚点。"
                "用户生活日以凌晨4点为界：00:00-03:59 仍算前一生活日；例如凌晨2点说“明天”指日历上的今天。"
                "title 和 summary 不得保留“今天/明天/后天/今晚/下周/周末”等相对日期词，必须改写成绝对日期或具体时间。"
                "只抽 Alicer 自己的事实，或 Alicer 对用户/关系作出的承诺；用户自己的行程、经历、计划不得变成 Alicer 的事实。"
                "如果没有精确时间但事实是当天已接受的软计划，填写 metadata.targetDate、metadata.timeHint、metadata.commitmentStrength='accepted'、metadata.flexibility='soft'。"
                "如果无法确定 actor，丢弃；如果无法确定时间但事实重要，status 用 candidate 且 confidence 不超过 0.6，已接受软计划除外。"
                "如果新事实修正或替代 activeFacts 中旧事实，在 summary 里说明修正点，并尽量给出 supersedesId。"
                "status 通常 planned 或 candidate，正在发生用 active。profile_fact 只用于稳定设定变化，必须高置信。"
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "now": extracted_at.isoformat(),
                    "extractedAt": extracted_at.isoformat(),
                    "relativeTimeRule": "以每个 pair 的 conversationTime 为锚点；先减去4小时得到用户生活日，再解析今天/明天/后天。",
                    "conversationPairs": conversation_pairs,
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
    for index, item in enumerate(facts[:24]):
        if not isinstance(item, dict):
            continue
        source_pair_id = str(item.get("sourcePairId") or item.get("pairId") or "")
        pair = pair_lookup.get(source_pair_id)
        if pair is None and len(pair_lookup) == 1:
            source_pair_id, pair = next(iter(pair_lookup.items()))
        if pair is None:
            continue
        user_message, assistant_message, conversation_time = pair
        normalized = _normalize_fact(
            item,
            user_message=user_message,
            assistant_message=assistant_message,
            anchor_time=conversation_time,
            extracted_at=extracted_at,
        )
        if normalized is None:
            continue
        normalized["fact_id"] = _batch_fact_id(source_pair_id, item, index)
        normalized.setdefault("related", {})["sourcePairId"] = source_pair_id
        normalized.setdefault("metadata", {})["sourcePairId"] = source_pair_id
        normalized.setdefault("metadata", {})["batchExtractedAt"] = extracted_at.isoformat()
        _supersede_conflicts(db, normalized)
        saved.append(db.upsert_life_fact(**normalized))
    if saved and reconcile:
        from .consistency_service import reconcile_after_life_facts_changed

        await reconcile_after_life_facts_changed(
            db,
            llm,
            settings=merged,
            facts=saved,
            reason="life_fact_batch_extraction",
        )
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
    processed_pair_ids = _processed_pair_ids(db)
    pending_pairs = [
        (user_message, assistant_message)
        for index, (user_message, assistant_message) in enumerate(pairs)
        if _pair_id(user_message, assistant_message, index=index) not in processed_pair_ids
    ]
    saved: list[dict] = []
    selected_pairs = pending_pairs[-10:]
    if selected_pairs:
        saved.extend(
            await extract_life_facts_batch(
                db,
                llm,
                settings=merged,
                pairs=selected_pairs,
                life_context={},
                reconcile=True,
            )
        )
    cleanup = cleanup_life_facts(db)
    return {
        "scannedMessages": len(messages),
        "candidatePairs": len(pairs),
        "pendingPairs": len(pending_pairs),
        "processedPairs": len(processed_pair_ids),
        "batchPairs": len(selected_pairs),
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
    latest_fact_updated_at = max((float(item.get("updatedAt") or 0) for item in facts), default=0.0)
    last_reconciliation = db.get_scheduled_job("consistency:life_projection:last")
    return {
        "enabled": True,
        "activeFacts": [_public_fact(item) for item in facts[:20]],
        "current": [_public_fact(item) for item in current[:8]],
        "upcoming": [_public_fact(item) for item in upcoming[:12]],
        "stable": [_public_fact(item) for item in stable[:8]],
        "prompt": _format_world_prompt(current=current, upcoming=upcoming, stable=stable),
        "audit": audit_life_facts(db),
        "freshness": {
            "latestFactUpdatedAt": latest_fact_updated_at or None,
            "lastReconciliation": last_reconciliation,
        },
    }


def fact_constraints_for_life(db: Database, settings: dict | None = None) -> dict:
    context = build_world_context(db, settings)
    facts = [*context.get("current", []), *context.get("upcoming", []), *context.get("stable", [])]
    return {
        "facts": facts[:16],
        "summary": _format_fact_lines(facts[:16]) or "暂无需要强制遵守的生活事实。",
    }


def resolve_life_constraints_for_day(
    db: Database,
    day: dt.date,
    settings: dict | None = None,
) -> dict:
    merged = merge_settings(settings or db.get_settings())
    cleanup_life_facts(db)
    facts = db.list_life_facts(statuses=ACTIVE_STATUSES, limit=120)
    day_start = dt.datetime(day.year, day.month, day.day, tzinfo=TZ)
    day_end = day_start + dt.timedelta(days=1)
    hard_blocks: list[dict] = []
    conditional: list[dict] = []
    soft_hints: list[dict] = []
    profile_facts: list[dict] = []
    allowed_locations: set[str] = set()

    for fact in facts:
        fact_type = str(fact.get("type") or "")
        text = f"{fact.get('title') or ''} {fact.get('summary') or ''}"
        start = _from_timestamp(fact.get("startsAt"))
        end = _from_timestamp(fact.get("endsAt"))
        if fact_type == "profile_fact":
            profile_facts.append(_public_fact(fact))
            allowed_locations.update(_locations_from_text(text))
            continue
        if not _touches_day(start, end, day_start, day_end):
            if fact_type == "life_event_hint" or _targets_day(fact, day):
                soft_hints.append(_public_fact(fact))
                allowed_locations.update(_locations_from_text(text))
            continue
        if _is_conditional_fact(fact):
            conditional.append(_public_fact(fact))
            allowed_locations.update(_locations_from_text(text))
            continue
        if _is_hard_schedule_fact(fact):
            blocks = _hard_blocks_from_fact(fact, day_start=day_start, day_end=day_end)
            hard_blocks.extend(blocks)
            for block in blocks:
                allowed_locations.update(_locations_from_text(f"{block.get('activity') or ''} {block.get('location') or ''}"))
            continue
        soft_hints.append(_public_fact(fact))
        allowed_locations.update(_locations_from_text(text))

    hard_blocks = _dedupe_hard_blocks(hard_blocks)
    conflicts = _find_constraint_conflicts(hard_blocks=hard_blocks, conditional=conditional, soft_hints=soft_hints)
    return {
        "day": day.isoformat(),
        "hardBlocks": hard_blocks,
        "conditionalCommitments": conditional[:16],
        "softHints": soft_hints[:16],
        "profileFacts": profile_facts[:12],
        "conflicts": conflicts[:24],
        "allowedLocations": sorted(allowed_locations),
        "summary": _format_constraint_summary(hard_blocks, conditional, soft_hints, conflicts),
    }


def cleanup_life_facts(db: Database, *, now: float | None = None) -> dict:
    value = now or dt.datetime.now(TZ).timestamp()
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
    expired = db.expire_life_facts(now=value)
    superseded = _dedupe_life_facts(db, now=value)
    retention = reflect_life_fact_retention(db, now=value)
    return {
        "expired": expired,
        "activated": activated,
        "completed": completed,
        "archived": archived,
        "supersededDuplicates": superseded,
        "retention": retention,
    }


def reflect_life_fact_retention(db: Database, *, now: float | None = None, force: bool = False) -> dict:
    value = now or dt.datetime.now(TZ).timestamp()
    last = db.get_scheduled_job(RETENTION_JOB_KEY)
    if not force and last and value - float(last.get("ranAt") or 0) < RETENTION_JOB_INTERVAL_SECONDS:
        return {"processed": False, "reason": "not_due"}

    reviewed = 0
    archived = 0
    memories_created = 0
    skipped_recent = 0
    for fact in db.list_life_facts(statuses=RETENTION_STATUSES, limit=160, include_expired=True):
        metadata = dict(fact.get("metadata") or {})
        if metadata.get("retentionReviewedAt"):
            continue
        if not _fact_old_enough_for_retention(fact, now=value):
            skipped_recent += 1
            continue

        reviewed += 1
        if _should_promote_fact_to_memory(fact):
            memory = _memory_from_life_fact(fact, now=value)
            db.upsert_memory(**memory)
            memories_created += 1
            db.update_life_fact_status(
                str(fact["id"]),
                status=str(fact.get("status") or "archived"),
                metadata={
                    "retentionReviewedAt": value,
                    "retentionDisposition": "promoted_to_memory",
                    "retentionMemoryId": memory["memory_id"],
                },
            )
        else:
            db.update_life_fact_status(
                str(fact["id"]),
                status="archived",
                metadata={
                    "retentionReviewedAt": value,
                    "retentionDisposition": "archived_low_value",
                },
            )
            archived += 1

    result = {
        "processed": True,
        "reviewed": reviewed,
        "memoriesCreated": memories_created,
        "archivedLowValue": archived,
        "skippedRecent": skipped_recent,
    }
    db.upsert_scheduled_job(job_key=RETENTION_JOB_KEY, result=result)
    return result


def _fact_old_enough_for_retention(fact: dict, *, now: float) -> bool:
    metadata = fact.get("metadata") or {}
    ended_at = metadata.get("endedAt")
    lifecycle_candidates = [
        _float_or_none(fact.get("endsAt")),
        _float_or_none(fact.get("expiresAt")),
        _float_or_none(ended_at),
    ]
    reference = max((item for item in lifecycle_candidates if item is not None), default=None)
    if reference is None:
        reference = _float_or_none(fact.get("updatedAt"))
    if reference is None:
        return False
    return now - reference >= RETENTION_AGE_SECONDS


def _should_promote_fact_to_memory(fact: dict) -> bool:
    fact_type = str(fact.get("type") or "")
    text = f"{fact.get('title') or ''} {fact.get('summary') or ''}"
    importance = float(fact.get("importance") or 0)
    confidence = float(fact.get("confidence") or 0)
    if fact_type == "profile_fact" and confidence >= 0.72:
        return True
    if importance >= 0.86 and confidence >= 0.68:
        return True
    if fact_type == "relationship_commitment" and importance >= 0.72 and _contains_long_term_signal(text):
        return True
    if fact_type == "current_state" and importance >= 0.78 and _contains_long_term_signal(text):
        return True
    return False


def _memory_from_life_fact(fact: dict, *, now: float) -> dict:
    fact_id = str(fact.get("id") or uuid_like())
    fact_type = str(fact.get("type") or "")
    title = str(fact.get("title") or "").strip()
    summary = str(fact.get("summary") or title).strip()
    content = summary or title
    if title and summary and title not in summary:
        content = f"{title}：{summary}"
    kind = "self_life" if fact_type in {"profile_fact", "schedule_commitment", "current_state", "life_event_hint"} else "relationship"
    subject = "companion" if kind == "self_life" else "relationship"
    return {
        "memory_id": f"mem_life_fact_{fact_id}",
        "kind": kind,
        "subject": subject,
        "content": content[:500],
        "summary": (title or summary)[:160],
        "tags": ["事实账本", _memory_tag_for_fact_type(fact_type)],
        "confidence": max(0.5, min(1.0, float(fact.get("confidence") or 0.7))),
        "importance": max(0.5, min(1.0, float(fact.get("importance") or 0.5))),
        "status": "active",
        "enabled": True,
        "pinned": fact_type == "profile_fact",
        "sensitive": False,
        "source": {
            "type": "life_fact_retention",
            "factId": fact_id,
            "factType": fact_type,
            "createdAt": dt.datetime.fromtimestamp(now, tz=TZ).isoformat(),
        },
        "expires_at": None,
    }


def _memory_tag_for_fact_type(fact_type: str) -> str:
    return {
        "schedule_commitment": "重要安排",
        "relationship_commitment": "关系承诺",
        "current_state": "状态沉淀",
        "profile_fact": "稳定设定",
        "life_event_hint": "生活线索",
        "moment_posted": "朋友圈",
    }.get(fact_type, "生活事实")


def _contains_long_term_signal(text: str) -> bool:
    return any(keyword in text for keyword in LONG_TERM_FACT_KEYWORDS)


def _float_or_none(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


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
    for source, target in (("effectiveAt", "effectiveAt"), ("endedAt", "endedAt")):
        if source in body:
            parsed = _parse_time(body.get(source))
            if parsed is not None:
                result.setdefault("metadata", {})[target] = parsed
    if "supersedesId" in body:
        result["supersedes_id"] = str(body.get("supersedesId") or "")
    return result


def _should_extract(user_message: dict, assistant_message: dict) -> bool:
    user_text = str(user_message.get("content") or "")
    assistant_text = str(assistant_message.get("content") or "")
    text = f"{user_text}\n{assistant_text}"
    if len(text.strip()) < 8:
        return False
    return bool(VALUE_SIGNALS.search(text) or ASSISTANT_COMMITMENT_SIGNALS.search(assistant_text))


def _pair_id(user_message: dict, assistant_message: dict, *, index: int = 0) -> str:
    user_id = str(user_message.get("id") or "").strip()
    assistant_id = str(assistant_message.get("id") or "").strip()
    if user_id or assistant_id:
        return f"{user_id}:{assistant_id}"
    text = f"{index}\n{user_message.get('createdAt') or user_message.get('created_at') or ''}\n{user_message.get('content') or ''}\n{assistant_message.get('content') or ''}"
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:24]


def _batch_fact_id(source_pair_id: str, item: dict, index: int) -> str:
    text = "\n".join(
        [
            source_pair_id,
            str(index),
            str(item.get("type") or ""),
            str(item.get("title") or ""),
            str(item.get("summary") or ""),
        ]
    )
    return f"fact_{hashlib.sha1(text.encode('utf-8')).hexdigest()[:12]}"


def _processed_pair_ids(db: Database) -> set[str]:
    result: set[str] = set()
    for fact in db.list_life_facts(statuses=VISIBLE_STATUSES, limit=200, include_expired=True):
        metadata = fact.get("metadata") or {}
        related = fact.get("related") or {}
        source_pair_id = str(metadata.get("sourcePairId") or related.get("sourcePairId") or "")
        if source_pair_id:
            result.add(source_pair_id)
            continue
        user_message_id = str(related.get("userMessageId") or fact.get("sourceMessageId") or "")
        assistant_message_id = str(related.get("assistantMessageId") or "")
        if user_message_id or assistant_message_id:
            result.add(f"{user_message_id}:{assistant_message_id}")
    return result


def _apply_soft_plan_defaults(
    metadata: dict,
    *,
    status: str,
    confidence: float,
    importance: float,
    anchor: dt.datetime,
    text: str,
) -> None:
    if status not in {"planned", "active", "candidate"}:
        return
    if importance < 0.5 and confidence < 0.65:
        return
    if not (SOFT_PLAN_SIGNALS.search(text) or ASSISTANT_COMMITMENT_SIGNALS.search(text)):
        return
    metadata.setdefault("targetDate", _life_day(anchor).isoformat())
    metadata.setdefault("flexibility", "soft")
    if any(word in text for word in ("下午", "午后")):
        metadata.setdefault("timeHint", "afternoon")
    elif any(word in text for word in ("今晚", "晚上")):
        metadata.setdefault("timeHint", "evening")
    elif any(word in text for word in ("等会儿", "一会儿", "待会儿", "稍后", "回头")):
        metadata.setdefault("timeHint", "soon")
    if status in {"planned", "active"} or ASSISTANT_COMMITMENT_SIGNALS.search(text):
        metadata.setdefault("commitmentStrength", "accepted")


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
    metadata = {
        "extractor": "life_fact_service",
        "rawType": item.get("type"),
        "timeAnchor": anchor.isoformat(),
        "userLifeDay": _life_day(anchor).isoformat(),
        "extractedAt": extracted.isoformat(),
        "rawTitle": raw_title,
        "rawSummary": raw_summary,
    }
    if isinstance(item.get("metadata"), dict):
        for key in ("targetDate", "timeHint", "commitmentStrength", "flexibility"):
            value = item["metadata"].get(key)
            if value not in (None, ""):
                metadata[key] = str(value)
    for key in ("targetDate", "timeHint", "commitmentStrength", "flexibility"):
        value = item.get(key)
        if value not in (None, ""):
            metadata[key] = str(value)
    if starts_at is None and fact_type in {"schedule_commitment", "relationship_commitment", "life_event_hint"}:
        _apply_soft_plan_defaults(
            metadata,
            status=status,
            confidence=confidence,
            importance=importance,
            anchor=anchor,
            text="\n".join(
                [
                    raw_title,
                    raw_summary,
                    str(user_message.get("content") or ""),
                    str(assistant_message.get("content") or ""),
                ]
            ),
        )
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
        "metadata": metadata,
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
        "updatedAt": item.get("updatedAt"),
        "timeWindow": _time_window(item),
        "metadata": item.get("metadata") or {},
    }


def _is_hard_schedule_fact(fact: dict) -> bool:
    fact_type = str(fact.get("type") or "")
    if fact_type not in {"schedule_commitment", "current_state"}:
        return False
    if fact.get("startsAt") is None:
        return False
    confidence = float(fact.get("confidence") or 0)
    importance = float(fact.get("importance") or 0)
    text = f"{fact.get('title') or ''} {fact.get('summary') or ''}"
    if any(word in text for word in HARD_SCHEDULE_KEYWORDS):
        return confidence >= 0.6 or importance >= 0.6
    if fact.get("endsAt") is not None:
        start = _from_timestamp(fact.get("startsAt"))
        end = _from_timestamp(fact.get("endsAt"))
        if start and end and (end - start) <= dt.timedelta(hours=14):
            return confidence >= 0.75 and importance >= 0.65
    return False


def _is_conditional_fact(fact: dict) -> bool:
    fact_type = str(fact.get("type") or "")
    text = f"{fact.get('title') or ''} {fact.get('summary') or ''}"
    if fact_type == "relationship_commitment":
        return True
    return any(word in text for word in CONDITIONAL_KEYWORDS)


def _hard_blocks_from_fact(fact: dict, *, day_start: dt.datetime, day_end: dt.datetime) -> list[dict]:
    start = _from_timestamp(fact.get("startsAt"))
    end = _from_timestamp(fact.get("endsAt"))
    if start is None:
        return []
    text = f"{fact.get('title') or ''} {fact.get('summary') or ''}"
    is_flight = any(word in text for word in ("航班", "执飞", "落地", "机组"))
    if end is None:
        end = start + (dt.timedelta(hours=4) if is_flight else dt.timedelta(hours=2))
    start = max(start, day_start)
    end = min(end, day_end)
    if end <= start:
        return []
    blocks: list[dict] = []
    if is_flight:
        prep_start = max(day_start, start - dt.timedelta(minutes=90))
        if prep_start < start:
            blocks.append(
                _constraint_block(
                    fact=fact,
                    start=prep_start,
                    end=start,
                    activity="前往机场和值机准备",
                    location=_infer_location_from_text(text, fallback="机场/路上"),
                    intent="为已确定航班预留通勤、值机和机组准备时间",
                    priority=95,
                    block_type="travel_buffer",
                )
            )
        blocks.append(
            _constraint_block(
                fact=fact,
                start=start,
                end=end,
                activity=str(fact.get("title") or "执飞航班")[:80],
                location=_infer_location_from_text(text, fallback="机场/机上"),
                intent=str(fact.get("summary") or "已确定航班任务，其他安排不得覆盖。")[:180],
                priority=100,
                block_type="hard_schedule",
            )
        )
        return blocks
    blocks.append(
        _constraint_block(
            fact=fact,
            start=start,
            end=end,
            activity=str(fact.get("title") or "已确定安排")[:80],
            location=_infer_location_from_text(text, fallback="按事实地点"),
            intent=str(fact.get("summary") or "已确定安排，其他安排不得覆盖。")[:180],
            priority=90,
            block_type="hard_schedule",
        )
    )
    return blocks


def _constraint_block(
    *,
    fact: dict,
    start: dt.datetime,
    end: dt.datetime,
    activity: str,
    location: str,
    intent: str,
    priority: int,
    block_type: str,
) -> dict:
    return {
        "timeRange": f"{start.strftime('%H:%M')}-{end.strftime('%H:%M')}",
        "startsAt": start.timestamp(),
        "endsAt": end.timestamp(),
        "activity": activity,
        "location": location,
        "intent": intent,
        "priority": priority,
        "type": block_type,
        "sourceFactIds": [fact.get("id")],
    }


def _dedupe_hard_blocks(blocks: list[dict]) -> list[dict]:
    result: list[dict] = []
    for block in sorted(blocks, key=lambda item: (float(item.get("startsAt") or 0), -int(item.get("priority") or 0))):
        duplicate_index = -1
        for index, existing in enumerate(result):
            if not _blocks_overlap(existing, block):
                continue
            same_kind = ("航班" in f"{existing.get('activity')} {block.get('activity')}") or existing.get("type") == block.get("type")
            if same_kind:
                duplicate_index = index
                break
        if duplicate_index < 0:
            result.append(block)
            continue
        existing = result[duplicate_index]
        keep, drop = (block, existing) if _block_score(block) > _block_score(existing) else (existing, block)
        keep["sourceFactIds"] = list(dict.fromkeys([*(keep.get("sourceFactIds") or []), *(drop.get("sourceFactIds") or [])]))
        result[duplicate_index] = keep
    return sorted(result, key=lambda item: float(item.get("startsAt") or 0))


def _block_score(block: dict) -> tuple[int, float, float]:
    return (
        int(block.get("priority") or 0),
        float(block.get("endsAt") or 0) - float(block.get("startsAt") or 0),
        float(block.get("startsAt") or 0),
    )


def _find_constraint_conflicts(*, hard_blocks: list[dict], conditional: list[dict], soft_hints: list[dict]) -> list[dict]:
    conflicts: list[dict] = []
    for fact in [*conditional, *soft_hints]:
        start = _from_timestamp(fact.get("startsAt"))
        end = _from_timestamp(fact.get("endsAt")) or (start + dt.timedelta(hours=2) if start else None)
        if start is None or end is None:
            continue
        for block in hard_blocks:
            block_start = _from_timestamp(block.get("startsAt"))
            block_end = _from_timestamp(block.get("endsAt"))
            if block_start and block_end and start < block_end and end > block_start:
                conflicts.append(
                    {
                        "factId": fact.get("id"),
                        "blockedBy": block.get("sourceFactIds") or [],
                        "message": f"{fact.get('title') or '安排'} 与硬日程 {block.get('timeRange')} {block.get('activity')} 冲突，应延期、改约或标记未触发。",
                    }
                )
    return conflicts


def _format_constraint_summary(hard_blocks: list[dict], conditional: list[dict], soft_hints: list[dict], conflicts: list[dict]) -> str:
    lines: list[str] = []
    if hard_blocks:
        lines.append("硬日程：")
        lines.extend(f"- {item['timeRange']} {item['activity']} @ {item['location']}" for item in hard_blocks[:8])
    if conditional:
        lines.append("条件承诺：")
        lines.extend(f"- {item.get('timeWindow') or ''} {item.get('title')}: {item.get('summary')}".strip() for item in conditional[:6])
    if soft_hints:
        lines.append("软提示：")
        lines.extend(f"- {item.get('title')}: {item.get('summary')}" for item in soft_hints[:6])
    if conflicts:
        lines.append("冲突处理：")
        lines.extend(f"- {item['message']}" for item in conflicts[:6])
    return "\n".join(lines) or "暂无当天额外日程约束。"


def _touches_day(start: dt.datetime | None, end: dt.datetime | None, day_start: dt.datetime, day_end: dt.datetime) -> bool:
    if start is None:
        return False
    end = end or start + dt.timedelta(hours=2)
    return start < day_end and end > day_start


def _targets_day(fact: dict, day: dt.date) -> bool:
    metadata = fact.get("metadata") or {}
    value = metadata.get("targetDate")
    if value is None:
        return False
    try:
        return dt.date.fromisoformat(str(value)[:10]) == day
    except ValueError:
        return False


def _blocks_overlap(left: dict, right: dict) -> bool:
    left_start = float(left.get("startsAt") or 0)
    left_end = float(left.get("endsAt") or left_start)
    right_start = float(right.get("startsAt") or 0)
    right_end = float(right.get("endsAt") or right_start)
    return left_start < right_end and right_start < left_end


def _locations_from_text(text: str) -> set[str]:
    locations: set[str] = set()
    for word in ("机场", "航站楼", "机上", "机组休息室", "酒店", "公司", "学校", "医院", "工作室", "家", "路上", "温泉镇", "马连洼", "大连", "北京", "广州", "上海", "深圳", "成都", "杭州"):
        if word in text:
            locations.add(word)
    if any(word in text for word in AVIATION_KEYWORDS):
        locations.update({"机场", "航站楼", "机上", "机组休息室", "路上"})
    return locations


def _infer_location_from_text(text: str, *, fallback: str) -> str:
    if "北京至大连" in text or "大连" in text:
        return "机场/机上/大连"
    if "广州" in text:
        return "机场/机上/广州"
    if any(word in text for word in ("航班", "执飞", "机组", "落地")):
        return "机场/机上"
    for word in ("机场", "航站楼", "机组休息室", "酒店", "公司", "学校", "工作室", "家", "温泉镇", "马连洼"):
        if word in text:
            return word
    return fallback


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
