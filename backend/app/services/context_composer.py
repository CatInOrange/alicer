from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

from .fortune_service import build_daily_fortune_context


RECENT_HISTORY_COUNT = 20
RECENT_HISTORY_CHAR_BUDGET = 12_000
OLDER_HISTORY_CHAR_BUDGET = 8_000
TZ = ZoneInfo("Asia/Shanghai")


def compose_prompt_context(
    *,
    settings: dict,
    recent_messages: list[dict],
    memories: list[dict],
    environment: dict,
    life_context: dict,
    user_context: dict,
    photo_context: dict,
    world_context: dict,
) -> dict:
    prompt_history = select_prompt_history(settings=settings, recent_messages=recent_messages)
    history_older, history_recent = _format_split_history(prompt_history)
    long_term = _format_memories(memories[:24]) if (settings.get("memory") or {}).get("longTerm", True) else ""
    short_term = _format_short_term(settings=settings, prompt_history=prompt_history)

    now = _context_now(environment)
    world_current = _format_world_current(
        settings=settings,
        environment=environment,
        world_context=world_context,
        life_context=life_context,
        now=now,
    )
    world_future = _format_future_timeline(life_context=life_context, world_context=world_context)
    world_commitments = _format_world_commitments(world_context)
    world_trajectory = _format_world_trajectory(life_context)
    world_user = _format_user_context(user_context)
    world_photos = _format_chat_photo_context(photo_context)
    world_fortune = _format_fortune_context(build_daily_fortune_context(settings, date=now.date()))
    world_memory = long_term or "暂无长期记忆。"
    world_guardrails = _format_world_guardrails(world_context)
    world_legacy = _format_world_context(world_context)
    life_text = _format_life_context(life_context)
    freshness = _build_projection_freshness(life_context=life_context, world_context=world_context, now=now)
    projection_freshness = _format_projection_freshness(freshness)
    context_brief = _format_context_brief(
        projection_freshness=projection_freshness,
        current=world_current,
        future=world_future,
        commitments=world_commitments,
        trajectory=world_trajectory,
        user=world_user,
        photos=world_photos,
        fortune=world_fortune,
        history_older=history_older,
        history_recent=history_recent,
        memory=world_memory,
        guardrails=world_guardrails,
    )

    companion = settings.get("companion") or {}
    environment_settings = settings.get("environment") or {}
    variables = {
        "companion.name": str(companion.get("name") or "Alice"),
        "user.name": str(companion.get("userName") or "你"),
        "current.time": _format_time(environment) if environment_settings.get("time", True) else "",
        "current.location": _format_location(environment) if environment_settings.get("location") else "",
        "current.weather": _format_weather(environment) if environment_settings.get("weather") else "",
        "world.context": world_legacy,
        "world.current": world_current,
        "world.future": world_future,
        "world.commitments": world_commitments,
        "world.trajectory": world_trajectory,
        "world.user": world_user,
        "world.photos": world_photos,
        "world.fortune": world_fortune,
        "world.memory": world_memory,
        "world.guardrails": world_guardrails,
        "context.freshness": projection_freshness,
        "context.brief": context_brief,
        "life.current": life_text,
        "user.current": world_user,
        "chat.photo": world_photos,
        "history.older": history_older,
        "history.recent_20": history_recent,
        "memory.short_term": short_term,
        "memory.long_term": long_term,
        "recent_messages": short_term,
    }
    return {
        "variables": variables,
        "package": {
            "world": {
                "brief": context_brief,
                "freshness": projection_freshness,
                "current": world_current,
                "future": world_future,
                "commitments": world_commitments,
                "trajectory": world_trajectory,
                "user": world_user,
                "photos": world_photos,
                "fortune": world_fortune,
                "memory": world_memory,
                "guardrails": world_guardrails,
            },
            "counts": {
                "history": len(prompt_history),
                "historyRecent": min(RECENT_HISTORY_COUNT, len(prompt_history)),
                "historyOlder": max(0, len(prompt_history) - RECENT_HISTORY_COUNT),
                "memories": len(memories),
                "worldFacts": len(world_context.get("activeFacts") or []),
                "lifeEvents": len(life_context.get("recentEvents") or []),
            },
            "freshness": freshness,
        },
        "promptHistory": prompt_history,
    }


