from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass
from zoneinfo import ZoneInfo


TZ = ZoneInfo("Asia/Shanghai")
J2000 = dt.datetime(2000, 1, 1, 12, tzinfo=dt.timezone.utc)

MAJOR_ASPECTS = {
    "conjunction": {"angle": 0.0, "label": "合相", "polarity": "intense", "baseScore": 1.0},
    "sextile": {"angle": 60.0, "label": "六合", "polarity": "supportive", "baseScore": 1.0},
    "square": {"angle": 90.0, "label": "刑相", "polarity": "challenging", "baseScore": -1.0},
    "trine": {"angle": 120.0, "label": "拱相", "polarity": "supportive", "baseScore": 1.4},
    "opposition": {"angle": 180.0, "label": "冲相", "polarity": "challenging", "baseScore": -1.3},
}

PLANETS = {
    "sun": {"label": "太阳", "period": 365.256, "j2000": 280.466, "weight": 1.0},
    "moon": {"label": "月亮", "period": 27.322, "j2000": 218.316, "weight": 0.75},
    "mercury": {"label": "水星", "period": 87.969, "j2000": 252.251, "weight": 0.85},
    "venus": {"label": "金星", "period": 224.701, "j2000": 181.980, "weight": 0.95},
    "mars": {"label": "火星", "period": 686.980, "j2000": 355.433, "weight": 1.0},
    "jupiter": {"label": "木星", "period": 4332.589, "j2000": 34.351, "weight": 0.8},
    "saturn": {"label": "土星", "period": 10759.22, "j2000": 50.077, "weight": 0.9},
}

TRANSIT_PLANETS = ("sun", "moon", "mercury", "venus", "mars", "jupiter", "saturn")
NATAL_PLANETS = ("sun", "mercury", "venus", "mars", "jupiter", "saturn")

PLANET_THEMES = {
    "sun": {
        "core": "自我状态、精力、主线表达",
        "support": "更容易确认方向和主动表达",
        "challenge": "自我感受更敏感，容易急着证明自己",
    },
    "moon": {
        "core": "情绪、安全感、本能反应",
        "support": "情绪流动较顺，适合被理解和安抚",
        "challenge": "情绪起伏更快，容易把小事放大",
    },
    "mercury": {
        "core": "沟通、思考、消息和理解",
        "support": "更适合说明想法、整理信息和轻松沟通",
        "challenge": "沟通容易变急，消息和措辞需要多确认",
    },
    "venus": {
        "core": "感情、亲密、愉悦、审美和社交",
        "support": "亲密表达更柔和，适合修复关系和表达喜欢",
        "challenge": "关系里的期待更敏感，容易用试探代替直说",
    },
    "mars": {
        "core": "行动、冲突、欲望、竞争和执行",
        "support": "行动力更足，适合推进明确任务",
        "challenge": "火气更容易冒头，容易硬碰硬或冲动回应",
    },
    "jupiter": {
        "core": "机会、扩张、信心、贵人感和乐观",
        "support": "更容易看见机会，适合展示和推进",
        "challenge": "容易过度乐观，承诺和花费要收一收",
    },
    "saturn": {
        "core": "压力、责任、边界、延迟和现实感",
        "support": "适合整理边界、承担责任和稳步收尾",
        "challenge": "压力感更强，进展可能慢一点，需要耐心",
    },
}

TARGET_TOPICS = {
    "sun": ("state", "work", "emotion"),
    "mercury": ("communication", "work"),
    "venus": ("love", "social", "emotion"),
    "mars": ("action", "conflict", "work"),
    "jupiter": ("opportunity", "work", "mood"),
    "saturn": ("responsibility", "work", "boundary"),
}

TOPIC_LABELS = {
    "state": "状态",
    "work": "工作",
    "emotion": "情绪",
    "communication": "沟通",
    "love": "感情",
    "social": "社交",
    "action": "行动",
    "conflict": "冲突",
    "opportunity": "机会",
    "mood": "心态",
    "responsibility": "责任",
    "boundary": "边界",
}

