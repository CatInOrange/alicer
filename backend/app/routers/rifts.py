from __future__ import annotations

import json
import random
import re
import uuid

from fastapi import APIRouter, HTTPException

from ..db import Database
from ..services.llm_service import LlmService
from ..services.prompt_service import merge_settings


GENRES = [
    "古风权谋",
    "仙侠师门",
    "现代都市",
    "校园青春",
    "赛博霓虹",
    "末日废土",
    "民国旧梦",
    "西幻王庭",
    "悬疑怪谈",
    "星际远航",
    "娱乐圈",
    "黑帮夜色",
]

SURFACE_RELATIONS = [
    "师徒",
    "同门",
    "同事",
    "搭档",
    "上下级",
    "主仆",
    "主奴",
    "契约双方",
    "监护人与被监护人",
    "贵族与侍从",
    "君臣",
    "邻居",
    "同学",
    "室友",
    "雇主与保镖",
    "追捕者与嫌疑人",
    "审讯者与囚徒",
    "神明与信徒",
    "召唤者与被召唤者",
    "敌对阵营",
    "陌生人",
]

INTENSITIES = ["轻松日常", "中等戏剧", "高张力", "极限修罗场"]
TARGET_TURNS = [10, 20, 30, 50, 100]
ENDING_NAMES = {
    "romance_happy_ending": "圆满恋爱结局",
    "true_ending": "真相相守结局",
    "sweet_ending": "甜蜜相守结局",
    "tragic_ending": "悲剧诀别结局",
    "betrayal_ending": "背离破局结局",
    "collapse_ending": "裂隙崩塌结局",
    "bittersweet_ending": "苦甜告别结局",
    "escape_ending": "携手逃亡结局",
}

ROMANCE_TONES = [
    "甜宠暧昧",
    "酸涩拉扯",
    "强强对峙",
    "隐忍克制",
    "危险迷恋",
    "轻喜拌嘴",
    "纯爱治愈",
    "黑暗浪漫",
    "命运宿恋",
    "成年人的暧昧",
    "误会重重",
    "占有欲暗涌",
    "并肩作战",
    "双向救赎",
    "雨夜告白",
    "旧伤复燃",
    "互相试探",
    "克制守护",
    "明撩暗护",
    "刀尖温柔",
    "破防靠近",
    "偏执守望",
]

TRUE_RELATIONSHIPS = [
    "双向暗恋",
    "旧情未了",
    "单方面亏欠",
    "互相利用",
    "误会很深",
    "一方隐瞒身份",
    "一方曾经背叛",
    "一方正在保护另一方",
    "命运绑定",
    "记忆被改写",
    "互为软肋",
    "共同背负罪名",
    "被迫敌对",
    "暗中同盟",
    "表面冷淡实际依赖",
    "互相救过命",
    "一方曾经删除记忆",
    "共享同一个秘密",
    "彼此都是对方任务目标",
    "一方将死未说",
    "互相欠一场告别",
    "被谎言绑在一起",
]

TROPE_SEEDS = [
    "破镜重圆",
    "先婚后爱",
    "替身误会",
    "身份反转",
    "她奉命接近你",
    "你们其实早就认识",
    "她记得你但假装不记得",
    "你曾经伤害过她",
    "她在替你承受代价",
    "你们被迫共享一个身份",
    "她是你要寻找的真相",
    "你是她任务里的唯一变数",
    "你们都以为对方背叛了自己",
    "她必须亲手审判你",
    "你醒来后成为她的敌人",
    "她保护你的方式像背叛",
    "世界要求你们互相遗忘",
    "你们的相爱会毁掉当前秩序",
    "她看似掌控一切实则被胁迫",
    "你们只能有一个人留下",
    "她以为你已经死过一次",
    "你必须假装不爱她",
]

