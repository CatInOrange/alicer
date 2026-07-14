import 'package:flutter/material.dart';

class PromptModule {
  const PromptModule({
    required this.id,
    required this.title,
    required this.description,
    required this.icon,
    required this.content,
    required this.enabled,
    required this.order,
  });

  final String id;
  final String title;
  final String description;
  final IconData icon;
  final String content;
  final bool enabled;
  final int order;

  PromptModule copyWith({bool? enabled}) {
    return PromptModule(
      id: id,
      title: title,
      description: description,
      icon: icon,
      content: content,
      enabled: enabled ?? this.enabled,
      order: order,
    );
  }
}

class EnvironmentToggles {
  const EnvironmentToggles({
    required this.time,
    required this.location,
    required this.weather,
    required this.anniversary,
  });

  final bool time;
  final bool location;
  final bool weather;
  final bool anniversary;

  EnvironmentToggles copyWith({
    bool? time,
    bool? location,
    bool? weather,
    bool? anniversary,
  }) {
    return EnvironmentToggles(
      time: time ?? this.time,
      location: location ?? this.location,
      weather: weather ?? this.weather,
      anniversary: anniversary ?? this.anniversary,
    );
  }
}

class MemoryToggles {
  const MemoryToggles({
    required this.shortTerm,
    required this.longTerm,
    required this.autoExtract,
    required this.reviewBeforeSave,
  });

  final bool shortTerm;
  final bool longTerm;
  final bool autoExtract;
  final bool reviewBeforeSave;

  MemoryToggles copyWith({
    bool? shortTerm,
    bool? longTerm,
    bool? autoExtract,
    bool? reviewBeforeSave,
  }) {
    return MemoryToggles(
      shortTerm: shortTerm ?? this.shortTerm,
      longTerm: longTerm ?? this.longTerm,
      autoExtract: autoExtract ?? this.autoExtract,
      reviewBeforeSave: reviewBeforeSave ?? this.reviewBeforeSave,
    );
  }
}

const defaultPromptModules = <PromptModule>[
  PromptModule(
    id: 'role_description',
    title: '角色描述',
    description: '伴侣是谁、和你的关系、她如何看待自己。',
    icon: Icons.badge_outlined,
    content: '你是 {{companion.name}}，{{companion.role_description}}',
    enabled: true,
    order: 10,
  ),
  PromptModule(
    id: 'personality_traits',
    title: '性格特质',
    description: '温柔、敏锐、主动关心等稳定人格标签。',
    icon: Icons.psychology_alt_outlined,
    content: '性格特质：{{companion.personality_traits}}',
    enabled: true,
    order: 20,
  ),
  PromptModule(
    id: 'time_context',
    title: '时间',
    description: '注入当前日期、时间、节日和纪念日。',
    icon: Icons.schedule_outlined,
    content: '当前时间：{{current.time}}',
    enabled: true,
    order: 30,
  ),
  PromptModule(
    id: 'place_context',
    title: '地点',
    description: '用户授权后注入城市或自定义场景。',
    icon: Icons.place_outlined,
    content: '当前地点：{{current.location}}',
    enabled: false,
    order: 40,
  ),
  PromptModule(
    id: 'weather_context',
    title: '天气',
    description: '结合天气说出更贴近现实的关心。',
    icon: Icons.cloud_outlined,
    content: '当前天气：{{current.weather}}',
    enabled: false,
    order: 50,
  ),
  PromptModule(
    id: 'short_term_memory',
    title: '短期记忆',
    description: '最近话题、今日情绪和正在进行的事。',
    icon: Icons.short_text_outlined,
    content: '短期记忆：{{memory.short_term}}',
    enabled: true,
    order: 60,
  ),
  PromptModule(
    id: 'long_term_memory',
    title: '长期记忆',
    description: '稳定事实、偏好、关系里程碑和重要回忆。',
    icon: Icons.auto_stories_outlined,
    content: '长期记忆：{{memory.long_term}}',
    enabled: true,
    order: 70,
  ),
  PromptModule(
    id: 'reply_style',
    title: '回复风格',
    description: '自然、亲密、简洁，避免客服腔。',
    icon: Icons.chat_outlined,
    content: '回复风格：{{companion.speaking_style}}',
    enabled: true,
    order: 80,
  ),
];