def _format_context_brief(
    *,
    projection_freshness: str,
    current: str,
    future: str,
    commitments: str,
    trajectory: str,
    user: str,
    photos: str,
    fortune: str,
    history_older: str,
    history_recent: str,
    memory: str,
    guardrails: str,
) -> str:
    sections = [
        ("最高优先级一致性规则", guardrails),
        ("投影新鲜度", projection_freshness),
        ("Alicer 当前状态", current),
        ("Alicer 未来时间线", future),
        ("未完成承诺、计划和稳定事实", commitments),
        ("用户现实线索", user),
        ("今日个人化运势", fortune),
        ("照片/自拍连续性", photos),
        ("Alicer 最近生活轨迹", trajectory),
        ("最近 20 条聊天", history_recent),
        ("更早聊天摘要", history_older),
        ("长期记忆", memory),
    ]
    lines = [
        "下面是本轮回复唯一需要使用的运行上下文，按优先级排列；不要逐段复述，只在相关时自然使用。",
        "如果不同来源冲突，优先级为：硬事实/明确承诺 > 当前生活状态 > 今日剩余计划 > 长期节律 > 最近聊天 > 长期记忆 > 随机发挥。",
    ]
    for title, content in sections:
        text = str(content or "").strip()
        if not text:
            continue
        lines.append(f"\n## {title}\n{text}")
    return "\n".join(lines)


def _build_projection_freshness(*, life_context: dict, world_context: dict, now: dt.datetime | None = None) -> dict:
    generated_at = (now or dt.datetime.now(TZ)).astimezone(TZ).isoformat()
    plan = life_context.get("plan") or {}
    world_freshness = world_context.get("freshness") or {}
    reconciliation = world_freshness.get("lastReconciliation") or {}
    reconciliation_result = reconciliation.get("result") if isinstance(reconciliation, dict) else {}
    latest_fact_updated_at = _to_float(world_freshness.get("latestFactUpdatedAt"))
    state = life_context.get("state") or {}
    life_state_updated_at = _to_float(state.get("updatedAt")) or _to_float(life_context.get("updatedAt"))
    return {
        "contextGeneratedAt": generated_at,
        "latestFactUpdatedAt": latest_fact_updated_at,
        "latestFactUpdatedAtText": _format_ts(latest_fact_updated_at),
        "lifeStateUpdatedAt": life_state_updated_at,
        "lifeStateUpdatedAtText": _format_ts(life_state_updated_at),
        "planGeneratedAt": str(plan.get("generatedAt") or ""),
        "planSource": str(plan.get("source") or ""),
        "lastReconciledAt": _to_float(reconciliation.get("ranAt")) if isinstance(reconciliation, dict) else None,
        "lastReconciledAtText": _format_ts(_to_float(reconciliation.get("ranAt")) if isinstance(reconciliation, dict) else None),
        "lastReconciliation": reconciliation_result or {},
    }


def _format_projection_freshness(freshness: dict) -> str:
    lines = [
        f"- Context Package 生成：{freshness.get('contextGeneratedAt') or '未知'}",
    ]
    if freshness.get("latestFactUpdatedAtText"):
        lines.append(f"- 最新事实账本更新：{freshness['latestFactUpdatedAtText']}")
    else:
        lines.append("- 最新事实账本更新：暂无 active/candidate/planned 事实。")
    if freshness.get("lifeStateUpdatedAtText"):
        lines.append(f"- 生活状态更新：{freshness['lifeStateUpdatedAtText']}")
    if freshness.get("planGeneratedAt"):
        source = str(freshness.get("planSource") or "").strip()
        suffix = f"，来源 {source}" if source else ""
        lines.append(f"- 今日计划生成：{freshness['planGeneratedAt']}{suffix}")
    if freshness.get("lastReconciledAtText"):
        result = freshness.get("lastReconciliation") or {}
        reason = str(result.get("sourceReason") or result.get("reason") or "").strip()
        refreshed = result.get("refreshedTodayPlan")
        parts = [freshness["lastReconciledAtText"]]
        if reason:
            parts.append(f"原因 {reason}")
        if refreshed is not None:
            parts.append(f"刷新今日计划 {bool(refreshed)}")
        lines.append("- 最近一致性调和：" + "，".join(parts))
    else:
        lines.append("- 最近一致性调和：暂无记录。")
    return "\n".join(lines)


