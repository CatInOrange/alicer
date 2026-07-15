from __future__ import annotations

import asyncio
import base64
import binascii
import datetime as dt
import random
import uuid
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException

from ..db import Database
from ..services.llm_service import LlmService
from ..services.prompt_service import merge_settings


TZ = ZoneInfo("Asia/Shanghai")


def create_moments_router(db: Database, llm: LlmService) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["moments"])

    @router.get("/moments")
    def list_moments(limit: int = 50) -> dict:
        moments = db.list_moments(limit=limit)
        if not moments:
            moments = [_seed_moment(db)]
        return {"moments": moments}

    @router.post("/moments/generate")
    async def generate_moment(body: dict | None = None) -> dict:
        payload = body or {}
        settings = merge_settings(payload.get("settings") or db.get_settings())
        probability = float(((settings.get("moments") or {}).get("dailyPostProbability") or 0.55))
        force = payload.get("force") is True
        if not force and random.random() > probability:
            return {"created": False, "moment": None}
        moment = await _generate_moment(
            db,
            llm,
            settings=settings,
            force_photo=payload.get("forcePhoto") is True,
        )
        return {"created": True, "moment": moment}

    @router.post("/moments/reference-image")
    def upload_reference_image(body: dict | None = None) -> dict:
        payload = body or {}
        raw_data = str(payload.get("data") or "")
        if "," in raw_data and raw_data.startswith("data:image/"):
            raw_data = raw_data.split(",", 1)[1]
        try:
            image_bytes = base64.b64decode(raw_data, validate=True)
        except (binascii.Error, ValueError):
            raise HTTPException(status_code=400, detail="invalid image data")
        if not image_bytes:
            raise HTTPException(status_code=400, detail="empty image data")
        if len(image_bytes) > 8 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="image is too large")
        extension = _image_extension(image_bytes)
        if not extension:
            raise HTTPException(status_code=400, detail="unsupported image type")
        target_dir = llm.settings.upload_dir / "reference"
        target_dir.mkdir(parents=True, exist_ok=True)
        filename = f"companion_{uuid.uuid4().hex}{extension}"
        target = target_dir / filename
        target.write_bytes(image_bytes)
        return {
            "imageUrl": f"/uploads/reference/{filename}",
            "size": len(image_bytes),
        }

    @router.post("/moments/{moment_id}/like")
    def like(moment_id: str, body: dict | None = None) -> dict:
        payload = body or {}
        user_name = str(payload.get("userName") or "你").strip() or "你"
        liked = payload.get("liked") is not False
        moment = db.set_moment_like(moment_id=moment_id, user_name=user_name, liked=liked)
        return {"moment": moment}

    @router.post("/moments/{moment_id}/comments")
    async def comment(moment_id: str, body: dict | None = None) -> dict:
        payload = body or {}
        content = str(payload.get("content") or "").strip()
        author = str(payload.get("author") or "你").strip() or "你"
        parent_id = str(payload.get("parentId") or "").strip()
        if not content:
            return {"error": "empty comment", "moment": db.get_moment(moment_id)}
        moment = db.add_moment_comment(
            comment_id=f"cmt_{uuid.uuid4().hex}",
            moment_id=moment_id,
            author=author,
            content=content,
            parent_id=parent_id,
        )
        settings = merge_settings(payload.get("settings") or db.get_settings())
        companion = str(((settings.get("companion") or {}).get("name") or "Alice")).strip() or "Alice"
        reply = await _reply_to_comment(llm, settings=settings, moment=moment or {}, comment=content)
        if reply:
            moment = db.add_moment_comment(
                comment_id=f"cmt_{uuid.uuid4().hex}",
                moment_id=moment_id,
                author=companion,
                content=reply,
                parent_id=parent_id,
            )
        return {"moment": moment}

    return router


async def run_moments_scheduler(db: Database, llm: LlmService) -> None:
    await _catch_up_daily_moment(db, llm)
    while True:
        next_run = _next_daily_moment_run()
        await asyncio.sleep(max(1.0, (next_run - dt.datetime.now(TZ)).total_seconds()))
        await _generate_scheduled_moment(db, llm, next_run.date())


async def _catch_up_daily_moment(db: Database, llm: LlmService) -> None:
    now = dt.datetime.now(TZ)
    today_target = dt.datetime.combine(now.date(), dt.time(hour=12), tzinfo=TZ)
    latest = today_target if now >= today_target else today_target - dt.timedelta(days=1)
    if now - latest <= dt.timedelta(hours=12):
        await _generate_scheduled_moment(db, llm, latest.date())


