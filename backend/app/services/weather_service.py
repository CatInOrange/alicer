from __future__ import annotations

import httpx

from ..config import get_settings


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
    if env.get("latitude") is None or env.get("longitude") is None:
        return env
    await _enrich_location_name(env)
    if env.get("weather"):
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


async def _enrich_location_name(env: dict) -> None:
    if str(env.get("locationName") or "").strip():
        return
    settings = get_settings()
    if not settings.amap_key:
        return
    try:
        params = {
            "key": settings.amap_key,
            "location": f"{env['longitude']},{env['latitude']}",
            "extensions": "base",
            "roadlevel": 0,
        }
        async with httpx.AsyncClient(timeout=6) as client:
            response = await client.get("https://restapi.amap.com/v3/geocode/regeo", params=params)
            response.raise_for_status()
            data = response.json()
        if str(data.get("status")) != "1":
            return
        regeocode = data.get("regeocode") or {}
        address = str(regeocode.get("formatted_address") or "").strip()
        component = regeocode.get("addressComponent") or {}
        city = component.get("city")
        if isinstance(city, list):
            city = ""
        district = str(component.get("district") or "").strip()
        township = str(component.get("township") or "").strip()
        short_parts = [str(item).strip() for item in (city, district, township) if str(item).strip()]
        env["locationName"] = " · ".join(short_parts) or address
        if address:
            env["locationAddress"] = address
    except Exception:
        return
