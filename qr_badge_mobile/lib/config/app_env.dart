import 'package:flutter_dotenv/flutter_dotenv.dart';

/// Lecture centralisée des variables (assets/app.env + éventuels --dart-define).
class AppEnv {
  AppEnv._();

  static const String _apiFromDefine = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: '',
  );
  static const String _logoutFromDefine = String.fromEnvironment(
    'SUPERVISOR_LOGOUT_CODE',
    defaultValue: '',
  );
  static const String _heartbeatSecDefine = String.fromEnvironment(
    'HEARTBEAT_INTERVAL_SECONDS',
    defaultValue: '',
  );
  static const String _heartbeatEnabledDefine = String.fromEnvironment(
    'HEARTBEAT_ENABLED',
    defaultValue: '',
  );
  static const String _privacyPolicyFromDefine = String.fromEnvironment(
    'PRIVACY_POLICY_URL',
    defaultValue: '',
  );

  static String? _dot(String key) {
    final v = dotenv.env[key]?.trim();
    if (v == null || v.isEmpty) {
      return null;
    }
    return v;
  }

  /// URL API explicite (dart-define ou .env) ; `null` = laisser la résolution plateforme.
  static String? get explicitApiBaseUrl {
    if (_apiFromDefine.isNotEmpty) {
      return _apiFromDefine;
    }
    return _dot('API_BASE_URL');
  }

  /// URL affichée / stockée par défaut avant toute logique async.
  static String get initialApiBaseUrl =>
      explicitApiBaseUrl ?? 'http://127.0.0.1:8001';

  static String get supervisorLogoutCode {
    if (_logoutFromDefine.isNotEmpty) {
      return _logoutFromDefine;
    }
    return _dot('SUPERVISOR_LOGOUT_CODE') ?? '';
  }

  /// Hôte LAN optionnel depuis .env (si pas de --dart-define).
  static String get devApiHostFromDot => _dot('DEV_API_HOST') ?? '';

  static String get devApiPortFromDot => _dot('DEV_API_PORT') ?? '8001';

  /// URL complète de la politique de confidentialité (stores).
  /// Priorité : `--dart-define=PRIVACY_POLICY_URL=` ou `PRIVACY_POLICY_URL` dans app.env,
  /// sinon dérivée de l’URL API : `{origin}/dashboard/legal/confidentialite-qr-badge/`.
  static String privacyPolicyUrlForApiBase(String apiBaseUrl) {
    final fromDefine = _privacyPolicyFromDefine.trim();
    if (fromDefine.isNotEmpty) {
      return fromDefine;
    }
    final fromDot = _dot('PRIVACY_POLICY_URL')?.trim();
    if (fromDot != null && fromDot.isNotEmpty) {
      return fromDot;
    }
    return _privacyUrlDerivedFromApiBase(apiBaseUrl);
  }

  static String _privacyUrlDerivedFromApiBase(String apiBaseUrl) {
    var raw = apiBaseUrl.trim();
    if (raw.isEmpty) {
      raw = 'http://127.0.0.1:8001';
    }
    if (!raw.contains('://')) {
      raw = 'http://$raw';
    }
    final u = Uri.parse(raw);
    if (!u.hasScheme || u.host.isEmpty) {
      return raw;
    }
    return Uri(
      scheme: u.scheme,
      host: u.host,
      port: u.hasPort ? u.port : null,
      path: '/dashboard/legal/confidentialite-qr-badge/',
    ).toString();
  }

  static bool _parseBoolEnv(String raw, {bool defaultValue = true}) {
    final v = raw.trim().toLowerCase();
    if (v.isEmpty) {
      return defaultValue;
    }
    if (v == 'false' || v == '0' || v == 'no' || v == 'off') {
      return false;
    }
    return true;
  }

  /// Envoi périodique de heartbeat pendant une session ouverte (défaut : activé).
  static bool get heartbeatEnabled {
    if (_heartbeatEnabledDefine.isNotEmpty) {
      return _parseBoolEnv(_heartbeatEnabledDefine);
    }
    return _parseBoolEnv(_dot('HEARTBEAT_ENABLED') ?? '');
  }

  /// Entre deux envois automatiques de heartbeat pendant une session ouverte.
  static Duration get heartbeatInterval {
    var sec = 60;
    if (_heartbeatSecDefine.isNotEmpty) {
      sec = int.tryParse(_heartbeatSecDefine.trim()) ?? sec;
    } else {
      final d = _dot('HEARTBEAT_INTERVAL_SECONDS');
      if (d != null) {
        sec = int.tryParse(d) ?? sec;
      }
    }
    sec = sec.clamp(30, 600);
    return Duration(seconds: sec);
  }
}
