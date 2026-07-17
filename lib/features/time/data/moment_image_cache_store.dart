import 'dart:convert';
import 'dart:io';

import 'package:crypto/crypto.dart';
import 'package:flutter/foundation.dart';
import 'package:path/path.dart' as p;
import 'package:path_provider/path_provider.dart';

import '../../../core/network/api_client.dart';

class MomentImageCacheStore {
  MomentImageCacheStore._();

  static final instance = MomentImageCacheStore._();
  final Map<String, Uint8List> _memory = <String, Uint8List>{};
  final Map<String, Future<Uint8List>> _inFlight =
      <String, Future<Uint8List>>{};

  Future<Uint8List> loadImage({
    required String apiBaseUrl,
    required String imageUrl,
  }) {
    final key = '$apiBaseUrl|$imageUrl';
    final cached = _memory[key];
    if (cached != null) return SynchronousFuture(cached);
    return _inFlight.putIfAbsent(key, () async {
      try {
        final diskCached = await _readCached(key);
        if (diskCached != null) {
          _remember(key, diskCached);
          return diskCached;
        }
        final bytes = await ApiClient(baseUrl: apiBaseUrl).getBytes(imageUrl);
        await _writeCached(key, bytes);
        _remember(key, bytes);
        return bytes;
      } finally {
        _inFlight.remove(key);
      }
    });
  }

  void _remember(String key, Uint8List bytes) {
    if (_memory.length >= 80 && !_memory.containsKey(key)) {
      _memory.remove(_memory.keys.first);
    }
    _memory[key] = bytes;
  }

  Future<Uint8List?> _readCached(String key) async {
    try {
      final file = await _fileForKey(key);
      if (await file.exists()) return file.readAsBytes();
    } catch (error, stackTrace) {
      debugPrint('[alicer.image.cache] read failed: $error\n$stackTrace');
    }
    return null;
  }

  Future<void> _writeCached(String key, Uint8List bytes) async {
    try {
      final file = await _fileForKey(key);
      await file.parent.create(recursive: true);
      await file.writeAsBytes(bytes, flush: true);
    } catch (error, stackTrace) {
      debugPrint('[alicer.image.cache] write failed: $error\n$stackTrace');
    }
  }

  Future<File> _fileForKey(String key) async {
    final directory = await getApplicationSupportDirectory();
    final digest = sha256.convert(utf8.encode(key)).toString();
    return File(p.join(directory.path, 'moment_images', digest));
  }
}
