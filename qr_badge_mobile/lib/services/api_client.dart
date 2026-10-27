import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:http/http.dart' as http;

import '../utils/app_log.dart';

/// Timeout appliqué à chaque requête réseau.
/// 10 s est suffisant sur un LAN ; au-delà le serveur est considéré injoignable.
const _kTimeout = Duration(seconds: 10);

class ApiClient {
  ApiClient({
    required this.baseUrl,
    this.accessToken,
    this.onRefreshToken,
  });

  final String baseUrl;
  final String? accessToken;

  /// Callback optionnel appelé quand le serveur renvoie 401.
  /// Doit retourner le nouveau token d'accès, ou null si le refresh a échoué.
  final Future<String?> Function()? onRefreshToken;

  /// Endpoints d'auth où un 401 est métier (identifiants invalides, refresh
  /// expiré) — ne jamais relancer via refresh + retry automatique.
  static bool _mayRefreshOn401(String path) {
    return !path.contains('/auth/login/') &&
        !path.contains('/auth/token/refresh/');
  }

  Uri _uri(String path) {
    final normalizedBase = baseUrl.endsWith('/')
        ? baseUrl.substring(0, baseUrl.length - 1)
        : baseUrl;
    final normalizedPath = path.startsWith('/') ? path : '/$path';
    return Uri.parse('$normalizedBase$normalizedPath');
  }

  Map<String, String> _headers({bool withAuth = true}) {
    return {
      'Content-Type': 'application/json',
      if (withAuth && accessToken != null && accessToken!.isNotEmpty)
        'Authorization': 'Bearer $accessToken',
    };
  }

  Map<String, String> _headersWithToken(String token) {
    return {
      'Content-Type': 'application/json',
      'Authorization': 'Bearer $token',
    };
  }

  Future<Map<String, dynamic>> post(
    String path, {
    Map<String, dynamic>? data,
    bool withAuth = true,
  }) async {
    final uri = _uri(path);
    AppLog.api('→ POST $path');
    try {
      final res = await http
          .post(
            uri,
            headers: _headers(withAuth: withAuth),
            body: jsonEncode(data ?? <String, dynamic>{}),
          )
          .timeout(_kTimeout);
      if (res.statusCode == 401 &&
          withAuth &&
          onRefreshToken != null &&
          _mayRefreshOn401(path)) {
        AppLog.api('POST $path → 401, tentative de refresh…');
        final newToken = await onRefreshToken!();
        if (newToken != null) {
          AppLog.api('POST $path → refresh OK, retry…');
          final retryRes = await http
              .post(
                uri,
                headers: _headersWithToken(newToken),
                body: jsonEncode(data ?? <String, dynamic>{}),
              )
              .timeout(_kTimeout);
          return _parse(retryRes, method: 'POST', path: path, uri: uri);
        }
        AppLog.api('POST $path → refresh échoué, session expirée.');
        throw const SessionExpiredException();
      }
      return _parse(res, method: 'POST', path: path, uri: uri);
    } on SessionExpiredException {
      rethrow;
    } on ApiResponseException {
      rethrow;
    } on ApiBusinessException {
      rethrow;
    } on NoProfileException {
      rethrow;
    } on TimeoutException {
      AppLog.api('POST $path → timeout (${_kTimeout.inSeconds}s)');
      throw const NetworkTimeoutException();
    } catch (e, st) {
      AppLog.error('api', 'POST $path → erreur réseau: $e', st);
      throw _asNetworkException(e);
    }
  }

  Future<Map<String, dynamic>> get(
    String path, {
    bool withAuth = true,
  }) async {
    final uri = _uri(path);
    AppLog.api('→ GET $path');
    try {
      final res = await http
          .get(
            uri,
            headers: _headers(withAuth: withAuth),
          )
          .timeout(_kTimeout);
      if (res.statusCode == 401 &&
          withAuth &&
          onRefreshToken != null &&
          _mayRefreshOn401(path)) {
        AppLog.api('GET $path → 401, tentative de refresh…');
        final newToken = await onRefreshToken!();
        if (newToken != null) {
          AppLog.api('GET $path → refresh OK, retry…');
          final retryRes = await http
              .get(
                uri,
                headers: _headersWithToken(newToken),
              )
              .timeout(_kTimeout);
          return _parse(retryRes, method: 'GET', path: path, uri: uri);
        }
        AppLog.api('GET $path → refresh échoué, session expirée.');
        throw const SessionExpiredException();
      }
      return _parse(res, method: 'GET', path: path, uri: uri);
    } on SessionExpiredException {
      rethrow;
    } on ApiResponseException {
      rethrow;
    } on ApiBusinessException {
      rethrow;
    } on NoProfileException {
      rethrow;
    } on TimeoutException {
      AppLog.api('GET $path → timeout (${_kTimeout.inSeconds}s)');
      throw const NetworkTimeoutException();
    } catch (e, st) {
      AppLog.error('api', 'GET $path → erreur réseau: $e', st);
      throw _asNetworkException(e);
    }
  }