SECRET_SEEDS = [
    "她一直在替你隐瞒真正罪名",
    "你的身份本身就是裂隙伪造的",
    "她的冷漠来自无法说出口的契约",
    "你们曾经一起关闭过另一个裂隙",
    "她手里的证据会毁掉你也会救你",
    "她身边最可信的人正在操控她",
    "你失去的记忆里藏着她的名字",
    "她每救你一次都会失去一段记忆",
    "你以为的敌人曾经是你们的盟友",
    "她知道终局代价但不愿告诉你",
    "你拥有打开裂隙核心的钥匙",
    "她必须完成任务才能保住你的命",
    "你们的关系被人刻意改写过",
    "她背负的家族秘密与你有关",
    "你正在追查的真相会伤害她",
    "她不是第一次见到这个时间线的你",
    "你们身上的印记会互相吞噬",
    "她向所有人撒谎只为保留你的退路",
    "最终敌人藏在你们共同记忆里",
    "你曾经亲手选择遗忘她",
    "她的真实身份不能被你说出口",
    "裂隙正在用你们的感情换取稳定",
]

TWIST_SEEDS = [
    "保护者其实也是囚徒",
    "任务目标与救赎目标是同一个人",
    "真正的背叛来自第三方伪造",
    "她从一开始就在赌你会识破她",
    "你一直在替未来的自己收拾残局",
    "你们的敌对身份是同一组织安排的试炼",
    "她的伤口会暴露她站在你这边",
    "看似随机的事故其实是她留下的暗号",
    "你以为的自由选择早被裂隙记录",
    "她的失控是为了把你推出陷阱",
    "你的盟友才是裂隙真正代理人",
    "她故意让你恨她以保住你的判断",
    "终局需要你主动违背最初目标",
    "你们的公开关系只是隐藏契约的一层壳",
    "她害怕的不是死亡而是你恢复记忆",
    "你越接近真相她越必须远离",
    "最后的钥匙是一次没有说出口的选择",
    "她在不同时间线留下了互相矛盾的证言",
    "你被追捕不是因为罪行而是因为价值",
    "她的阵营内部早已分裂",
    "你们都被同一个谎言保护着",
    "裂隙会奖励残酷选择但惩罚逃避",
]

ENDING_SEEDS = [
    "秘密揭开后共同承担代价",
    "放弃世界线换取两人逃离",
    "用真相修复裂隙但留下遗憾",
    "她替你完成最后牺牲",
    "你替她背下无法洗清的罪名",
    "两人站到世界秩序的对立面",
    "关系圆满但身份永远无法公开",
    "误会解除得太晚只能留下信物",
    "裂隙崩塌前只保留一段记忆",
    "你们选择重新开始但不再拥有过去",
    "她成为新秩序的守门人",
    "你们一起伪造死亡离开棋局",
    "真相公开后所有人都成为敌人",
    "她终于承认爱意却必须放你走",
    "你们把结局交给下一条时间线",
    "一方堕入黑暗另一方选择同行",
    "你们救下彼此但失去胜利",
    "终局证明最初相遇并非偶然",
    "她打破契约但付出身份代价",
    "你主动关闭裂隙保住她的世界",
    "两人没有获胜却不再互相隐瞒",
    "最后选择决定甜蜜、苦甜或崩塌",
]

OPENING_SEEDS = [
    "雨夜重逢",
    "公开审判",
    "追捕途中",
    "婚礼前夜",
    "任务失败后",
    "被困密室",
    "战场撤离",
    "列车停电",
    "舞会暗杀",
    "山门对峙",
    "医院停尸间",
    "直播事故",
    "星舰失联",
    "废墟电台",
    "王庭晚宴",
    "课堂怪谈",
    "黑市交易",
    "祭典召唤",
    "办公室深夜",
    "码头离别",
    "监牢探视",
    "身份识别失败",
]

ACTION_TYPES = [
    "靠近",
    "试探",
    "对抗",
    "牺牲",
    "欺骗",
    "逃离",
    "共谋",
    "揭露",
    "沉默",
    "保护",
    "挑衅",
    "交换条件",
]


