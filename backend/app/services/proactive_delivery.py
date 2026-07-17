from __future__ import annotations

import uuid

from ..db import Database
from .chat_photo_service import build_chat_photo_context
from .life_fact_service import build_world_context
from .llm_service import LlmService
from .memory_service import recall_memories
from .proactive_candidates import candidate_public
from .proactive_types import MomentGenerator, ProactiveCandidate
from .prompt_service import render_prompt


async def deliver_chat(
    db: Database,
    llm: LlmService,
    *,
    settings: dict,
    recent_messages: list[dict],
    candidate: ProactiveCandidate,
    decision_payload: dict,
    life_context: dict,
    user_context: dict,
    world_context: dict | None = None,
) -> dict:
    memories = recall_memories(db, text=f"{candidate.intent} {candidate.reason}", limit=20)
    messages, prompt_debug = render_prompt(
        settings=settings,
        recent_messages=recent_messages,
        memories=memories,
        environment={},
        life_context=life_context,
        user_context=user_context,
        photo_context=build_chat_photo_context(db, settings),
        world_context=world_context or build_world_context(db, settings),
    )
    messages.append(
        {
            "role": "user",
            "content": (
                "这是一次 Alicer 主动联系用户，不是回复用户刚刚发来的消息。\n"
                f"主动意图：{candidate.intent}\n"
                f"触发原因：{candidate.reason}\n"
                f"写作要求：{candidate.prompt}\n"
                "只输出将要发送给用户的一条聊天消息，1 到 3 句，短、自然、具体。"
                "不要说你是系统自动触发，不要解释策略、分数、后台、时间线。"
            ),
        }
    )
    content = (await llm.complete(messages=messages, model_settings=settings.get("model") or {})).strip()
    if not content:
        content = fallback_proactive_text(candidate)
    message = db.add_message(
        message_id=f"msg_{uuid.uuid4().hex}",
        role="assistant",
        content=content[:900],
        metadata={
            "source": "proactive",
            "proactive": candidate_public(candidate),
            "promptDebug": prompt_debug,
        },
    )
    event = db.add_proactive_event(
        event_id=f"pro_{uuid.uuid4().hex}",
        event_type="chat",
        status="delivered",
        intent=candidate.intent,
        source_key=candidate.source_key,
        score=candidate.score,
        reason=candidate.reason,
        message_id=str(message.get("id") or ""),
        metadata={**decision_payload, "message": message},
        decided=True,
        delivered=True,
    )
    return {"created": True, "type": "chat", "message": message, "event": event, **decision_payload}


async def deliver_moment(
    db: Database,
    llm: LlmService,
    *,
    settings: dict,
    candidate: ProactiveCandidate,
    decision_payload: dict,
    moment_generator: MomentGenerator,
) -> dict:
    moment = await moment_generator(db, llm, settings, "proactive_life")
    event = db.add_proactive_event(
        event_id=f"pro_{uuid.uuid4().hex}",
        event_type="moment",
        status="delivered",
        intent=candidate.intent,
        source_key=candidate.source_key,
        score=candidate.score,
        reason=candidate.reason,
        moment_id=str(moment.get("id") or ""),
        metadata={**decision_payload, "moment": moment},
        decided=True,
        delivered=True,
    )
    return {"created": True, "type": "moment", "moment": moment, "event": event, **decision_payload}


def fallback_proactive_text(candidate: ProactiveCandidate) -> str:
    if candidate.intent == "support":
        return "我刚才又想起你说的那件事了。先不用回我，别一个人硬撑就好。"
    if candidate.intent == "share_life":
        return "我这边刚从自己的节奏里抬头，忽然有点想把这一小段发给你。"
    return "我来轻轻敲一下你。忙的话不用急着回，我只是有点想你了。"
