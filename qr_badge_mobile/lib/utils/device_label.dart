import 'package:device_info_plus/device_info_plus.dart';
import 'package:flutter/foundation.dart';

/// Libellé lisible de l'appareil (nom utilisateur iOS, marque/modèle Android, etc.).
class DeviceLabel {
  DeviceLabel._();

  static final DeviceInfoPlugin _deviceInfo = DeviceInfoPlugin();
  static Future<String>? _cachedFuture;

  static Future<String> resolve() {
    _cachedFuture ??= _compute();
    return _cachedFuture!;
  }

  static Future<String> _compute() async {
    try {
      if (kIsWeb) {
        final web = await _deviceInfo.webBrowserInfo;
        final browser = web.browserName.name;
        final platform = web.platform ?? 'Web';
        return '$browser ($platform)';
      }
      switch (defaultTargetPlatform) {
        case TargetPlatform.iOS:
          final ios = await _deviceInfo.iosInfo;
          final name = ios.name.trim();
          if (name.isNotEmpty) {
            return name;
          }
          return 'Apple ${ios.model}'.trim();
        case TargetPlatform.android:
          final android = await _deviceInfo.androidInfo;
          final brand = android.brand.trim();
          final model = android.model.trim();
          if (brand.isNotEmpty && model.isNotEmpty) {
            return '$brand $model';
          }
          return model.isNotEmpty ? model : brand;
        case TargetPlatform.macOS:
          final mac = await _deviceInfo.macOsInfo;
          final name = mac.computerName.trim();
          if (name.isNotEmpty) {
            return name;
          }
          return mac.model.trim();
        default:
          return defaultTargetPlatform.name;
      }
    } catch (_) {
      return 'Appareil mobile';
    }
  }
}