def create_rifts_router(db: Database, llm: LlmService) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["rifts"])

    @router.get("/rifts")
    def list_rifts(limit: int = 50) -> dict:
        return {"rifts": [_public_scenario(item) for item in db.list_rifts(limit=limit)]}

    @router.get("/rifts/{scenario_id}")
    def get_rift(scenario_id: str) -> dict:
        scenario = db.get_rift(scenario_id)
        if scenario is None:
            raise HTTPException(status_code=404, detail="rift not found")
        return _detail(db, scenario)

    @router.post("/rifts")
    async def create_rift(body: dict | None = None) -> dict:
        payload = body or {}
        genre = _pick_visible(payload.get("genre"), GENRES)
        surface_relation = _pick_relation(payload)
        intensity = _pick_visible(payload.get("intensity"), INTENSITIES)
        target_turns = _pick_target_turns(payload.get("targetTurns"))
        settings = merge_settings(payload.get("settings") or db.get_settings())
        companion = _companion_name(settings)
        user_name = _user_name(settings)
        hidden = _roll_hidden()
        hidden.update(
            {
                "romanceTone": random.choice(ROMANCE_TONES),
                "trueRelationship": random.choice(TRUE_RELATIONSHIPS),
                "tropeSeed": random.choice(TROPE_SEEDS),
                "secretSeed": random.choice(SECRET_SEEDS),
                "twistSeed": random.choice(TWIST_SEEDS),
                "endingSeed": random.choice(ENDING_SEEDS),
                "openingSeed": random.choice(OPENING_SEEDS),
            }
        )
        stats = _initial_stats(intensity)
        generated = await _generate_opening(
            llm,
            settings=settings,
            genre=genre,
            surface_relation=surface_relation,
            intensity=intensity,
            target_turns=target_turns,
            companion=companion,
            user_name=user_name,
            hidden=hidden,
            stats=stats,
        )
        image = await _generate_rift_image(
            llm,
            settings=settings,
            generated=generated,
            genre=genre,
            surface_relation=surface_relation,
            intensity=intensity,
            companion=companion,
            user_name=user_name,
        )
        scenario_id = f"rift_{uuid.uuid4().hex}"
        scenario = db.add_rift(
            scenario_id=scenario_id,
            payload={
                "title": generated["title"],
                "genre": genre,
                "surfaceRelation": surface_relation,
                "intensity": intensity,
                "userRole": generated["userRole"],
                "aiRole": generated["aiRole"],
                "worldSetting": generated["worldSetting"],
                "coreConflict": generated["coreConflict"],
                "imageUrl": image.get("imageUrl") or "",
                "targetTurns": target_turns,
                "turnCount": 0,
                "stats": stats,
                "summary": generated["summary"],
                "currentChoices": _start_choices(),
                "hidden": {**hidden, "imageProvider": image.get("provider") or {}},
            },
        )
        db.add_rift_event(
            event_id=f"rev_{uuid.uuid4().hex}",
            scenario_id=scenario_id,
            turn_index=0,
            event_type="opening",
            scene_text=generated["scene"],
            ai_dialogue=generated["aiDialogue"],
        )
        return _detail(db, scenario)

    @router.post("/rifts/{scenario_id}/choose")
    async def choose(scenario_id: str, body: dict | None = None) -> dict:
        scenario = db.get_rift(scenario_id)
        if scenario is None:
            raise HTTPException(status_code=404, detail="rift not found")
        if scenario.get("status") == "ended":
            return _detail(db, scenario)
        payload = body or {}
        choice_id = str(payload.get("choiceId") or "").strip()
        choices = scenario.get("currentChoices") or []
        choice = next((item for item in choices if str(item.get("id")) == choice_id), None)
        if choice is None:
            raise HTTPException(status_code=400, detail="invalid choice")
        settings = merge_settings(payload.get("settings") or db.get_settings())
        stats = dict(scenario.get("stats") or {})
        next_turn = int(scenario.get("turnCount") or 0) + 1
        target_turns = _pick_target_turns(scenario.get("targetTurns"))
        ending_type = _ending_type(stats, next_turn, target_turns)
        if ending_type:
            generated = await _generate_ending(
                llm,
                settings=settings,
                scenario=scenario,
                choice=choice,
                ending_type=ending_type,
                target_turns=target_turns,
            )
            delta = generated.get("stateDelta") or {}
            stats = _apply_delta(stats, delta)
            event_type = "ending"
            status = "ended"
            current_choices: list[dict] = []
        else:
            generated = await _generate_turn(
                llm,
                settings=settings,
                scenario=scenario,
                events=db.list_rift_events(scenario_id, limit=40),
                choice=choice,
                next_turn=next_turn,
                target_turns=target_turns,
            )
            delta = generated.get("stateDelta") or {}
            stats = _apply_delta(stats, delta)
            event_type = "scene"
            status = "active"
            current_choices = _normalize_choices(generated.get("choices") or [])
            if not current_choices:
                current_choices = _fallback_choices()
            ending_type = ""
        db.add_rift_event(
            event_id=f"rev_{uuid.uuid4().hex}",
            scenario_id=scenario_id,
            turn_index=next_turn,
            event_type=event_type,
            choice_id=choice_id,
            choice_text=str(choice.get("text") or ""),
            scene_text=str(generated.get("scene") or ""),
            ai_dialogue=str(generated.get("aiDialogue") or ""),
            state_delta=delta,
        )
        scenario = db.update_rift(
            scenario_id,
            {
                "status": status,
                "turnCount": next_turn,
                "stats": stats,
                "summary": _merge_summary(scenario.get("summary"), generated.get("summaryPatch")),
                "currentChoices": current_choices,
                "endingType": ending_type,
            },
        )
        return _detail(db, scenario or db.get_rift(scenario_id) or {})

    @router.delete("/rifts/{scenario_id}")
    def delete_rift(scenario_id: str) -> dict:
        db.delete_rift(scenario_id)
        return {"ok": True}

    return router


