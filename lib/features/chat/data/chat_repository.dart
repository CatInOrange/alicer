import 'dart:async';
import 'dart:convert';

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

  Stream<ChatStreamEvent> streamMessage({
    required String text,
    required Map<String, dynamic> environment,
  }) async* {
    final response = await _client.postStream('/api/chat/stream', {
      'text': text,
      'environment': environment,
      'settings': settings.toBackendJson(),
    });
    if (response.statusCode < 200 || response.statusCode >= 300) {
      final body = await response.stream.bytesToString();
      throw ApiException(statusCode: response.statusCode, message: body);
    }
    var event = 'message';
    final dataLines = <String>[];
    await for (final line in response.stream
        .transform(utf8.decoder)
        .transform(const LineSplitter())) {
      if (line.startsWith('event:')) {
        event = line.substring(6).trim();
        continue;
      }
      if (line.startsWith('data:')) {
        dataLines.add(line.substring(5).trimLeft());
        continue;
      }
      if (line.trim().isNotEmpty) continue;
      if (dataLines.isEmpty) {
        event = 'message';
        continue;
      }
      final payload = jsonDecode(dataLines.join('\n'));
      if (payload is Map) {
        yield ChatStreamEvent(
          type: event,
          payload: Map<String, dynamic>.from(payload),
        );
      }
      event = 'message';
      dataLines.clear();
    }
  }

  Future<Map<String, dynamic>> previewPrompt({
    required Map<String, dynamic> environment,
  }) {
    return _client.postJson('/api/prompt/preview', {
      'settings': settings.toBackendJson(),
      'environment': environment,
    });
  }

  Future<Map<String, dynamic>> previewFortune() {
    return _client.postJson('/api/fortune/preview', {
      'settings': settings.toBackendJson(),
    });
  }

  Future<void> syncSettings() async {
    await _client.putJson('/api/settings', settings.toBackendJson());
  }
}

class ChatStreamEvent {
  const ChatStreamEvent({required this.type, required this.payload});

  final String type;
  final Map<String, dynamic> payload;
}
