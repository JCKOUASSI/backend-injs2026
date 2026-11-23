import 'package:battery_plus/battery_plus.dart';
import 'package:geolocator/geolocator.dart';

/// Données lues automatiquement sur l’appareil (GPS, précision, batterie).
class DeviceTelemetry {
  const DeviceTelemetry({
    this.latitude,
    this.longitude,
    this.accuracyM,
    this.batteryLevel,
    this.isCharging,
    this.locationError,
  });

  final double? latitude;
  final double? longitude;
  final double? accuracyM;
  final int? batteryLevel;
  final bool? isCharging;
  final String? locationError;

  bool get hasPosition =>
      latitude != null && longitude != null && latitude!.isFinite && longitude!.isFinite;
}

class DeviceTelemetryService {
  DeviceTelemetryService({Battery? battery}) : _battery = battery ?? Battery();

  final Battery _battery;

  DeviceTelemetry? _cached;
  DateTime? _cachedAt;

  /// Durée pendant laquelle une capture récente est réutilisée sans relire le GPS.
  static const cacheTtl = Duration(seconds: 15);

  /// Récupère position (une lecture) + état batterie. Ne demande pas la localisation si déjà refusée définitivement sans nouvelle demande.
  ///
  /// Pour rester rapide, on réutilise d'abord le dernier point connu (retour
  /// quasi instantané). Un fix frais n'est demandé qu'en secours, avec un
  /// timeout court, afin de ne pas bloquer le badgeage plusieurs secondes.
  ///
  /// Les appels rapprochés (< [cacheTtl]) renvoient le même résultat en mémoire,
  /// sauf si [forceRefresh] est vrai (ex. bouton « Recalculer la position »).
  Future<DeviceTelemetry> capture({
    Duration locationTimeout = const Duration(seconds: 6),
    Duration lastKnownMaxAge = const Duration(seconds: 30),
    bool forceRefresh = false,
  }) async {
    if (!forceRefresh &&
        _cached != null &&
        _cachedAt != null &&
        DateTime.now().difference(_cachedAt!) <= cacheTtl) {
      return _cached!;
    }
    String? locErr;
    double? lat;
    double? lng;
    double? acc;

    try {
      final serviceOn = await Geolocator.isLocationServiceEnabled();
      if (!serviceOn) {
        locErr = 'Service de localisation désactivé sur l’appareil.';
      } else {
        var perm = await Geolocator.checkPermission();
        if (perm == LocationPermission.denied) {
          perm = await Geolocator.requestPermission();
        }
        if (perm == LocationPermission.denied) {
          locErr = 'Localisation refusée.';
        } else if (perm == LocationPermission.deniedForever) {
          locErr = 'Localisation refusée définitivement. Activez-la dans les réglages.';
        } else {
          // 1) Dernier point connu : instantané s'il est encore récent.
          try {
            final last = await Geolocator.getLastKnownPosition();
            final ts = last?.timestamp;
            final fresh = last != null &&
                ts != null &&
                DateTime.now().difference(ts) <= lastKnownMaxAge;
            if (fresh) {
              lat = last.latitude;
              lng = last.longitude;
              acc = last.accuracy;
            }
          } catch (_) {
            // Ignoré : on tentera un fix frais ci-dessous.
          }

          // 2) Sinon, fix frais avec timeout court.
          if (lat == null || lng == null) {
            final p = await Geolocator.getCurrentPosition(
              locationSettings: LocationSettings(
                accuracy: LocationAccuracy.medium,
                timeLimit: locationTimeout,
              ),
            );
            lat = p.latitude;
            lng = p.longitude;
            acc = p.accuracy;
          }
        }
      }
    } catch (e) {
      locErr = e.toString();
    }

    int? level;
    bool? charging;
    try {
      level = await _battery.batteryLevel;
      final state = await _battery.batteryState;
      charging = state == BatteryState.charging || state == BatteryState.full;
    } catch (_) {
      // Simulateur / bureau : souvent indisponible
    }

    final result = DeviceTelemetry(
      latitude: lat,
      longitude: lng,
      accuracyM: acc,
      batteryLevel: level,
      isCharging: charging,
      locationError: locErr,
    );
    _cached = result;
    _cachedAt = DateTime.now();
    return result;
  }
}
