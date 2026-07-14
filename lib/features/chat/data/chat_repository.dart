import '../../../core/network/api_client.dart';
import '../../settings/domain/app_settings.dart';
import '../domain/chat_models.dart';

class ChatRepository {
  ChatRepository({required this.settings})
    : _client = ApiClient(baseUrl: settings.apiBaseUrl);

  final AlicerSettings settings;
  final ApiClient _client;

  Future<List<ChatMessage>> fetchMessages() async {
    final response = await _client.getJson('/api/messages');
    final list = (response['messages'] as List?) ?? const <dynamic>[];
    return list
        .whereType<Map>()
        .map((item) => ChatMessage.fromJson(Map<String, dynamic>.from(item)))
        .toList(growable: false);
  }

  Future<ChatMessage> sendMessage({
    required String text,
    required Map<String, dynamic> environment,
  }) async {
    final response = await _client.postJson('/api/chat', {
      'text': text,
      'environment': environment,
      'settings': settings.toBackendJson(),
    });
    return ChatMessage.fromJson(
      Map<String, dynamic>.from(response['assistantMessage'] as Map),
    );
  }

  Future<Map<String, dynamic>> previewPrompt({
    required Map<String, dynamic> environment,
  }) {
    return _client.postJson('/api/prompt/preview', {
      'settings': settings.toBackendJson(),
      'environment': environment,
    });
  }

  Future<void> syncSettings() async {
    await _client.putJson('/api/settings', settings.toBackendJson());
  }
}
