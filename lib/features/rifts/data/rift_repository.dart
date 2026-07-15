import '../../../core/network/api_client.dart';
import '../../settings/domain/app_settings.dart';
import '../domain/rift_models.dart';

class RiftRepository {
  RiftRepository({required this.settings})
    : _client = ApiClient(baseUrl: settings.apiBaseUrl);

  final AlicerSettings settings;
  final ApiClient _client;

  Future<List<RiftScenario>> listRifts() async {
    final response = await _client.getJson('/api/rifts');
    final list = (response['rifts'] as List?) ?? const [];
    return list
        .whereType<Map>()
        .map((item) => RiftScenario.fromJson(Map<String, dynamic>.from(item)))
        .toList(growable: false);
  }

  Future<RiftDetail> getRift(String id) async {
    final response = await _client.getJson('/api/rifts/$id');
    return RiftDetail.fromJson(response);
  }

  Future<RiftDetail> createRift({
    required String genre,
    required String surfaceRelation,
    required String intensity,
    required int targetTurns,
    String customSurfaceRelation = '',
  }) async {
    final response = await _client.postJson('/api/rifts', {
      'genre': genre,
      'surfaceRelation': surfaceRelation,
      'customSurfaceRelation': customSurfaceRelation,
      'intensity': intensity,
      'targetTurns': targetTurns,
      'settings': settings.toBackendJson(),
    });
    return RiftDetail.fromJson(response);
  }

  Future<RiftDetail> choose(String id, String choiceId) async {
    final response = await _client.postJson('/api/rifts/$id/choose', {
      'choiceId': choiceId,
      'settings': settings.toBackendJson(),
    });
    return RiftDetail.fromJson(response);
  }

  Future<void> deleteRift(String id) async {
    await _client.deleteJson('/api/rifts/$id');
  }
}
