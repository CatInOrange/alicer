import '../../../core/network/api_client.dart';
import '../../settings/domain/app_settings.dart';
import '../domain/time_models.dart';

class TimeRepository {
  TimeRepository({required this.settings})
    : _client = ApiClient(baseUrl: settings.apiBaseUrl);

  final AlicerSettings settings;
  final ApiClient _client;

  Future<List<TimeEntry>> listDiary(String kind) async {
    final response = await _client.getJson('/api/diary/entries', {
      'kind': kind,
    });
    final list = (response['entries'] as List?) ?? const <dynamic>[];
    return list
        .whereType<Map>()
        .map((item) => TimeEntry.fromJson(Map<String, dynamic>.from(item)))
        .toList(growable: false);
  }

  Future<TimeEntry?> generateDiary(String kind, String periodKey) async {
    final response = await _client.postJson(
      '/api/diary/entries/$kind/$periodKey/generate',
      {'force': true, 'source': 'manual_app'},
    );
    final raw = response['entry'];
    if (raw is! Map) return null;
    return TimeEntry.fromJson(Map<String, dynamic>.from(raw));
  }

  Future<List<MomentPost>> listMoments() async {
    final response = await _client.getJson('/api/moments');
    final list = (response['moments'] as List?) ?? const <dynamic>[];
    return list
        .whereType<Map>()
        .map((item) => MomentPost.fromJson(Map<String, dynamic>.from(item)))
        .toList(growable: false);
  }

  Future<MomentPost?> generateMoment() async {
    final response = await _client.postJson('/api/moments/generate', {
      'force': true,
      'settings': settings.toBackendJson(),
    });
    final raw = response['moment'];
    if (raw is! Map) return null;
    return MomentPost.fromJson(Map<String, dynamic>.from(raw));
  }

  Future<MomentPost?> setLike(
    String momentId,
    String userName,
    bool liked,
  ) async {
    final response = await _client.postJson('/api/moments/$momentId/like', {
      'userName': userName,
      'liked': liked,
    });
    final raw = response['moment'];
    if (raw is! Map) return null;
    return MomentPost.fromJson(Map<String, dynamic>.from(raw));
  }

  Future<MomentPost?> comment(
    String momentId,
    String userName,
    String content,
  ) async {
    final response = await _client.postJson('/api/moments/$momentId/comments', {
      'author': userName,
      'content': content,
      'settings': settings.toBackendJson(),
    });
    final raw = response['moment'];
    if (raw is! Map) return null;
    return MomentPost.fromJson(Map<String, dynamic>.from(raw));
  }
}
