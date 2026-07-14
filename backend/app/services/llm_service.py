from __future__ import annotations

import httpx

from ..config import Settings


class LlmService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def complete(self, *, messages: list[dict], model_settings: dict) -> str:
        if not self.settings.deepseek_api_key:
            return self._fallback_reply(messages)
        payload = {
            "model": model_settings.get("model") or self.settings.deepseek_model,
            "messages": messages,
            "temperature": float(model_settings.get("temperature", 0.8)),
            "max_tokens": int(model_settings.get("maxTokens", 1200)),
        }
        url = self.settings.deepseek_base_url.rstrip("/") + "/chat/completions"
        async with httpx.AsyncClient(timeout=self.settings.request_timeout_seconds) as client:
            response = await client.post(
                url,
                headers={
                    "Authorization": f"Bearer {self.settings.deepseek_api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
        choices = data.get("choices") or []
        if not choices:
            raise RuntimeError("DeepSeek response has no choices")
        return str(((choices[0].get("message") or {}).get("content") or "")).strip()

    def _fallback_reply(self, messages: list[dict]) -> str:
        last_user = next((item["content"] for item in reversed(messages) if item.get("role") == "user"), "")
        if not last_user:
            return "我在呢。"
        return f"我收到啦：{last_user}\n\n后端已经连通；配置 DEEPSEEK_API_KEY 后，我会用 DeepSeek 正式回复你。"
