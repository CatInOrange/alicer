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
  });

  final bool time;
  final bool location;
  final bool weather;

  factory EnvironmentToggles.fromJson(Map<String, dynamic> json) {
    return EnvironmentToggles(
      time: json['time'] != false,
      location: json['location'] != false,
      weather: json['weather'] != false,
    );
  }

  Map<String, dynamic> toJson() => {
    'time': time,
    'location': location,
    'weather': weather,
  };

  EnvironmentToggles copyWith({bool? time, bool? location, bool? weather}) {
    return EnvironmentToggles(
      time: time ?? this.time,
      location: location ?? this.location,
      weather: weather ?? this.weather,
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
      shortTerm: json['shortTerm'] == true,
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
    this.retentionDays = 2,
    this.syncIntervalMinutes = 30,
  });

  final bool enabled;
  final bool backgroundSync;
  final bool location;
  final bool music;
  final bool motion;
  final bool device;
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

class FortuneSettings {
  const FortuneSettings({
    this.enabled = false,
    this.birthday = '',
    this.style = 'companion',
    this.includeInContext = true,
    this.maxProactiveMentionsPerDay = 1,
    this.orbDegrees = 3.0,
  });

  final bool enabled;
  final String birthday;
  final String style;
  final bool includeInContext;
  final int maxProactiveMentionsPerDay;
  final double orbDegrees;

  factory FortuneSettings.fromJson(Map<String, dynamic> json) {
    return FortuneSettings(
      enabled: json['enabled'] == true,
      birthday: (json['birthday'] ?? '').toString(),
      style: normalizeFortuneStyle((json['style'] ?? 'companion').toString()),
      includeInContext: json['includeInContext'] != false,
      maxProactiveMentionsPerDay: _clampInt(
        json['maxProactiveMentionsPerDay'],
        1,
        0,
        3,
      ),
      orbDegrees: _clampDouble(json['orbDegrees'], 3.0, 1.0, 6.0),
    );
  }

  Map<String, dynamic> toJson() => {
    'enabled': enabled,
    'birthday': birthday,
    'style': style,
    'includeInContext': includeInContext,
    'maxProactiveMentionsPerDay': maxProactiveMentionsPerDay,
    'orbDegrees': orbDegrees,
  };

  FortuneSettings copyWith({
    bool? enabled,
    String? birthday,
    String? style,
    bool? includeInContext,
    int? maxProactiveMentionsPerDay,
    double? orbDegrees,
  }) {
    return FortuneSettings(
      enabled: enabled ?? this.enabled,
      birthday: birthday ?? this.birthday,
      style: style == null ? this.style : normalizeFortuneStyle(style),
      includeInContext: includeInContext ?? this.includeInContext,
      maxProactiveMentionsPerDay: _clampInt(
        maxProactiveMentionsPerDay,
        this.maxProactiveMentionsPerDay,
        0,
        3,
      ),
      orbDegrees: _clampDouble(orbDegrees, this.orbDegrees, 1.0, 6.0),
    );
  }
}

String normalizeFortuneStyle(String value) {
  return switch (value) {
    'classic' || 'quiet' || 'companion' => value,
    _ => 'companion',
  };
}

class ProactiveQuietHours {
  const ProactiveQuietHours({this.start = '23:30', this.end = '08:00'});

  final String start;
  final String end;

  factory ProactiveQuietHours.fromJson(Map<String, dynamic> json) {
    return ProactiveQuietHours(
      start: _normalizeClock((json['start'] ?? '23:30').toString(), '23:30'),
      end: _normalizeClock((json['end'] ?? '08:00').toString(), '08:00'),
    );
  }

  Map<String, dynamic> toJson() => {'start': start, 'end': end};

  ProactiveQuietHours copyWith({String? start, String? end}) {
    return ProactiveQuietHours(
      start: _normalizeClock(start ?? this.start, this.start),
      end: _normalizeClock(end ?? this.end, this.end),
    );
  }
}

class ProactiveSettings {
  const ProactiveSettings({
    this.enabled = true,
    this.quietHours = const ProactiveQuietHours(),
    this.intervalMinutes = 20,
    this.minIdleHoursBeforeChat = 5,
    this.minHoursBetweenChat = 3,
    this.minHoursBetweenMoments = 8,
    this.maxChatPerDay = 3,
    this.maxMomentsPerDay = 2,
    this.chatThreshold = 0.66,
    this.momentThreshold = 0.68,
  });

