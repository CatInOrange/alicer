from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel


ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")


class Settings(BaseModel):
    host: str = os.environ.get("ALICER_HOST", "127.0.0.1")
    port: int = int(os.environ.get("ALICER_PORT", "18083"))
    db_path: Path = Path(os.environ.get("ALICER_DB_PATH", ROOT / "data" / "alicer.db")).expanduser()
    cors_origins: list[str] = [
        item.strip()
        for item in os.environ.get("ALICER_CORS_ORIGINS", "*").split(",")
        if item.strip()
    ]
    deepseek_api_key: str = os.environ.get("DEEPSEEK_API_KEY", "")
    deepseek_base_url: str = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    deepseek_model: str = os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-flash")
    amap_key: str = os.environ.get("AMAP_KEY", "")
    request_timeout_seconds: float = float(os.environ.get("ALICER_REQUEST_TIMEOUT_SECONDS", "60"))


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    return settings
