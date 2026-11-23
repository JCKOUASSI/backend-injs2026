import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter_foreground_task/flutter_foreground_task.dart';
import 'package:geolocator/geolocator.dart';

/// TaskHandler minimal du service en avant-plan (Android).
///
/// Ce handler ne fait *rien* fonctionnellement : son seul rôle est de garder
/// le process Android vivant via la notification persistante. Le heartbeat
/// continue d'être émis depuis l'isolate principal (où vit `SessionProvider`),
/// car un service en avant-plan empêche l'OS de suspendre le process et
/// donc d'arrêter le `Timer.periodic` du heartbeat.
@pragma('vm:entry-point')
void backgroundKeepaliveEntry() {
  FlutterForegroundTask.setTaskHandler(_KeepaliveTaskHandler());
}

class _KeepaliveTaskHandler extends TaskHandler {
  @override
  Future<void> onStart(DateTime timestamp, TaskStarter starter) async {}

  @override
  void onRepeatEvent(DateTime timestamp) {}

  @override
  Future<void> onDestroy(DateTime timestamp) async {}
}

/// Garde l'app vivante en arrière-plan tant qu'une session de heartbeat est ouverte.
///
/// - **Android** : démarre un foreground service via `flutter_foreground_task`
///   avec une notification persistante. Le process reste alors en priorité
///   "foreground", ce qui permet au `Timer.periodic` du heartbeat (dans
///   l'isolate principal) de continuer à tourner même écran éteint.
/// - **iOS** : ouvre un flux `Geolocator.getPositionStream` avec
///   `showBackgroundLocationIndicator: true`. Tant que le flux est actif, iOS
///   maintient l'app vivante en arrière-plan et continue d'exécuter le code
///   Dart (donc les timers).
class BackgroundKeepalive {
  BackgroundKeepalive._();
  static final BackgroundKeepalive instance = BackgroundKeepalive._();

  bool _initialized = false;
  bool _running = false;
  StreamSubscription<Position>? _iosPosSub;

  bool get isRunning => _running;

  /// À appeler une fois au démarrage de l'app (avant `runApp`).
  Future<void> initialize() async {
    if (_initialized) return;
    _initialized = true;
    if (kIsWeb) return;
    if (defaultTargetPlatform != TargetPlatform.android) return;

    FlutterForegroundTask.initCommunicationPort();
    FlutterForegroundTask.init(
      androidNotificationOptions: AndroidNotificationOptions(
        channelId: 'qr_badge_presence',
        channelName: 'Suivi de présence',
        channelDescription:
            'Maintient la session de badgeage active en arrière-plan.',
        channelImportance: NotificationChannelImportance.LOW,
        priority: NotificationPriority.LOW,
      ),
      iosNotificationOptions: const IOSNotificationOptions(
        showNotification: false,
        playSound: false,
      ),
      foregroundTaskOptions: ForegroundTaskOptions(
        eventAction: ForegroundTaskEventAction.nothing(),
        autoRunOnBoot: false,
        autoRunOnMyPackageReplaced: false,
        allowWakeLock: true,
        allowWifiLock: false,
      ),
    );
  }

  /// Démarre le mécanisme de keepalive.
  Future<void> start() async {
    if (kIsWeb) return;
    if (_running) return;
    _running = true;
    try {
      if (defaultTargetPlatform == TargetPlatform.android) {
        await initialize();
        final running = await FlutterForegroundTask.isRunningService;
        if (!running) {
          await FlutterForegroundTask.startService(
            notificationTitle: 'QR Badge',
            notificationText: 'Suivi de présence actif',
            notificationIcon: null,
            callback: backgroundKeepaliveEntry,
          );
        }
      } else if (defaultTargetPlatform == TargetPlatform.iOS) {
        await _startIosLocationStream();
      }
    } catch (e, st) {
      debugPrint('[qr_badge.keepalive] start: $e\n$st');
    }
  }

  /// Arrête le mécanisme de keepalive.
  Future<void> stop() async {
    if (!_running) return;
    _running = false;
    try {
      if (defaultTargetPlatform == TargetPlatform.android) {
        if (await FlutterForegroundTask.isRunningService) {
          await FlutterForegroundTask.stopService();
        }
      } else if (defaultTargetPlatform == TargetPlatform.iOS) {
        await _iosPosSub?.cancel();
        _iosPosSub = null;
      }
    } catch (e, st) {
      debugPrint('[qr_badge.keepalive] stop: $e\n$st');
    }
  }

  Future<void> _startIosLocationStream() async {
    await _iosPosSub?.cancel();
    final settings = AppleSettings(
      accuracy: LocationAccuracy.high,
      activityType: ActivityType.other,
      pauseLocationUpdatesAutomatically: false,
      showBackgroundLocationIndicator: true,
      allowBackgroundLocationUpdates: true,
      distanceFilter: 0,
    );
    _iosPosSub = Geolocator.getPositionStream(locationSettings: settings)
        .listen((_) {}, onError: (Object e, StackTrace st) {
      debugPrint('[qr_badge.keepalive] iOS stream error: $e');
    });
  }
}