SOURCE_REFS = {
    "major_aspects": {
        "title": "Astrodienst: The Aspects",
        "url": "https://www.astro.com/astrology/in_aspect_e.htm",
    },
    "planet_keywords": {
        "title": "Cafe Astrology: Planets in Astrology",
        "url": "https://cafeastrology.com/articles/planetsinastrology.html",
    },
    "transits": {
        "title": "Cafe Astrology: Transits",
        "url": "https://cafeastrology.com/transits.html",
    },
    "method_note": {
        "title": "Alicer built-in rulebook",
        "url": "internal://fortune/rulebook/v1",
    },
}


@dataclass(frozen=True)
class FortuneSettings:
    enabled: bool
    birthday: str
    style: str
    include_in_context: bool
    max_proactive_mentions_per_day: int
    orb_degrees: float


def build_daily_fortune_context(settings: dict, *, date: dt.date | None = None) -> dict:
    config = fortune_settings(settings)
    target_date = date or dt.datetime.now(TZ).date()
    if not config.enabled:
        return {"enabled": False, "date": target_date.isoformat(), "reason": "fortune disabled"}
    birthday = _parse_date(config.birthday)
    if birthday is None:
        return {
            "enabled": True,
            "configured": False,
            "date": target_date.isoformat(),
            "reason": "birthday is required",
            "prompt": "",
        }
    natal = {planet: _planet_longitude(planet, _local_noon(birthday)) for planet in NATAL_PLANETS}
    transit = {planet: _planet_longitude(planet, _local_noon(target_date)) for planet in TRANSIT_PLANETS}
    signals = _build_signals(natal=natal, transit=transit, max_orb=config.orb_degrees)
    summary = _summarize(signals)
    prompt = _format_prompt(summary=summary, signals=signals, settings=config, date=target_date)
    return {
        "enabled": True,
        "configured": True,
        "date": target_date.isoformat(),
        "birthday": birthday.isoformat(),
        "method": "western_transit_major_aspects_builtin_ephemeris",
        "precision": "low_to_medium_without_birth_time",
        "style": config.style,
        "natal": {planet: round(value, 3) for planet, value in natal.items()},
        "transit": {planet: round(value, 3) for planet, value in transit.items()},
        "signals": signals[:12],
        "summary": summary,
        "prompt": prompt,
        "sourceRefs": SOURCE_REFS,
        "guardrails": [
            "只作为娱乐和自我观察，不用于医疗、投资和重大人生决策。",
            "LLM 只能转述结构化结果，不能新增未命中的吉凶判断。",
            "主动提及时要轻，不要说成绝对预测。",
        ],
    }


def fortune_settings(settings: dict | None) -> FortuneSettings:
    raw = ((settings or {}).get("fortune") or {})
    return FortuneSettings(
        enabled=raw.get("enabled") is True,
        birthday=str(raw.get("birthday") or "").strip(),
        style=_normalize_style(str(raw.get("style") or "companion")),
        include_in_context=raw.get("includeInContext") is not False,
        max_proactive_mentions_per_day=_clamp_int(raw.get("maxProactiveMentionsPerDay"), 1, 0, 3),
        orb_degrees=_clamp_float(raw.get("orbDegrees"), 3.0, 1.0, 6.0),
    )


