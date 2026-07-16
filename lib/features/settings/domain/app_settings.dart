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

  PromptModule copyWith({bool? enabled, String? content, int? order}) {
    return PromptModule(
      id: id,
      title: title,
      description: description,
      icon: icon,
      content: content ?? this.content,
      enabled: enabled ?? this.enabled,
      order: order ?? this.order,
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
    this.shortTerm = false,
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

class UserTimelineSettings {
  const UserTimelineSettings({
    this.enabled = true,
    this.backgroundSync = true,
    this.location = true,
    this.music = true,
    this.motion = true,
    this.device = true,
    this.appUsage = false,
    this.retentionDays = 2,
    this.syncIntervalMinutes = 30,
  });

  final bool enabled;
  final bool backgroundSync;
  final bool location;
  final bool music;
  final bool motion;
  final bool device;
  final bool appUsage;
  final int retentionDays;
  final int syncIntervalMinutes;

  factory UserTimelineSettings.fromJson(Map<String, dynamic> json) {
    return UserTimelineSettings(
      enabled: json['enabled'] != false,
      backgroundSync: json['backgroundSync'] != false,
      location: json['location'] != false,
      music: json['music'] != false,
      motion: json['motion'] != false,
      device: json['device'] != false,
      appUsage: json['appUsage'] == true,
      retentionDays: _clampInt(json['retentionDays'], 2, 1, 2),
      syncIntervalMinutes: _clampInt(json['syncIntervalMinutes'], 30, 15, 180),
    );
  }

  Map<String, dynamic> toJson() => {
    'enabled': enabled,
    'backgroundSync': backgroundSync,
    'location': location,
    'music': music,
    'motion': motion,
    'device': device,
    'appUsage': appUsage,
    'retentionDays': retentionDays,
    'syncIntervalMinutes': syncIntervalMinutes,
  };

  UserTimelineSettings copyWith({
    bool? enabled,
    bool? backgroundSync,
    bool? location,
    bool? music,
    bool? motion,
    bool? device,
    bool? appUsage,
    int? retentionDays,
    int? syncIntervalMinutes,
  }) {
    return UserTimelineSettings(
      enabled: enabled ?? this.enabled,
      backgroundSync: backgroundSync ?? this.backgroundSync,
      location: location ?? this.location,
      music: music ?? this.music,
      motion: motion ?? this.motion,
      device: device ?? this.device,
      appUsage: appUsage ?? this.appUsage,
      retentionDays: _clampInt(retentionDays, this.retentionDays, 1, 2),
      syncIntervalMinutes: _clampInt(
        syncIntervalMinutes,
        this.syncIntervalMinutes,
        15,
        180,
      ),
    );
  }
}

class MomentsSettings {
  const MomentsSettings({
    this.dailyPostProbability = 0.55,
    this.photoProbability = 0.45,
    this.referenceImageUrl =
        'https://yzcos-1317705976.cos.ap-singapore.myqcloud.com/reference/my_avatar.jpg',
    this.identityPromptPrefix = defaultMomentIdentityPromptPrefix,
  });

  final double dailyPostProbability;
  final double photoProbability;
  final String referenceImageUrl;
  final String identityPromptPrefix;

  factory MomentsSettings.fromJson(Map<String, dynamic> json) {
    final daily = (json['dailyPostProbability'] as num?)?.toDouble() ?? 0.55;
    final photo = (json['photoProbability'] as num?)?.toDouble() ?? 0.45;
    return MomentsSettings(
      dailyPostProbability: daily.clamp(0.0, 1.0),
      photoProbability: photo.clamp(0.0, 1.0),
      referenceImageUrl:
          (json['referenceImageUrl'] ??
                  'https://yzcos-1317705976.cos.ap-singapore.myqcloud.com/reference/my_avatar.jpg')
              .toString(),
      identityPromptPrefix:
          (json['identityPromptPrefix'] ?? defaultMomentIdentityPromptPrefix)
              .toString(),
    );
  }

  Map<String, dynamic> toJson() => {
    'dailyPostProbability': dailyPostProbability,
    'photoProbability': photoProbability,
    'referenceImageUrl': referenceImageUrl,
    'identityPromptPrefix': identityPromptPrefix,
  };

  MomentsSettings copyWith({
    double? dailyPostProbability,
    double? photoProbability,
    String? referenceImageUrl,
    String? identityPromptPrefix,
  }) {
    return MomentsSettings(
      dailyPostProbability:
          dailyPostProbability?.clamp(0.0, 1.0) ?? this.dailyPostProbability,
      photoProbability:
          photoProbability?.clamp(0.0, 1.0) ?? this.photoProbability,
      referenceImageUrl: referenceImageUrl ?? this.referenceImageUrl,
      identityPromptPrefix: identityPromptPrefix ?? this.identityPromptPrefix,
    );
  }
}

const defaultMomentIdentityPromptPrefix =
    'The only person in the image is {{companion.name}}. Use the reference image as the identity source. '
    'Preserve the exact same face, facial structure, hairstyle, hair color, age impression, body type, and overall vibe from the reference image. '
    "If any scene detail conflicts with the reference person's identity, the reference image wins. "
    'Do not create a different woman, do not change ethnicity, do not change hairstyle, do not add other people. '
    'Natural candid smartphone photo for a WeChat Moments post, soft realistic lighting, no text, no watermark.';

class ChatContextSettings {
  const ChatContextSettings({
    this.historyMode = 'all',
    this.recentMessages = 120,
    this.maxHistoryMessages = 300,
  });

  final String historyMode;
  final int recentMessages;
  final int maxHistoryMessages;

  factory ChatContextSettings.fromJson(Map<String, dynamic> json) {
    return ChatContextSettings(
      historyMode: normalizeHistoryMode(
        (json['historyMode'] ?? 'all').toString(),
      ),
      recentMessages: _clampInt(json['recentMessages'], 120, 1, 300),
      maxHistoryMessages: _clampInt(json['maxHistoryMessages'], 300, 1, 300),
    );
  }

  Map<String, dynamic> toJson() => {
    'historyMode': historyMode,
    'recentMessages': recentMessages,
    'maxHistoryMessages': maxHistoryMessages,
  };

  ChatContextSettings copyWith({
    String? historyMode,
    int? recentMessages,
    int? maxHistoryMessages,
  }) {
    return ChatContextSettings(
      historyMode:
          historyMode == null
              ? this.historyMode
              : normalizeHistoryMode(historyMode),
      recentMessages: _clampInt(recentMessages, this.recentMessages, 1, 300),
      maxHistoryMessages: _clampInt(
        maxHistoryMessages,
        this.maxHistoryMessages,
        1,
        300,
      ),
    );
  }
}

class LifeSettings {
  const LifeSettings({
    this.enabled = true,
    this.updateIntervalHours = 1,
    this.randomness = 0.62,
    this.autoMomentsFromLife = true,
    this.profileRefreshHours = 24,
  });

  final bool enabled;
  final int updateIntervalHours;
  final double randomness;
  final bool autoMomentsFromLife;
  final int profileRefreshHours;

  factory LifeSettings.fromJson(Map<String, dynamic> json) {
    return LifeSettings(
      enabled: json['enabled'] != false,
      updateIntervalHours: _clampInt(json['updateIntervalHours'], 1, 1, 6),
      randomness: ((json['randomness'] as num?)?.toDouble() ?? 0.62).clamp(
        0.0,
        1.0,
      ),
      autoMomentsFromLife: json['autoMomentsFromLife'] != false,
      profileRefreshHours: _clampInt(json['profileRefreshHours'], 24, 6, 168),
    );
  }

  Map<String, dynamic> toJson() => {
    'enabled': enabled,
    'updateIntervalHours': updateIntervalHours,
    'randomness': randomness,
    'autoMomentsFromLife': autoMomentsFromLife,
    'profileRefreshHours': profileRefreshHours,
  };

  LifeSettings copyWith({
    bool? enabled,
    int? updateIntervalHours,
    double? randomness,
    bool? autoMomentsFromLife,
    int? profileRefreshHours,
  }) {
    return LifeSettings(
      enabled: enabled ?? this.enabled,
      updateIntervalHours: _clampInt(
        updateIntervalHours,
        this.updateIntervalHours,
        1,
        6,
      ),
      randomness: randomness?.clamp(0.0, 1.0) ?? this.randomness,
      autoMomentsFromLife: autoMomentsFromLife ?? this.autoMomentsFromLife,
      profileRefreshHours: _clampInt(
        profileRefreshHours,
        this.profileRefreshHours,
        6,
        168,
      ),
    );
  }
}

class ChatPhotoSettings {
  const ChatPhotoSettings({
    this.enabled = true,
    this.allowRequested = true,
    this.allowProactive = true,
    this.dailySuccessfulLimit = 1,
    this.minHoursBetweenPhotos = 12,
  });

  final bool enabled;
  final bool allowRequested;
  final bool allowProactive;
  final int dailySuccessfulLimit;
  final int minHoursBetweenPhotos;

  factory ChatPhotoSettings.fromJson(Map<String, dynamic> json) {
    return ChatPhotoSettings(
      enabled: json['enabled'] != false,
      allowRequested: json['allowRequested'] != false,
      allowProactive: json['allowProactive'] != false,
      dailySuccessfulLimit: _clampInt(json['dailySuccessfulLimit'], 1, 0, 5),
      minHoursBetweenPhotos: _clampInt(
        json['minHoursBetweenPhotos'],
        12,
        0,
        72,
      ),
    );
  }

  Map<String, dynamic> toJson() => {
    'enabled': enabled,
    'allowRequested': allowRequested,
    'allowProactive': allowProactive,
    'dailySuccessfulLimit': dailySuccessfulLimit,
    'minHoursBetweenPhotos': minHoursBetweenPhotos,
  };

  ChatPhotoSettings copyWith({
    bool? enabled,
    bool? allowRequested,
    bool? allowProactive,
    int? dailySuccessfulLimit,
    int? minHoursBetweenPhotos,
  }) {
    return ChatPhotoSettings(
      enabled: enabled ?? this.enabled,
      allowRequested: allowRequested ?? this.allowRequested,
      allowProactive: allowProactive ?? this.allowProactive,
      dailySuccessfulLimit: _clampInt(
        dailySuccessfulLimit,
        this.dailySuccessfulLimit,
        0,
        5,
      ),
      minHoursBetweenPhotos: _clampInt(
        minHoursBetweenPhotos,
        this.minHoursBetweenPhotos,
        0,
        72,
      ),
    );
  }
}

String normalizeHistoryMode(String value) {
  return switch (value) {
    'recent' || 'day' || 'month' || 'all' => value,
    _ => 'all',
  };
}

int _clampInt(Object? value, int fallback, int min, int max) {
  final parsed =
      value is num ? value.toInt() : int.tryParse(value?.toString() ?? '');
  return (parsed ?? fallback).clamp(min, max);
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
    this.adminToken = '',
    this.companion = const CompanionProfile(),
    this.promptModules = defaultPromptModules,
    this.environment = const EnvironmentToggles(),
    this.memory = const MemoryToggles(),
    this.chatContext = const ChatContextSettings(),
    this.moments = const MomentsSettings(),
    this.life = const LifeSettings(),
    this.userTimeline = const UserTimelineSettings(),
    this.chatPhotos = const ChatPhotoSettings(),
    this.model = const ModelSettings(),
  });

  final String apiBaseUrl;
  final String adminToken;
  final CompanionProfile companion;
  final List<PromptModule> promptModules;
  final EnvironmentToggles environment;
  final MemoryToggles memory;
  final ChatContextSettings chatContext;
  final MomentsSettings moments;
  final LifeSettings life;
  final UserTimelineSettings userTimeline;
  final ChatPhotoSettings chatPhotos;
  final ModelSettings model;

  factory AlicerSettings.fromJson(Map<String, dynamic> json) {
    return AlicerSettings(
      apiBaseUrl: (json['apiBaseUrl'] ?? 'https://emo.newthu.com').toString(),
      adminToken: (json['adminToken'] ?? '').toString(),
      companion: CompanionProfile.fromJson(
        Map<String, dynamic>.from((json['companion'] as Map?) ?? const {}),
      ),
      promptModules: _mergePromptModules(
        ((json['promptModules'] as List?) ?? const [])
            .whereType<Map>()
            .map(
              (item) => PromptModule.fromJson(Map<String, dynamic>.from(item)),
            )
            .toList(growable: false),
      ),
      environment: EnvironmentToggles.fromJson(
        Map<String, dynamic>.from((json['environment'] as Map?) ?? const {}),
      ),
      memory: MemoryToggles.fromJson(
        Map<String, dynamic>.from((json['memory'] as Map?) ?? const {}),
      ),
      chatContext: ChatContextSettings.fromJson(
        Map<String, dynamic>.from((json['chatContext'] as Map?) ?? const {}),
      ),
      moments: MomentsSettings.fromJson(
        Map<String, dynamic>.from((json['moments'] as Map?) ?? const {}),
      ),
      life: LifeSettings.fromJson(
        Map<String, dynamic>.from((json['life'] as Map?) ?? const {}),
      ),
      userTimeline: UserTimelineSettings.fromJson(
        Map<String, dynamic>.from((json['userTimeline'] as Map?) ?? const {}),
      ),
      chatPhotos: ChatPhotoSettings.fromJson(
        Map<String, dynamic>.from((json['chatPhotos'] as Map?) ?? const {}),
      ),
      model: ModelSettings.fromJson(
        Map<String, dynamic>.from((json['model'] as Map?) ?? const {}),
      ),
    );
  }

  Map<String, dynamic> toJson() => {
    'apiBaseUrl': apiBaseUrl,
    'adminToken': adminToken,
    'companion': companion.toJson(),
    'promptModules': promptModules.map((item) => item.toJson()).toList(),
    'environment': environment.toJson(),
    'memory': memory.toJson(),
    'chatContext': chatContext.toJson(),
    'moments': moments.toJson(),
    'life': life.toJson(),
    'userTimeline': userTimeline.toJson(),
    'chatPhotos': chatPhotos.toJson(),
    'model': model.toJson(),
  };

  Map<String, dynamic> toBackendJson() => {
    'companion': companion.toJson(),
    'promptModules': promptModules.map((item) => item.toJson()).toList(),
    'environment': environment.toJson(),
    'memory': memory.toJson(),
    'chatContext': chatContext.toJson(),
    'moments': moments.toJson(),
    'life': life.toJson(),
    'userTimeline': userTimeline.toJson(),
    'chatPhotos': chatPhotos.toJson(),
    'model': model.toJson(),
  };

  AlicerSettings copyWith({
    String? apiBaseUrl,
    String? adminToken,
    CompanionProfile? companion,
    List<PromptModule>? promptModules,
    EnvironmentToggles? environment,
    MemoryToggles? memory,
    ChatContextSettings? chatContext,
    MomentsSettings? moments,
    LifeSettings? life,
    UserTimelineSettings? userTimeline,
    ChatPhotoSettings? chatPhotos,
    ModelSettings? model,
  }) {
    return AlicerSettings(
      apiBaseUrl: apiBaseUrl ?? this.apiBaseUrl,
      adminToken: adminToken ?? this.adminToken,
      companion: companion ?? this.companion,
      promptModules: promptModules ?? this.promptModules,
      environment: environment ?? this.environment,
      memory: memory ?? this.memory,
      chatContext: chatContext ?? this.chatContext,
      moments: moments ?? this.moments,
      life: life ?? this.life,
      userTimeline: userTimeline ?? this.userTimeline,
      chatPhotos: chatPhotos ?? this.chatPhotos,
      model: model ?? this.model,
    );
  }
}

