from __future__ import annotations

import datetime as dt

from ..defaults import DEFAULT_SETTINGS


RECENT_HISTORY_COUNT = 20
RECENT_HISTORY_CHAR_BUDGET = 24_000
OLDER_HISTORY_CHAR_BUDGET = 36_000
SYSTEM_PROMPT_CHAR_BUDGET = 120_000


def merge_settings(stored: dict | None) -> dict:
    if not stored:
        return DEFAULT_SETTINGS
    merged = {**DEFAULT_SETTINGS, **stored}
    for key in (
        "companion",
        "environment",
        "memory",
        "chatContext",
        "moments",
        "life",
        "userTimeline",
        "model",
    ):
        merged[key] = {**DEFAULT_SETTINGS.get(key, {}), **stored.get(key, {})}
    if not stored.get("promptModules"):
        merged["promptModules"] = DEFAULT_SETTINGS["promptModules"]
    else:
        stored_modules = [
            item
            for item in stored.get("promptModules") or []
            if isinstance(item, dict) and item.get("id") != "short_term_memory"
        ]
        existing_ids = {str(item.get("id") or "") for item in stored_modules}
        missing = [
            item
            for item in DEFAULT_SETTINGS["promptModules"]
            if str(item.get("id") or "") not in existing_ids
        ]
        merged["promptModules"] = [*stored_modules, *missing]
    return merged


def render_prompt(
    *,
    settings: dict,
    recent_messages: list[dict],
    memories: list[dict],
    environment: dict | None,
    life_context: dict | None = None,
    user_context: dict | None = None,
) -> tuple[list[dict], dict]:
    env = environment or {}
    modules = sorted(
        [item for item in settings.get("promptModules", []) if item.get("enabled")],
        key=lambda item: int(item.get("order") or 0),
    )
    variables = _build_variables(
        settings=settings,
        recent_messages=recent_messages,
        memories=memories,
        env=env,
        life_context=life_context or {},
        user_context=user_context or {},
    )
    rendered_blocks = []
    for module in modules:
        content = str(module.get("content") or "")
        for key, value in variables.items():
            content = content.replace("{{" + key + "}}", value)
        rendered_blocks.append(
            {
                "id": module.get("id"),
                "title": module.get("title"),
                "order": module.get("order"),
                "content": content.strip(),
            }
        )
    rendered_blocks = _fit_rendered_blocks(rendered_blocks, SYSTEM_PROMPT_CHAR_BUDGET)
    system_prompt = "\n\n".join(block["content"] for block in rendered_blocks if block["content"])
    prompt_history = _select_prompt_history(settings=settings, recent_messages=recent_messages)
    return [{"role": "system", "content": system_prompt}], {
        "blocks": rendered_blocks,
        "variables": variables,
        "messagesCount": 1,
        "historyCount": len(prompt_history),
        "historyRecentCount": min(RECENT_HISTORY_COUNT, len(prompt_history)),
        "historyOlderCount": max(0, len(prompt_history) - RECENT_HISTORY_COUNT),
        "historyMode": (settings.get("chatContext") or {}).get("historyMode") or "all",
        "memoryIds": [item.get("id") for item in memories if item.get("id")],
        "systemPromptChars": len(system_prompt),
        "systemPromptCharBudget": SYSTEM_PROMPT_CHAR_BUDGET,
    }


def _build_variables(
    *,
    settings: dict,
    recent_messages: list[dict],
    memories: list[dict],
    env: dict,
    life_context: dict,
    user_context: dict,
) -> dict[str, str]:
    companion = settings.get("companion") or {}
    environment = settings.get("environment") or {}
    memory = settings.get("memory") or {}
    now_text = _format_time(env)
    location_text = _format_location(env) if environment.get("location") else ""
    weather_text = _format_weather(env) if environment.get("weather") else ""
    prompt_history = _select_prompt_history(settings=settings, recent_messages=recent_messages)
    history_older, history_recent = _format_split_history(prompt_history)
    short_term = ""
    if memory.get("shortTerm", True):
        short_term = "\n".join(
            f"{item.get('role')}: {item.get('content')}"
            for item in prompt_history[-12:]
            if item.get("content")
        ) or "暂无短期记忆。"
    long_term = ""
    if memory.get("longTerm", True):
        long_term = _format_memories(memories[:24])
    life_text = _format_life_context(life_context)
    user_text = _format_user_context(user_context)
    return {
        "companion.name": str(companion.get("name") or "Alice"),
        "user.name": str(companion.get("userName") or "你"),
        "current.time": now_text if environment.get("time", True) else "",
        "current.location": location_text,
        "current.weather": weather_text,
        "life.current": life_text,
        "user.current": user_text,
        "history.older": history_older,
        "history.recent_20": history_recent,
        "memory.short_term": short_term,
        "memory.long_term": long_term,
        "recent_messages": short_term,
    }