  final bool enabled;
  final ProactiveQuietHours quietHours;
  final int intervalMinutes;
  final int minIdleHoursBeforeChat;
  final int minHoursBetweenChat;
  final int minHoursBetweenMoments;
  final int maxChatPerDay;
  final int maxMomentsPerDay;
  final double chatThreshold;
  final double momentThreshold;

  factory ProactiveSettings.fromJson(Map<String, dynamic> json) {
    return ProactiveSettings(
      enabled: json['enabled'] != false,
      quietHours: ProactiveQuietHours.fromJson(
        Map<String, dynamic>.from((json['quietHours'] as Map?) ?? const {}),
      ),
      intervalMinutes: _clampInt(json['intervalMinutes'], 20, 5, 180),
      minIdleHoursBeforeChat: _clampInt(
        json['minIdleHoursBeforeChat'],
        5,
        1,
        72,
      ),
      minHoursBetweenChat: _clampInt(json['minHoursBetweenChat'], 3, 1, 24),
      minHoursBetweenMoments: _clampInt(
        json['minHoursBetweenMoments'],
        8,
        1,
        48,
      ),
      maxChatPerDay: _clampInt(json['maxChatPerDay'], 3, 0, 12),
      maxMomentsPerDay: _clampInt(json['maxMomentsPerDay'], 2, 0, 6),
      chatThreshold: _clampDouble(json['chatThreshold'], 0.66, 0.2, 0.98),
      momentThreshold: _clampDouble(json['momentThreshold'], 0.68, 0.2, 0.98),
    );
  }

  Map<String, dynamic> toJson() => {
    'enabled': enabled,
    'quietHours': quietHours.toJson(),
    'intervalMinutes': intervalMinutes,
    'minIdleHoursBeforeChat': minIdleHoursBeforeChat,
    'minHoursBetweenChat': minHoursBetweenChat,
    'minHoursBetweenMoments': minHoursBetweenMoments,
    'maxChatPerDay': maxChatPerDay,
    'maxMomentsPerDay': maxMomentsPerDay,
    'chatThreshold': chatThreshold,
    'momentThreshold': momentThreshold,
  };

  ProactiveSettings copyWith({
    bool? enabled,
    ProactiveQuietHours? quietHours,
    int? intervalMinutes,
    int? minIdleHoursBeforeChat,
    int? minHoursBetweenChat,
    int? minHoursBetweenMoments,
    int? maxChatPerDay,
    int? maxMomentsPerDay,
    double? chatThreshold,
    double? momentThreshold,
  }) {
    return ProactiveSettings(
      enabled: enabled ?? this.enabled,
      quietHours: quietHours ?? this.quietHours,
      intervalMinutes: _clampInt(intervalMinutes, this.intervalMinutes, 5, 180),
      minIdleHoursBeforeChat: _clampInt(
        minIdleHoursBeforeChat,
        this.minIdleHoursBeforeChat,
        1,
        72,
      ),
      minHoursBetweenChat: _clampInt(
        minHoursBetweenChat,
        this.minHoursBetweenChat,
        1,
        24,
      ),
      minHoursBetweenMoments: _clampInt(
        minHoursBetweenMoments,
        this.minHoursBetweenMoments,
        1,
        48,
      ),
      maxChatPerDay: _clampInt(maxChatPerDay, this.maxChatPerDay, 0, 12),
      maxMomentsPerDay: _clampInt(
        maxMomentsPerDay,
        this.maxMomentsPerDay,
        0,
        6,
      ),
      chatThreshold: _clampDouble(chatThreshold, this.chatThreshold, 0.2, 0.98),
      momentThreshold: _clampDouble(
        momentThreshold,
        this.momentThreshold,
        0.2,
        0.98,
      ),
    );
  }
}

class DailyMaintenanceSettings {
  const DailyMaintenanceSettings({
    this.enabled = true,
    this.runTime = '03:30',
    this.target = 'yesterday',
    this.generateDiary = true,
    this.cleanupFacts = true,
    this.processMemory = true,
    this.advanceLife = true,
    this.consistencyCheck = true,
  });

  final bool enabled;
  final String runTime;
  final String target;
  final bool generateDiary;
  final bool cleanupFacts;
  final bool processMemory;
  final bool advanceLife;
  final bool consistencyCheck;

  factory DailyMaintenanceSettings.fromJson(Map<String, dynamic> json) {
    final rawTarget = (json['target'] ?? 'yesterday').toString();
    return DailyMaintenanceSettings(
      enabled: json['enabled'] != false,
      runTime: _normalizeClock(
        (json['runTime'] ?? '03:30').toString(),
        '03:30',
      ),
      target: rawTarget == 'today' ? 'today' : 'yesterday',
      generateDiary: json['generateDiary'] != false,
      cleanupFacts: json['cleanupFacts'] != false,
      processMemory: json['processMemory'] != false,
      advanceLife: json['advanceLife'] != false,
      consistencyCheck: json['consistencyCheck'] != false,
    );
  }