def _build_signals(*, natal: dict[str, float], transit: dict[str, float], max_orb: float) -> list[dict]:
    signals = []
    for transit_planet in TRANSIT_PLANETS:
        for natal_planet in NATAL_PLANETS:
            found = _major_aspect(transit[transit_planet], natal[natal_planet], max_orb=max_orb)
            if not found:
                continue
            aspect_id, orb = found
            aspect = MAJOR_ASPECTS[aspect_id]
            transit_info = PLANET_THEMES[transit_planet]
            natal_info = PLANET_THEMES[natal_planet]
            supportive = aspect["polarity"] == "supportive" or (
                aspect_id == "conjunction" and transit_planet in {"venus", "jupiter"}
            )
            challenging = aspect["polarity"] == "challenging" or (
                aspect_id == "conjunction" and transit_planet in {"mars", "saturn"}
            )
            base = float(aspect["baseScore"])
            if aspect_id == "conjunction":
                if supportive:
                    base = 1.2
                elif challenging:
                    base = -1.2
                else:
                    base = 0.4
            strength = max(0.25, 1.0 - (orb / max(max_orb, 0.1)) * 0.55)
            weight = float(PLANETS[transit_planet]["weight"]) * float(PLANETS[natal_planet]["weight"])
            score = round(base * strength * weight, 2)
            polarity = "supportive" if score > 0.25 else "challenging" if score < -0.25 else "neutral"
            topics = list(dict.fromkeys([*TARGET_TOPICS.get(natal_planet, ()), *_transit_topics(transit_planet)]))[:4]
            signals.append(
                {
                    "id": f"transit_{transit_planet}_{aspect_id}_natal_{natal_planet}",
                    "transitPlanet": transit_planet,
                    "transitPlanetLabel": PLANETS[transit_planet]["label"],
                    "natalPlanet": natal_planet,
                    "natalPlanetLabel": PLANETS[natal_planet]["label"],
                    "aspect": aspect_id,
                    "aspectLabel": aspect["label"],
                    "orb": round(orb, 2),
                    "score": score,
                    "polarity": polarity,
                    "topics": topics,
                    "meaning": _meaning(
                        transit_planet=transit_planet,
                        natal_planet=natal_planet,
                        aspect_id=aspect_id,
                        polarity=polarity,
                        transit_info=transit_info,
                        natal_info=natal_info,
                    ),
                    "advice": _advice(transit_planet, natal_planet, polarity),
                    "sourceRefs": ["major_aspects", "planet_keywords", "transits", "method_note"],
                }
            )
    signals.sort(key=lambda item: (abs(float(item["score"])), -float(item["orb"])), reverse=True)
    return signals


def _summarize(signals: list[dict]) -> dict:
    if not signals:
        return {
            "overall": "neutral",
            "score": 0,
            "theme": "平稳观察",
            "headline": "今天没有命中特别强的行运相位，适合按原计划慢慢推进。",
            "love": "感情上不需要刻意制造戏剧感，舒服一点就好。",
            "work": "工作上按既有节奏推进，别为了找感觉临时开太多新坑。",
            "emotion": "情绪整体偏平，适合照顾身体和节奏。",
            "avoid": ["把普通波动解读成重大预兆"],
        }
    score = round(sum(float(item["score"]) for item in signals[:6]), 2)
    topic_scores: dict[str, float] = {}
    for item in signals[:8]:
        for topic in item.get("topics") or []:
            topic_scores[topic] = topic_scores.get(topic, 0.0) + float(item["score"])
    main_topic = max(topic_scores.items(), key=lambda item: abs(item[1]))[0] if topic_scores else "state"
    overall = "supportive" if score >= 1.2 else "challenging" if score <= -1.2 else "mixed"
    strongest = _representative_signal(signals, overall)
    theme = _theme(main_topic, overall)
    return {
        "overall": overall,
        "score": score,
        "mainTopic": main_topic,
        "theme": theme,
        "headline": _headline(overall, strongest),
        "love": _topic_advice("love", signals, overall),
        "work": _topic_advice("work", signals, overall),
        "emotion": _topic_advice("emotion", signals, overall),
        "avoid": _avoid_list(signals, overall),
        "evidence": [
            (
                f"{item['transitPlanetLabel']}{item['aspectLabel']}本命{item['natalPlanetLabel']}"
                f"（orb {item['orb']}°）"
            )
            for item in signals[:4]
        ],
    }