def select_prompt_history(*, settings: dict, recent_messages: list[dict]) -> list[dict]:
    context = settings.get("chatContext") or {}
    mode = str(context.get("historyMode") or "all").strip()
    recent_limit = _clamp_int(context.get("recentMessages"), default=120, minimum=1, maximum=300)
    max_limit = _clamp_int(context.get("maxHistoryMessages"), default=300, minimum=1, maximum=300)
    messages = [
        item
        for item in recent_messages
        if item.get("role") in {"user", "assistant"} and item.get("content")
    ]
    now = dt.datetime.now().astimezone()
    if mode == "day":
        cutoff = now - dt.timedelta(days=1)
        messages = [item for item in messages if _created_at(item) >= cutoff]
    elif mode == "month":
        cutoff = now - dt.timedelta(days=31)
        messages = [item for item in messages if _created_at(item) >= cutoff]
    elif mode == "recent":
        messages = messages[-recent_limit:]
    return messages[-max_limit:]


def _format_world_current(
    *,
    world_context: dict,
    life_context: dict,
    settings: dict | None = None,
    environment: dict | None = None,
    now: dt.datetime | None = None,
) -> str:
    current_now = (now or _context_now(environment or {})).astimezone(TZ)
    lines = [
        f"当前真实时间（Asia/Shanghai）：{current_now.strftime('%Y-%m-%d %H:%M')}；北京时间=大连时间，不存在时差。",
        "不要从旧生活事件、旧片段或“凌晨/早上”等叙事文字推断当前钟点；当前钟点只以这一行真实时间为准。",
    ]
    current = world_context.get("current") or []
    if current:
        lines.append("当前必须保持一致的事实：")
        lines.extend(_fact_line(item) for item in current[:8])
    state = life_context.get("state") or {}
    state_parts = [
        str(state.get("activity") or "").strip(),
        str(state.get("location") or "").strip(),
        f"心情{state.get('mood')}" if state.get("mood") else "",
        f"精力{state.get('energy')}" if state.get("energy") else "",
    ]
    compact = "，".join(item for item in state_parts if item)
    state_updated_at = _to_float(state.get("updatedAt")) or _to_float(life_context.get("updatedAt"))
    state_is_fresh = _life_state_is_fresh(
        state_updated_at,
        now=current_now,
        settings=settings or {},
    )
    if compact:
        if state_is_fresh:
            lines.append(f"生活模拟当前状态：{compact}")
        else:
            age = _age_text(state_updated_at, now=current_now)
            suffix = f"（最后记录 {age}，可能已过期）" if age else "（没有可靠更新时间，不能当作当前状态）"
            lines.append(f"上次生活模拟状态{suffix}：{compact}")
    if state.get("summary"):
        if state_is_fresh:
            lines.append(f"当前片段：{state['summary']}")
        else:
            lines.append("旧生活片段已过期，不能把其中的时间词当成当前时间。")
    plan = life_context.get("plan") or {}
    next_event, _remaining, _earlier = _split_plan_events(plan.get("plannedEvents") or [], now=current_now)
    if not state_is_fresh and next_event:
        lines.append("按今日计划当前/下一段参考：")
        lines.append("  - " + _timeline_event_line(next_event, default_certainty=str(next_event.get("certainty") or "planned")))
    return "\n".join(lines) or "暂无明确当前事实；回答时不要凭空声称正在做具体事情。"


def _format_world_commitments(world_context: dict) -> str:
    upcoming = world_context.get("upcoming") or []
    stable = world_context.get("stable") or []
    lines = []
    if stable:
        lines.append("稳定生活事实：")
        lines.extend(_fact_line(item) for item in stable[:6])
    if upcoming:
        lines.append("未完成/即将发生的承诺与计划：")
        lines.extend(_fact_line(item) for item in upcoming[:10])
    return "\n".join(lines) or "暂无未完成承诺或近期计划。"