  Map<String, dynamic> toJson() => {
    'enabled': enabled,
    'runTime': runTime,
    'target': target,
    'generateDiary': generateDiary,
    'cleanupFacts': cleanupFacts,
    'processMemory': processMemory,
    'advanceLife': advanceLife,
    'consistencyCheck': consistencyCheck,
  };

  DailyMaintenanceSettings copyWith({
    bool? enabled,
    String? runTime,
    String? target,
    bool? generateDiary,
    bool? cleanupFacts,
    bool? processMemory,
    bool? advanceLife,
    bool? consistencyCheck,
  }) {
    final nextTarget = target ?? this.target;
    return DailyMaintenanceSettings(
      enabled: enabled ?? this.enabled,
      runTime: _normalizeClock(runTime ?? this.runTime, this.runTime),
      target: nextTarget == 'today' ? 'today' : 'yesterday',
      generateDiary: generateDiary ?? this.generateDiary,
      cleanupFacts: cleanupFacts ?? this.cleanupFacts,
      processMemory: processMemory ?? this.processMemory,
      advanceLife: advanceLife ?? this.advanceLife,
      consistencyCheck: consistencyCheck ?? this.consistencyCheck,
    );
  }
}

String normalizeHistoryMode(String value) {
  return switch (value) {
    'recent' || 'day' || 'month' || 'all' => value,
    _ => 'all',
  };
}

double _clampDouble(Object? value, double fallback, double min, double max) {
  final parsed =
      value is num
          ? value.toDouble()
          : double.tryParse(value?.toString() ?? '');
  return (parsed ?? fallback).clamp(min, max);
}

int _clampInt(Object? value, int fallback, int min, int max) {
  final parsed =
      value is num ? value.toInt() : int.tryParse(value?.toString() ?? '');
  return (parsed ?? fallback).clamp(min, max);
}

String _normalizeClock(String value, String fallback) {
  final match = RegExp(r'^(\d{1,2}):(\d{2})$').firstMatch(value.trim());
  if (match == null) return fallback;
  final hour = int.tryParse(match.group(1) ?? '');
  final minute = int.tryParse(match.group(2) ?? '');
  if (hour == null || minute == null) return fallback;
  if (hour < 0 || hour > 23 || minute < 0 || minute > 59) return fallback;
  return '${hour.toString().padLeft(2, '0')}:${minute.toString().padLeft(2, '0')}';
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
    this.fortune = const FortuneSettings(),
    this.chatPhotos = const ChatPhotoSettings(),
    this.proactive = const ProactiveSettings(),
    this.dailyMaintenance = const DailyMaintenanceSettings(),
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
  final FortuneSettings fortune;
  final ChatPhotoSettings chatPhotos;
  final ProactiveSettings proactive;
  final DailyMaintenanceSettings dailyMaintenance;
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
      fortune: FortuneSettings.fromJson(
        Map<String, dynamic>.from((json['fortune'] as Map?) ?? const {}),
      ),
      chatPhotos: ChatPhotoSettings.fromJson(
        Map<String, dynamic>.from((json['chatPhotos'] as Map?) ?? const {}),
      ),
      proactive: ProactiveSettings.fromJson(
        Map<String, dynamic>.from((json['proactive'] as Map?) ?? const {}),
      ),
      dailyMaintenance: DailyMaintenanceSettings.fromJson(
        Map<String, dynamic>.from(
          (json['dailyMaintenance'] as Map?) ?? const {},
        ),
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
    'fortune': fortune.toJson(),
    'chatPhotos': chatPhotos.toJson(),
    'proactive': proactive.toJson(),
    'dailyMaintenance': dailyMaintenance.toJson(),
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
    'fortune': fortune.toJson(),
    'chatPhotos': chatPhotos.toJson(),
    'proactive': proactive.toJson(),
    'dailyMaintenance': dailyMaintenance.toJson(),
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
    FortuneSettings? fortune,
    ChatPhotoSettings? chatPhotos,
    ProactiveSettings? proactive,
    DailyMaintenanceSettings? dailyMaintenance,
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
      fortune: fortune ?? this.fortune,
      chatPhotos: chatPhotos ?? this.chatPhotos,
      proactive: proactive ?? this.proactive,
      dailyMaintenance: dailyMaintenance ?? this.dailyMaintenance,
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