def _format_prompt(*, summary: dict, signals: list[dict], settings: FortuneSettings, date: dt.date) -> str:
    if not settings.include_in_context:
        return ""
    if not signals:
        signal_text = "没有命中特别强的主要相位。"
    else:
        signal_text = "；".join(
            f"{item['transitPlanetLabel']}{item['aspectLabel']}本命{item['natalPlanetLabel']} orb {item['orb']}°"
            for item in signals[:3]
        )
    return (
        f"今日个人化运势（{date.isoformat()}，西洋占星行运，娱乐和自我观察）："
        f"总体 {summary.get('overall')}，主题“{summary.get('theme')}”。"
        f"{summary.get('headline')} "
        f"感情：{summary.get('love')} 工作：{summary.get('work')} 情绪：{summary.get('emotion')} "
        f"避免：{'、'.join(summary.get('avoid') or [])}。"
        f"依据：{signal_text}。"
        f"伴侣表达规则：今天最多自然主动提 {settings.max_proactive_mentions_per_day} 次；"
        "不要说成命运预测，不要用于医疗、投资、重大决策；如果用户主动问运势，可以展开。"
    )


def _planet_longitude(planet: str, when: dt.datetime) -> float:
    days = (when.astimezone(dt.timezone.utc) - J2000).total_seconds() / 86400.0
    if planet == "sun":
        return _sun_longitude(days)
    info = PLANETS[planet]
    mean = float(info["j2000"]) + 360.0 * days / float(info["period"])
    return mean % 360.0


def _sun_longitude(days_since_j2000: float) -> float:
    mean_long = (280.46646 + 0.98564736 * days_since_j2000) % 360.0
    mean_anomaly = math.radians((357.52911 + 0.98560028 * days_since_j2000) % 360.0)
    equation = (
        1.914602 * math.sin(mean_anomaly)
        + 0.019993 * math.sin(2 * mean_anomaly)
        + 0.000289 * math.sin(3 * mean_anomaly)
    )
    return (mean_long + equation) % 360.0


def _major_aspect(a: float, b: float, *, max_orb: float) -> tuple[str, float] | None:
    delta = abs((a - b + 180.0) % 360.0 - 180.0)
    best: tuple[str, float] | None = None
    for aspect_id, info in MAJOR_ASPECTS.items():
        orb = abs(delta - float(info["angle"]))
        if orb <= max_orb and (best is None or orb < best[1]):
            best = (aspect_id, orb)
    return best


def _meaning(
    *,
    transit_planet: str,
    natal_planet: str,
    aspect_id: str,
    polarity: str,
    transit_info: dict,
    natal_info: dict,
) -> str:
    aspect_label = MAJOR_ASPECTS[aspect_id]["label"]
    if polarity == "supportive":
        return (
            f"今日{PLANETS[transit_planet]['label']}的{transit_info['core']}，"
            f"用比较顺的方式触碰你的{natal_info['core']}；{transit_info['support']}。"
        )
    if polarity == "challenging":
        return (
            f"今日{PLANETS[transit_planet]['label']}的{transit_info['core']}，"
            f"通过{aspect_label}给你的{natal_info['core']}带来摩擦；{transit_info['challenge']}。"
        )
    return (
        f"今日{PLANETS[transit_planet]['label']}和本命{PLANETS[natal_planet]['label']}形成{aspect_label}，"
        "主题会被放大，但吉凶取决于你怎么处理。"
    )


def _advice(transit_planet: str, natal_planet: str, polarity: str) -> str:
    if polarity == "supportive":
        if transit_planet == "venus" or natal_planet == "venus":
            return "适合柔和表达喜欢、修复气氛，别把好感藏太深。"
        if transit_planet == "jupiter":
            return "适合展示、申请、推进计划，但承诺仍要留余地。"
        return "适合顺势推进，把想法说清楚，别浪费今天的助力。"
    if polarity == "challenging":
        if transit_planet == "mars" or natal_planet == "mars":
            return "先把火气放慢半拍，避免用质问或硬碰硬解决关系问题。"
        if transit_planet == "saturn":
            return "把压力拆小，先做确定的小步骤，不急着求即时结果。"
        if transit_planet == "mercury" or natal_planet == "mercury":
            return "重要沟通多确认一次，别靠猜，也别深夜咬文嚼字。"
        return "先稳住节奏，别把一时感受说成最后决定。"
    return "把它当作今日提醒即可，保持观察，不需要过度解读。"


