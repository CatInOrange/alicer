import 'dart:convert';
import 'dart:typed_data';

import 'package:http/http.dart' as http;

import 'http_client_factory.dart';

class ApiClient {
  ApiClient({required this.baseUrl, http.Client? httpClient})
    : _httpClient = httpClient ?? createHttpClient(baseUrl);

  final String baseUrl;
  final http.Client _httpClient;

  Uri uri(String path, [Map<String, String>? query]) {
    final normalized = path.startsWith('/') ? path : '/$path';
    return Uri.parse('$baseUrl$normalized').replace(queryParameters: query);
  }

  Future<Map<String, dynamic>> getJson(
    String path, [
    Map<String, String>? query,
  ]) async {
    final response = await _httpClient
        .get(uri(path, query), headers: {'Accept': 'application/json'})
        .timeout(const Duration(seconds: 18));
    return _decodeResponse(response);
  }

  Future<Uint8List> getBytes(String pathOrUrl) async {
    final uri =
        pathOrUrl.startsWith('http://') || pathOrUrl.startsWith('https://')
            ? Uri.parse(pathOrUrl)
            : this.uri(pathOrUrl);
    final response = await _httpClient
        .get(uri, headers: {'Accept': 'image/*'})
        .timeout(const Duration(seconds: 30));
    if (response.statusCode < 200 || response.statusCode >= 300) {
      throw ApiException(
        statusCode: response.statusCode,
        message: 'Failed to load image bytes from $uri',
      );
    }
    return response.bodyBytes;
  }

  Future<Map<String, dynamic>> postJson(
    String path,
    Map<String, dynamic> body, {
    Map<String, String>? headers,
  }) async {
    final response = await _httpClient
        .post(
          uri(path),
          headers: {
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            ...?headers,
          },
          body: jsonEncode(body),
        )
        .timeout(const Duration(seconds: 75));
    return _decodeResponse(response);
  }

  Future<Map<String, dynamic>> postImageData(
    String path, {
    required Uint8List bytes,
    required String filename,
    required String mimeType,
  }) {
    return postJson(path, {
      'filename': filename,
      'mimeType': mimeType,
      'data': base64Encode(bytes),
    });
  }

  Future<Map<String, dynamic>> putJson(
    String path,
    Map<String, dynamic> body,
  ) async {
    final response = await _httpClient
        .put(
          uri(path),
          headers: {
            'Accept': 'application/json',
            'Content-Type': 'application/json',
          },
          body: jsonEncode(body),
        )
        .timeout(const Duration(seconds: 30));
    return _decodeResponse(response);
  }

  Future<Map<String, dynamic>> deleteJson(String path) async {
    final response = await _httpClient
        .delete(uri(path), headers: {'Accept': 'application/json'})
        .timeout(const Duration(seconds: 30));
    return _decodeResponse(response);
  }

  Future<http.StreamedResponse> postStream(
    String path,
    Map<String, dynamic> body,
  ) async {
    final request =
        http.Request('POST', uri(path))
          ..headers.addAll({
            'Accept': 'text/event-stream',
            'Content-Type': 'application/json',
          })
          ..body = jsonEncode(body);
    return _httpClient.send(request).timeout(const Duration(seconds: 90));
  }

  Map<String, dynamic> _decodeResponse(http.Response response) {
    final decoded =
        response.body.trim().isEmpty
            ? <String, dynamic>{}
            : jsonDecode(utf8.decode(response.bodyBytes));
    if (response.statusCode < 200 || response.statusCode >= 300) {
      throw ApiException(
        statusCode: response.statusCode,
        message: decoded is Map ? decoded.toString() : response.body,
      );
    }
    if (decoded is Map<String, dynamic>) return decoded;
    if (decoded is Map) return Map<String, dynamic>.from(decoded);
    return {'data': decoded};
  }
}

class ApiException implements Exception {
  const ApiException({required this.statusCode, required this.message});

  final int statusCode;
  final String message;

  @override
  String toString() => 'HTTP $statusCode: $message';
}
