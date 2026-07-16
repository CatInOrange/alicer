from __future__ import annotations

import datetime as dt

from ..defaults import DEFAULT_SETTINGS


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
    system_prompt = "\n\n".join(block["content"] for block in rendered_blocks if block["content"])
    prompt_history = _select_prompt_history(settings=settings, recent_messages=recent_messages)
    history = [
        {
            "role": "assistant" if item["role"] == "assistant" else "user",
            "content": item["content"],
        }
        for item in prompt_history
        if item.get("role") in {"user", "assistant"} and item.get("content")
    ]
    return [{"role": "system", "content": system_prompt}, *history], {
        "blocks": rendered_blocks,
        "variables": variables,
        "messagesCount": len(history) + 1,
        "historyCount": len(history),
        "historyMode": (settings.get("chatContext") or {}).get("historyMode") or "all",
        "memoryIds": [item.get("id") for item in memories if item.get("id")],
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
    short_term = ""
    if memory.get("shortTerm", True):
        prompt_history = _select_prompt_history(settings=settings, recent_messages=recent_messages)
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
    state_parts = [
        str(state.get("activity") or "").strip(),
        f"地点线索：{state.get('locationLabel')}" if state.get("locationLabel") else "",
        f"音乐：{state.get('music')}" if state.get("music") else "",
        f"运动：{state.get('motion')}" if state.get("motion") else "",
        f"耳机：{state.get('headset')}" if state.get("headset") else "",
        f"注意状态：{state.get('attentionState')}" if state.get("attentionState") else "",
    ]
    compact = "；".join(part for part in state_parts if part)
    lines.append("- 用户当前状态：" + (compact or "暂无手机轨迹状态。"))
    if state.get("summary"):
        lines.append(f"- 用户近期摘要：{state['summary']}")
    if recent_events:
        lines.append("- 用户最近轨迹：")
        for item in recent_events[-8:]:
            time_text = str(item.get("timeLabel") or "").strip()
            summary = str(item.get("summary") or item.get("title") or "").strip()
            lines.append(f"  - {time_text}：{summary}".strip())
    lines.append("- 这是用户授权的手机上下文，只能自然地用于关心和判断打扰程度。")
    lines.append("- 不要暴露精确坐标、不要表现得像监控；除非用户询问，否则不要逐条汇报。")
    lines.append("- 如果用户问“我在哪/我在干嘛/我刚才做什么/我在听什么”，优先依据这里回答，并说明不确定性。")
    return "\n".join(lines)


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
