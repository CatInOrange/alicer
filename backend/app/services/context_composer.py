from __future__ import annotations

import datetime as dt


RECENT_HISTORY_COUNT = 20
RECENT_HISTORY_CHAR_BUDGET = 24_000
OLDER_HISTORY_CHAR_BUDGET = 36_000


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

    world_current = _format_world_current(world_context=world_context, life_context=life_context)
    world_commitments = _format_world_commitments(world_context)
    world_trajectory = _format_world_trajectory(life_context)
    world_user = _format_user_context(user_context)
    world_photos = _format_chat_photo_context(photo_context)
    world_memory = long_term or "暂无长期记忆。"
    world_guardrails = _format_world_guardrails(world_context)
    world_legacy = _format_world_context(world_context)
    life_text = _format_life_context(life_context)

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
        "world.commitments": world_commitments,
        "world.trajectory": world_trajectory,
        "world.user": world_user,
        "world.photos": world_photos,
        "world.memory": world_memory,
        "world.guardrails": world_guardrails,
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
                "current": world_current,
                "commitments": world_commitments,
                "trajectory": world_trajectory,
                "user": world_user,
                "photos": world_photos,
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
        },
        "promptHistory": prompt_history,
    }


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


def _format_world_current(*, world_context: dict, life_context: dict) -> str:
    lines = []
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
    if compact:
        lines.append(f"生活模拟当前状态：{compact}")
    if state.get("summary"):
        lines.append(f"当前片段：{state['summary']}")
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
    lines.append(f"- 伴侣主动发照片：{'允许但必须非常克制' if allow_proactive and remaining > 0 else '当前不允许'}。")
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


def _format_world_guardrails(world_context: dict) -> str:
    facts = world_context.get("activeFacts") or []
    lines = [
        "一致性守则：",
        "- 事实账本、明确承诺、生活模拟当前状态优先于即兴发挥。",
        "- 不要把用户的行程改写成 Alicer 自己的经历。",
        "- 不要临时改变职业、住处、长期习惯；除非事实账本明确更新。",
        "- 如果已有计划/承诺，不要安排冲突地点、时间或行动。",
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
    return dt.datetime.fromtimestamp(value, tz=dt.timezone.utc).astimezone()


def _clamp_int(value: object, *, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))

