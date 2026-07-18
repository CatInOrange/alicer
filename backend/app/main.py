from __future__ import annotations

import asyncio
import os
import secrets
import sys
import threading
import time

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .config import get_settings
from .db import Database
from .routers.chat import create_chat_router
from .routers.diary import create_diary_router, run_diary_scheduler
from .routers.life import create_life_router
from .routers.memories import create_memories_router
from .routers.moments import create_moments_router
from .services.moment_service import generate_life_moment, run_moments_scheduler
from .routers.proactive import create_proactive_router
from .routers.rifts import create_rifts_router
from .routers.settings import create_settings_router
from .routers.user_timeline import create_user_timeline_router
from .services.daily_maintenance_service import run_daily_maintenance_scheduler
from .services.llm_service import LlmService
from .services.life_service import run_life_scheduler
from .services.proactive_service import run_proactive_scheduler


DEEPSEEK_MODELS = [
    {
        "id": "deepseek-v4-flash",
        "name": "DeepSeek V4 Flash",
        "description": "速度优先，适合日常陪伴聊天。",
        "maxTokens": 8192,
    },
    {
        "id": "deepseek-v4-pro",
        "name": "DeepSeek V4 Pro",
        "description": "能力优先，适合复杂表达、长上下文和高质量回复。",
        "maxTokens": 8192,
    },
]


def create_app() -> FastAPI:
    settings = get_settings()
    db = Database(settings.db_path)
    db.ensure_schema()
    llm = LlmService(settings)
    app = FastAPI(title="Alicer Backend", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(create_settings_router(db))
    app.include_router(create_chat_router(db, llm))
    app.include_router(create_diary_router(db, llm))
    app.include_router(create_life_router(db, llm))
    app.include_router(create_user_timeline_router(db))
    app.include_router(create_moments_router(db, llm))
    app.include_router(create_proactive_router(db, llm))
    app.include_router(create_memories_router(db, llm))
    app.include_router(create_rifts_router(db, llm))
    app.mount("/uploads", StaticFiles(directory=settings.upload_dir), name="uploads")

    @app.on_event("startup")
    async def start_background_tasks() -> None:
        app.state.diary_task = asyncio.create_task(run_diary_scheduler(db, llm))
        app.state.life_task = asyncio.create_task(run_life_scheduler(db, llm))
        app.state.moments_task = asyncio.create_task(run_moments_scheduler(db, llm))
        app.state.daily_maintenance_task = asyncio.create_task(
            run_daily_maintenance_scheduler(db, llm)
        )
        app.state.proactive_task = asyncio.create_task(
            run_proactive_scheduler(db, llm, moment_generator=generate_life_moment)
        )

    @app.on_event("shutdown")
    async def stop_background_tasks() -> None:
        for task_name in (
            "diary_task",
            "life_task",
            "moments_task",
            "daily_maintenance_task",
            "proactive_task",
        ):
            task = getattr(app.state, task_name, None)
            if task is not None:
                task.cancel()

    @app.get("/api/health")
    def health() -> dict:
        return {
            "ok": True,
            "provider": "deepseek",
            "model": settings.deepseek_model,
            "deepseekConfigured": bool(settings.deepseek_api_key),
            "imageConfigured": bool(settings.image_api_key),
            "reverseGeocodingConfigured": bool(settings.amap_key),
        }

    @app.get("/api/models")
    def models() -> dict:
        return {"models": DEEPSEEK_MODELS, "defaultModel": settings.deepseek_model}

    @app.post("/api/admin/restart")
    def restart_backend(x_alicer_admin_token: str = Header(default="")) -> dict:
        if settings.admin_token:
            if not secrets.compare_digest(x_alicer_admin_token, settings.admin_token):
                raise HTTPException(status_code=403, detail="invalid admin token")
        else:
            raise HTTPException(status_code=503, detail="admin restart is not configured")
        threading.Thread(target=_restart_process_soon, daemon=True).start()
        return {"ok": True, "message": "restart scheduled"}

    return app


app = create_app()


def _restart_process_soon() -> None:
    time.sleep(0.5)
    os.execv(sys.executable, [sys.executable, *sys.argv])
