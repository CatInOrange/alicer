import 'dart:io';

import 'package:http/http.dart' as http;
import 'package:http/io_client.dart';

http.Client createHttpClient(String baseUrl) {
  final uri = Uri.tryParse(baseUrl);
  final client = HttpClient();
  if (uri?.host == 'emo.newthu.com') {
    client.badCertificateCallback =
        (cert, host, port) => host == 'emo.newthu.com';
  }
  return IOClient(client);
}