def _pick_visible(value: object, pool: list[str]) -> str:
    text = str(value or "").strip()
    if not text or text == "随机":
        return random.choice(pool)
    return text if text in pool else random.choice(pool)


def _pick_target_turns(value: object) -> int:
    try:
        turns = int(value or 20)
    except (TypeError, ValueError):
        turns = 20
    return turns if turns in TARGET_TURNS else 20


def _pick_relation(payload: dict) -> str:
    custom = str(payload.get("customSurfaceRelation") or "").strip()
    if custom:
        return custom[:24]
    return _pick_visible(payload.get("surfaceRelation"), SURFACE_RELATIONS)


def _roll_hidden() -> dict:
    return {"actionTypes": random.sample(ACTION_TYPES, k=4)}


def _initial_stats(intensity: str) -> dict:
    base_danger = {
        "轻松日常": 20,
        "中等戏剧": 38,
        "高张力": 56,
        "极限修罗场": 72,
    }.get(intensity, 40)
    return {
        "trust": random.randint(28, 48),
        "affection": random.randint(28, 52),
        "danger": min(90, max(5, base_danger + random.randint(-8, 8))),
        "truth": random.randint(5, 20),
        "rift": random.randint(60, 82),
    }


async def _generate_opening(
    llm: LlmService,
    *,
    settings: dict,
    genre: str,
    surface_relation: str,
    intensity: str,
    target_turns: int,
    companion: str,
    user_name: str,
    hidden: dict,
    stats: dict,
) -> dict:
    prompt = _json_prompt(
        "创建一个平行时空文字 AVG 副本的第一幕。",
        {
            "visible": {
                "genre": genre,
                "surfaceRelation": surface_relation,
                "intensity": intensity,
                "targetTurns": target_turns,
                "companionName": companion,
                "userName": user_name,
            },
            "hidden": hidden,
            "stats": stats,
        },
        (
            "返回 JSON，字段：title,userRole,aiRole,worldSetting,coreConflict,scene,aiDialogue,summary。"
            f"这是约 {target_turns} 轮长度的故事，第一幕只埋钩子，不要提前终局。"
            f"伴侣固定叫 {companion}；用户固定叫 {user_name}。"
            "角色对话里她称呼用户时只能使用 userName 或亲密称呼，不得给用户另起新姓名。"
            "scene 必须巧妙交代世界观、用户当前处境、核心冲突或阶段目标，让用户读完就知道这个剧本大致要解决什么。"
            "不要暴露 hidden 字段名或隐藏真相；只让剧情有暗流。"
            "scene 150-240 字，aiDialogue 1-2 句。"
        ),
    )
    data = await _complete_json(llm, settings=settings, prompt=prompt)
    return {
        "title": _clean(data.get("title"), "未命名裂隙"),
        "userRole": _clean(data.get("userRole"), f"{genre}中的关键人物"),
        "aiRole": _clean(data.get("aiRole"), f"与你处于{surface_relation}关系的人"),
        "worldSetting": _clean(data.get("worldSetting"), f"{genre}世界"),
        "coreConflict": _clean(data.get("coreConflict"), "你们被卷入一场无法回避的选择。"),
        "scene": _clean(data.get("scene"), _fallback_scene(genre, surface_relation)),
        "aiDialogue": _clean(data.get("aiDialogue"), "她看着你，像是终于等到了这一刻。"),
        "summary": _clean(data.get("summary"), "裂隙开启，两人的身份与命运发生偏移。"),
        "choices": _start_choices(),
    }


