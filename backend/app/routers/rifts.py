from __future__ import annotations

import json
import random
import re
import uuid

from fastapi import APIRouter, HTTPException

from ..db import Database
from ..services.llm_service import GROK_REFERENCE_IMAGE_URL, LlmService
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
    "collapse_ending": "失控崩塌结局",
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
    "一方隐瞒现实压力",
    "一方曾经错过约定",
    "一方正在保护另一方",
    "目标暂时一致",
    "价值观互相吸引",
    "互为软肋",
    "共同背负责任",
    "被迫站到对立立场",
    "暗中同盟",
    "表面冷淡实际依赖",
    "互相救过命",
    "一方曾经替对方承担后果",
    "共享同一个秘密",
    "彼此都是对方任务目标",
    "一方正准备离开",
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
    "她明明在意却假装疏远",
    "你曾经伤害过她",
    "她在替你承受代价",
    "你们被迫共用同一份资源",
    "她掌握你要完成目标的关键",
    "你是她任务里的唯一变数",
    "你们都以为对方背叛了自己",
    "她必须亲手否定你的方案",
    "你醒来后成为她的敌人",
    "她保护你的方式像背叛",
    "世俗眼光要求你们保持距离",
    "你们的相爱会毁掉当前秩序",
    "她看似掌控一切实则被胁迫",
    "你们只能有一个人留下",
    "她以为你已经放弃她",
    "你必须假装不爱她",
]

SECRET_SEEDS = [
    "她一直在替你隐瞒真正风险",
    "你的公开身份会让她陷入麻烦",
    "她的冷漠来自无法说出口的约定",
    "你们曾经一起处理过一场失败",
    "她手里的证据会毁掉计划也会救你",
    "她身边最可信的人正在操控她",
    "你忽略的细节里藏着她的付出",
    "她每帮你一次都会失去重要筹码",
    "你以为的敌人曾经是你们的盟友",
    "她知道终局代价但不愿告诉你",
    "你拥有改变局势的唯一筹码",
    "她必须完成任务才能保住你的命",
    "你们的关系被人刻意改写过",
    "她背负的家族秘密与你有关",
    "你正在追查的真相会伤害她",
    "她早就预判过你会做出的选择",
    "你们身上的责任会互相牵连",
    "她向所有人撒谎只为保留你的退路",
    "最终阻力来自你们共同信任的人",
    "你曾经亲手推开她",
    "她的真实身份不能被你说出口",
    "当前秩序正在利用你们的关系",
]

TWIST_SEEDS = [
    "保护者其实也是囚徒",
    "任务目标与救赎目标是同一个人",
    "真正的背叛来自第三方伪造",
    "她从一开始就在赌你会识破她",
    "你一直在替过去的决定收拾残局",
    "你们的敌对身份是同一组织安排的试炼",
    "她的伤口会暴露她站在你这边",
    "看似随机的事故其实是她留下的暗号",
    "你以为的自由选择早被对手预判",
    "她的失控是为了把你推出陷阱",
    "你的盟友才是真正的操盘手",
    "她故意让你恨她以保住你的判断",
    "终局需要你主动违背最初目标",
    "你们的公开关系只是隐藏契约的一层壳",
    "她害怕的不是失败而是你知道代价",
    "你越接近真相她越必须远离",
    "最后的钥匙是一次没有说出口的选择",
    "她在不同场合留下了互相矛盾的证言",
    "你被追捕不是因为罪行而是因为价值",
    "她的阵营内部早已分裂",
    "你们都被同一个谎言保护着",
    "规则会奖励残酷选择但惩罚逃避",
]

