from __future__ import annotations

import asyncio
import datetime as dt
import json
import uuid
from zoneinfo import ZoneInfo

from ..db import Database
from .llm_service import GROK_REFERENCE_IMAGE_URL, LlmService


TZ = ZoneInfo("Asia/Shanghai")
PHOTO_TASKS: set[asyncio.Task] = set()


def chat_photo_settings(settings: dict) -> dict:
    raw = settings.get("chatPhotos") or {}
    return {
        "enabled": raw.get("enabled") is not False,
        "allowRequested": raw.get("allowRequested") is not False,
        "allowProactive": raw.get("allowProactive") is not False,
        "dailySuccessfulLimit": _clamp_int(raw.get("dailySuccessfulLimit"), default=1, minimum=0, maximum=5),
        "minHoursBetweenPhotos": _clamp_int(raw.get("minHoursBetweenPhotos"), default=12, minimum=0, maximum=72),
    }


def build_chat_photo_context(db: Database, settings: dict) -> dict:
    config = chat_photo_settings(settings)
    day_start = _today_start_timestamp()
    sent_today = db.count_sent_chat_photos_since(day_start)
    active = _active_task(db)
    latest = db.latest_sent_chat_photo()
    remaining = max(0, int(config["dailySuccessfulLimit"]) - sent_today)
    return {
        "enabled": config["enabled"],
        "allowRequested": config["allowRequested"],
        "allowProactive": config["allowProactive"],
        "dailySuccessfulLimit": config["dailySuccessfulLimit"],
        "minHoursBetweenPhotos": config["minHoursBetweenPhotos"],
        "sentToday": sent_today,
        "remainingToday": remaining,
        "activeTask": active,
        "latestSent": latest,
    }


def schedule_chat_photo_decision(
    db: Database,
    llm: LlmService,
    *,
    settings: dict,
    user_message: dict,
    assistant_message: dict,
    recent_messages: list[dict],
    life_context: dict,
    user_context: dict,
) -> None:
    task = asyncio.create_task(
        maybe_create_chat_photo_task(
            db,
            llm,
            settings=settings,
            user_message=user_message,
            assistant_message=assistant_message,
            recent_messages=recent_messages,
            life_context=life_context,
            user_context=user_context,
        )
    )
    PHOTO_TASKS.add(task)
    task.add_done_callback(PHOTO_TASKS.discard)


async def maybe_create_chat_photo_task(
    db: Database,
    llm: LlmService,
    *,
    settings: dict,
    user_message: dict,
    assistant_message: dict,
    recent_messages: list[dict],
    life_context: dict,
    user_context: dict,
) -> dict | None:
    config = chat_photo_settings(settings)
    if not config["enabled"] or not getattr(llm.settings, "image_api_key", ""):
        return None
    guard = _quota_guard(db, config)
    if not guard["allowed"]:
        return None
    decision = await _photo_director_decision(
        llm,
        settings=settings,
        config=config,
        user_message=user_message,
        assistant_message=assistant_message,
        recent_messages=recent_messages,
        life_context=life_context,
        user_context=user_context,
        quota=guard,
    )
    if decision.get("action") != "send_companion_photo":
        return None
    source = str(decision.get("source") or "requested").strip()
    if source == "proactive" and not config["allowProactive"]:
        return None
    if source != "proactive" and not config["allowRequested"]:
        return None
    guard = _quota_guard(db, config)
    if not guard["allowed"]:
        return None
    companion = str(((settings.get("companion") or {}).get("name") or "Alice")).strip() or "Alice"
    user_name = str(((settings.get("companion") or {}).get("userName") or "用户")).strip() or "用户"
    image_prompt = _build_image_prompt(settings, decision, companion=companion, user_name=user_name)
    caption = _clean_caption(str(decision.get("caption_hint") or "刚刚那张拍好了。"))
    task = db.create_chat_photo_task(
        task_id=f"photo_{uuid.uuid4().hex}",
        source="proactive" if source == "proactive" else "requested",
        requested_by_message_id=str(user_message.get("id") or ""),
        assistant_text_message_id=str(assistant_message.get("id") or ""),
        prompt=decision,
        image_prompt=image_prompt,
        caption=caption,
        date_key=_date_key(),
        metadata={"quota": guard},
    )
    await _run_chat_photo_task(db, llm, settings=settings, task=task)
    return task