def _format_future_timeline(*, life_context: dict, world_context: dict) -> str:
    if not life_context or life_context.get("enabled") is False:
        return "未启用生活模拟；不要凭空声称未来具体安排。"
    plan = life_context.get("plan") or {}
    constraints = life_context.get("lifeConstraints") or {}
    routine = life_context.get("routine") or {}
    now = dt.datetime.now().astimezone()
    lines = [
        "未来回答规则：",
        "- 用户问“等会儿/下午/今晚/明天做什么”时，优先使用这里的时间线；不要脱离计划临场编排。",
        "- 硬日程用确定语气；普通计划用“准备/大概/计划是”；节律推断只能说成倾向。",
        "- 如果未来安排冲突，承认原计划被硬事实阻断，并自然改期或说明不能同时做到。",
    ]
    if plan:
        date = str(plan.get("date") or life_context.get("planDate") or "").strip()
        source = str(plan.get("source") or "").strip()
        day_theme = str(plan.get("dayTheme") or "").strip()
        generated = str(plan.get("generatedAt") or "").strip()
        meta = "，".join(item for item in (f"日期 {date}" if date else "", f"来源 {source}" if source else "", f"生成 {generated}" if generated else "") if item)
        if meta or day_theme:
            lines.append("今日计划概况：" + "；".join(item for item in (meta, day_theme) if item))
    next_event, remaining, earlier = _split_plan_events(plan.get("plannedEvents") or [], now=now)
    hard_blocks = constraints.get("hardBlocks") or plan.get("hardBlocks") or []
    if hard_blocks:
        lines.append("已锁定硬日程：")
        for item in hard_blocks[:8]:
            lines.append("  - " + _timeline_event_line(item, default_certainty="hard"))
    if next_event:
        lines.append("下一段计划：")
        lines.append("  - " + _timeline_event_line(next_event, default_certainty=str(next_event.get("certainty") or "planned")))
    if remaining:
        lines.append("今日剩余计划：")
        for item in remaining[:8]:
            lines.append("  - " + _timeline_event_line(item, default_certainty=str(item.get("certainty") or "planned")))
    elif earlier and not hard_blocks:
        lines.append("今日计划中没有剩余可用时间块；不要继续沿用已过去的安排。")
    conflicts = constraints.get("conflicts") or []
    if conflicts:
        lines.append("已知冲突/阻断：")
        for item in conflicts[:5]:
            message = str(item.get("message") or item.get("title") or "").strip()
            if message:
                lines.append(f"  - {message[:180]}")
    upcoming = world_context.get("upcoming") or []
    if upcoming:
        lines.append("近未来明确事实/承诺：")
        lines.extend("  - " + _fact_line(item) for item in upcoming[:6])
    routine_summary = _routine_summary(routine)
    if routine_summary:
        lines.append("长期节律推断：" + routine_summary)
    return "\n".join(lines)


def _split_plan_events(events: list[dict], *, now: dt.datetime) -> tuple[dict | None, list[dict], list[dict]]:
    parsed = []
    for index, item in enumerate(events):
        if not isinstance(item, dict):
            continue
        start, end = _parse_event_range_today(str(item.get("timeRange") or ""), now=now)
        parsed.append((start, end, index, item))
    parsed.sort(key=lambda row: (row[0] or dt.datetime.max.replace(tzinfo=now.tzinfo), row[2]))
    current_or_next = None
    remaining = []
    earlier = []
    for start, end, _index, item in parsed:
        if end is not None and end <= now:
            earlier.append(item)
            continue
        if current_or_next is None:
            current_or_next = item
        else:
            remaining.append(item)
    return current_or_next, remaining, earlier


def _parse_event_range_today(value: str, *, now: dt.datetime) -> tuple[dt.datetime | None, dt.datetime | None]:
    text = value.strip()
    if "-" not in text:
        return None, None
    left, right = [part.strip() for part in text.split("-", 1)]
    start = _parse_clock_today(left, now=now)
    end = _parse_clock_today(right, now=now)
    if start is not None and end is not None and end <= start:
        end += dt.timedelta(days=1)
    return start, end


def _parse_clock_today(value: str, *, now: dt.datetime) -> dt.datetime | None:
    try:
        hour_text, minute_text = value.split(":", 1)
        hour = int(hour_text)
        minute = int(minute_text[:2])
    except Exception:
        return None
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    return now.replace(hour=hour, minute=minute, second=0, microsecond=0)


