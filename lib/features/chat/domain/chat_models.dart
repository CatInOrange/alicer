class ChatMessage {
  const ChatMessage({
    required this.id,
    required this.role,
    required this.content,
    required this.createdAt,
    this.metadata = const <String, dynamic>{},
    this.isPending = false,
    this.isError = false,
  });

  final String id;
  final String role;
  final String content;
  final DateTime createdAt;
  final Map<String, dynamic> metadata;
  final bool isPending;
  final bool isError;

  bool get isUser => role == 'user';
  bool get isAssistant => role == 'assistant';

  factory ChatMessage.fromJson(Map<String, dynamic> json) {
    return ChatMessage(
      id: (json['id'] ?? '').toString(),
      role: (json['role'] ?? '').toString(),
      content: (json['content'] ?? '').toString(),
      createdAt: _parseDate(json['createdAt']),
      metadata: Map<String, dynamic>.from(
        (json['metadata'] as Map?) ?? const <String, dynamic>{},
      ),
    );
  }

  Map<String, dynamic> toJson() => {
    'id': id,
    'role': role,
    'content': content,
    'createdAt': createdAt.toIso8601String(),
    if (metadata.isNotEmpty) 'metadata': metadata,
  };

  ChatMessage copyWith({String? content, bool? isPending, bool? isError}) {
    return ChatMessage(
      id: id,
      role: role,
      content: content ?? this.content,
      createdAt: createdAt,
      metadata: metadata,
      isPending: isPending ?? this.isPending,
      isError: isError ?? this.isError,
    );
  }
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
