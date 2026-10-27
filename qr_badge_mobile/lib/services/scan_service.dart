import 'api_client.dart';

class ScanService {
  Future<Map<String, dynamic>> secureScan({
    required String baseUrl,
    required String accessToken,
    required String tokenQr,
    required String deviceId,
    double? latitude,
    double? longitude,
    double? accuracyM,
    int? batteryLevel,
    bool? isCharging,
    Future<String?> Function()? onRefreshToken,
  }) async {
    final client = ApiClient(
      baseUrl: baseUrl,
      accessToken: accessToken,
      onRefreshToken: onRefreshToken,
    );
    return client.post(
      '/api/scan/secure/',
      data: {
        'token_qr': tokenQr,
        'device_id': deviceId,
        'latitude': ?latitude,
        'longitude': ?longitude,
        'accuracy_m': ?accuracyM,
        'battery_level': ?batteryLevel,
        'is_charging': ?isCharging,
      },
    );
  }

  Future<Map<String, dynamic>> heartbeat({
    required String baseUrl,
    required String accessToken,
    required String tokenQr,
    required String deviceId,
    required double latitude,
    required double longitude,
    double? accuracyM,
    int? batteryLevel,
    bool? isCharging,
    Future<String?> Function()? onRefreshToken,
  }) async {
    final client = ApiClient(
      baseUrl: baseUrl,
      accessToken: accessToken,
      onRefreshToken: onRefreshToken,
    );
    return client.post(
      '/api/scan/secure/heartbeat/',
      data: {
        'token_qr': tokenQr,
        'device_id': deviceId,
        'latitude': latitude,
        'longitude': longitude,
        'accuracy_m': ?accuracyM,
        'battery_level': ?batteryLevel,
        'is_charging': ?isCharging,
      },
    );
  }

  Future<Map<String, dynamic>> checkSecureStatus({
    required String baseUrl,
    required String accessToken,
    required String tokenQr,
    double? latitude,
    double? longitude,
    double? accuracyM,
    Future<String?> Function()? onRefreshToken,
  }) async {
    final client = ApiClient(
      baseUrl: baseUrl,
      accessToken: accessToken,
      onRefreshToken: onRefreshToken,
    );
    final params = <String, String>{'token_qr': tokenQr};
    if (latitude != null) params['latitude'] = latitude.toString();
    if (longitude != null) params['longitude'] = longitude.toString();
    if (accuracyM != null) params['accuracy_m'] = accuracyM.toString();
    final query = params.entries
        .map((e) => '${e.key}=${Uri.encodeQueryComponent(e.value)}')
        .join('&');
    return client.get('/api/scan/secure/check-status/?$query');
  }

  Future<Map<String, dynamic>> myHistory({
    required String baseUrl,
    required String accessToken,
    Future<String?> Function()? onRefreshToken,
  }) async {
    final client = ApiClient(
      baseUrl: baseUrl,
      accessToken: accessToken,
      onRefreshToken: onRefreshToken,
    );
    return client.get('/api/me/historique/');
  }
}