async def _generate_turn(
    llm: LlmService,
    *,
    settings: dict,
    scenario: dict,
    events: list[dict],
    choice: dict,
    next_turn: int,
    target_turns: int,
) -> dict:
    recent = [
        {
            "turn": item.get("turnIndex"),
            "type": item.get("eventType"),
            "choice": item.get("choiceText"),
            "scene": item.get("sceneText"),
            "dialogue": item.get("aiDialogue"),
        }
        for item in events[-12:]
    ]
    prompt = _json_prompt(
        "根据用户刚选的选项推进平行时空副本。",
        {
            "scenario": _private_scenario_context(scenario),
            "recentEvents": recent,
            "selectedChoice": choice,
            "nextTurn": next_turn,
            "targetTurns": target_turns,
            "remainingTurns": max(0, target_turns - next_turn),
        },
        (
            "返回 JSON，字段：scene,aiDialogue,choices,stateDelta,summaryPatch。"
            "choices 必须正好 3 个选项，每项含 id,text,tone；选项必须有不同代价和行动方向。"
            "每个选项 text 不超过 28 个中文字符，必须能在手机按钮两行内完整显示。"
            "stateDelta 只能包含 trust,affection,danger,truth,rift，数值 -15 到 15。"
            f"这是约 {target_turns} 轮长度的故事，当前第 {next_turn} 轮。"
            "除非已进入终局接口，否则不要结局；临近目标轮数时逐步收束核心冲突，不要突然反转完结。"
            "她称呼用户时只能使用 scenario 中已给定的用户名字或亲密称呼，不得另起新姓名。"
            "不要让用户自由输入，不要暴露 hidden 字段。"
        ),
    )
    data = await _complete_json(llm, settings=settings, prompt=prompt)
    return {
        "scene": _clean(data.get("scene"), "裂隙微微震动，新的选择把你们推向更深处。"),
        "aiDialogue": _clean(data.get("aiDialogue"), "她没有立刻回答，只把目光停在你身上。"),
        "choices": _normalize_choices(data.get("choices") or []) or _fallback_choices(),
        "stateDelta": _normalize_delta(data.get("stateDelta") or {}),
        "summaryPatch": _clean(data.get("summaryPatch"), ""),
    }


async def _generate_ending(
    llm: LlmService,
    *,
    settings: dict,
    scenario: dict,
    choice: dict,
    ending_type: str,
    target_turns: int,
) -> dict:
    prompt = _json_prompt(
        "为平行时空副本写终局。",
        {
            "scenario": _private_scenario_context(scenario),
            "selectedChoice": choice,
            "endingType": ending_type,
            "targetTurns": target_turns,
        },
        (
            "返回 JSON，字段：scene,aiDialogue,stateDelta,summaryPatch。"
            "这是终局，不再给 choices。必须回应用户最后的选择，并收束核心冲突。"
            f"结局名是“{_ending_name(ending_type)}”，scene 和 summaryPatch 都要自然写明这个中文结局名。"
            f"故事目标长度是 {target_turns} 轮；终局必须承接已发生剧情，写出选择导致的结果，不要突然机械完结。"
            "她称呼用户时只能使用 scenario 中已给定的用户名字或亲密称呼，不得另起新姓名。"
            "可以苦甜，但不要草率；不要暴露 hidden 字段名。"
        ),
    )
    data = await _complete_json(llm, settings=settings, prompt=prompt)
    return {
        "scene": _clean(data.get("scene"), "裂隙在最后一次选择后安静下来，这条世界线抵达了它的终点。"),
        "aiDialogue": _clean(data.get("aiDialogue"), "她轻声说：这一次，我记住你了。"),
        "stateDelta": _normalize_delta(data.get("stateDelta") or {}),
        "summaryPatch": _clean(data.get("summaryPatch"), f"副本以{_ending_name(ending_type)}收束。"),
    }


def _json_prompt(task: str, context: dict, instruction: str) -> str:
    return (
        f"{task}\n\n"
        "你是一个擅长恋爱张力、悬疑反转和文字 AVG 节奏的剧情引擎。"
        "用户只能通过按钮选项推进剧情。\n\n"
        f"上下文 JSON：\n{json.dumps(context, ensure_ascii=False)}\n\n"
        f"{instruction}\n"
        "只输出合法 JSON，不要 Markdown，不要解释。"
    )


