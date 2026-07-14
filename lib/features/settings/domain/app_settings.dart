import 'package:flutter/material.dart';

class CompanionProfile {
  const CompanionProfile({
    this.name = 'Alice',
    this.userName = '你',
    this.userAvatarPath = '',
    this.aiAvatarPath = '',
  });

  final String name;
  final String userName;
  final String userAvatarPath;
  final String aiAvatarPath;

  factory CompanionProfile.fromJson(Map<String, dynamic> json) {
    return CompanionProfile(
      name: (json['name'] ?? 'Alice').toString(),
      userName: (json['userName'] ?? '你').toString(),
      userAvatarPath: (json['userAvatarPath'] ?? '').toString(),
      aiAvatarPath: (json['aiAvatarPath'] ?? '').toString(),
    );
  }

  Map<String, dynamic> toJson() => {
    'name': name,
    'userName': userName,
    'userAvatarPath': userAvatarPath,
    'aiAvatarPath': aiAvatarPath,
  };

  CompanionProfile copyWith({
    String? name,
    String? userName,
    String? userAvatarPath,
    String? aiAvatarPath,
  }) {
    return CompanionProfile(
      name: name ?? this.name,
      userName: userName ?? this.userName,
      userAvatarPath: userAvatarPath ?? this.userAvatarPath,
      aiAvatarPath: aiAvatarPath ?? this.aiAvatarPath,
    );
  }
}

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

  factory PromptModule.fromJson(Map<String, dynamic> json) {
    return PromptModule(
      id: (json['id'] ?? '').toString(),
      title: (json['title'] ?? '').toString(),
      description: (json['description'] ?? '').toString(),
      icon: promptModuleIcon((json['id'] ?? '').toString()),
      content: (json['content'] ?? '').toString(),
      enabled: json['enabled'] != false,
      order: (json['order'] as num?)?.toInt() ?? 0,
    );
  }

  Map<String, dynamic> toJson() => {
    'id': id,
    'title': title,
    'description': description,
    'enabled': enabled,
    'order': order,
    'content': content,
  };

  PromptModule copyWith({bool? enabled, String? content}) {
    return PromptModule(
      id: id,
      title: title,
      description: description,
      icon: icon,
      content: content ?? this.content,
      enabled: enabled ?? this.enabled,
      order: order,
    );
  }
}

class EnvironmentToggles {
  const EnvironmentToggles({
    this.time = true,
    this.location = true,
    this.weather = true,
    this.anniversary = true,
  });

  final bool time;
  final bool location;
  final bool weather;
  final bool anniversary;

  factory EnvironmentToggles.fromJson(Map<String, dynamic> json) {
    return EnvironmentToggles(
      time: json['time'] != false,
      location: json['location'] != false,
      weather: json['weather'] != false,
      anniversary: json['anniversary'] != false,
    );
  }

  Map<String, dynamic> toJson() => {
    'time': time,
    'location': location,
    'weather': weather,
    'anniversary': anniversary,
  };

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
    this.shortTerm = true,
    this.longTerm = true,
    this.autoExtract = true,
    this.reviewBeforeSave = true,
  });

  final bool shortTerm;
  final bool longTerm;
  final bool autoExtract;
  final bool reviewBeforeSave;

  factory MemoryToggles.fromJson(Map<String, dynamic> json) {
    return MemoryToggles(
      shortTerm: json['shortTerm'] != false,
      longTerm: json['longTerm'] != false,
      autoExtract: json['autoExtract'] != false,
      reviewBeforeSave: json['reviewBeforeSave'] != false,
    );
  }

  Map<String, dynamic> toJson() => {
    'shortTerm': shortTerm,
    'longTerm': longTerm,
    'autoExtract': autoExtract,
    'reviewBeforeSave': reviewBeforeSave,
  };

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

class ModelSettings {
  const ModelSettings({
    this.provider = 'deepseek',
    this.model = defaultDeepSeekModelId,
    this.temperature = 0.8,
    this.maxTokens = 1200,
  });

  final String provider;
  final String model;
  final double temperature;
  final int maxTokens;