async def _run_chat_photo_task(db: Database, llm: LlmService, *, settings: dict, task: dict) -> None:
    task_id = str(task.get("id") or "")
    if not task_id:
        return
    db.update_chat_photo_task(task_id, status="generating", mark_started=True)
    try:
        moments = settings.get("moments") or {}
        reference_image_url = str(moments.get("referenceImageUrl") or "").strip() or GROK_REFERENCE_IMAGE_URL
        image = await llm.generate_image(
            prompt=str(task.get("imagePrompt") or ""),
            bucket="chat",
            reference_image_url=reference_image_url,
        )
        image_url = str(image.get("imageUrl") or "")
        if not image_url:
            db.update_chat_photo_task(
                task_id,
                status="failed",
                metadata={"imageProvider": image.get("provider") or {}, "error": "empty image url"},
            )
            return
        db.update_chat_photo_task(
            task_id,
            status="generated",
            image_url=image_url,
            metadata={"imageProvider": image.get("provider") or {}},
            mark_generated=True,
        )
        message_id = f"msg_{uuid.uuid4().hex}"
        caption = _clean_caption(str(task.get("caption") or "刚刚那张拍好了。"))
        message = db.add_message(
            message_id=message_id,
            role="assistant",
            content=caption,
            metadata={
                "kind": "chat_photo",
                "imageUrl": image_url,
                "imagePrompt": task.get("imagePrompt") or "",
                "chatPhotoTaskId": task_id,
                "photoSource": task.get("source") or "requested",
            },
        )
        db.update_chat_photo_task(
            task_id,
            status="sent",
            photo_message_id=message_id,
            image_url=image_url,
            caption=caption,
            mark_sent=True,
            metadata={"photoMessage": {"id": message.get("id"), "createdAt": message.get("createdAt")}},
        )
    except Exception as exc:  # noqa: BLE001
        db.update_chat_photo_task(task_id, status="failed", metadata={"error": str(exc)[:500]})


async def _photo_director_decision(
    llm: LlmService,
    *,
    settings: dict,
    config: dict,
    user_message: dict,
    assistant_message: dict,
    recent_messages: list[dict],
    life_context: dict,
    user_context: dict,
    quota: dict,
) -> dict:
    companion = str(((settings.get("companion") or {}).get("name") or "Alice")).strip() or "Alice"
    user_name = str(((settings.get("companion") or {}).get("userName") or "用户")).strip() or "用户"
    history = "\n".join(
        f"- {item.get('role')}: {str(item.get('content') or '')[:240]}"
        for item in recent_messages[-20:]
        if item.get("content")
    )
    prompt = [
        {
            "role": "system",
            "content": (
                "你是聊天照片导演，不负责聊天正文，只决定是否创建一张伴侣照片任务。"
                "把 request_companion_photo 当作可调用工具，但你必须只输出 JSON，不要输出解释。"
                "照片很贵，生成前必须克制；一旦决定生成，后端会尽量发出，所以不要随便创建。"
                "用户明确要求自拍/照片/看看你/穿某件衣服拍给我时，可以创建 requested。"
                "用户没有明确要求时，只有氛围非常自然、当天额度充足、且主动发照片会显得像真人分享时，才创建 proactive。"
                "不要因为普通寒暄、普通关心、普通问候就发照片。"
                "如果额度不足、有活跃照片任务、场景不适合、用户只是在聊别的话题，输出 none。"
                "照片必须是伴侣自己的自然自拍或生活照，不要包含用户，不要声称已经发送，不要暴露精确地址。"
                "输出格式："
                '{"action":"none"} 或 '
                '{"action":"send_companion_photo","source":"requested|proactive","reason":"...","scene":"...",'
                '"outfit":"...","pose":"...","mood":"...","caption_hint":"..."}'
            ),
        },
        {
            "role": "user",
            "content": (
                f"伴侣名：{companion}\n用户称呼：{user_name}\n"
                f"配置：允许用户请求={config['allowRequested']}，允许主动={config['allowProactive']}，"
                f"每日成功发送上限={config['dailySuccessfulLimit']}，最小间隔小时={config['minHoursBetweenPhotos']}\n"
                f"当前额度：{json.dumps(quota, ensure_ascii=False)}\n"
                f"伴侣生活状态：{json.dumps(life_context.get('state') or {}, ensure_ascii=False)[:1200]}\n"
                f"用户现实状态：{json.dumps(user_context.get('state') or {}, ensure_ascii=False)[:1200]}\n"
                f"最近聊天：\n{history or '暂无'}\n\n"
                f"用户最新消息：{user_message.get('content') or ''}\n"
                f"伴侣刚刚回复：{assistant_message.get('content') or ''}"
            ),
        },
    ]
    raw = await llm.complete(messages=prompt, model_settings=settings.get("model") or {})
    return _parse_json_object(raw)