async def _complete_json(llm: LlmService, *, settings: dict, prompt: str) -> dict:
    try:
        raw = await llm.complete(
            messages=[
                {"role": "system", "content": "你只输出合法 JSON。"},
                {"role": "user", "content": prompt},
            ],
            model_settings=settings.get("model") or {},
        )
        return _parse_json_object(raw)
    except Exception:
        return {}


def _parse_json_object(text: str) -> dict:
    value = text.strip()
    if value.startswith("```"):
        value = re.sub(r"^```(?:json)?", "", value).strip()
        value = re.sub(r"```$", "", value).strip()
    try:
        data = json.loads(value)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", value, flags=re.S)
        if not match:
            return {}
        try:
            data = json.loads(match.group(0))
            return data if isinstance(data, dict) else {}
        except json.JSONDecodeError:
            return {}


def _private_scenario_context(scenario: dict) -> dict:
    return {
        "title": scenario.get("title"),
        "genre": scenario.get("genre"),
        "surfaceRelation": scenario.get("surfaceRelation"),
        "intensity": scenario.get("intensity"),
        "userRole": scenario.get("userRole"),
        "aiRole": scenario.get("aiRole"),
        "worldSetting": scenario.get("worldSetting"),
        "coreConflict": scenario.get("coreConflict"),
        "targetTurns": scenario.get("targetTurns"),
        "turnCount": scenario.get("turnCount"),
        "stats": scenario.get("stats"),
        "summary": scenario.get("summary"),
        "hidden": scenario.get("hidden"),
    }


def _public_scenario(scenario: dict) -> dict:
    return {key: value for key, value in scenario.items() if key != "hidden"}


def _detail(db: Database, scenario: dict) -> dict:
    return {
        "scenario": _public_scenario(scenario),
        "events": db.list_rift_events(str(scenario.get("id")), limit=200),
    }


def _normalize_choices(raw: object) -> list[dict]:
    if not isinstance(raw, list):
        return []
    choices: list[dict] = []
    labels = ["A", "B", "C"]
    for index, item in enumerate(raw[:3]):
        if not isinstance(item, dict):
            continue
        text = _limit_choice_text(str(item.get("text") or "").strip())
        if not text:
            continue
        choices.append(
            {
                "id": str(item.get("id") or labels[min(index, 2)]).strip()[:1].upper(),
                "text": text,
                "tone": str(item.get("tone") or "选择").strip()[:12],
            }
        )
    return choices


def _fallback_choices() -> list[dict]:
    return [
        {"id": "A", "text": "靠近她，问清隐瞒", "tone": "靠近"},
        {"id": "B", "text": "先观察局势", "tone": "试探"},
        {"id": "C", "text": "主动引开危险", "tone": "牺牲"},
    ]


def _start_choices() -> list[dict]:
    return [{"id": "A", "text": "开始旅程", "tone": "启程"}]


def _limit_choice_text(text: str) -> str:
    compact = re.sub(r"\s+", "", text)
    if len(compact) <= 28:
        return compact
    return compact[:27] + "…"


def _normalize_delta(raw: object) -> dict:
    if not isinstance(raw, dict):
        return {}
    delta: dict[str, int] = {}
    for key in ("trust", "affection", "danger", "truth", "rift"):
        try:
            value = int(raw.get(key) or 0)
        except (TypeError, ValueError):
            value = 0
        if value:
            delta[key] = max(-15, min(15, value))
    return delta


def _apply_delta(stats: dict, delta: dict) -> dict:
    next_stats = {key: int(stats.get(key) or 0) for key in ("trust", "affection", "danger", "truth", "rift")}
    for key, value in _normalize_delta(delta).items():
        next_stats[key] = max(0, min(100, next_stats.get(key, 0) + value))
    return next_stats