def _timeline_event_line(item: dict, *, default_certainty: str) -> str:
    time_range = str(item.get("timeRange") or "").strip()
    activity = str(item.get("activity") or item.get("title") or "未命名安排").strip()
    location = str(item.get("location") or "").strip()
    intent = str(item.get("intent") or "").strip()
    certainty = str(item.get("certainty") or default_certainty or "planned").strip()
    source = str(item.get("source") or "").strip()
    label = {
        "hard": "硬日程",
        "planned": "计划",
        "routine": "节律推断",
        "tentative": "暂定",
    }.get(certainty, certainty)
    parts = [time_range, activity]
    if location:
        parts.append(f"@{location}")
    detail = " ".join(part for part in parts if part)
    suffix = "，".join(item for item in (label, f"来源 {source}" if source else "", intent[:100] if intent else "") if item)
    return f"{detail}（{suffix}）" if suffix else detail


def _routine_summary(routine: dict) -> str:
    if not routine:
        return ""
    routine_type = str(routine.get("type") or "").strip()
    if routine_type == "roster":
        return "排班制；没有硬航班事实时，只能推断为备勤、培训、恢复、休息或个人/兼职安排，不能说每天执飞。"
    if routine_type == "weekday_office":
        return "工作日办公室节律；周末默认休息，除非事实账本明确有加班/兼职/约定。"
    if routine_type == "flexible":
        return "弹性工作节律；可安排项目、副业、个人事务，但具体承诺仍以事实账本为准。"
    if routine_type == "campus":
        return "校园节律；课程、自习和休息按日期变化，具体安排以事实账本和今日计划为准。"
    return str(routine.get("description") or routine_type or "").strip()[:160]


def _format_world_trajectory(life_context: dict) -> str:
    recent_events = life_context.get("recentEvents") or []
    if not recent_events:
        return "暂无最近生活轨迹。"
    lines = ["最近生活轨迹："]
    for item in recent_events[-12:]:
        time_text = str(item.get("timeLabel") or "").strip()
        summary = str(item.get("summary") or item.get("activity") or "").strip()
        place = str(item.get("location") or "").strip()
        lines.append(f"- {time_text} {place}：{summary}".strip())
    return "\n".join(lines)


def _format_life_context(life_context: dict) -> str:
    if not life_context or life_context.get("enabled") is False:
        return "未启用生活模拟；不要凭空声称自己正在做具体事情。"
    profile = life_context.get("profile") or {}
    plan = life_context.get("plan") or {}
    lines = []
    occupation = str(profile.get("occupation") or "").strip()
    if occupation:
        lines.append(f"- 稳定生活画像：{occupation}")
    if plan.get("dayTheme"):
        lines.append(f"- 今日计划主题：{plan['dayTheme']}")
    lines.append("- " + _format_world_current(world_context={}, life_context=life_context))
    trajectory = _format_world_trajectory(life_context)
    if "暂无" not in trajectory:
        lines.append(trajectory)
    facts = (life_context.get("factConstraints") or {}).get("summary")
    if facts:
        lines.append("- 生活事实约束：\n" + str(facts))
    lines.append("- 回答时把这些当作她自己的真实日常；不要随意改职业、住处、作息等稳定事实。")
    lines.append("- 如果用户问“你在干嘛/在哪/今天做什么”，优先引用当前状态和最近轨迹；普通聊天不要生硬汇报全部轨迹。")
    return "\n".join(lines)


