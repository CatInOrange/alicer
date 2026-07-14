from __future__ import annotations

import httpx


WEATHER_CODES = {
    0: "晴",
    1: "大部晴朗",
    2: "局部多云",
    3: "阴",
    45: "雾",
    48: "雾凇",
    51: "小毛毛雨",
    53: "毛毛雨",
    55: "较强毛毛雨",
    61: "小雨",
    63: "雨",
    65: "大雨",
    80: "阵雨",
    95: "雷雨",
}


async def enrich_weather(environment: dict | None) -> dict:
    env = dict(environment or {})
    if env.get("weather") or env.get("latitude") is None or env.get("longitude") is None:
        return env
    try:
        params = {
            "latitude": env["latitude"],
            "longitude": env["longitude"],
            "current": "temperature_2m,weather_code",
            "timezone": "auto",
        }
        async with httpx.AsyncClient(timeout=8) as client:
            response = await client.get("https://api.open-meteo.com/v1/forecast", params=params)
            response.raise_for_status()
            current = response.json().get("current") or {}
        code = int(current.get("weather_code") or 0)
        env["weather"] = {
            "summary": WEATHER_CODES.get(code, f"天气代码 {code}"),
            "temperature": current.get("temperature_2m"),
        }
    except Exception:
        env["weather"] = {"summary": "天气暂时获取失败"}
    return env
