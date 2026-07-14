from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .db import Database
from .routers.chat import create_chat_router
from .routers.settings import create_settings_router
from .services.llm_service import LlmService


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

    @app.get("/api/health")
    def health() -> dict:
        return {
            "ok": True,
            "provider": "deepseek",
            "model": settings.deepseek_model,
            "deepseekConfigured": bool(settings.deepseek_api_key),
            "reverseGeocodingConfigured": bool(settings.amap_key),
        }

    @app.get("/api/models")
    def models() -> dict:
        return {"models": DEEPSEEK_MODELS, "defaultModel": settings.deepseek_model}

    return app


app = create_app()
