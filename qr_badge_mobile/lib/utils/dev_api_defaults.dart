import 'package:device_info_plus/device_info_plus.dart';
import 'package:flutter/foundation.dart';

import '../config/app_env.dart';

/// URL du backend en développement (port 8001 par défaut).
///
/// - **Simulateur iOS** / bureau : `http://127.0.0.1:8001`
/// - **Émulateur Android** : `http://10.0.2.2:8001` (alias de la machine hôte)
/// - **Téléphone réel** : lancer avec `--dart-define=DEV_API_HOST=192.168.x.x`
///   ou remplir DEV_API_HOST / API_BASE_URL dans assets/app.env.
class DevApiDefaults {
  DevApiDefaults._();

  static const String _hostFromEnv = String.fromEnvironment(
    'DEV_API_HOST',
    defaultValue: '',
  );
  static const String _portFromEnv = String.fromEnvironment(
    'DEV_API_PORT',
    defaultValue: '8001',
  );

  static String _url(String host, String port) =>
      'http://${host.trim()}:${port.trim()}';

  static String _hostBuildOrDot() {
    final h = _hostFromEnv.trim();
    if (h.isNotEmpty) {
      return h;
    }
    return AppEnv.devApiHostFromDot.trim();
  }

  static String _portForResolvedHost() {
    if (_hostFromEnv.trim().isNotEmpty) {
      return _portFromEnv.trim().isNotEmpty ? _portFromEnv.trim() : '8001';
    }
    return AppEnv.devApiPortFromDot.trim().isNotEmpty
        ? AppEnv.devApiPortFromDot.trim()
        : '8001';
  }

  static final DeviceInfoPlugin _deviceInfo = DeviceInfoPlugin();
  static Future<bool>? _emuOrSimFuture;

  static Future<bool> _isEmulatorOrSimulator() async {
    if (kIsWeb) {
      return false;
    }
    _emuOrSimFuture ??= _computeEmulatorOrSimulator();
    return _emuOrSimFuture!;
  }

  static Future<bool> _computeEmulatorOrSimulator() async {
    if (kIsWeb) {
      return false;
    }
    try {
      if (defaultTargetPlatform == TargetPlatform.iOS) {
        final ios = await _deviceInfo.iosInfo;
        return !ios.isPhysicalDevice;
      }
      if (defaultTargetPlatform == TargetPlatform.android) {
        final a = await _deviceInfo.androidInfo;
        if (!a.isPhysicalDevice) {
          return true;
        }
        final fingerprint =
            '${a.model} ${a.product} ${a.device} ${a.fingerprint}'.toLowerCase();
        return fingerprint.contains('generic') ||
            fingerprint.contains('emulator') ||
            fingerprint.contains('sdk_gphone') ||
            fingerprint.contains('google_sdk');
      }
    } catch (_) {
      return false;
    }
    return false;
  }

  /// Première URL à utiliser si rien n’est enregistré dans les préférences.
  static Future<String> resolve() async {
    final host = _hostBuildOrDot();
    if (host.isNotEmpty) {
      return _url(host, _portForResolvedHost());
    }
    if (kIsWeb) {
      return _url('127.0.0.1', _portFromEnv);
    }
    if (defaultTargetPlatform == TargetPlatform.android) {
      if (await _isEmulatorOrSimulator()) {
        return _url('10.0.2.2', _portFromEnv);
      }
      return _url('127.0.0.1', _portFromEnv);
    }
    if (defaultTargetPlatform == TargetPlatform.iOS) {
      if (await _isEmulatorOrSimulator()) {
        return _url('127.0.0.1', _portFromEnv);
      }
      return _url('127.0.0.1', _portFromEnv);
    }
    return _url('127.0.0.1', _portFromEnv);
  }

}