  Future<Map<String, dynamic>> patch(
    String path, {
    Map<String, dynamic>? data,
    bool withAuth = true,
  }) async {
    final uri = _uri(path);
    AppLog.api('→ PATCH $path');
    try {
      final res = await http
          .patch(
            uri,
            headers: _headers(withAuth: withAuth),
            body: jsonEncode(data ?? <String, dynamic>{}),
          )
          .timeout(_kTimeout);
      if (res.statusCode == 401 &&
          withAuth &&
          onRefreshToken != null &&
          _mayRefreshOn401(path)) {
        final newToken = await onRefreshToken!();
        if (newToken != null) {
          final retryRes = await http
              .patch(
                uri,
                headers: _headersWithToken(newToken),
                body: jsonEncode(data ?? <String, dynamic>{}),
              )
              .timeout(_kTimeout);
          return _parse(retryRes, method: 'PATCH', path: path, uri: uri);
        }
        throw const SessionExpiredException();
      }
      return _parse(res, method: 'PATCH', path: path, uri: uri);
    } on SessionExpiredException {
      rethrow;
    } on ApiResponseException {
      rethrow;
    } on ApiBusinessException {
      rethrow;
    } on NoProfileException {
      rethrow;
    } on TimeoutException {
      throw const NetworkTimeoutException();
    } catch (e, st) {
      AppLog.error('api', 'PATCH $path → erreur réseau: $e', st);
      throw _asNetworkException(e);
    }
  }

  Never _asNetworkException(Object error) {
    if (error is NetworkTimeoutException ||
        error is NetworkUnreachableException ||
        error is SessionExpiredException ||
        error is ApiResponseException ||
        error is ApiBusinessException ||
        error is NoProfileException) {
      throw error;
    }
    if (error is SocketException ||
        error is http.ClientException ||
        error is HandshakeException ||
        error is TlsException) {
      throw const NetworkUnreachableException();
    }
    throw error;
  }

  Map<String, dynamic> _parse(
    http.Response res, {
    required String method,
    required String path,
    required Uri uri,
  }) {
    Map<String, dynamic> json = <String, dynamic>{};
    if (res.body.isNotEmpty) {
      try {
        final decoded = jsonDecode(res.body);
        if (decoded is Map<String, dynamic>) {
          json = decoded;
        } else {
          json = {'data': decoded};
        }
      } catch (_) {
        final trimmed = res.body.trimLeft();
        if (trimmed.startsWith('<!DOCTYPE') ||
            trimmed.startsWith('<html') ||
            trimmed.startsWith('<')) {
          throw ApiResponseException(
            statusCode: res.statusCode,
            path: path,
            message: res.statusCode == 404
                ? 'Service indisponible.'
                : 'Réponse inattendue du serveur.',
          );
        }
        rethrow;
      }
    }
    if (res.statusCode >= 200 && res.statusCode < 300) {
      AppLog.api('← $method $path HTTP ${res.statusCode}');
      return json;
    }
    final bodyPreview = res.body.length > 800
        ? '${res.body.substring(0, 800)}…'
        : res.body;
    AppLog.api('$method $path → HTTP ${res.statusCode} uri=$uri body=$bodyPreview');
    if (json['code']?.toString() == 'PASSWORD_CHANGE_REQUIRED') {
      throw ApiBusinessException(
        'PASSWORD_CHANGE_REQUIRED',
        json['detail']?.toString(),
      );
    }
    if (json['code']?.toString() == 'NO_PROFILE') {
      throw NoProfileException(json['detail']?.toString());
    }
    final code = json['code']?.toString();
    if (code != null && code.isNotEmpty) {
      throw ApiBusinessException(
        code,
        json['detail']?.toString(),
      );
    }
    final detail = json['detail']?.toString() ??
        json['message']?.toString() ??
        _firstFieldError(json) ??
        'Erreur API (${res.statusCode})';
    if (res.statusCode == 429) {
      throw ApiResponseException(
        statusCode: res.statusCode,
        path: path,
        message: detail.contains('Request was throttled') ||
                detail.contains('Too Many')
            ? 'Trop de tentatives de connexion. Patientez une minute puis réessayez.'
            : detail,
      );
    }
    throw ApiResponseException(
      statusCode: res.statusCode,
      path: path,
      message: detail,
    );
  }

