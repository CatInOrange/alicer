from __future__ import annotations

from ..defaults import DEFAULT_SETTINGS
from .context_composer import RECENT_HISTORY_COUNT, compose_prompt_context


SYSTEM_PROMPT_CHAR_BUDGET = 120_000


def merge_settings(stored: dict | None) -> dict:
    if not stored:
        return DEFAULT_SETTINGS
    merged = {**DEFAULT_SETTINGS, **stored}
    for key in (
        "companion",
        "environment",
        "memory",
        "chatContext",
        "moments",
        "life",
        "userTimeline",
        "chatPhotos",
        "model",
    ):
        merged[key] = {**DEFAULT_SETTINGS.get(key, {}), **stored.get(key, {})}
    if not stored.get("promptModules"):
        merged["promptModules"] = DEFAULT_SETTINGS["promptModules"]
    else:
        stored_modules = [
            item
            for item in stored.get("promptModules") or []
            if isinstance(item, dict) and item.get("id") != "short_term_memory"
        ]
        existing_ids = {str(item.get("id") or "") for item in stored_modules}
        missing = [
            item
            for item in DEFAULT_SETTINGS["promptModules"]
            if str(item.get("id") or "") not in existing_ids
        ]
        merged["promptModules"] = [*stored_modules, *missing]
    return merged


def render_prompt(
    *,
    settings: dict,
    recent_messages: list[dict],
    memories: list[dict],
    environment: dict | None,
    life_context: dict | None = None,
    user_context: dict | None = None,
    photo_context: dict | None = None,
    world_context: dict | None = None,
) -> tuple[list[dict], dict]:
    env = environment or {}
    modules = sorted(
        [item for item in settings.get("promptModules", []) if item.get("enabled")],
        key=lambda item: int(item.get("order") or 0),
    )
    composed = compose_prompt_context(
        settings=settings,
        recent_messages=recent_messages,
        memories=memories,
        environment=env,
        life_context=life_context or {},
        user_context=user_context or {},
        photo_context=photo_context or {},
        world_context=world_context or {},
    )
    variables = composed["variables"]
    rendered_blocks = []
    for module in modules:
        content = str(module.get("content") or "")
        for key, value in variables.items():
            content = content.replace("{{" + key + "}}", value)
        rendered_blocks.append(
            {
                "id": module.get("id"),
                "title": module.get("title"),
                "order": module.get("order"),
                "content": content.strip(),
            }
        )
    rendered_blocks = _fit_rendered_blocks(rendered_blocks, SYSTEM_PROMPT_CHAR_BUDGET)
    system_prompt = "\n\n".join(block["content"] for block in rendered_blocks if block["content"])
    prompt_history = composed["promptHistory"]
    return [{"role": "system", "content": system_prompt}], {
        "blocks": rendered_blocks,
        "variables": variables,
        "contextPackage": composed["package"],
        "messagesCount": 1,
        "historyCount": len(prompt_history),
        "historyRecentCount": min(RECENT_HISTORY_COUNT, len(prompt_history)),
        "historyOlderCount": max(0, len(prompt_history) - RECENT_HISTORY_COUNT),
        "historyMode": (settings.get("chatContext") or {}).get("historyMode") or "all",
        "memoryIds": [item.get("id") for item in memories if item.get("id")],
        "systemPromptChars": len(system_prompt),
        "systemPromptCharBudget": SYSTEM_PROMPT_CHAR_BUDGET,
    }


def _fit_rendered_blocks(blocks: list[dict], char_budget: int) -> list[dict]:
    fitted = []
    used = 0
    for block in blocks:
        content = str(block.get("content") or "")
        remaining = char_budget - used
        if remaining <= 0:
            next_block = {**block, "content": ""}
        elif len(content) > remaining:
            next_block = {**block, "content": content[: max(0, remaining - 1)].rstrip() + "…"}
            used = char_budget
        else:
            next_block = block
            used += len(content) + 2
        fitted.append(next_block)
    return fitted