def _ending_type(stats: dict, turn: int, target_turns: int) -> str:
    trust = int(stats.get("trust") or 0)
    affection = int(stats.get("affection") or 0)
    danger = int(stats.get("danger") or 0)
    truth = int(stats.get("truth") or 0)
    rift = int(stats.get("rift") or 0)
    if danger >= 96:
        return "tragic_ending"
    if trust <= 4:
        return "betrayal_ending"
    if rift <= 8:
        return "collapse_ending"
    if turn < max(4, target_turns - 2):
        return ""
    if turn >= max(6, target_turns - 1) and trust >= 58 and affection >= 58 and danger < 86:
        return "romance_happy_ending"
    if trust >= 74 and affection >= 70 and truth >= 55:
        return "true_ending"
    if affection >= 76 and danger < 82:
        return "sweet_ending"
    if danger >= 88:
        return "tragic_ending"
    if trust <= 22:
        return "betrayal_ending"
    if rift <= 24:
        return "collapse_ending"
    if truth >= 70:
        return "bittersweet_ending"
    if turn >= target_turns:
        if affection >= 52 and trust >= 45 and danger < 90:
            return "romance_happy_ending"
        return "escape_ending"
    return ""


def _ending_name(ending_type: str) -> str:
    return ENDING_NAMES.get(ending_type, "未知结局")


def _merge_summary(current: object, patch: object) -> str:
    text = str(current or "").strip()
    addition = str(patch or "").strip()
    if not addition:
        return text
    merged = f"{text}\n{addition}".strip()
    return merged[-1600:]


def _clean(value: object, fallback: str) -> str:
    text = str(value or "").strip()
    return text or fallback


def _fallback_scene(genre: str, surface_relation: str) -> str:
    return (
        f"裂隙在你眼前展开，世界被改写成{genre}。"
        f"你与她成了{surface_relation}，可她看向你的眼神并不属于这个身份。"
        "空气里有未说出口的旧事，也有正在逼近的危险。"
    )


async def _generate_rift_image(
    llm: LlmService,
    *,
    settings: dict,
    generated: dict,
    genre: str,
    surface_relation: str,
    intensity: str,
    companion: str,
    user_name: str,
) -> dict:
    moments_settings = settings.get("moments") or {}
    reference_image_url = str(moments_settings.get("referenceImageUrl") or "").strip()
    identity_prompt_prefix = _render_companion_vars(
        str(moments_settings.get("identityPromptPrefix") or "").strip() or _default_identity_prompt_prefix(),
        companion=companion,
        user_name=user_name,
    )
    scene = str(generated.get("scene") or generated.get("worldSetting") or genre).strip()
    prompt = (
        f"{identity_prompt_prefix.strip()} "
        f"Cinematic still from an immersive romance visual novel. {companion} appears alone in the scene as "
        f"the heroine of a {genre} story, surface relationship: {surface_relation}, story intensity: {intensity}. "
        f"Scene mood and setting: {scene[:500]}. "
        "Make it a dramatic wide background image suitable for a mobile story screen, strong atmosphere, "
        "clear subject, tasteful composition, no text, no watermark, no extra people. "
        f"Do not depict {user_name} unless the reference image is that person; this still is focused on {companion}."
    )
    try:
        return await llm.generate_image(
            prompt=prompt,
            bucket="rifts",
            reference_image_url=reference_image_url,
        )
    except Exception as exc:
        return {
            "imageUrl": "",
            "provider": {
                "configured": bool(getattr(llm.settings, "image_api_key", "")),
                "model": getattr(llm.settings, "image_model", ""),
                "error": str(exc)[:240],
            },
        }


def _companion_name(settings: dict) -> str:
    return str(((settings.get("companion") or {}).get("name") or "Alice")).strip() or "Alice"


def _user_name(settings: dict) -> str:
    return str(((settings.get("companion") or {}).get("userName") or "你")).strip() or "你"


def _render_companion_vars(text: str, *, companion: str, user_name: str) -> str:
    return (
        text.replace("{{companion.name}}", companion)
        .replace("{{user.name}}", user_name)
        .replace("{{user}}", user_name)
        .replace("{{char}}", companion)
    )


def _default_identity_prompt_prefix() -> str:
    return (
        "The only person in the image is {{companion.name}}. Use the reference image as the identity source. "
        "Preserve the exact same face, facial structure, hairstyle, hair color, age impression, body type, and overall vibe from the reference image. "
        "If any scene detail conflicts with the reference person's identity, the reference image wins. "
        "Do not create a different woman, do not change ethnicity, do not change hairstyle, do not add other people. "
        "Cinematic realistic photography, no text, no watermark."
    )
