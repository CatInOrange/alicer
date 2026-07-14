from __future__ import annotations

import datetime as dt

from ..defaults import DEFAULT_SETTINGS


def merge_settings(stored: dict | None) -> dict:
    if not stored:
        return DEFAULT_SETTINGS
    merged = {**DEFAULT_SETTINGS, **stored}
    for key in ("companion", "environment", "memory", "model"):
        merged[key] = {**DEFAULT_SETTINGS.get(key, {}), **stored.get(key, {})}
    if not stored.get("promptModules"):
        merged["promptModules"] = DEFAULT_SETTINGS["promptModules"]
    return merged


def render_prompt(
    *,
    settings: dict,
    recent_messages: list[dict],
    memories: list[dict],
    environment: dict | None,
) -> tuple[list[dict], dict]:
    env = environment or {}
    modules = sorted(
        [item for item in settings.get("promptModules", []) if item.get("enabled")],
        key=lambda item: int(item.get("order") or 0),
    )
    variables = _build_variables(settings=settings, recent_messages=recent_messages, memories=memories, env=env)
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
    history = [
        {
            "role": "assistant" if item["role"] == "assistant" else "user",
            "content": item["content"],
        }
        for item in recent_messages[-24:]
        if item.get("role") in {"user", "assistant"} and item.get("content")
    ]
    return [{"role": "system", "content": system_prompt}, *history], {
        "blocks": rendered_blocks,
        "variables": variables,
        "messagesCount": len(history) + 1,
    }


def _build_variables(*, settings: dict, recent_messages: list[dict], memories: list[dict], env: dict) -> dict[str, str]:
    companion = settings.get("companion") or {}
    environment = settings.get("environment") or {}
    memory = settings.get("memory") or {}
    now_text = _format_time(env)
    location_text = _format_location(env) if environment.get("location") else ""
    weather_text = _format_weather(env) if environment.get("weather") else ""
    short_term = ""
    if memory.get("shortTerm", True):
        short_term = "\n".join(
            f"{item.get('role')}: {item.get('content')}"
            for item in recent_messages[-8:]
            if item.get("content")
        ) or "暂无短期记忆。"
    long_term = ""
    if memory.get("longTerm", True):
        long_term = "\n".join(f"- {item['content']}" for item in memories[:20]) or "暂无长期记忆。"
    return {
        "companion.name": str(companion.get("name") or "Alice"),
        "user.name": str(companion.get("userName") or "你"),
        "current.time": now_text if environment.get("time", True) else "",
        "current.location": location_text,
        "current.weather": weather_text,
        "memory.short_term": short_term,
        "memory.long_term": long_term,
        "recent_messages": short_term,
    }


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
