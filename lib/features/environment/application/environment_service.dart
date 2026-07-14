import 'package:geolocator/geolocator.dart';
import 'package:intl/intl.dart';

import '../../settings/domain/app_settings.dart';

class EnvironmentSnapshot {
  const EnvironmentSnapshot({required this.payload, required this.label});

  final Map<String, dynamic> payload;
  final String label;
}

class EnvironmentService {
  Future<EnvironmentSnapshot> collect(EnvironmentToggles toggles) async {
    final now = DateTime.now();
    final payload = <String, dynamic>{
      if (toggles.time) 'time': DateFormat('yyyy-MM-dd HH:mm').format(now),
      'timezone': now.timeZoneName,
    };
    final labels = <String>[
      if (toggles.time) DateFormat('M月d日 HH:mm').format(now),
    ];
    if (toggles.location || toggles.weather) {
      final position = await _tryGetPosition();
      if (position != null) {
        payload['latitude'] = double.parse(
          position.latitude.toStringAsFixed(5),
        );
        payload['longitude'] = double.parse(
          position.longitude.toStringAsFixed(5),
        );
        labels.add('已读取位置');
      }
    }
    return EnvironmentSnapshot(
      payload: payload,
      label: labels.isEmpty ? '未注入环境' : labels.join(' · '),
    );
  }

  Future<Position?> _tryGetPosition() async {
    try {
      final enabled = await Geolocator.isLocationServiceEnabled();
      if (!enabled) return null;
      var permission = await Geolocator.checkPermission();
      if (permission == LocationPermission.denied) {
        permission = await Geolocator.requestPermission();
      }
      if (permission == LocationPermission.denied ||
          permission == LocationPermission.deniedForever) {
        return null;
      }
      return Geolocator.getCurrentPosition(
        locationSettings: const LocationSettings(
          accuracy: LocationAccuracy.low,
          timeLimit: Duration(seconds: 8),
        ),
      );
    } catch (_) {
      return null;
    }
  }
}
