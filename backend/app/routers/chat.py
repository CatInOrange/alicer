from __future__ import annotations

import asyncio
import datetime as dt
import time
import uuid
from zoneinfo import ZoneInfo

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ..db import Database
from ..services.chat_photo_service import build_chat_photo_context, schedule_chat_photo_decision
from ..services.life_fact_service import build_world_context, schedule_fact_extraction
from ..services.llm_service import LlmService
from ..services.life_service import advance_life_until_now, build_life_context
from ..services.memory_service import maybe_process_memory_queue, memory_trigger_type, recall_memories
from ..services.prompt_service import merge_settings, render_prompt
from ..services.user_timeline_service import build_user_timeline_context
from ..services.weather_service import enrich_weather


class ChatRequest(BaseModel):
    text: str
    environment: dict | None = None
    settings: dict | None = None


_BACKGROUND_STREAM_TASKS: set[asyncio.Task] = set()
TZ = ZoneInfo("Asia/Shanghai")


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
        recent = [
            message
            for message in db.list_messages(limit=300)
            if message.get("id") != user_message.get("id")
        ]
        memories = recall_memories(db, text=text, limit=30)
        life_context = await _build_current_life_context(db, llm, settings=settings, source="chat")
        user_context = build_user_timeline_context(db, settings)
        world_context = build_world_context(db, settings)
        messages, prompt_debug = render_prompt(
            settings=settings,
            recent_messages=recent,
            memories=memories,
            environment=environment,
            life_context=life_context,
            user_context=user_context,
            photo_context=build_chat_photo_context(db, settings),
            world_context=world_context,
        )
        messages.append({"role": "user", "content": text})
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
        schedule_fact_extraction(
            db,
            llm,
            settings=settings,
            user_message=user_message,
            assistant_message=assistant_message,
            life_context=life_context,
        )
        schedule_chat_photo_decision(
            db,
            llm,
            settings=settings,
            user_message=user_message,
            assistant_message=assistant_message,
            recent_messages=[*recent, user_message, assistant_message],
            life_context=life_context,
            user_context=user_context,
            world_context=world_context,
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
    queue: asyncio.Queue[tuple[str, dict] | None] = asyncio.Queue()
    task = asyncio.create_task(
        _run_stream_generation(
            request,
            db=db,
            llm=llm,
            queue=queue,
            user_message=user_message,
            assistant_id=assistant_id,
        )
    )
    _BACKGROUND_STREAM_TASKS.add(task)
    task.add_done_callback(_BACKGROUND_STREAM_TASKS.discard)
    yield _sse("start", {"userMessage": user_message, "assistantMessage": assistant_message})
    try:
        while True:
            item = await queue.get()
            if item is None:
                return
            event, payload = item
            yield _sse(event, payload)
    except asyncio.CancelledError:
        # The UI may leave the page while a reply is still being generated.
        # Keep the background task alive so /api/messages can recover it later.
        raise


async def _run_stream_generation(
    request: ChatRequest,
    *,
    db: Database,
    llm: LlmService,
    queue: asyncio.Queue[tuple[str, dict] | None],
    user_message: dict,
    assistant_id: str,
) -> None:
    full_reply = ""
    prompt_debug: dict = {}
    try:
        text = request.text.strip()
        settings = merge_settings(request.settings or db.get_settings())
        environment = await enrich_weather(request.environment)
        recent = [
            message
            for message in db.list_messages(limit=300)
            if message.get("id") not in {assistant_id, user_message.get("id")}
        ]
        memories = recall_memories(db, text=text, limit=30)
        life_context = await _build_current_life_context(db, llm, settings=settings, source="chat_stream")
        user_context = build_user_timeline_context(db, settings)
        world_context = build_world_context(db, settings)
        messages, prompt_debug = render_prompt(
            settings=settings,
            recent_messages=recent,
            memories=memories,
            environment=environment,
            life_context=life_context,
            user_context=user_context,
            photo_context=build_chat_photo_context(db, settings),
            world_context=world_context,
        )
        messages.append({"role": "user", "content": text})
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
            await queue.put(("chunk", {"delta": chunk}))
        assistant_message = db.update_message(
            message_id=assistant_id,
            content=full_reply.strip(),
            metadata={"streamStatus": "complete", "promptDebug": prompt_debug},
        ) or db.get_message(assistant_id)
        if assistant_message is None:
            return
        _queue_memory_extraction(
            db,
            llm,
            settings=settings,
            user_message=user_message,
            assistant_message=assistant_message,
        )
        schedule_fact_extraction(
            db,
            llm,
            settings=settings,
            user_message=user_message,
            assistant_message=assistant_message,
            life_context=life_context,
        )
        schedule_chat_photo_decision(
            db,
            llm,
            settings=settings,
            user_message=user_message,
            assistant_message=assistant_message,
            recent_messages=[*recent, user_message, assistant_message],
            life_context=life_context,
            user_context=user_context,
            world_context=world_context,
        )
        await queue.put(
            (
                "final",
                {
                    "userMessage": user_message,
                    "assistantMessage": assistant_message,
                    "promptDebug": prompt_debug,
                },
            )
        )
    except asyncio.CancelledError:
        db.update_message(
            message_id=assistant_id,
            content=full_reply,
            metadata={"streamStatus": "cancelled", "promptDebug": prompt_debug},
        )
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
        await queue.put(("error", {"error": str(exc)}))
    finally:
        await queue.put(None)


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


async def _build_current_life_context(
    db: Database,
    llm: LlmService,
    *,
    settings: dict,
    source: str,
) -> dict:
    try:
        force = _life_state_needs_chat_refresh(db)
        result = await asyncio.wait_for(
            advance_life_until_now(db, llm, settings=settings, force=force),
            timeout=12.0,
        )
        context = result.get("context") or build_life_context(db, settings)
        db.upsert_scheduled_job(
            job_key="life:advance:chat:last",
            result={
                "ok": True,
                "source": source,
                "force": force,
                "advanced": bool(result.get("advanced")),
                "reason": result.get("reason") or "",
                "createdCount": len(result.get("created") or []),
                "ranAt": time.time(),
            },
        )
        return context
    except asyncio.CancelledError:
        raise
    except Exception as exc:  # noqa: BLE001
        db.upsert_scheduled_job(
            job_key="life:advance:chat:error",
            result={
                "ok": False,
                "source": source,
                "errorType": type(exc).__name__,
                "error": str(exc)[:500],
                "ranAt": time.time(),
            },
        )
        return build_life_context(db, settings)


def _life_state_needs_chat_refresh(db: Database) -> bool:
    now = dt.datetime.now(TZ).replace(minute=0, second=0, microsecond=0)
    latest = db.latest_life_event_before(now.timestamp())
    if not latest:
        return True
    try:
        latest_time = dt.datetime.fromtimestamp(float(latest["eventTime"]), tz=TZ)
    except (TypeError, ValueError, OSError, KeyError):
        return True
    if latest_time.replace(minute=0, second=0, microsecond=0) >= now:
        return False
    return dt.datetime.now(TZ) - latest_time > dt.timedelta(minutes=90)
