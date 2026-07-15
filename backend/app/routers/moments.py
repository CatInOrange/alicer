from __future__ import annotations

import random
import uuid

from fastapi import APIRouter

from ..db import Database
from ..services.llm_service import LlmService
from ..services.prompt_service import merge_settings


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
        moment = await _generate_moment(db, llm, settings=settings)
        return {"created": True, "moment": moment}

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


async def _generate_moment(db: Database, llm: LlmService, *, settings: dict) -> dict:
    companion = str(((settings.get("companion") or {}).get("name") or "Alice")).strip() or "Alice"
    moments_settings = settings.get("moments") or {}
    photo_probability = _probability(moments_settings.get("photoProbability"), default=0.45)
    reference_image_url = str(moments_settings.get("referenceImageUrl") or "").strip()
    recent = db.list_messages(limit=120)
    recent_text = "\n".join(
        f"- {item['role']}: {item['content'][:300]}" for item in recent[-40:] if item.get("content")
    )
    prompt = [
        {
            "role": "system",
            "content": (
                f"你是{companion}，要写一条微信朋友圈。"
                "像真实的人，不要像公告；文字有趣、有生活感，允许少量 emoji。"
                "输出 JSON：content 是朋友圈正文，imagePrompt 是给图像模型的照片提示词。"
                "imagePrompt 要描述真实随手拍场景、衣着、光线和动作，不要改变人物身份。"
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
    image = {"imageUrl": "", "provider": {"skippedByProbability": True}}
    if random.random() <= photo_probability:
        image = await llm.generate_image(
            prompt=(
                "Keep the same face and hairstyle, tall slender body with long legs, "
                "natural candid smartphone photo for a WeChat Moments post, "
                "soft realistic lighting, no text, no watermark, professional photography. "
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
            "referenceImageUrl": reference_image_url,
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


def _probability(value: object, *, default: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = default
    return max(0.0, min(1.0, parsed))


def _seed_moment(db: Database) -> dict:
    return db.add_moment(
        moment_id=f"mom_{uuid.uuid4().hex}",
        author="Alice",
        content="今天先把这里布置好。等你来点赞，我再假装只是路过看到 😊",
        image_url="",
        image_prompt="warm desk, phone screen glow, cozy evening",
        metadata={"seed": True},
    )