def _format_user_context(user_context: dict) -> str:
    if not user_context or user_context.get("enabled") is False:
        return "未启用用户生活轨迹；不要假装知道用户当前手机状态。"
    state = user_context.get("state") or {}
    recent_events = user_context.get("recentEvents") or []
    location_bits = [
        str(state.get("scene") or "").strip(),
        str(state.get("locationLabel") or "").strip(),
        f"城市：{state.get('city')}" if state.get("city") else "",
        f"区县：{state.get('district')}" if state.get("district") else "",
        f"约{state.get('locationAgeMinutes')}分钟前更新"
        if state.get("locationAgeMinutes") is not None
        else "",
        "位置线索可能过期" if state.get("locationStale") else "",
    ]
    state_parts = [
        str(state.get("activity") or "").strip(),
        f"地点线索：{_join_text(location_bits, '，')}" if any(location_bits) else "",
        f"可打扰程度：{state.get('availability')}" if state.get("availability") else "",
        f"音乐：{state.get('music')}" if state.get("music") else "",
        f"运动：{state.get('motion')}" if state.get("motion") else "",
        f"注意状态：{state.get('attentionState')}" if state.get("attentionState") else "",
    ]
    lines = ["- 用户当前状态：" + ("；".join(part for part in state_parts if part) or "暂无手机轨迹状态。")]
    if state.get("cityChanged"):
        lines.append("- 重要变化：用户所在城市发生变化，这是强信号；优先考虑旅途、出差、旅行、返程等语境。")
    elif state.get("placeChanged"):
        lines.append("- 重要变化：用户地点刚发生变化，可以自然关心是不是刚到一个地方。")
    if state.get("summary"):
        lines.append(f"- 用户近期摘要：{state['summary']}")
    if state.get("relationshipCue"):
        lines.append(f"- 聊天使用建议：{state['relationshipCue']}")
    if recent_events:
        lines.append("- 用户最近高价值轨迹：")
        for item in recent_events[-6:]:
            time_text = str(item.get("timeLabel") or "").strip()
            summary = str(item.get("summary") or item.get("title") or "").strip()
            lines.append(f"  - {time_text}：{summary}".strip())
    lines.append("- 这是用户授权的现实上下文，要自然用于语气、话题选择、关心点和打扰程度判断。")
    lines.append("- 可以轻描淡写地联动用户状态，但不要暴露精确坐标、不要逐条汇报、不要表现得像监控。")
    lines.append("- 位置/音乐/运动低置信或过期时只当弱线索；不要把推断说成绝对事实。")
    return "\n".join(lines)


def _format_chat_photo_context(photo_context: dict) -> str:
    if not photo_context or photo_context.get("enabled") is False:
        return "未启用聊天照片；不要承诺会发自拍或生活照。"
    lines = []
    limit = int(photo_context.get("dailySuccessfulLimit") or 0)
    sent_today = int(photo_context.get("sentToday") or 0)
    remaining = int(photo_context.get("remainingToday") or 0)
    allow_requested = photo_context.get("allowRequested") is not False
    allow_proactive = photo_context.get("allowProactive") is True
    lines.append(f"- 今日聊天照片额度：已成功发送 {sent_today}/{limit}，剩余额度 {remaining}。")
    lines.append(f"- 用户明确要照片：{'允许' if allow_requested and remaining > 0 else '当前不允许或额度不足'}。")
    lines.append(f"- 伴侣主动发照片：{'允许，按当下氛围自然发送' if allow_proactive and remaining > 0 else '当前不允许'}。")
    if photo_context.get("minHoursBetweenPhotos"):
        lines.append(f"- 两次成功发送至少间隔 {photo_context['minHoursBetweenPhotos']} 小时。")
    active = photo_context.get("activeTask") or {}
    if active:
        prompt = active.get("prompt") if isinstance(active.get("prompt"), dict) else {}
        bits = [
            str(prompt.get("scene") or active.get("imagePrompt") or "").strip(),
            str(prompt.get("outfit") or "").strip(),
            str(prompt.get("pose") or "").strip(),
        ]
        lines.append(
            "- 当前有未完成的照片承诺："
            + "，".join(item for item in bits if item)
            + f"；状态 {active.get('status') or '进行中'}。"
        )
        lines.append("- 如果用户继续聊天，要自然记得这件事；不要说“图片生成中”，可以说还在换衣服、找角度、刚才答应的那张等。")
    else:
        lines.append("- 如果用户明确要自拍/照片，可以自然答应但不要说已经发出；后端会决定是否创建照片任务。")
    lines.append("- 不要机械提到额度、任务、生成、API、工具调用。额度不足时用伴侣口吻自然拒绝或留悬念。")
    lines.append("- 一旦已经答应并开始拍照，后续聊天要保持连续性，不要像忘了这件事。")
    return "\n".join(lines)


def _format_world_context(world_context: dict) -> str:
    prompt = str(world_context.get("prompt") or "").strip()
    if prompt:
        return prompt
    facts = world_context.get("activeFacts") or []
    if not facts:
        return "暂无统一生活事实账本；回答时仍要避免随意改写稳定设定。"
    lines = ["当前需要保持一致的生活事实："]
    lines.extend(_fact_line(item) for item in facts[:12])
    lines.append("聊天、朋友圈和生活模拟都必须优先服从这些事实；不要安排冲突的地点、工作、行程或承诺。")
    return "\n".join(lines)


