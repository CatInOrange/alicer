import 'dart:async';
import 'dart:io';

import 'package:flutter/services.dart';
import 'package:geolocator/geolocator.dart';

import '../../../core/network/api_client.dart';
import '../../settings/domain/app_settings.dart';

class UserTimelineSyncResult {
  const UserTimelineSyncResult({
    required this.accepted,
    required this.events,
    required this.label,
  });

  final int accepted;
  final List<Map<String, dynamic>> events;
  final String label;
}

class UserTimelineService {
  static const _channel = MethodChannel('com.openclaw.alicer/user_timeline');

  Future<UserTimelineSyncResult> syncNow(AlicerSettings settings) async {
    final timeline = settings.userTimeline;
    final events = <Map<String, dynamic>>[
      _foregroundEvent(),
      if (timeline.location) ...await _locationEvents(),
      if (Platform.isAndroid) ...await _androidEvents(settings),
    ];
    final response = await ApiClient(baseUrl: settings.apiBaseUrl).postJson(
      '/api/user/timeline/events',
      {'settings': settings.toBackendJson(), 'events': events},
      timeout: const Duration(seconds: 30),
    );
    final accepted = (response['accepted'] as num?)?.toInt() ?? 0;
    return UserTimelineSyncResult(
      accepted: accepted,
      events: events,
      label: accepted == 0 ? '没有新的手机轨迹' : '已同步 $accepted 条手机轨迹',
    );
  }

  Future<void> configureBackground(AlicerSettings settings) async {
    if (!Platform.isAndroid) return;
    await _channel.invokeMethod<void>('configureBackground', {
      'enabled':
          settings.userTimeline.enabled && settings.userTimeline.backgroundSync,
      'baseUrl': settings.apiBaseUrl,
      'settings': settings.toBackendJson(),
      'intervalMinutes': settings.userTimeline.syncIntervalMinutes,
      'signals': settings.userTimeline.toJson(),
    });
  }

  Future<String> requestAndroidPermissions(
    UserTimelineSettings timeline,
  ) async {
    if (!Platform.isAndroid) return '当前平台不需要 Android 权限';
    final result = await _channel.invokeMethod<Map<dynamic, dynamic>>(
      'requestPermissions',
      timeline.toJson(),
    );
    final map = Map<String, dynamic>.from(result ?? const {});
    final granted = (map['granted'] as List?)?.join('、') ?? '';
    final pending = (map['pending'] as List?)?.join('、') ?? '';
    if (pending.isEmpty) return granted.isEmpty ? '权限已处理' : '已授权：$granted';
    return '仍需手动开启：$pending';
  }

  Map<String, dynamic> _foregroundEvent() {
    final now = DateTime.now();
    return {
      'eventTime': now.millisecondsSinceEpoch / 1000,
      'source': 'flutter',
      'eventType': 'app_foreground',
      'title': '打开 Alicer',
      'summary': '用户打开了 Alicer，适合刷新一次当前状态。',
      'confidence': 0.9,
      'privacyLevel': 'context',
      'metadata': {'timezone': now.timeZoneName},
    };
  }

  Future<List<Map<String, dynamic>>> _locationEvents() async {
    try {
      final enabled = await Geolocator.isLocationServiceEnabled();
      if (!enabled) return const [];
      var permission = await Geolocator.checkPermission();
      if (permission == LocationPermission.denied) {
        permission = await Geolocator.requestPermission();
      }
      if (permission == LocationPermission.denied ||
          permission == LocationPermission.deniedForever) {
        return const [];
      }
      final position = await Geolocator.getCurrentPosition(
        locationSettings: const LocationSettings(
          accuracy: LocationAccuracy.low,
          timeLimit: Duration(seconds: 8),
        ),
      );
      return [
        {
          'eventTime': DateTime.now().millisecondsSinceEpoch / 1000,
          'source': 'flutter',
          'eventType': 'location_snapshot',
          'title': '读取当前位置',
          'summary': '手机更新了一次低精度位置。',
          'confidence': 0.72,
          'privacyLevel': 'context',
          'metadata': {
            'label': '当前位置',
            'latitude': double.parse(position.latitude.toStringAsFixed(4)),
            'longitude': double.parse(position.longitude.toStringAsFixed(4)),
            'accuracy': position.accuracy,
          },
        },
      ];
    } catch (_) {
      return const [];
    }
  }

  Future<List<Map<String, dynamic>>> _androidEvents(
    AlicerSettings settings,
  ) async {
    try {
      final raw = await _channel.invokeMethod<List<dynamic>>(
        'collectSnapshot',
        {'signals': settings.userTimeline.toJson()},
      );
      return (raw ?? const [])
          .whereType<Map>()
          .map((item) => Map<String, dynamic>.from(item))
          .toList(growable: false);
    } catch (_) {
      return const [];
    }
  }
}