def _topic_advice(topic: str, signals: list[dict], overall: str) -> str:
    topic_hits = [item for item in signals[:8] if topic in (item.get("topics") or [])]
    if topic_hits:
        return str(topic_hits[0].get("advice") or "")
    fallback = {
        "love": {
            "supportive": "可以主动表达一点亲近，轻松一点会更顺。",
            "challenging": "别用试探代替直说，也别急着摊牌。",
            "mixed": "适合温柔沟通，但别把话说太满。",
        },
        "work": {
            "supportive": "适合推进明确任务和展示成果。",
            "challenging": "适合收尾和拆解压力，不适合硬开新战线。",
            "mixed": "先做优先级最高的小任务，别被情绪带节奏。",
        },
        "emotion": {
            "supportive": "情绪有回暖空间，适合给自己一点好东西。",
            "challenging": "火气或压力容易冒头，先慢一拍再回应。",
            "mixed": "情绪有起伏，适合边做事边观察自己。",
        },
    }
    return fallback.get(topic, {}).get(overall, fallback.get(topic, {}).get("mixed", "保持观察。"))


def _avoid_list(signals: list[dict], overall: str) -> list[str]:
    avoid = []
    ids = {item.get("transitPlanet") for item in signals[:6]} | {item.get("natalPlanet") for item in signals[:6]}
    if "mars" in ids:
        avoid.extend(["冲动回复", "硬碰硬"])
    if "mercury" in ids:
        avoid.append("靠猜测沟通")
    if "venus" in ids:
        avoid.append("用试探代替直说")
    if "saturn" in ids:
        avoid.append("把延迟当成失败")
    if not avoid:
        avoid.append("把普通波动解读成重大预兆")
    if overall == "supportive":
        avoid.append("过度乐观承诺")
    return list(dict.fromkeys(avoid))[:4]


def _theme(topic: str, overall: str) -> str:
    label = TOPIC_LABELS.get(topic, "状态")
    suffix = {"supportive": "顺势推进", "challenging": "先稳住", "mixed": "有起伏"}[overall]
    return f"{label}{suffix}"


def _headline(overall: str, strongest: dict) -> str:
    planet = strongest.get("transitPlanetLabel")
    target = strongest.get("natalPlanetLabel")
    aspect = strongest.get("aspectLabel")
    if overall == "supportive":
        return f"今天{planet}{aspect}本命{target}带来一点顺风，可以把关系和计划往前轻轻推。"
    if overall == "challenging":
        return f"今天{planet}{aspect}本命{target}让节奏偏紧，先别急着赢，稳住会更好。"
    return f"今天{planet}{aspect}本命{target}让主题被放大，有助力也有摩擦，适合边走边调。"


def _representative_signal(signals: list[dict], overall: str) -> dict:
    if overall == "challenging":
        for item in signals:
            if item.get("polarity") == "challenging":
                return item
    if overall == "supportive":
        for item in signals:
            if item.get("polarity") == "supportive":
                return item
    return signals[0]


def _transit_topics(planet: str) -> tuple[str, ...]:
    return {
        "sun": ("state",),
        "moon": ("emotion",),
        "mercury": ("communication",),
        "venus": ("love", "social"),
        "mars": ("action", "conflict"),
        "jupiter": ("opportunity",),
        "saturn": ("responsibility", "boundary"),
    }.get(planet, ("state",))


def _parse_date(value: str) -> dt.date | None:
    text = value.strip()
    if not text:
        return None
    try:
        return dt.date.fromisoformat(text)
    except ValueError:
        return None


def _local_noon(day: dt.date) -> dt.datetime:
    return dt.datetime(day.year, day.month, day.day, 12, tzinfo=TZ)


def _normalize_style(value: str) -> str:
    return value if value in {"companion", "classic", "quiet"} else "companion"


def _clamp_int(value: object, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


def _clamp_float(value: object, default: float, minimum: float, maximum: float) -> float:
    try:
        parsed = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))