def _format_fortune_context(fortune_context: dict) -> str:
    if not fortune_context.get("enabled"):
        return ""
    if not fortune_context.get("configured"):
        return "今日运势引擎已开启，但还没有配置用户生日；不要主动提运势。"
    prompt = str(fortune_context.get("prompt") or "").strip()
    if not prompt:
        return ""
    return prompt


def _format_world_guardrails(world_context: dict) -> str:
    facts = world_context.get("activeFacts") or []
    lines = [
        "一致性守则：",
        "- 事实账本、明确承诺、生活模拟当前状态、未来时间线优先于即兴发挥。",
        "- 回答未来安排时必须先看未来时间线；硬日程不能改，普通计划可用“准备/大概/计划是”表达，节律推断不能说成承诺。",
        "- 不要把用户的行程改写成 Alicer 自己的经历。",
        "- 不要临时改变职业、住处、长期习惯；除非事实账本明确更新。",
        "- 如果已有计划/承诺，不要安排冲突地点、时间或行动。",
        "- 如果用户提出的新请求与硬日程冲突，要自然说明做不到或改期；不要嘴上答应但让后台计划不一致。",
    ]
    if facts:
        lines.append("- 低置信事实只能含蓄处理；时间已过或状态不明时不要说成确定发生。")
    return "\n".join(lines)


def _format_short_term(*, settings: dict, prompt_history: list[dict]) -> str:
    memory = settings.get("memory") or {}
    if not memory.get("shortTerm", True):
        return ""
    return "\n".join(
        f"{item.get('role')}: {item.get('content')}"
        for item in prompt_history[-12:]
        if item.get("content")
    ) or "暂无短期记忆。"


def _format_memories(memories: list[dict]) -> str:
    if not memories:
        return "暂无长期记忆。"
    labels = {
        "fact": "事实",
        "preference": "偏好",
        "relationship": "关系",
        "state": "近期状态",
        "self_life": "她自己的生活",
    }
    grouped: dict[str, list[str]] = {}
    for item in memories:
        kind = str(item.get("kind") or "fact")
        label = labels.get(kind, kind)
        subject = str(item.get("subject") or "").strip()
        prefix = f"{subject}: " if subject and subject not in {"user", "relationship"} else ""
        grouped.setdefault(label, []).append(f"- {prefix}{item.get('content')}")
    sections = []
    for label, lines in grouped.items():
        sections.append(label + "：\n" + "\n".join(lines[:8]))
    return "\n".join(sections)


def _format_split_history(messages: list[dict]) -> tuple[str, str]:
    older = messages[:-RECENT_HISTORY_COUNT]
    recent = messages[-RECENT_HISTORY_COUNT:]
    return (
        _format_history_block(older, char_budget=OLDER_HISTORY_CHAR_BUDGET, empty_text="暂无更早聊天历史。"),
        _format_history_block(recent, char_budget=RECENT_HISTORY_CHAR_BUDGET, empty_text="暂无最近聊天历史。"),
    )


def _format_history_block(messages: list[dict], *, char_budget: int, empty_text: str) -> str:
    lines = []
    for item in messages:
        role = "Alice" if item.get("role") == "assistant" else "用户"
        time_text = _format_message_time(item)
        content = " ".join(str(item.get("content") or "").split())
        if content:
            lines.append(f"- {time_text} {role}: {content}".strip())
    if not lines:
        return empty_text
    selected = []
    used = 0
    for line in reversed(lines):
        cost = len(line) + 1
        if selected and used + cost > char_budget:
            break
        if cost > char_budget:
            line = line[: max(0, char_budget - 1)].rstrip() + "…"
            cost = len(line)
        selected.append(line)
        used += cost
    selected.reverse()
    omitted = len(lines) - len(selected)
    if omitted > 0:
        selected.insert(0, f"- 已省略更早的 {omitted} 条聊天。")
    return "\n".join(selected)


def _format_message_time(item: dict) -> str:
    created = _created_at(item)
    if created.year <= 1970:
        return ""
    return created.strftime("%m-%d %H:%M")