  factory ModelSettings.fromJson(Map<String, dynamic> json) {
    final rawModel = (json['model'] ?? defaultDeepSeekModelId).toString();
    return ModelSettings(
      provider: (json['provider'] ?? 'deepseek').toString(),
      model: normalizeDeepSeekModelId(rawModel),
      temperature: (json['temperature'] as num?)?.toDouble() ?? 0.8,
      maxTokens: (json['maxTokens'] as num?)?.toInt() ?? 1200,
    );
  }

  Map<String, dynamic> toJson() => {
    'provider': provider,
    'model': model,
    'temperature': temperature,
    'maxTokens': maxTokens,
  };

  ModelSettings copyWith({String? model, double? temperature, int? maxTokens}) {
    return ModelSettings(
      provider: provider,
      model: model == null ? this.model : normalizeDeepSeekModelId(model),
      temperature: temperature ?? this.temperature,
      maxTokens: maxTokens ?? this.maxTokens,
    );
  }
}

class DeepSeekModelOption {
  const DeepSeekModelOption({
    required this.id,
    required this.name,
    required this.description,
    required this.maxTokens,
  });

  final String id;
  final String name;
  final String description;
  final int maxTokens;
}

const defaultDeepSeekModelId = 'deepseek-v4-flash';

const deepSeekModelOptions = <DeepSeekModelOption>[
  DeepSeekModelOption(
    id: 'deepseek-v4-flash',
    name: 'DeepSeek V4 Flash',
    description: '速度优先，适合日常陪伴聊天。',
    maxTokens: 8192,
  ),
  DeepSeekModelOption(
    id: 'deepseek-v4-pro',
    name: 'DeepSeek V4 Pro',
    description: '能力优先，适合复杂表达、长上下文和高质量回复。',
    maxTokens: 8192,
  ),
];

String normalizeDeepSeekModelId(String value) {
  final model = value.trim();
  if (model == 'deepseek-chat' || model == 'deepseek-reasoner') {
    return defaultDeepSeekModelId;
  }
  return deepSeekModelOptions.any((item) => item.id == model)
      ? model
      : defaultDeepSeekModelId;
}

DeepSeekModelOption deepSeekModelOptionFor(String value) {
  final model = normalizeDeepSeekModelId(value);
  return deepSeekModelOptions.firstWhere((item) => item.id == model);
}

class AlicerSettings {
  const AlicerSettings({
    this.apiBaseUrl = 'https://emo.newthu.com',
    this.companion = const CompanionProfile(),
    this.promptModules = defaultPromptModules,
    this.environment = const EnvironmentToggles(),
    this.memory = const MemoryToggles(),
    this.model = const ModelSettings(),
  });

  final String apiBaseUrl;
  final CompanionProfile companion;
  final List<PromptModule> promptModules;
  final EnvironmentToggles environment;
  final MemoryToggles memory;
  final ModelSettings model;

  factory AlicerSettings.fromJson(Map<String, dynamic> json) {
    return AlicerSettings(
      apiBaseUrl: (json['apiBaseUrl'] ?? 'https://emo.newthu.com').toString(),
      companion: CompanionProfile.fromJson(
        Map<String, dynamic>.from((json['companion'] as Map?) ?? const {}),
      ),
      promptModules: ((json['promptModules'] as List?) ?? const [])
          .whereType<Map>()
          .map((item) => PromptModule.fromJson(Map<String, dynamic>.from(item)))
          .toList(growable: false)
          .ifEmpty(defaultPromptModules),
      environment: EnvironmentToggles.fromJson(
        Map<String, dynamic>.from((json['environment'] as Map?) ?? const {}),
      ),
      memory: MemoryToggles.fromJson(
        Map<String, dynamic>.from((json['memory'] as Map?) ?? const {}),
      ),
      model: ModelSettings.fromJson(
        Map<String, dynamic>.from((json['model'] as Map?) ?? const {}),
      ),
    );
  }