  String? _firstFieldError(Map<String, dynamic> body) {
    for (final entry in body.entries) {
      final v = entry.value;
      if (v is List && v.isNotEmpty) {
        return v.first.toString();
      }
      if (v is String && v.isNotEmpty) {
        return v;
      }
    }
    return null;
  }
}

/// Message utilisateur pour les codes d'erreur métier renvoyés par l'API.
String friendlyApiMessage(String code, [String? detail]) {
  switch (code) {
    case 'NOT_IN_LIST':
      if (detail != null && detail.contains('encadrant')) {
        return detail;
      }
      return detail ??
          'Vous n\u2019\u00eates pas autoris\u00e9(e) pour ce module.';
    case 'NO_MATRICULE':
      return detail ??
          'Aucun matricule sur votre compte encadrant. '
          'Contactez le secr\u00e9tariat.';
    case 'LOCATION_REQUIRED':
      return 'Activez la g\u00e9olocalisation pour badger cette s\u00e9ance '
          '(p\u00e9rim\u00e8tre obligatoire sur le site).';
    case 'OUT_OF_GEOFENCE':
      return detail ??
          'Vous \u00eates hors du p\u00e9rim\u00e8tre autoris\u00e9 pour badger. '
          'Rapprochez-vous du site de formation.';
    case 'LOCATION_INVALID':
      return detail ??
          'Coordonn\u00e9es GPS invalides. R\u00e9essayez apr\u00e8s avoir '
          'actualis\u00e9 la position.';
    case 'PASSWORD_CHANGE_REQUIRED':
      return detail ??
          'Vous devez changer votre mot de passe avant de continuer.';
    case 'DEVICE_REQUIRED':
      return detail ??
          'Identifiant appareil manquant. Reconnectez-vous \u00e0 l\u2019application.';
    case 'DEVICE_LOCKED':
      return detail ??
          'Cet appareil est d\u00e9j\u00e0 li\u00e9 \u00e0 un autre compte.';
    default:
      return detail ?? 'Erreur ($code).';
  }
}

/// Erreur m\u00e9tier renvoy\u00e9e par l'API avec un code JSON explicite.
class ApiBusinessException implements Exception {
  const ApiBusinessException(this.code, [this.detail]);
  final String code;
  final String? detail;

  @override
  String toString() => friendlyApiMessage(code, detail);
}

/// Exception levée quand une requête d\u00e9passe [_kTimeout].
class NetworkTimeoutException implements Exception {
  const NetworkTimeoutException();

  @override
  String toString() => 'Délai de connexion dépassé.';
}

/// Connexion réseau impossible (hôte injoignable, TLS, socket…).
class NetworkUnreachableException implements Exception {
  const NetworkUnreachableException();

  @override
  String toString() => 'Connexion au serveur impossible.';
}

/// Exception publique pour que les appelants puissent capturer la session expir\u00e9e.
class SessionExpiredException implements Exception {
  const SessionExpiredException();
  @override
  String toString() => 'Session expir\u00e9e. Veuillez vous reconnecter.';
}

/// Levée quand le compte n'a aucun profil étudiant/formateur/encadrant lié
/// (HTTP 403, code `NO_PROFILE`). Permet d'afficher un état vide dédié.
class NoProfileException implements Exception {
  const NoProfileException([this.detail]);
  final String? detail;
  @override
  String toString() =>
      detail ??
      'Aucun profil étudiant, formateur ou encadrant n\u2019est li\u00e9 \u00e0 ce compte.';
}

/// Réponse HTTP non JSON (souvent une page 404 HTML Django).
class ApiResponseException implements Exception {
  const ApiResponseException({
    required this.statusCode,
    required this.path,
    required this.message,
  });

  final int statusCode;
  final String path;
  final String message;

  @override
  String toString() => message;
}