def _format_time(env: dict) -> str:
    raw = str(env.get("time") or "").strip()
    if raw:
        return raw
    return dt.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M")


def _format_location(env: dict) -> str:
    name = str(env.get("locationName") or "").strip()
    lat = env.get("latitude")
    lon = env.get("longitude")
    if name:
        return f"\n- 地点：{name}"
    if lat is not None and lon is not None:
        return f"\n- 坐标：{lat}, {lon}"
    return ""


def _format_weather(env: dict) -> str:
    weather = env.get("weather")
    if isinstance(weather, dict):
        parts = []
        if weather.get("summary"):
            parts.append(str(weather["summary"]))
        if weather.get("temperature") is not None:
            parts.append(f"{weather['temperature']}°C")
        if parts:
            return "\n- 天气：" + "，".join(parts)
    if isinstance(weather, str) and weather.strip():
        return "\n- 天气：" + weather.strip()
    return ""


def _fact_line(item: dict) -> str:
    title = str(item.get("title") or "").strip()
    summary = str(item.get("summary") or "").strip()
    time_window = str(item.get("timeWindow") or "").strip()
    prefix = f"{time_window} " if time_window else ""
    return f"- {prefix}{title}: {summary}".strip()


def _join_text(items: list[str], separator: str) -> str:
    return separator.join(item for item in (str(value or "").strip() for value in items) if item)


def _created_at(item: dict) -> dt.datetime:
    raw = item.get("createdAt")
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return dt.datetime.fromtimestamp(0, tz=dt.timezone.utc)
    return dt.datetime.fromtimestamp(value, tz=dt.timezone.utc).astimezone(TZ)


def _to_float(value: object) -> float | None:
    try:
        if value is None:
            return None
        parsed = float(value)
        return parsed if parsed > 0 else None
    except (TypeError, ValueError):
        return None


def _format_ts(value: float | None) -> str:
    if value is None:
        return ""
    return dt.datetime.fromtimestamp(value, tz=dt.timezone.utc).astimezone(TZ).isoformat()


def _context_now(environment: dict | None) -> dt.datetime:
    raw = str((environment or {}).get("time") or "").strip()
    if raw:
        parsed = _parse_datetime(raw)
        if parsed is not None:
            return parsed.astimezone(TZ)
    return dt.datetime.now(TZ)


def _parse_datetime(value: str) -> dt.datetime | None:
    text = value.strip()
    if not text:
        return None
    candidates = [text]
    if text.endswith("Z"):
        candidates.append(text[:-1] + "+00:00")
    for candidate in candidates:
        try:
            parsed = dt.datetime.fromisoformat(candidate)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=TZ)
            return parsed
        except ValueError:
            pass
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S"):
        try:
            return dt.datetime.strptime(text[:19], fmt).replace(tzinfo=TZ)
        except ValueError:
            pass
    return None


def _life_state_is_fresh(state_updated_at: float | None, *, now: dt.datetime, settings: dict) -> bool:
    if state_updated_at is None:
        return False
    state_time = dt.datetime.fromtimestamp(state_updated_at, tz=TZ)
    life_settings = (settings or {}).get("life") or {}
    interval_hours = _clamp_int(life_settings.get("updateIntervalHours"), default=1, minimum=1, maximum=6)
    freshness_window = min(dt.timedelta(hours=interval_hours, minutes=30), dt.timedelta(minutes=90))
    return now - state_time <= freshness_window


def _age_text(timestamp: float | None, *, now: dt.datetime) -> str:
    if timestamp is None:
        return ""
    updated = dt.datetime.fromtimestamp(timestamp, tz=TZ)
    delta = max(dt.timedelta(), now - updated)
    if delta < dt.timedelta(minutes=1):
        return "刚刚"
    minutes = int(delta.total_seconds() // 60)
    if minutes < 60:
        return f"{minutes} 分钟前 {updated.strftime('%H:%M')}"
    hours, remainder = divmod(minutes, 60)
    if hours < 24:
        return f"{hours} 小时 {remainder} 分钟前 {updated.strftime('%H:%M')}"
    days, hours = divmod(hours, 24)
    return f"{days} 天 {hours} 小时前 {updated.strftime('%m-%d %H:%M')}"


def _clamp_int(value: object, *, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))
