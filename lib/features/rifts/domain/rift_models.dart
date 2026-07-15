class RiftScenario {
  const RiftScenario({
    required this.id,
    required this.title,
    required this.genre,
    required this.surfaceRelation,
    required this.intensity,
    required this.userRole,
    required this.aiRole,
    required this.worldSetting,
    required this.coreConflict,
    required this.imageUrl,
    required this.status,
    required this.targetTurns,
    required this.turnCount,
    required this.stats,
    required this.summary,
    required this.currentChoices,
    required this.endingType,
    required this.createdAt,
    required this.updatedAt,
  });

  final String id;
  final String title;
  final String genre;
  final String surfaceRelation;
  final String intensity;
  final String userRole;
  final String aiRole;
  final String worldSetting;
  final String coreConflict;
  final String imageUrl;
  final String status;
  final int targetTurns;
  final int turnCount;
  final Map<String, int> stats;
  final String summary;
  final List<RiftChoice> currentChoices;
  final String endingType;
  final DateTime createdAt;
  final DateTime updatedAt;

  bool get isEnded => status == 'ended';

  factory RiftScenario.fromJson(Map<String, dynamic> json) {
    final statsJson = (json['stats'] as Map?) ?? const {};
    final choicesJson = (json['currentChoices'] as List?) ?? const [];
    return RiftScenario(
      id: json['id']?.toString() ?? '',
      title: json['title']?.toString() ?? '未命名裂隙',
      genre: json['genre']?.toString() ?? '',
      surfaceRelation: json['surfaceRelation']?.toString() ?? '',
      intensity: json['intensity']?.toString() ?? '',
      userRole: json['userRole']?.toString() ?? '',
      aiRole: json['aiRole']?.toString() ?? '',
      worldSetting: json['worldSetting']?.toString() ?? '',
      coreConflict: json['coreConflict']?.toString() ?? '',
      imageUrl: json['imageUrl']?.toString() ?? '',
      status: json['status']?.toString() ?? 'active',
      targetTurns: (json['targetTurns'] as num?)?.toInt() ?? 20,
      turnCount: (json['turnCount'] as num?)?.toInt() ?? 0,
      stats: {
        for (final entry in statsJson.entries)
          entry.key.toString(): (entry.value as num?)?.toInt() ?? 0,
      },
      summary: json['summary']?.toString() ?? '',
      currentChoices: choicesJson
          .whereType<Map>()
          .map((item) => RiftChoice.fromJson(Map<String, dynamic>.from(item)))
          .toList(growable: false),
      endingType: json['endingType']?.toString() ?? '',
      createdAt: _date(json['createdAt']),
      updatedAt: _date(json['updatedAt']),
    );
  }
}

class RiftEvent {
  const RiftEvent({
    required this.id,
    required this.turnIndex,
    required this.eventType,
    required this.choiceId,
    required this.choiceText,
    required this.sceneText,
    required this.aiDialogue,
    required this.createdAt,
  });

  final String id;
  final int turnIndex;
  final String eventType;
  final String choiceId;
  final String choiceText;
  final String sceneText;
  final String aiDialogue;
  final DateTime createdAt;

  bool get isEnding => eventType == 'ending';

  factory RiftEvent.fromJson(Map<String, dynamic> json) {
    return RiftEvent(
      id: json['id']?.toString() ?? '',
      turnIndex: (json['turnIndex'] as num?)?.toInt() ?? 0,
      eventType: json['eventType']?.toString() ?? 'scene',
      choiceId: json['choiceId']?.toString() ?? '',
      choiceText: json['choiceText']?.toString() ?? '',
      sceneText: json['sceneText']?.toString() ?? '',
      aiDialogue: json['aiDialogue']?.toString() ?? '',
      createdAt: _date(json['createdAt']),
    );
  }
}

class RiftChoice {
  const RiftChoice({required this.id, required this.text, required this.tone});

  final String id;
  final String text;
  final String tone;

  factory RiftChoice.fromJson(Map<String, dynamic> json) {
    return RiftChoice(
      id: json['id']?.toString() ?? '',
      text: json['text']?.toString() ?? '',
      tone: json['tone']?.toString() ?? '',
    );
  }
}

class RiftDetail {
  const RiftDetail({required this.scenario, required this.events});

  final RiftScenario scenario;
  final List<RiftEvent> events;

  factory RiftDetail.fromJson(Map<String, dynamic> json) {
    final eventsJson = (json['events'] as List?) ?? const [];
    return RiftDetail(
      scenario: RiftScenario.fromJson(
        Map<String, dynamic>.from((json['scenario'] as Map?) ?? const {}),
      ),
      events: eventsJson
          .whereType<Map>()
          .map((item) => RiftEvent.fromJson(Map<String, dynamic>.from(item)))
          .toList(growable: false),
    );
  }
}

DateTime _date(Object? value) {
  final seconds = (value as num?)?.toDouble() ?? 0;
  if (seconds <= 0) return DateTime.fromMillisecondsSinceEpoch(0);
  return DateTime.fromMillisecondsSinceEpoch((seconds * 1000).round());
}
