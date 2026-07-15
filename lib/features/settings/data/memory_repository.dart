import '../../../core/network/api_client.dart';
import '../domain/app_settings.dart';
import '../domain/memory_models.dart';

class MemoryRepository {
  MemoryRepository({required this.settings})
    : _client = ApiClient(baseUrl: settings.apiBaseUrl);

  final AlicerSettings settings;
  final ApiClient _client;

  Future<MemoryListResult> listMemories({
    String status = 'active',
    String query = '',
  }) async {
    final response = await _client.getJson('/api/memories', {
      'status': status,
      if (query.trim().isNotEmpty) 'query': query.trim(),
      'limit': '120',
    });
    final items = (response['memories'] as List?) ?? const <dynamic>[];
    return MemoryListResult(
      memories: items
          .whereType<Map>()
          .map(
            (item) => CompanionMemory.fromJson(Map<String, dynamic>.from(item)),
          )
          .toList(growable: false),
      pendingQueue: (response['pendingQueue'] as num?)?.toInt() ?? 0,
    );
  }

  Future<CompanionMemory> createMemory(CompanionMemory memory) async {
    final response = await _client.postJson(
      '/api/memories',
      memory.toPayload(),
    );
    return CompanionMemory.fromJson(
      Map<String, dynamic>.from(response['memory'] as Map),
    );
  }

  Future<CompanionMemory> updateMemory(CompanionMemory memory) async {
    final response = await _client.putJson(
      '/api/memories/${memory.id}',
      memory.toPayload(),
    );
    return CompanionMemory.fromJson(
      Map<String, dynamic>.from(response['memory'] as Map),
    );
  }

  Future<void> archiveMemory(String memoryId) async {
    await _client.deleteJson('/api/memories/$memoryId');
  }

  Future<void> processQueue() async {
    await _client.postJson('/api/memories/process', {
      'settings': settings.toBackendJson(),
    });
  }
}
