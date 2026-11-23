import 'api_client.dart';

class MobileConfigService {
  Future<Map<String, dynamic>> fetch({
    required String baseUrl,
    required String accessToken,
    Future<String?> Function()? onRefreshToken,
  }) async {
    final client = ApiClient(
      baseUrl: baseUrl,
      accessToken: accessToken,
      onRefreshToken: onRefreshToken,
    );
    return client.get('/api/mobile/config/');
  }
}