List<PromptModule> _mergePromptModules(List<PromptModule> stored) {
  const legacyContextModuleIds = {
    'short_term_memory',
    'world_context',
    'life_state',
    'user_timeline',
    'chat_photo',
    'history_older',
    'history_recent_20',
    'long_term_memory',
  };
  final filtered =
      stored
          .where((item) => !legacyContextModuleIds.contains(item.id))
          .toList();
  if (filtered.isEmpty) return defaultPromptModules;
  final ids = filtered.map((item) => item.id).toSet();
  return [
    ...filtered,
    for (final module in defaultPromptModules)
      if (!ids.contains(module.id)) module,
  ];
}

IconData promptModuleIcon(String id) {
  return switch (id) {
    'base_rules' => Icons.shield_outlined,
    'role_description' => Icons.badge_outlined,
    'personality_traits' => Icons.psychology_alt_outlined,
    'reply_style' => Icons.chat_outlined,
    'emoji_style' => Icons.emoji_emotions_outlined,
    'environment' => Icons.wb_sunny_outlined,
    'runtime_context' => Icons.account_tree_outlined,
    'world_context' => Icons.account_tree_outlined,
    'life_state' => Icons.timeline_outlined,
    'user_timeline' => Icons.phone_android_outlined,
    'chat_photo' => Icons.add_a_photo_outlined,
    'history_older' => Icons.manage_history_outlined,
    'history_recent_20' => Icons.forum_outlined,
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
    id: 'emoji_style',
    title: '表情习惯',
    description: '控制聊天和朋友圈回复里的 emoji 使用。',
    icon: Icons.emoji_emotions_outlined,
    content:
        '可以自然带少量常用 emoji 或颜文字，比如 😊、🥺、✨、哼、欸嘿，但不要每句都加；亲密、调侃或朋友圈评论时可以更像真人一点。',
    enabled: true,
    order: 35,
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
    id: 'runtime_context',
    title: '运行上下文',
    description: '统一组织事实账本、生活状态、用户轨迹、照片承诺、历史和长期记忆。',
    icon: Icons.account_tree_outlined,
    content: '{{context.brief}}',
    enabled: true,
    order: 44,
  ),
];
