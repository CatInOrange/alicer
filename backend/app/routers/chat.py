from __future__ import annotations

import asyncio
import time
import uuid

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ..db import Database
from ..services.llm_service import LlmService
from ..services.life_service import build_life_context
from ..services.memory_service import maybe_process_memory_queue, memory_trigger_type, recall_memories
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
        recent = db.list_messages(limit=300)
        memories = recall_memories(db, text=text, limit=30)
        messages, prompt_debug = render_prompt(
            settings=settings,
            recent_messages=recent,
            memories=memories,
            environment=environment,
            life_context=build_life_context(db, settings),
        )
        reply = await llm.complete(messages=messages, model_settings=settings.get("model") or {})
        assistant_message = db.add_message(
            message_id=f"msg_{uuid.uuid4().hex}",
            role="assistant",
            content=reply,
            metadata={"promptDebug": prompt_debug},
        )
        _queue_memory_extraction(
            db,
            llm,
            settings=settings,
            user_message=user_message,
            assistant_message=assistant_message,
        )
        return {
            "userMessage": user_message,
            "assistantMessage": assistant_message,
            "promptDebug": prompt_debug,
        }

    @router.post("/chat/stream")
    async def chat_stream(request: ChatRequest) -> StreamingResponse:
        return StreamingResponse(
            _stream_chat(request, db=db, llm=llm),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
        )

    return router


async def _stream_chat(request: ChatRequest, *, db: Database, llm: LlmService):
    text = request.text.strip()
    if not text:
        yield _sse("error", {"error": "empty message"})
        return
    user_message = db.add_message(
        message_id=f"msg_{uuid.uuid4().hex}",
        role="user",
        content=text,
    )
    assistant_message = db.add_message(
        message_id=f"msg_{uuid.uuid4().hex}",
        role="assistant",
        content="",
        metadata={"streamStatus": "streaming"},
    )
    assistant_id = str(assistant_message["id"])
    full_reply = ""
    prompt_debug: dict = {}
    completed = False
    yield _sse("start", {"userMessage": user_message, "assistantMessage": assistant_message})
    try:
        settings = merge_settings(request.settings or db.get_settings())
        environment = await enrich_weather(request.environment)
        recent = [
            message
            for message in db.list_messages(limit=300)
            if message.get("id") != assistant_id
        ]
        memories = recall_memories(db, text=text, limit=30)
        messages, prompt_debug = render_prompt(
            settings=settings,
            recent_messages=recent,
            memories=memories,
            environment=environment,
            life_context=build_life_context(db, settings),
        )
        last_persisted_at = time.monotonic()
        async for chunk in llm.stream_complete(messages=messages, model_settings=settings.get("model") or {}):
            full_reply += chunk
            now = time.monotonic()
            if now - last_persisted_at >= 0.75:
                db.update_message(
                    message_id=assistant_id,
                    content=full_reply,
                    metadata={"streamStatus": "streaming", "promptDebug": prompt_debug},
                )
                last_persisted_at = now
            yield _sse("chunk", {"delta": chunk})
        assistant_message = db.update_message(
            message_id=assistant_id,
            content=full_reply.strip(),
            metadata={"streamStatus": "complete", "promptDebug": prompt_debug},
        ) or assistant_message
        completed = True
        _queue_memory_extraction(
            db,
            llm,
            settings=settings,
            user_message=user_message,
            assistant_message=assistant_message,
        )
        yield _sse(
            "final",
            {
                "userMessage": user_message,
                "assistantMessage": assistant_message,
                "promptDebug": prompt_debug,
            },
        )
    except asyncio.CancelledError:
        db.update_message(
            message_id=assistant_id,
            content=full_reply,
            metadata={"streamStatus": "interrupted", "promptDebug": prompt_debug},
        )
        completed = True
        raise
    except Exception as exc:  # noqa: BLE001
        db.update_message(
            message_id=assistant_id,
            content=full_reply,
            metadata={
                "streamStatus": "error",
                "streamError": str(exc),
                "promptDebug": prompt_debug,
            },
        )
        completed = True
        yield _sse("error", {"error": str(exc)})
    finally:
        if not completed and full_reply:
            db.update_message(
                message_id=assistant_id,
                content=full_reply,
                metadata={"streamStatus": "interrupted", "promptDebug": prompt_debug},
            )


def _sse(event: str, payload: dict) -> str:
    import json

    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _queue_memory_extraction(
    db: Database,
    llm: LlmService,
    *,
    settings: dict,
    user_message: dict,
    assistant_message: dict,
) -> None:
    if (settings.get("memory") or {}).get("autoExtract") is False:
        return
    trigger = memory_trigger_type(str(user_message.get("content") or ""))
    db.enqueue_memory_message(
        message_id=str(user_message["id"]),
        role="user",
        content=str(user_message.get("content") or ""),
        trigger_type=trigger,
    )
    db.enqueue_memory_message(
        message_id=str(assistant_message["id"]),
        role="assistant",
        content=str(assistant_message.get("content") or ""),
        trigger_type=trigger,
    )
    asyncio.create_task(
        maybe_process_memory_queue(
            db,
            llm,
            settings=settings,
            force=trigger == "explicit",
        )
    )