async def _generate_scheduled_moment(db: Database, llm: LlmService, day: dt.date) -> dict:
    job_key = f"moments:daily:{day.isoformat()}"
    if db.get_scheduled_job(job_key) or _has_scheduled_moment_for_day(db, day):
        return {"created": False, "moment": None, "reason": "already_decided"}
    settings = merge_settings(db.get_settings())
    probability = _probability((settings.get("moments") or {}).get("dailyPostProbability"), default=0.55)
    if random.random() > probability:
        result = {
            "created": False,
            "reason": "skipped_by_probability",
            "probability": probability,
        }
        db.upsert_scheduled_job(job_key=job_key, result=result)
        return {"created": False, "moment": None, "reason": "skipped_by_probability"}
    moment = await _generate_moment(
        db,
        llm,
        settings=settings,
        source="scheduled_1200",
    )
    db.upsert_scheduled_job(
        job_key=job_key,
        result={
            "created": True,
            "momentId": moment.get("id"),
            "probability": probability,
        },
    )
    return {"created": True, "moment": moment}


def _next_daily_moment_run() -> dt.datetime:
    now = dt.datetime.now(TZ)
    target = dt.datetime.combine(now.date(), dt.time(hour=12), tzinfo=TZ)
    return target if now < target else target + dt.timedelta(days=1)


def _has_scheduled_moment_for_day(db: Database, day: dt.date) -> bool:
    start = dt.datetime.combine(day, dt.time.min, tzinfo=TZ).timestamp()
    end = dt.datetime.combine(day, dt.time.max, tzinfo=TZ).timestamp()
    for item in db.list_moments(limit=100):
        created_at = float(item.get("createdAt") or 0)
        metadata = item.get("metadata") or {}
        if start <= created_at <= end and metadata.get("source") == "scheduled_1200":
            return True
    return False


async def _generate_moment(
    db: Database,
    llm: LlmService,
    *,
    settings: dict,
    force_photo: bool = False,
    source: str = "manual",
) -> dict:
    companion = str(((settings.get("companion") or {}).get("name") or "Alice")).strip() or "Alice"
    user_name = str(((settings.get("companion") or {}).get("userName") or "用户")).strip() or "用户"
    moments_settings = settings.get("moments") or {}
    photo_probability = _probability(moments_settings.get("photoProbability"), default=0.45)
    reference_image_url = str(moments_settings.get("referenceImageUrl") or "").strip()
    identity_prompt_prefix = _render_companion_vars(
        str(moments_settings.get("identityPromptPrefix") or "").strip() or _default_identity_prompt_prefix(),
        companion=companion,
        user_name=user_name,
    )
    role_context = _companion_context(settings, companion=companion, user_name=user_name)
    recent = db.list_messages(limit=120)
    recent_text = "\n".join(
        f"- {item['role']}: {item['content'][:300]}" for item in recent[-40:] if item.get("content")
    )
    prompt = [
        {
            "role": "system",
            "content": (
                f"你是{companion}，要以自己的身份写一条微信朋友圈，不是替{user_name}发动态。"
                "你有自己的生活、工作/学习、社交、兴趣和日常安排；如果角色设定没有明确职业，就写通用日常，不要编成用户的单位、公司、岗位、项目或行程。"
                "最近聊天只能提供情绪、关系氛围和灵感，禁止把用户说过的第一人称经历改写成你的经历。"
                "不要出现“我在你的公司/单位/项目里”这类混淆身份的内容。"
                "内容和 imagePrompt 都禁止出现“咖啡”两个字，也不要使用英文 coffee。"
                "像真实的人，不要像公告；文字短一点、有生活感，允许少量 emoji。"
                "输出 JSON：content 是朋友圈正文，imagePrompt 是给图像模型的照片提示词。"
                "imagePrompt 只描述你自己的随手拍场景、衣着、光线和动作，不要描述用户，不要出现其他主要人物。"
                f"\n\n你的稳定角色设定：\n{role_context or '温柔、独立、有自己的日常节奏。'}"
            ),
        },
        {
            "role": "user",
            "content": (
                "参考最近聊天，但不要泄露隐私，不要把聊天逐字搬进朋友圈。\n"
                f"{recent_text or '最近没有聊天，可写一条日常心情。'}"
            ),
        },
    ]
    raw = await llm.complete(messages=prompt, model_settings=settings.get("model") or {})
    content, image_prompt = _parse_moment(raw)
    content = _sanitize_scene_text(content)
    image_prompt = _sanitize_scene_text(image_prompt)
    image = {"imageUrl": "", "provider": {"skippedByProbability": True}}
    if force_photo or random.random() <= photo_probability:
        image = await llm.generate_image(
            prompt=(
                f"{identity_prompt_prefix.strip()} "
                f"Scene: {image_prompt}"
            ),
            bucket="moments",
            reference_image_url=reference_image_url,
        )
    return db.add_moment(
        moment_id=f"mom_{uuid.uuid4().hex}",
        author=companion,
        content=content,
        image_url=str(image.get("imageUrl") or ""),
        image_prompt=image_prompt,
        metadata={
            "imageProvider": image.get("provider") or {},
            "photoProbability": photo_probability,
            "forcePhoto": force_photo,
            "referenceImageUrl": reference_image_url,
            "identityPromptPrefix": identity_prompt_prefix,
            "source": source,
        },
    )