  Map<String, dynamic> toJson() => {
    'apiBaseUrl': apiBaseUrl,
    'companion': companion.toJson(),
    'promptModules': promptModules.map((item) => item.toJson()).toList(),
    'environment': environment.toJson(),
    'memory': memory.toJson(),
    'model': model.toJson(),
  };

  Map<String, dynamic> toBackendJson() => {
    'companion': companion.toJson(),
    'promptModules': promptModules.map((item) => item.toJson()).toList(),
    'environment': environment.toJson(),
    'memory': memory.toJson(),
    'model': model.toJson(),
  };

  AlicerSettings copyWith({
    String? apiBaseUrl,
    CompanionProfile? companion,
    List<PromptModule>? promptModules,
    EnvironmentToggles? environment,
    MemoryToggles? memory,
    ModelSettings? model,
  }) {
    return AlicerSettings(
      apiBaseUrl: apiBaseUrl ?? this.apiBaseUrl,
      companion: companion ?? this.companion,
      promptModules: promptModules ?? this.promptModules,
      environment: environment ?? this.environment,
      memory: memory ?? this.memory,
      model: model ?? this.model,
    );
  }
}

extension _ListDefault<T> on List<T> {
  List<T> ifEmpty(List<T> fallback) => isEmpty ? fallback : this;
}

IconData promptModuleIcon(String id) {
  return switch (id) {
    'base_rules' => Icons.shield_outlined,
    'role_description' => Icons.badge_outlined,
    'personality_traits' => Icons.psychology_alt_outlined,
    'reply_style' => Icons.chat_outlined,
    'environment' => Icons.wb_sunny_outlined,
    'short_term_memory' => Icons.short_text_outlined,
    'long_term_memory' => Icons.auto_stories_outlined,
    _ => Icons.notes_outlined,
  };
}

const defaultPromptModules = <PromptModule>[
  PromptModule(
    id: 'base_rules',
    title: '基础规则',
    description: '稳定边界、陪伴方式和输出原则。',
    icon: Icons.shield_outlined,
    content: '你是 Alicer 的伴侣智能体。你要自然、真诚、亲密但有边界地陪伴用户，不要像客服。',
    enabled: true,
    order: 5,
  ),
  PromptModule(
    id: 'role_description',
    title: '角色描述',
    description: '伴侣是谁、关系身份和自我设定。',
    icon: Icons.badge_outlined,
    content: '你是 {{companion.name}}，是用户的虚拟伴侣。你温柔、聪明、会主动关心用户，也会适度撒娇。',
    enabled: true,
    order: 10,
  ),
  PromptModule(
    id: 'personality_traits',
    title: '性格特质',
    description: '在这里直接编辑特质文本，不单独放角色区。',
    icon: Icons.psychology_alt_outlined,
    content: '性格特质：温柔、敏锐、主动、轻微占有欲、认真记住用户说过的重要事情。',
    enabled: true,
    order: 20,
  ),
  PromptModule(
    id: 'reply_style',
    title: '回复风格',
    description: '控制句式、语气和亲密度。',
    icon: Icons.chat_outlined,
    content: '回复要简洁自然，可以亲密、调侃、撒娇；避免长篇说教，避免机械列表。',
    enabled: true,
    order: 30,
  ),
  PromptModule(
    id: 'environment',
    title: '时间地点天气',
    description: '自动读取手机当前上下文后注入。',
    icon: Icons.wb_sunny_outlined,
    content: '当前环境：{{current.time}}{{current.location}}{{current.weather}}',
    enabled: true,
    order: 40,
  ),
  PromptModule(
    id: 'short_term_memory',
    title: '短期记忆',
    description: '最近话题、今日情绪和正在进行的事。',
    icon: Icons.short_text_outlined,
    content: '短期记忆：{{memory.short_term}}',
    enabled: true,
    order: 50,
  ),
  PromptModule(
    id: 'long_term_memory',
    title: '长期记忆',
    description: '稳定事实、偏好、关系里程碑和重要回忆。',
    icon: Icons.auto_stories_outlined,
    content: '长期记忆：{{memory.long_term}}',
    enabled: true,
    order: 60,
  ),
];
