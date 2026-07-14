from __future__ import annotations

import uuid

from fastapi import APIRouter
from pydantic import BaseModel

from ..db import Database
from ..services.llm_service import LlmService
from ..services.prompt_service import merge_settings, render_prompt
from ..services.weather_service import enrich_weather


class ChatRequest(BaseModel):
    text: str
    environment: dict | None = None
    settings: dict | None = None


def create_chat_router(db: Database, llm: LlmService) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["chat"])

    @router.get("/messages")
    def list_messages(limit: int = 100) -> dict:
        return {"messages": db.list_messages(limit=limit)}

    @router.post("/chat")
    async def chat(request: ChatRequest) -> dict:
        text = request.text.strip()
        if not text:
            return {"error": "empty message"}
        user_message = db.add_message(
            message_id=f"msg_{uuid.uuid4().hex}",
            role="user",
            content=text,
        )
        settings = merge_settings(request.settings or db.get_settings())
        environment = await enrich_weather(request.environment)
        recent = db.list_messages(limit=40)
        memories = db.list_memories(limit=30)
        messages, prompt_debug = render_prompt(
            settings=settings,
            recent_messages=recent,
            memories=memories,
            environment=environment,
        )
        reply = await llm.complete(messages=messages, model_settings=settings.get("model") or {})
        assistant_message = db.add_message(
            message_id=f"msg_{uuid.uuid4().hex}",
            role="assistant",
            content=reply,
            metadata={"promptDebug": prompt_debug},
        )
        return {
            "userMessage": user_message,
            "assistantMessage": assistant_message,
            "promptDebug": prompt_debug,
        }

    return router