async def _reply_to_comment(llm: LlmService, *, settings: dict, moment: dict, comment: str) -> str:
    companion = str(((settings.get("companion") or {}).get("name") or "Alice")).strip() or "Alice"
    messages = [
        {
            "role": "system",
            "content": (
                f"你是{companion}，正在回复自己朋友圈下面的评论。"
                "回复要短，像真人随手回的，可以带 emoji 或语气词，不要解释。"
            ),
        },
        {
            "role": "user",
            "content": f"朋友圈：{moment.get('content') or ''}\n用户评论：{comment}",
        },
    ]
    try:
        return (await llm.complete(messages=messages, model_settings=settings.get("model") or {})).strip()[:160]
    except Exception:
        return "我看到啦，偷偷记一下 😊"


def _parse_moment(raw: str) -> tuple[str, str]:
    text = raw.strip()
    content = ""
    image_prompt = ""
    if "content" in text and "imagePrompt" in text:
        import json

        try:
            parsed = json.loads(text[text.find("{") : text.rfind("}") + 1])
            content = str(parsed.get("content") or "").strip()
            image_prompt = str(parsed.get("imagePrompt") or "").strip()
        except Exception:
            pass
    if not content:
        lines = [line.strip(" -") for line in text.splitlines() if line.strip()]
        content = lines[0] if lines else "今天的风很乖，像是提前替你说了晚安。"
    if not image_prompt:
        image_prompt = content
    return content[:500], image_prompt[:800]


def _sanitize_scene_text(text: str) -> str:
    result = text
    result = result.replace("咖啡", "饮品")
    result = result.replace("coffee", "drink")
    result = result.replace("Coffee", "drink")
    result = result.replace("COFFEE", "DRINK")
    return result


def _probability(value: object, *, default: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = default
    return max(0.0, min(1.0, parsed))


def _companion_context(settings: dict, *, companion: str, user_name: str) -> str:
    modules = [
        item
        for item in settings.get("promptModules") or []
        if isinstance(item, dict) and item.get("enabled") is not False
    ]
    modules.sort(key=lambda item: int(item.get("order") or 0))
    texts: list[str] = []
    for item in modules:
        module_id = str(item.get("id") or "")
        if module_id not in {
            "role_description",
            "personality_traits",
            "long_term_memory",
        }:
            continue
        content = str(item.get("content") or "").strip()
        if content:
            texts.append(
                _render_companion_vars(
                    content,
                    companion=companion,
                    user_name=user_name,
                )[:700]
            )
    return "\n".join(texts)[:1800]


def _render_companion_vars(text: str, *, companion: str, user_name: str) -> str:
    return (
        text.replace("{{companion.name}}", companion)
        .replace("{{user.name}}", user_name)
        .replace("{{user}}", user_name)
        .replace("{{char}}", companion)
    )


def _default_identity_prompt_prefix() -> str:
    return (
        "The only person in the image is {{companion.name}}. Use the reference image as the identity source. "
        "Preserve the exact same face, facial structure, hairstyle, hair color, age impression, body type, and overall vibe from the reference image. "
        "If any scene detail conflicts with the reference person's identity, the reference image wins. "
        "Do not create a different woman, do not change ethnicity, do not change hairstyle, do not add other people. "
        "Natural candid smartphone photo for a WeChat Moments post, soft realistic lighting, no text, no watermark."
    )


def _image_extension(image_bytes: bytes) -> str:
    if image_bytes.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if image_bytes[:4] == b"RIFF" and image_bytes[8:12] == b"WEBP":
        return ".webp"
    return ""


def _seed_moment(db: Database) -> dict:
    return db.add_moment(
        moment_id=f"mom_{uuid.uuid4().hex}",
        author="Alice",
        content="今天先把这里布置好。等你来点赞，我再假装只是路过看到 😊",
        image_url="",
        image_prompt="warm desk, phone screen glow, cozy evening",
        metadata={"seed": True},
    )
