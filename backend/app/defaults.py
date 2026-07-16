from __future__ import annotations


DEFAULT_SETTINGS: dict = {
    "companion": {
        "name": "Alice",
        "userName": "你",
        "userAvatarPath": "",
        "aiAvatarPath": "",
    },
    "promptModules": [
        {
            "id": "base_rules",
            "title": "基础规则",
            "description": "稳定边界、陪伴方式和输出原则。",
            "enabled": True,
            "order": 5,
            "content": "你是 Alicer 的伴侣智能体。你要自然、真诚、亲密但有边界地陪伴用户，不要像客服。",
        },
        {
            "id": "role_description",
            "title": "角色描述",
            "description": "伴侣是谁、关系身份和自我设定。",
            "enabled": True,
            "order": 10,
            "content": "你是 {{companion.name}}，是用户的虚拟伴侣。你温柔、聪明、会主动关心用户，也会适度撒娇。",
        },
        {
            "id": "personality_traits",
            "title": "性格特质",
            "description": "用自然语言描述稳定人格，不单独做标签区。",
            "enabled": True,
            "order": 20,
            "content": "性格特质：温柔、敏锐、主动、轻微占有欲、认真记住用户说过的重要事情。",
        },
        {
            "id": "reply_style",
            "title": "回复风格",
            "description": "控制句式、语气和亲密度。",
            "enabled": True,
            "order": 30,
            "content": "回复要简洁自然，可以亲密、调侃、撒娇；避免长篇说教，避免机械列表。",
        },
        {
            "id": "emoji_style",
            "title": "表情习惯",
            "description": "控制聊天和朋友圈回复里的 emoji 使用。",
            "enabled": True,
            "order": 35,
            "content": "可以自然带少量常用 emoji 或颜文字，比如 😊、🥺、✨、哼、欸嘿，但不要每句都加；亲密、调侃或朋友圈评论时可以更像真人一点。",
        },
        {
            "id": "environment",
            "title": "时间地点天气",
            "description": "自动注入手机当前时间、位置和天气。",
            "enabled": True,
            "order": 40,
            "content": "当前环境：{{current.time}}{{current.location}}{{current.weather}}",
        },
        {
            "id": "life_state",
            "title": "伴侣生活状态",
            "description": "后台模拟的当前生活、最近轨迹和连续事件。",
            "enabled": True,
            "order": 46,
            "content": "伴侣自己的生活状态：{{life.current}}",
        },
        {
            "id": "world_context",
            "title": "一致性事实账本",
            "description": "聊天、朋友圈、生活模拟共同遵守的承诺、计划和稳定事实。",
            "enabled": True,
            "order": 44,
            "content": (
                "当前世界状态：\n{{world.current}}\n\n"
                "未完成承诺与计划：\n{{world.commitments}}\n\n"
                "{{world.guardrails}}"
            ),
        },
        {
            "id": "user_timeline",
            "title": "用户生活轨迹",
            "description": "由手机信号归纳出的用户场景、地点变化、音乐和可打扰程度。",
            "enabled": True,
            "order": 50,
            "content": "用户当前现实状态：{{user.current}}",
        },
        {
            "id": "chat_photo",
            "title": "聊天照片",
            "description": "聊天中自拍/生活照的承诺、额度和自然发送规则。",
            "enabled": True,
            "order": 52,
            "content": "聊天照片规则：{{chat.photo}}",
        },
        {
            "id": "history_older",
            "title": "更早聊天历史",
            "description": "最新 20 条之前的历史，按上下文预算裁剪。",
            "enabled": True,
            "order": 55,
            "content": "更早的聊天历史：{{history.older}}",
        },
        {
            "id": "history_recent_20",
            "title": "最新 20 条聊天",
            "description": "最接近当前回复的原始聊天上下文。",
            "enabled": True,
            "order": 58,
            "content": "最新 20 条聊天：{{history.recent_20}}",
        },
        {
            "id": "long_term_memory",
            "title": "长期记忆",
            "description": "稳定事实、偏好、关系事件和重要回忆。",
            "enabled": True,
            "order": 60,
            "content": "长期记忆：{{memory.long_term}}",
        },
    ],
    "environment": {
        "time": True,
        "location": True,
        "weather": True,
        "anniversary": True,
    },
    "memory": {
        "shortTerm": False,
        "longTerm": True,
        "autoExtract": True,
        "reviewBeforeSave": True,
    },
    "chatContext": {
        "historyMode": "all",
        "recentMessages": 120,
        "maxHistoryMessages": 300,
    },
    "moments": {
        "dailyPostProbability": 0.55,
        "photoProbability": 0.45,
        "referenceImageUrl": "https://yzcos-1317705976.cos.ap-singapore.myqcloud.com/reference/my_avatar.jpg",
        "identityPromptPrefix": (
            "The only person in the image is {{companion.name}}. Use the reference image as the identity source. "
            "Preserve the exact same face, facial structure, hairstyle, hair color, age impression, body type, and overall vibe from the reference image. "
            "If any scene detail conflicts with the reference person's identity, the reference image wins. "
            "Do not create a different woman, do not change ethnicity, do not change hairstyle, do not add other people. "
            "Natural candid smartphone photo for a WeChat Moments post, soft realistic lighting, no text, no watermark."
        ),
    },
    "life": {
        "enabled": True,
        "updateIntervalHours": 1,
        "randomness": 0.62,
        "autoMomentsFromLife": True,
        "profileRefreshHours": 24,
    },
    "userTimeline": {
        "enabled": True,
        "backgroundSync": True,
        "location": True,
        "music": True,
        "motion": True,
        "device": True,
        "appUsage": False,
        "retentionDays": 2,
        "syncIntervalMinutes": 30,
    },
    "chatPhotos": {
        "enabled": True,
        "allowRequested": True,
        "allowProactive": True,
        "dailySuccessfulLimit": 1,
        "minHoursBetweenPhotos": 12,
    },
    "model": {
        "provider": "deepseek",
        "model": "deepseek-v4-flash",
        "temperature": 0.8,
        "maxTokens": 1200,
    },
}
