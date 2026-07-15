import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:path/path.dart' as p;
import 'package:shared_preferences/shared_preferences.dart';
import 'package:sqflite/sqflite.dart';

import '../domain/chat_models.dart';

class ChatCacheStore {
  ChatCacheStore._();

  static final instance = ChatCacheStore._();
  static const _dbName = 'alicer_chat_cache.db';
  static const _dbVersion = 1;
  static const _lastSyncKey = 'alicer_chat_cache_last_sync_ms';
  static const refreshAfter = Duration(minutes: 5);
  static const maxCachedMessages = 240;

  Database? _db;

  Future<Database> _database() async {
    final existing = _db;
    if (existing != null) return existing;
    final path = p.join(await getDatabasesPath(), _dbName);
    _db = await openDatabase(
      path,
      version: _dbVersion,
      onCreate: (db, version) async {
        await db.execute('''
          CREATE TABLE messages (
            id TEXT PRIMARY KEY,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at INTEGER NOT NULL,
            metadata_json TEXT NOT NULL
          )
        ''');
        await db.execute(
          'CREATE INDEX idx_messages_created ON messages(created_at, id)',
        );
      },
    );
    return _db!;
  }

  Future<List<ChatMessage>> loadMessages() async {
    try {
      final db = await _database();
      final rows = await db.query(
        'messages',
        orderBy: 'created_at ASC, id ASC',
        limit: maxCachedMessages,
      );
      return rows.map(_fromRow).toList(growable: false);
    } catch (error, stackTrace) {
      debugPrint('[alicer.cache] load failed: $error\n$stackTrace');
      return const <ChatMessage>[];
    }
  }

  Future<void> saveMessages(
    List<ChatMessage> messages, {
    bool markSynced = true,
  }) async {
    try {
      final db = await _database();
      final trimmed =
          messages.length <= maxCachedMessages
              ? messages
              : messages.sublist(messages.length - maxCachedMessages);
      await db.transaction((txn) async {
        await txn.delete('messages');
        final batch = txn.batch();
        for (final message in trimmed) {
          batch.insert(
            'messages',
            _toRow(message),
            conflictAlgorithm: ConflictAlgorithm.replace,
          );
        }
        await batch.commit(noResult: true);
      });
      if (markSynced) {
        final prefs = await SharedPreferences.getInstance();
        await prefs.setInt(_lastSyncKey, DateTime.now().millisecondsSinceEpoch);
      }
    } catch (error, stackTrace) {
      debugPrint('[alicer.cache] save failed: $error\n$stackTrace');
    }
  }

  Future<bool> isFresh() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final raw = prefs.getInt(_lastSyncKey);
      if (raw == null) return false;
      final age = DateTime.now().difference(
        DateTime.fromMillisecondsSinceEpoch(raw),
      );
      return age < refreshAfter;
    } catch (_) {
      return false;
    }
  }

  ChatMessage _fromRow(Map<String, Object?> row) {
    return ChatMessage(
      id: (row['id'] ?? '').toString(),
      role: (row['role'] ?? '').toString(),
      content: (row['content'] ?? '').toString(),
      createdAt: DateTime.fromMillisecondsSinceEpoch(
        (row['created_at'] as int?) ?? DateTime.now().millisecondsSinceEpoch,
      ),
      metadata: _decodeMap(row['metadata_json']),
    );
  }

  Map<String, Object?> _toRow(ChatMessage message) => {
    'id': message.id,
    'role': message.role,
    'content': message.content,
    'created_at': message.createdAt.millisecondsSinceEpoch,
    'metadata_json': jsonEncode(message.metadata),
  };

  Map<String, dynamic> _decodeMap(Object? raw) {
    if (raw is! String || raw.isEmpty) return const <String, dynamic>{};
    try {
      final decoded = jsonDecode(raw);
      if (decoded is Map) return Map<String, dynamic>.from(decoded);
    } catch (_) {}
    return const <String, dynamic>{};
  }
}