ENDING_SEEDS = [
    "秘密揭开后共同承担代价",
    "放弃既得利益换取两人离开",
    "用真相修复关系但留下遗憾",
    "她替你完成最后牺牲",
    "你替她背下无法洗清的罪名",
    "两人站到世界秩序的对立面",
    "关系圆满但身份永远无法公开",
    "误会解除得太晚只能留下信物",
    "局势崩塌前只保住一份承诺",
    "你们选择重新开始但不再拥有过去",
    "她成为新秩序的守门人",
    "你们一起伪造死亡离开棋局",
    "真相公开后所有人都成为敌人",
    "她终于承认爱意却必须放你走",
    "你们把结局交给未来的自己",
    "一方堕入黑暗另一方选择同行",
    "你们救下彼此但失去胜利",
    "终局证明最初相遇并非偶然",
    "她打破契约但付出身份代价",
    "你主动放弃目标保住她的生活",
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

WORLD_THEME_POOLS = {
    "古风权谋": ["夺嫡暗潮", "边关和亲", "朝堂翻案", "密诏护送", "家族沉冤", "女官升迁", "王府避祸", "商路夺权", "宫宴试探", "旧案重审"],
    "仙侠师门": ["宗门试炼", "秘境护送", "除魔同行", "灵脉危机", "剑冢传承", "禁术反噬", "门规审判", "仙盟大比", "妖祸平乱", "飞升抉择"],
    "现代都市": ["职场暗涌", "项目翻盘", "合租边界", "创业危机", "家族压力", "都市救援", "酒会误会", "旧友重逢", "地下恋情", "事业抉择"],
    "校园青春": ["社团竞赛", "毕业约定", "补习攻防", "运动会赌约", "校园流言", "升学分歧", "天台告白", "交换日记", "班级危机", "青春和解"],
    "赛博霓虹": ["黑客追踪", "义体失控", "企业潜入", "数据交易", "地下竞速", "仿生人审判", "数据逃亡", "霓虹悬赏", "身份加密", "城市断电"],
    "末日废土": ["荒城求生", "补给争夺", "避难所内斗", "感染倒计时", "车队远征", "荒岛生存", "废墟电台", "净土传闻", "救援抉择", "寒潮迁徙"],
    "民国旧梦": ["报馆风波", "码头暗线", "戏院旧约", "家族婚约", "租界追查", "商会博弈", "书信错递", "谍影护送", "雨巷重逢", "火车离城"],
    "西幻王庭": ["王位试炼", "龙灾远征", "骑士誓约", "魔法学院", "圣物护送", "边境叛乱", "贵族婚约", "森林诅咒", "王庭舞会", "魔王讨伐"],
    "悬疑怪谈": ["旧楼调查", "规则怪谈", "失踪追查", "夜校谜案", "剧院诅咒", "旅馆求生", "档案重启", "村庄禁忌", "梦境审讯", "真凶博弈"],
    "星际远航": ["星舰失联", "殖民星救援", "跃迁事故", "外星遗迹", "舰队叛乱", "深空求生", "外交危机", "AI审判", "能源争夺", "归航倒计时"],
    "娱乐圈": ["综艺搭档", "黑料澄清", "剧组暗恋", "颁奖夜博弈", "限定营业", "舞台救场", "经纪合约", "粉丝风波", "复出计划", "电影试镜"],
    "黑帮夜色": ["地盘谈判", "卧底边缘", "债务赎身", "码头交易", "家族继承", "夜店风波", "保镖护送", "叛徒清查", "危险联盟", "逃离组织"],
}

RELATION_THEME_POOLS = {
    "师徒": ["禁忌心动", "传承与越界", "门规压力", "救赎教学", "师门审判", "共同破局", "偏爱被揭穿", "离师独立", "守护与放手", "名分重定"],
    "同门": ["并肩试炼", "竞争出头", "旧怨和解", "师门危机", "双人任务", "资源争夺", "暗中偏袒", "互为榜样", "流言澄清", "共同背责"],
    "同事": ["项目危机", "办公室暧昧", "竞聘对手", "并肩加班", "职场流言", "客户攻坚", "秘密恋情", "离职抉择", "创业邀约", "责任背锅"],
    "搭档": ["任务分歧", "默契考验", "临场救援", "信任重建", "共同潜入", "目标冲突", "互相掩护", "搭档拆组", "战术诱饵", "最终协作"],
    "上下级": ["权力边界", "升迁选择", "公开偏袒", "责任追究", "越级保护", "办公室试探", "制度压力", "信任授权", "离职挽留", "共同担责"],
    "主仆": ["忠诚试炼", "身份越界", "护主逃亡", "契约松动", "旧恩偿还", "名分反转", "秘密守护", "自由选择", "阶层压力", "生死托付"],
    "主奴": ["支配边界", "依赖反转", "忠诚与自由", "危险占有", "契约重写", "保护服从", "反抗试探", "身份解放", "信任驯化", "共同逃离"],
    "契约双方": ["契约恋爱", "假戏真做", "利益交换", "违约代价", "期限倒计时", "条款重写", "公开演戏", "秘密加码", "信任谈判", "终止选择"],
    "监护人与被监护人": ["责任边界", "成长独立", "保护过度", "旧案牵连", "成年抉择", "家庭阻力", "安全与自由", "信任放手", "外界审视", "依赖改变"],
    "贵族与侍从": ["阶层禁恋", "礼法试探", "护送逃亡", "继承危机", "忠诚与名分", "舞会掩护", "家族审判", "秘密私奔", "身份赦免", "权力交换"],
    "君臣": ["忠义两难", "帝位危机", "谏言触怒", "托孤承诺", "权臣试探", "朝堂公开", "私情与社稷", "兵权交付", "叛乱平定", "退位选择"],
    "邻居": ["近水楼台", "误会互助", "社区危机", "深夜求助", "旧物牵线", "边界试探", "搬家倒计时", "共同照料", "邻里流言", "日常告白"],
    "同学": ["校园暗恋", "成绩竞争", "社团搭档", "毕业倒计时", "流言压力", "补习约定", "班级危机", "青春赌约", "升学分叉", "天台坦白"],
    "室友": ["同居边界", "生活磨合", "秘密曝光", "合租危机", "照顾生病", "账单争执", "临时伪装", "搬离抉择", "夜谈破防", "日久生情"],
    "雇主与保镖": ["护送任务", "贴身保护", "安全与自由", "雇佣边界", "危险诱饵", "信任授权", "替身挡刀", "任务终止", "身份曝光", "逃亡同行"],
    "追捕者与嫌疑人": ["追逃博弈", "真凶反转", "证据交换", "临时合作", "审讯心动", "逃亡护送", "信任试探", "罪名洗清", "放手或逮捕", "共同缉凶"],
    "审讯者与囚徒": ["攻防审讯", "证词交易", "心理拉扯", "越狱合作", "冤案翻供", "权力反转", "信任破冰", "替罪风险", "放人与留人", "真相公开"],
    "神明与信徒": ["信仰动摇", "神谕试炼", "献祭阻止", "神格坠落", "祈愿代价", "人间同行", "信徒反叛", "神迹伪装", "拯救苍生", "爱与信仰"],
    "召唤者与被召唤者": ["契约召唤", "异界适应", "命令边界", "反向守护", "召回倒计时", "契约破损", "共同升级", "身份误认", "留在此界", "解除束缚"],
    "敌对阵营": ["立场对决", "战场救援", "卧底试探", "停战谈判", "共同敌人", "阵营背叛", "秘密会面", "信念动摇", "私奔逃离", "和平代价"],
    "陌生人": ["临时同行", "误拿行李", "共同避险", "一日约定", "身份猜测", "互相利用", "旅途靠近", "秘密委托", "救命之恩", "重逢选择"],
}

DEFAULT_RELATION_THEMES = ["共同目标", "误会和解", "并肩求生", "秘密协作", "情感试探", "身份压力", "目标竞争", "互相救援", "公开选择", "终局告白"]


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
        story_theme = _roll_story_theme(genre, surface_relation)
        hidden = _roll_hidden()
        hidden.update(
            {
                "storyTheme": story_theme,
                "romanceTone": random.choice(ROMANCE_TONES),
                "relationshipHistory": random.choice(TRUE_RELATIONSHIPS),
                "relationshipTwist": random.choice(TROPE_SEEDS),
                "personalStake": random.choice(SECRET_SEEDS),
                "midpointTurn": random.choice(TWIST_SEEDS),
                "endingSeed": random.choice(ENDING_SEEDS),
                "openingBeat": random.choice(OPENING_SEEDS),
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
        stats = _apply_delta(stats, choice.get("impact") or {})
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
                "summary": (
                    _ending_summary(generated.get("summaryPatch"), ending_type)
                    if status == "ended"
                    else _merge_summary(scenario.get("summary"), generated.get("summaryPatch"))
                ),
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


def _roll_story_theme(genre: str, relation: str) -> dict:
    themes = _compatible_story_themes(genre, relation)
    return random.choice(themes)


def _compatible_story_themes(genre: str, relation: str) -> list[dict]:
    world_pool = WORLD_THEME_POOLS.get(genre) or WORLD_THEME_POOLS["现代都市"]
    relation_pool = RELATION_THEME_POOLS.get(relation) or DEFAULT_RELATION_THEMES
    count = max(10, min(len(world_pool), len(relation_pool)))
    themes: list[dict] = []
    for index in range(count):
        world_hook = world_pool[index % len(world_pool)]
        relation_arc = relation_pool[(index * 3) % len(relation_pool)]
        themes.append(
            {
                "name": f"{world_hook}·{relation_arc}",
                "worldHook": world_hook,
                "relationArc": relation_arc,
                "goal": _theme_goal(world_hook, relation_arc, relation),
                "endingRoutes": _ending_routes_for_arc(relation_arc),
            }
        )
    return themes


def _theme_goal(world_hook: str, relation_arc: str, relation: str) -> str:
    return f"围绕“{world_hook}”解决外部目标，同时让“{relation}”关系经历“{relation_arc}”的选择压力。"


def _ending_routes_for_arc(relation_arc: str) -> list[str]:
    routes = ["共同达成目标并确认恋爱", "目标达成但关系保留遗憾", "关系升温却牺牲外部目标", "信任破裂导致分离"]
    if any(key in relation_arc for key in ("竞争", "对决", "追逃", "审讯", "权力", "阵营")):
        routes.append("立场无法调和但互相放过")
    else:
        routes.append("跨过外界压力后公开选择彼此")
    return routes


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
        "pressure": random.randint(36, 68),
        "goal": random.randint(18, 38),
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
        "创建一个沉浸式文字 AVG 剧本的第一幕。",
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
            "产品功能名叫“时空裂隙”，但它不是剧情设定；正文、标题、台词、世界观、结局名不得出现“裂隙”或把故事写成时空异常，除非用户选择的世界主题明确要求。"
            f"世界主题必须严格属于“{genre}”，身份关系必须严格保持为“{surface_relation}”；hidden 只能在这个关系内制造冲突，不得改写为师生、同事、主仆、医患等其他关系。"
            f"伴侣固定叫 {companion}；用户固定叫 {user_name}。"
            "角色对话里她称呼用户时只能使用 userName 或亲密称呼，不得给用户另起新姓名。"
            "必须围绕 hidden.storyTheme.name、goal、endingRoutes 设计剧本，不要默认写失忆、时间线、被改写记忆或悬疑阴谋。"
            "scene 必须巧妙交代世界观、用户当前处境、核心冲突或阶段目标，让用户读完就知道这个剧本大致要解决什么。"
            "不要暴露 hidden 字段名或隐藏真相；只让剧情有暗流。"
            "scene 150-240 字，aiDialogue 1-2 句。"
        ),
    )
    data = await _complete_json(llm, settings=settings, prompt=prompt)
    return {
        "title": _clean(data.get("title"), "未命名剧本"),
        "userRole": _clean(data.get("userRole"), f"{genre}中的关键人物"),
        "aiRole": _clean(data.get("aiRole"), f"与你处于{surface_relation}关系的人"),
        "worldSetting": _clean(data.get("worldSetting"), f"{genre}世界"),
        "coreConflict": _clean(data.get("coreConflict"), "你们被卷入一场无法回避的选择。"),
        "scene": _clean(data.get("scene"), _fallback_scene(genre, surface_relation)),
        "aiDialogue": _clean(data.get("aiDialogue"), "她看着你，像是终于等到了这一刻。"),
        "summary": _clean(data.get("summary"), f"剧本以{genre}为舞台，围绕{surface_relation}关系展开。"),
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
        "根据用户刚选的选项推进沉浸式文字剧本。",
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
            "choices 必须正好 3 个选项，每项含 id,text,tone,impact；选项必须有不同代价和行动方向。"
            "每个选项 text 不超过 28 个中文字符，必须能在手机按钮两行内完整显示。"
            "每个选项都必须让玩家纠结：情感、信任、危险、目标进度、真相或外界压力至少两项互相拉扯，不允许三个选项只是同义推进剧情。"
            "impact 写该选项倾向影响的隐藏数值，例如 {affection:+8,danger:+5,goal:-3}；不同选项必须导向不同结局路线。"
            "stateDelta 只能包含 trust,affection,danger,truth,pressure,goal，数值 -15 到 15。"
            f"这是约 {target_turns} 轮长度的故事，当前第 {next_turn} 轮。"
            "除非已进入终局接口，否则不要结局；临近目标轮数时逐步收束核心冲突，不要突然反转完结。"
            "产品功能名叫“时空裂隙”，但它不是剧情设定；正文、标题、台词、世界观、结局名不得出现“裂隙”或把故事写成时空异常。"
            "必须保持 scenario.genre 和 scenario.surfaceRelation，不得中途改写两人的身份关系。"
            "推进必须服务 scenario.hidden.storyTheme.goal 和 endingRoutes，让选择逐步影响结局路线。"
            "她称呼用户时只能使用 scenario 中已给定的用户名字或亲密称呼，不得另起新姓名。"
            "不要让用户自由输入，不要暴露 hidden 字段。"
        ),
    )
    data = await _complete_json(llm, settings=settings, prompt=prompt)
    return {
        "scene": _clean(data.get("scene"), "新的选择让局势继续逼近关键节点。"),
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
        "为沉浸式文字剧本写终局。",
        {
            "scenario": _private_scenario_context(scenario),
            "selectedChoice": choice,
            "endingType": ending_type,
            "targetTurns": target_turns,
        },
        (
            "返回 JSON，字段：scene,aiDialogue,stateDelta,summaryPatch。"
            "这是终局，不再给 choices。必须回应用户最后的选择，并收束核心冲突。"
            f"结局名是“{_ending_name(ending_type)}”，scene 可以自然写明这个中文结局名。"
            f"故事目标长度是 {target_turns} 轮；终局必须承接已发生剧情，写出最后选择导致的结果，不要突然机械完结。"
            "scene 只写终局当下的一小段，不要从第一幕开始复述。"
            "summaryPatch 是展示在结局名下方的最终结语，只能 1-2 句，不超过 70 个中文字符，不要复述完整剧情。"
            "如果是圆满、真相相守、甜蜜、携手逃亡等正向结局，summaryPatch 写一句祝福或余韵，例如有情人终成眷属。"
            "如果是悲剧、背离、失控等负向结局，summaryPatch 用一句话暗示原因或教训，例如不要轻信陌生人。"
            "她称呼用户时只能使用 scenario 中已给定的用户名字或亲密称呼，不得另起新姓名。"
            "不得把产品名“时空裂隙”或“裂隙”写进剧情。"
            "可以苦甜，但不要草率；不要暴露 hidden 字段名。"
        ),
    )
    data = await _complete_json(llm, settings=settings, prompt=prompt)
    return {
        "scene": _clean(data.get("scene"), "最后一次选择落定，这段故事抵达了它的终点。"),
        "aiDialogue": _clean(data.get("aiDialogue"), "她轻声说：这一次，我记住你了。"),
        "stateDelta": _normalize_delta(data.get("stateDelta") or {}),
        "summaryPatch": _clean(data.get("summaryPatch"), f"剧本以{_ending_name(ending_type)}收束。"),
    }


