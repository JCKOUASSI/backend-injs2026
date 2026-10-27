import 'package:flutter/foundation.dart';

/// Journalisation debug (préfixe `[qr_badge.*]` — filtrable dans le terminal).
///
/// Voir les logs pendant `flutter run`, ou :
/// `flutter logs | grep qr_badge`
class AppLog {
  AppLog._();

  static void d(String tag, String message) {
    if (kDebugMode) {
      debugPrint('[qr_badge.$tag] $message');
    }
  }

  static void api(String message) => d('api', message);

  static void session(String message) => d('session', message);

  static void scan(String message) => d('scan', message);

  static void nav(String message) => d('nav', message);

  static void location(String message) => d('location', message);

  static void error(String tag, Object error, [StackTrace? stackTrace]) {
    if (!kDebugMode) {
      return;
    }
    debugPrint('[qr_badge.$tag] $error');
    if (stackTrace != null) {
      debugPrint('$stackTrace');
    }
  }
}