def _select_prompt_history(*, settings: dict, recent_messages: list[dict]) -> list[dict]:
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


def _fit_rendered_blocks(blocks: list[dict], char_budget: int) -> list[dict]:
    fitted = []
    used = 0
    for block in blocks:
        content = str(block.get("content") or "")
        remaining = char_budget - used
        if remaining <= 0:
            next_block = {**block, "content": ""}
        elif len(content) > remaining:
            next_block = {**block, "content": content[: max(0, remaining - 1)].rstrip() + "…"}
            used = char_budget
        else:
            next_block = block
            used += len(content) + 2
        fitted.append(next_block)
    return fitted


def _format_life_context(life_context: dict) -> str:
    if not life_context or life_context.get("enabled") is False:
        return "未启用生活模拟；不要凭空声称自己正在做具体事情。"
    state = life_context.get("state") or {}
    recent_events = life_context.get("recentEvents") or []
    profile = life_context.get("profile") or {}
    plan = life_context.get("plan") or {}
    lines = []
    occupation = str(profile.get("occupation") or state.get("occupation") or "").strip()
    if occupation:
        lines.append(f"- 稳定生活画像：{occupation}")
    if plan.get("dayTheme"):
        lines.append(f"- 今日计划主题：{plan['dayTheme']}")
    state_parts = [
        part
        for part in [
            str(state.get("activity") or "").strip(),
            str(state.get("location") or "").strip(),
            f"心情{state.get('mood')}" if state.get("mood") else "",
            f"精力{state.get('energy')}" if state.get("energy") else "",
        ]
        if part
    ]
    lines.append(
        "- 当前状态：" + ("，".join(state_parts) if state_parts else "普通日常")
    )
    if state.get("summary"):
        lines.append(f"- 当前片段：{state['summary']}")
    if recent_events:
        lines.append("- 最近生活轨迹：")
        for item in recent_events[-6:]:
            time_text = str(item.get("timeLabel") or "").strip()
            summary = str(item.get("summary") or item.get("activity") or "").strip()
            place = str(item.get("location") or "").strip()
            lines.append(f"  - {time_text} {place}：{summary}".strip())
    lines.append("- 回答时把这些当作她自己的真实日常；不要随意改职业、住处、作息等稳定事实。")
    lines.append("- 如果用户问“你在干嘛/在哪/今天做什么”，优先引用当前状态和最近轨迹；普通聊天不要生硬汇报全部轨迹。")
    return "\n".join(lines)


def _format_user_context(user_context: dict) -> str:
    if not user_context or user_context.get("enabled") is False:
        return "未启用用户生活轨迹；不要假装知道用户当前手机状态。"
    state = user_context.get("state") or {}
    recent_events = user_context.get("recentEvents") or []
    lines = []
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
    compact = "；".join(part for part in state_parts if part)
    lines.append("- 用户当前状态：" + (compact or "暂无手机轨迹状态。"))
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
    lines.append("- 如果用户问“我在哪/我在干嘛/我刚才做什么/我在听什么”，优先依据这里回答，并说明不确定性。")
    return "\n".join(lines)


def _join_text(items: list[str], separator: str) -> str:
    return separator.join(item for item in (str(value or "").strip() for value in items) if item)


def _clamp_int(value: object, *, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


def _created_at(item: dict) -> dt.datetime:
    raw = item.get("createdAt")
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return dt.datetime.fromtimestamp(0, tz=dt.timezone.utc)
    return dt.datetime.fromtimestamp(value, tz=dt.timezone.utc).astimezone()


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