def _json_prompt(task: str, context: dict, instruction: str) -> str:
    return (
        f"{task}\n\n"
        "你是一个擅长多题材恋爱、冒险、生存、目标挑战和文字 AVG 节奏的剧情引擎。"
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
        choice = {
            "id": str(item.get("id") or labels[min(index, 2)]).strip()[:1].upper(),
            "text": text,
            "tone": str(item.get("tone") or "选择").strip()[:12],
        }
        impact = _normalize_delta(item.get("impact") or {})
        if impact:
            choice["impact"] = impact
        choices.append(choice)
    if 0 < len(choices) < 3:
        used = {item["id"] for item in choices}
        for fallback in _fallback_choices():
            if fallback["id"] not in used:
                choices.append(fallback)
            if len(choices) >= 3:
                break
    return choices


def _fallback_choices() -> list[dict]:
    return [
        {"id": "A", "text": "坦白靠近她", "tone": "情感", "impact": {"affection": 8, "danger": 4, "goal": -2}},
        {"id": "B", "text": "优先完成目标", "tone": "理性", "impact": {"goal": 8, "trust": -3, "pressure": 4}},
        {"id": "C", "text": "替她承担风险", "tone": "守护", "impact": {"trust": 7, "danger": 7, "truth": -2}},
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
    for key in ("trust", "affection", "danger", "truth", "pressure", "goal"):
        try:
            value = int(raw.get(key) or 0)
        except (TypeError, ValueError):
            value = 0
        if value:
            delta[key] = max(-15, min(15, value))
    return delta


def _apply_delta(stats: dict, delta: dict) -> dict:
    next_stats = {
        key: int(stats.get(key) or 0)
        for key in ("trust", "affection", "danger", "truth", "pressure", "goal")
    }
    for key, value in _normalize_delta(delta).items():
        next_stats[key] = max(0, min(100, next_stats.get(key, 0) + value))
    return next_stats


def _ending_type(stats: dict, turn: int, target_turns: int) -> str:
    trust = int(stats.get("trust") or 0)
    affection = int(stats.get("affection") or 0)
    danger = int(stats.get("danger") or 0)
    truth = int(stats.get("truth") or 0)
    pressure = int(stats.get("pressure", stats.get("rift") or 50) or 0)
    goal = int(stats.get("goal") or 0)
    if danger >= 96:
        return "tragic_ending"
    if trust <= 4:
        return "betrayal_ending"
    if pressure >= 96:
        return "collapse_ending"
    if turn < max(4, target_turns - 2):
        return ""
    if turn >= max(6, target_turns - 1) and trust >= 58 and affection >= 58 and danger < 86:
        return "romance_happy_ending"
    if trust >= 74 and affection >= 70 and (truth >= 55 or goal >= 65):
        return "true_ending"
    if affection >= 76 and danger < 82:
        return "sweet_ending"
    if danger >= 88:
        return "tragic_ending"
    if trust <= 22:
        return "betrayal_ending"
    if pressure >= 88:
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


def _ending_summary(patch: object, ending_type: str) -> str:
    text = re.sub(r"\s+", "", str(patch or "").strip())
    if text:
        parts = re.findall(r"[^。！？!?]+[。！？!?]?", text)
        text = "".join(parts[:2]).strip()
    if not text:
        text = _fallback_ending_summary(ending_type)
    if len(text) > 70:
        text = text[:69].rstrip("，、；：,. ") + "…"
    return text


def _fallback_ending_summary(ending_type: str) -> str:
    if ending_type in {"romance_happy_ending", "true_ending", "sweet_ending", "escape_ending"}:
        return "愿有情人终成眷属，从此并肩走向下一程。"
    if ending_type == "bittersweet_ending":
        return "有些告别也是守护，愿你们都记得曾经真心相待。"
    if ending_type == "betrayal_ending":
        return "背叛往往始于轻信，别把真心交给看不清的人。"
    if ending_type == "collapse_ending":
        return "失控并非一瞬造成，越危险时越要守住清醒。"
    if ending_type == "tragic_ending":
        return "悲剧多半藏在迟疑与误信里，下一次别再错过真相。"
    return "故事到此落幕，愿你记得最后一次选择的重量。"


def _clean(value: object, fallback: str) -> str:
    text = str(value or "").strip()
    return text or fallback


def _fallback_scene(genre: str, surface_relation: str) -> str:
    return (
        f"故事从{genre}的一场关键变故开始。"
        f"你与她保持着{surface_relation}的关系，却被同一个目标推到必须并肩的位置。"
        "空气里有未说出口的心意，也有正在逼近的选择。"
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
    reference_image_url = GROK_REFERENCE_IMAGE_URL
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
        "Keep the heroine's face, facial structure, hairstyle, hair color, age impression, body type, and overall vibe exactly consistent with the reference image. "
        "If the story setting or costume conflicts with the reference person's identity, preserve the reference face and hairstyle first. "
        "Make it a dramatic wide background image suitable for a mobile story screen, strong atmosphere, "
        "clear subject, tasteful composition, no text, no watermark, no extra people. "
        f"Do not depict {user_name} unless the reference image is that person; this still is focused on {companion}."
    )
    try:
        return await llm.generate_image(
            prompt=prompt,
            bucket="rifts",
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
