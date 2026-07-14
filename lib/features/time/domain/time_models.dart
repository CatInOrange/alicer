class TimeEntry {
  const TimeEntry({
    required this.id,
    required this.kind,
    required this.periodKey,
    required this.title,
    required this.content,
    required this.status,
    required this.createdAt,
    this.generatedAt,
    this.error = '',
  });

  final String id;
  final String kind;
  final String periodKey;
  final String title;
  final String content;
  final String status;
  final DateTime createdAt;
  final DateTime? generatedAt;
  final String error;

  factory TimeEntry.fromJson(Map<String, dynamic> json) {
    return TimeEntry(
      id: (json['id'] ?? '').toString(),
      kind: (json['kind'] ?? 'day').toString(),
      periodKey: (json['periodKey'] ?? '').toString(),
      title: (json['title'] ?? '').toString(),
      content: (json['content'] ?? '').toString(),
      status: (json['status'] ?? '').toString(),
      createdAt: _parseDate(json['createdAt']),
      generatedAt:
          json['generatedAt'] == null ? null : _parseDate(json['generatedAt']),
      error: (json['error'] ?? '').toString(),
    );
  }
}

class MomentPost {
  const MomentPost({
    required this.id,
    required this.author,
    required this.content,
    required this.imageUrl,
    required this.createdAt,
    required this.likes,
    required this.comments,
  });

  final String id;
  final String author;
  final String content;
  final String imageUrl;
  final DateTime createdAt;
  final List<String> likes;
  final List<MomentComment> comments;

  factory MomentPost.fromJson(Map<String, dynamic> json) {
    return MomentPost(
      id: (json['id'] ?? '').toString(),
      author: (json['author'] ?? '').toString(),
      content: (json['content'] ?? '').toString(),
      imageUrl: (json['imageUrl'] ?? '').toString(),
      createdAt: _parseDate(json['createdAt']),
      likes: ((json['likes'] as List?) ?? const <dynamic>[])
          .map((item) => item.toString())
          .toList(growable: false),
      comments: ((json['comments'] as List?) ?? const <dynamic>[])
          .whereType<Map>()
          .map(
            (item) => MomentComment.fromJson(Map<String, dynamic>.from(item)),
          )
          .toList(growable: false),
    );
  }
}

class MomentComment {
  const MomentComment({
    required this.id,
    required this.author,
    required this.content,
    required this.parentId,
    required this.createdAt,
  });

  final String id;
  final String author;
  final String content;
  final String parentId;
  final DateTime createdAt;

  factory MomentComment.fromJson(Map<String, dynamic> json) {
    return MomentComment(
      id: (json['id'] ?? '').toString(),
      author: (json['author'] ?? '').toString(),
      content: (json['content'] ?? '').toString(),
      parentId: (json['parentId'] ?? '').toString(),
      createdAt: _parseDate(json['createdAt']),
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
