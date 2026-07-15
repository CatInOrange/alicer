class CompanionMemory {
  const CompanionMemory({
    required this.id,
    required this.kind,
    required this.subject,
    required this.content,
    required this.summary,
    required this.tags,
    required this.confidence,
    required this.importance,
    required this.status,
    required this.enabled,
    required this.pinned,
    required this.sensitive,
    required this.createdAt,
    required this.updatedAt,
    this.expiresAt,
    this.lastUsedAt,
  });

  final String id;
  final String kind;
  final String subject;
  final String content;
  final String summary;
  final List<String> tags;
  final double confidence;
  final double importance;
  final String status;
  final bool enabled;
  final bool pinned;
  final bool sensitive;
  final DateTime createdAt;
  final DateTime updatedAt;
  final DateTime? expiresAt;
  final DateTime? lastUsedAt;

  factory CompanionMemory.fromJson(Map<String, dynamic> json) {
    return CompanionMemory(
      id: (json['id'] ?? '').toString(),
      kind: (json['kind'] ?? 'fact').toString(),
      subject: (json['subject'] ?? 'user').toString(),
      content: (json['content'] ?? '').toString(),
      summary: (json['summary'] ?? '').toString(),
      tags: ((json['tags'] as List?) ?? const <dynamic>[])
          .map((item) => item.toString())
          .toList(growable: false),
      confidence: _parseDouble(json['confidence'], 0.7),
      importance: _parseDouble(json['importance'], 0.5),
      status: (json['status'] ?? 'active').toString(),
      enabled: json['enabled'] != false,
      pinned: json['pinned'] == true,
      sensitive: json['sensitive'] == true,
      createdAt: _parseDate(json['createdAt']),
      updatedAt: _parseDate(json['updatedAt']),
      expiresAt:
          json['expiresAt'] == null ? null : _parseDate(json['expiresAt']),
      lastUsedAt:
          json['lastUsedAt'] == null ? null : _parseDate(json['lastUsedAt']),
    );
  }

  Map<String, dynamic> toPayload() => {
    'kind': kind,
    'subject': subject,
    'content': content,
    'summary': summary,
    'tags': tags,
    'confidence': confidence,
    'importance': importance,
    'status': status,
    'enabled': enabled,
    'pinned': pinned,
    'sensitive': sensitive,
    'expiresAt':
        expiresAt == null ? null : expiresAt!.millisecondsSinceEpoch / 1000,
  };

  CompanionMemory copyWith({
    String? kind,
    String? subject,
    String? content,
    String? summary,
    List<String>? tags,
    double? confidence,
    double? importance,
    String? status,
    bool? enabled,
    bool? pinned,
    bool? sensitive,
    DateTime? expiresAt,
  }) {
    return CompanionMemory(
      id: id,
      kind: kind ?? this.kind,
      subject: subject ?? this.subject,
      content: content ?? this.content,
      summary: summary ?? this.summary,
      tags: tags ?? this.tags,
      confidence: confidence ?? this.confidence,
      importance: importance ?? this.importance,
      status: status ?? this.status,
      enabled: enabled ?? this.enabled,
      pinned: pinned ?? this.pinned,
      sensitive: sensitive ?? this.sensitive,
      createdAt: createdAt,
      updatedAt: updatedAt,
      expiresAt: expiresAt ?? this.expiresAt,
      lastUsedAt: lastUsedAt,
    );
  }
}

class MemoryListResult {
  const MemoryListResult({required this.memories, required this.pendingQueue});

  final List<CompanionMemory> memories;
  final int pendingQueue;
}

String memoryKindLabel(String kind) {
  return switch (kind) {
    'preference' => '偏好',
    'relationship' => '关系',
    'state' => '近期状态',
    'self_life' => '她自己的生活',
    _ => '事实',
  };
}

String memorySubjectLabel(String subject) {
  return switch (subject) {
    'companion' => '她',
    'relationship' => '我们',
    _ => '用户',
  };
}

DateTime _parseDate(Object? raw) {
  if (raw is num) {
    final value = raw.toDouble();
    return DateTime.fromMillisecondsSinceEpoch(
      value > 100000000000 ? value.toInt() : (value * 1000).toInt(),
    );
  }
  if (raw is String) {
    final parsed = DateTime.tryParse(raw);
    if (parsed != null) return parsed;
    final numeric = num.tryParse(raw);
    if (numeric != null) return _parseDate(numeric);
  }
  return DateTime.now();
}

double _parseDouble(Object? raw, double fallback) {
  if (raw is num) return raw.toDouble();
  if (raw is String) return double.tryParse(raw) ?? fallback;
  return fallback;
}
