from __future__ import annotations

import base64
import time

import httpx

from ..config import Settings


class LlmService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def complete(self, *, messages: list[dict], model_settings: dict) -> str:
        if not self.settings.deepseek_api_key:
            return self._fallback_reply(messages)
        payload = self._payload(messages=messages, model_settings=model_settings, stream=False)
        data = await self._post_chat(payload)
        choices = data.get("choices") or []
        if not choices:
            raise RuntimeError("DeepSeek response has no choices")
        return str(((choices[0].get("message") or {}).get("content") or "")).strip()

    async def stream_complete(self, *, messages: list[dict], model_settings: dict):
        if not self.settings.deepseek_api_key:
            fallback = self._fallback_reply(messages)
            for token in _chunk_text(fallback):
                yield token
            return

        payload = self._payload(messages=messages, model_settings=model_settings, stream=True)
        url = self.settings.deepseek_base_url.rstrip("/") + "/chat/completions"
        async with httpx.AsyncClient(timeout=self.settings.request_timeout_seconds) as client:
            async with client.stream(
                "POST",
                url,
                headers={
                    "Authorization": f"Bearer {self.settings.deepseek_api_key}",
                    "Content-Type": "application/json",
                    "Accept": "text/event-stream",
                },
                json=payload,
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    line = line.strip()
                    if not line or not line.startswith("data:"):
                        continue
                    data = line.removeprefix("data:").strip()
                    if data == "[DONE]":
                        break
                    try:
                        parsed = httpx.Response(200, content=data).json()
                    except Exception:
                        continue
                    choices = parsed.get("choices") or []
                    if not choices:
                        continue
                    delta = choices[0].get("delta") or {}
                    text = str(delta.get("content") or "")
                    if text:
                        yield text

    async def generate_image(self, *, prompt: str, bucket: str = "moments", reference_image_url: str = "") -> dict:
        if not self.settings.image_api_key:
            return {
                "imageUrl": "",
                "provider": {"configured": False, "model": self.settings.image_model},
            }
        has_reference = bool(reference_image_url.strip())
        url = self.settings.image_base_url.rstrip("/") + (
            "/images/edits" if has_reference else "/images/generations"
        )
        payload = {
            "model": self.settings.image_model,
            "prompt": prompt,
            "n": 1,
            "response_format": "b64_json",
        }
        if has_reference:
            payload["image"] = {"url": reference_image_url.strip()}
        async with httpx.AsyncClient(timeout=max(self.settings.request_timeout_seconds, 120)) as client:
            response = await client.post(
                url,
                headers={
                    "Authorization": f"Bearer {self.settings.image_api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
        first = ((data.get("data") or [{}])[0] or {})
        b64 = first.get("b64_json") or first.get("b64")
        if first.get("url"):
            return {
                "imageUrl": str(first["url"]),
                "provider": {"configured": True, "model": self.settings.image_model, "remote": True},
            }
        if not b64:
            raise RuntimeError("image response has no image payload")
        image_bytes = base64.b64decode(str(b64))
        target_dir = self.settings.upload_dir / bucket
        target_dir.mkdir(parents=True, exist_ok=True)
        name = f"{int(time.time() * 1000)}.png"
        target = target_dir / name
        target.write_bytes(image_bytes)
        return {
            "imageUrl": f"/uploads/{bucket}/{name}",
            "provider": {"configured": True, "model": self.settings.image_model, "remote": False},
        }

    def _payload(self, *, messages: list[dict], model_settings: dict, stream: bool) -> dict:
        return {
            "model": model_settings.get("model") or self.settings.deepseek_model,
            "messages": messages,
            "temperature": float(model_settings.get("temperature", 0.8)),
            "max_tokens": int(model_settings.get("maxTokens", 1200)),
            "stream": stream,
        }

    async def _post_chat(self, payload: dict) -> dict:
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
            return response.json()

    def _fallback_reply(self, messages: list[dict]) -> str:
        last_user = next((item["content"] for item in reversed(messages) if item.get("role") == "user"), "")
        if not last_user:
            return "我在呢。"
        return f"我收到啦：{last_user}\n\n后端已经连通；配置 DEEPSEEK_API_KEY 后，我会用 DeepSeek 正式回复你。"


def _chunk_text(text: str, size: int = 8):
    for index in range(0, len(text), size):
        yield text[index : index + size]