def _build_image_prompt(settings: dict, decision: dict, *, companion: str, user_name: str) -> str:
    moments = settings.get("moments") or {}
    identity = str(moments.get("identityPromptPrefix") or "").strip() or (
        "The only person in the image is {{companion.name}}. Use the reference image as the identity source. "
        "Preserve the same face, hairstyle, body type, and overall vibe. Natural candid smartphone photo, no text, no watermark."
    )
    identity = identity.replace("{{companion.name}}", companion).replace("{{user.name}}", user_name)
    scene = str(decision.get("scene") or "natural casual selfie").strip()
    outfit = str(decision.get("outfit") or "natural everyday outfit").strip()
    pose = str(decision.get("pose") or "relaxed smartphone selfie").strip()
    mood = str(decision.get("mood") or "warm and intimate").strip()
    return (
        f"{identity} "
        f"Scene: {scene}. Outfit: {outfit}. Pose: {pose}. Mood: {mood}. "
        "The image should feel like a private chat photo she just took naturally, not a studio portrait. "
        "Only one person, no other main characters."
    )


def _quota_guard(db: Database, config: dict) -> dict:
    limit = int(config["dailySuccessfulLimit"])
    day_start = _today_start_timestamp()
    sent_today = db.count_sent_chat_photos_since(day_start)
    active = _active_task(db)
    latest = db.latest_sent_chat_photo()
    min_hours = int(config["minHoursBetweenPhotos"])
    latest_sent_at = float((latest or {}).get("sentAt") or 0)
    hours_since_latest = (dt.datetime.now(TZ).timestamp() - latest_sent_at) / 3600 if latest_sent_at else None
    reason = ""
    allowed = True
    if limit <= 0:
        allowed = False
        reason = "daily_limit_zero"
    elif sent_today >= limit:
        allowed = False
        reason = "daily_limit_reached"
    elif active:
        allowed = False
        reason = "active_task_exists"
    elif hours_since_latest is not None and hours_since_latest < min_hours:
        allowed = False
        reason = "min_interval_not_reached"
    return {
        "allowed": allowed,
        "reason": reason,
        "sentToday": sent_today,
        "dailySuccessfulLimit": limit,
        "remainingToday": max(0, limit - sent_today),
        "activeTaskId": (active or {}).get("id") or "",
        "hoursSinceLatest": hours_since_latest,
        "minHoursBetweenPhotos": min_hours,
    }


def _active_task(db: Database) -> dict | None:
    active = db.get_active_chat_photo_task()
    if not active:
        return None
    updated_at = float(active.get("updatedAt") or active.get("createdAt") or 0)
    if updated_at and dt.datetime.now(TZ).timestamp() - updated_at > 3600:
        db.update_chat_photo_task(
            str(active["id"]),
            status="failed",
            metadata={"error": "stale active photo task expired"},
        )
        return None
    return active


def _parse_json_object(raw: str) -> dict:
    text = raw.strip()
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return {"action": "none"}
    try:
        parsed = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return {"action": "none"}
    return parsed if isinstance(parsed, dict) else {"action": "none"}


def _clean_caption(value: str) -> str:
    caption = " ".join(value.split()).strip()
    if not caption:
        return "刚刚那张拍好了。"
    return caption[:120]


def _date_key() -> str:
    return dt.datetime.now(TZ).date().isoformat()


def _today_start_timestamp() -> float:
    today = dt.datetime.now(TZ).date()
    return dt.datetime.combine(today, dt.time.min, tzinfo=TZ).timestamp()


def _clamp_int(value: object, *, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))
