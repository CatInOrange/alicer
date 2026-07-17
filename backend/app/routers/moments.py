from __future__ import annotations

import base64
import binascii
import uuid

from fastapi import APIRouter, HTTPException

from ..db import Database
from ..services.llm_service import LlmService
from ..services.moment_service import (
    generate_moment,
    reply_to_comment,
    seed_moment,
)
from ..services.prompt_service import merge_settings


def create_moments_router(db: Database, llm: LlmService) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["moments"])

    @router.get("/moments")
    def list_moments(limit: int = 50) -> dict:
        moments = db.list_moments(limit=limit)
        if not moments:
            moments = [seed_moment(db)]
        return {"moments": moments}

    @router.post("/moments/generate")
    async def generate(body: dict | None = None) -> dict:
        payload = body or {}
        result = await generate_moment(
            db,
            llm,
            settings=merge_settings(payload.get("settings") or db.get_settings()),
            force=payload.get("force") is True,
            force_photo=payload.get("forcePhoto") is True,
            source="manual_app" if payload.get("force") is True else "manual",
        )
        return result

    @router.post("/moments/reference-image")
    def upload_reference_image(body: dict | None = None) -> dict:
        payload = body or {}
        raw_data = str(payload.get("data") or "")
        if "," in raw_data and raw_data.startswith("data:image/"):
            raw_data = raw_data.split(",", 1)[1]
        try:
            image_bytes = base64.b64decode(raw_data, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise HTTPException(status_code=400, detail="invalid image data") from exc
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
        reply = await reply_to_comment(llm, settings=settings, moment=moment or {}, comment=content)
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


def _image_extension(image_bytes: bytes) -> str:
    if image_bytes.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if image_bytes[:4] == b"RIFF" and image_bytes[8:12] == b"WEBP":
        return ".webp"
    return ""
