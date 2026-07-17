import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../settings/data/settings_store.dart';
import '../domain/time_models.dart';
import 'moment_cache_store.dart';
import 'time_repository.dart';

class MomentUnreadTracker extends ChangeNotifier {
  MomentUnreadTracker._();

  static final instance = MomentUnreadTracker._();
  static const _lastSeenMomentIdKey = 'alicer_moments_last_seen_id';

  bool _hasUnread = false;
  bool _refreshing = false;

  bool get hasUnread => _hasUnread;

  Future<void> refresh() async {
    if (_refreshing) return;
    _refreshing = true;
    try {
      final settings = await SettingsStore.load();
      var moments = await MomentCacheStore.instance.loadMoments();
      try {
        final remote = await TimeRepository(settings: settings).listMoments();
        if (remote.isNotEmpty) {
          moments = remote;
          await MomentCacheStore.instance.saveMoments(remote);
        }
      } catch (error, stackTrace) {
        debugPrint(
          '[alicer.moments.unread] refresh failed: $error\n$stackTrace',
        );
      }
      await _updateUnread(moments);
    } finally {
      _refreshing = false;
    }
  }

  Future<void> markSeen(List<MomentPost> moments) async {
    final latestId = _latestMomentId(moments);
    if (latestId == null) {
      _setUnread(false);
      return;
    }
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_lastSeenMomentIdKey, latestId);
    _setUnread(false);
  }

  Future<void> _updateUnread(List<MomentPost> moments) async {
    final latestId = _latestMomentId(moments);
    if (latestId == null) {
      _setUnread(false);
      return;
    }
    final prefs = await SharedPreferences.getInstance();
    final lastSeenId = prefs.getString(_lastSeenMomentIdKey);
    if (lastSeenId == null || lastSeenId.isEmpty) {
      await prefs.setString(_lastSeenMomentIdKey, latestId);
      _setUnread(false);
      return;
    }
    _setUnread(latestId != lastSeenId);
  }

  String? _latestMomentId(List<MomentPost> moments) {
    if (moments.isEmpty) return null;
    final sorted = [...moments]
      ..sort((a, b) => b.createdAt.compareTo(a.createdAt));
    return sorted.first.id.isEmpty ? null : sorted.first.id;
  }

  void _setUnread(bool value) {
    if (_hasUnread == value) return;
    _hasUnread = value;
    notifyListeners();
  }
}
