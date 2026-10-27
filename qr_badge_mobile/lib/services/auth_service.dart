import 'api_client.dart';

class AuthService {
  Future<Map<String, dynamic>> login({
    required String baseUrl,
    required String username,
    required String password,
    required String deviceId,
    required String deviceInfo,
  }) async {
    final client = ApiClient(baseUrl: baseUrl);
    return client.post(
      '/api/auth/login/',
      withAuth: false,
      data: {
        'username': username,
        'password': password,
        'device_id': deviceId,
        'device_info': deviceInfo,
      },
    );
  }

  Future<Map<String, dynamic>> me({
    required String baseUrl,
    required String accessToken,
  }) async {
    final client = ApiClient(baseUrl: baseUrl, accessToken: accessToken);
    return client.get('/api/auth/me/');
  }

  Future<Map<String, dynamic>> refreshToken({
    required String baseUrl,
    required String refreshToken,
  }) async {
    final client = ApiClient(baseUrl: baseUrl);
    return client.post(
      '/api/auth/token/refresh/',
      withAuth: false,
      data: {'refresh': refreshToken},
    );
  }

  Future<Map<String, dynamic>> changePassword({
    required String baseUrl,
    required String accessToken,
    required String oldPassword,
    required String newPassword,
  }) async {
    final client = ApiClient(baseUrl: baseUrl, accessToken: accessToken);
    return client.post(
      '/api/auth/me/change-password/',
      data: {
        'old_password': oldPassword,
        'new_password': newPassword,
      },
    );
  }

  /// Champs autorisés : prénom, nom, e-mail, téléphone, organisation, grade, matricule.
  Future<Map<String, dynamic>> updateMyProfile({
    required String baseUrl,
    required String accessToken,
    required Map<String, dynamic> data,
    Future<String?> Function()? onRefreshToken,
  }) async {
    final client = ApiClient(
      baseUrl: baseUrl,
      accessToken: accessToken,
      onRefreshToken: onRefreshToken,
    );
    return client.patch('/api/auth/me/', data: data);
  }
}
