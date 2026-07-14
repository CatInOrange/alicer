import 'dart:convert';

import 'package:shared_preferences/shared_preferences.dart';

import '../../../core/config/app_config.dart';
import '../domain/app_settings.dart';

class SettingsStore {
  const SettingsStore._();

  static const _settingsKey = 'alicer.settings.v1';

  static Future<AlicerSettings> load() async {
    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getString(_settingsKey);
    if (raw == null || raw.trim().isEmpty) {
      return const AlicerSettings(apiBaseUrl: AppConfig.defaultApiBaseUrl);
    }
    try {
      final decoded = jsonDecode(raw);
      if (decoded is Map) {
        return AlicerSettings.fromJson(Map<String, dynamic>.from(decoded));
      }
    } catch (_) {}
    return const AlicerSettings(apiBaseUrl: AppConfig.defaultApiBaseUrl);
  }

  static Future<void> save(AlicerSettings settings) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_settingsKey, jsonEncode(settings.toJson()));
  }
}
