import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:path/path.dart' as p;
import 'package:shared_preferences/shared_preferences.dart';
import 'package:sqflite/sqflite.dart';

import '../domain/time_models.dart';

class MomentCacheStore {
  MomentCacheStore._();

  static final instance = MomentCacheStore._();
  static const _dbName = 'alicer_moment_cache.db';
  static const _dbVersion = 1;
  static const _lastSyncKey = 'alicer_moment_cache_last_sync_ms';
  static const refreshAfter = Duration(minutes: 5);
  static const maxCachedMoments = 120;

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
          CREATE TABLE moments (
            id TEXT PRIMARY KEY,
            created_at INTEGER NOT NULL,
            payload_json TEXT NOT NULL
          )
        ''');
        await db.execute(
          'CREATE INDEX idx_moments_created ON moments(created_at DESC, id DESC)',
        );
      },
    );
    return _db!;
  }

  Future<List<MomentPost>> loadMoments() async {
    try {
      final db = await _database();
      final rows = await db.query(
        'moments',
        orderBy: 'created_at DESC, id DESC',
        limit: maxCachedMoments,
      );
      return rows.map(_fromRow).toList(growable: false);
    } catch (error, stackTrace) {
      debugPrint('[alicer.moments.cache] load failed: $error\n$stackTrace');
      return const <MomentPost>[];
    }
  }

  Future<void> saveMoments(List<MomentPost> moments) async {
    try {
      final db = await _database();
      final trimmed =
          moments.length <= maxCachedMoments
              ? moments
              : moments.sublist(0, maxCachedMoments);
      await db.transaction((txn) async {
        await txn.delete('moments');
        final batch = txn.batch();
        for (final moment in trimmed) {
          batch.insert(
            'moments',
            _toRow(moment),
            conflictAlgorithm: ConflictAlgorithm.replace,
          );
        }
        await batch.commit(noResult: true);
      });
      final prefs = await SharedPreferences.getInstance();
      await prefs.setInt(_lastSyncKey, DateTime.now().millisecondsSinceEpoch);
    } catch (error, stackTrace) {
      debugPrint('[alicer.moments.cache] save failed: $error\n$stackTrace');
    }
  }

  Future<void> upsertMoment(MomentPost moment) async {
    try {
      final db = await _database();
      await db.insert(
        'moments',
        _toRow(moment),
        conflictAlgorithm: ConflictAlgorithm.replace,
      );
      final prefs = await SharedPreferences.getInstance();
      await prefs.setInt(_lastSyncKey, DateTime.now().millisecondsSinceEpoch);
    } catch (error, stackTrace) {
      debugPrint('[alicer.moments.cache] upsert failed: $error\n$stackTrace');
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

  MomentPost _fromRow(Map<String, Object?> row) {
    final payload = (row['payload_json'] ?? '').toString();
    final decoded = jsonDecode(payload);
    return MomentPost.fromJson(Map<String, dynamic>.from(decoded as Map));
  }

  Map<String, Object?> _toRow(MomentPost moment) => {
    'id': moment.id,
    'created_at': moment.createdAt.millisecondsSinceEpoch,
    'payload_json': jsonEncode(moment.toJson()),
  };
}
