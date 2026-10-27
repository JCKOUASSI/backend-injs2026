import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:geolocator/geolocator.dart';
import 'package:permission_handler/permission_handler.dart';

/// Service GPS actif et permission accordée, sans afficher de dialogue.
Future<bool> isLocationReady() async {
  if (!await Geolocator.isLocationServiceEnabled()) {
    return false;
  }
  final perm = await Geolocator.checkPermission();
  return perm == LocationPermission.always ||
      perm == LocationPermission.whileInUse;
}

/// Demande l'autorisation de localisation (runtime iOS/Android).
/// Affiche une boîte de dialogue explicative avant le prompt système,
/// et propose d'ouvrir les réglages si l'utilisateur a refusé définitivement.
///
/// Retourne `true` si la permission est accordée (whileInUse ou always).
Future<bool> ensureLocationPermission(BuildContext context) async {
  final serviceOn = await Geolocator.isLocationServiceEnabled();
  if (!serviceOn) {
    if (!context.mounted) {
      return false;
    }
    await showDialog<void>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Localisation désactivée'),
        content: const Text(
          'Le service de localisation est désactivé sur l\u2019appareil. '
          'Activez-le dans les réglages pour pouvoir badger.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: const Text('OK'),
          ),
          FilledButton(
            onPressed: () {
              Navigator.pop(ctx);
              Geolocator.openLocationSettings();
            },
            child: const Text('Réglages'),
          ),
        ],
      ),
    );
    return false;
  }

  var perm = await Geolocator.checkPermission();
  if (perm == LocationPermission.always ||
      perm == LocationPermission.whileInUse) {
    return true;
  }

  if (perm == LocationPermission.deniedForever) {
    if (!context.mounted) {
      return false;
    }
    await showDialog<void>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Localisation refusée'),
        content: const Text(
          'L\u2019accès à la position GPS est nécessaire pour badger '
          '(entrée, sortie, suivi de présence). '
          'Vous pouvez l\u2019activer dans les réglages de l\u2019application.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: const Text('OK'),
          ),
          FilledButton(
            onPressed: () {
              Navigator.pop(ctx);
              openAppSettings();
            },
            child: const Text('Réglages'),
          ),
        ],
      ),
    );
    return false;
  }

  // Explication avant le prompt natif.
  //
  // iOS (App Review 5.1.1) : ne pas proposer un bouton de sortie sur l'écran
  // explicatif qui précède la demande système — on affiche l'info, puis on
  // enchaîne sur le prompt.
  if (!context.mounted) {
    return false;
  }
  if (defaultTargetPlatform == TargetPlatform.iOS) {
    await showDialog<void>(
      context: context,
      barrierDismissible: false,
      builder: (ctx) => AlertDialog(
        title: const Text('Autoriser la localisation'),
        content: const Text(
          'QR Badge a besoin de votre position GPS pour valider votre présence '
          'sur le site de formation lors du badgeage et du suivi de session.',
        ),
        actions: [
          FilledButton(
            onPressed: () => Navigator.pop(ctx),
            child: const Text('Continuer'),
          ),
        ],
      ),
    );
  } else {
    await showDialog<void>(
      context: context,
      barrierDismissible: false,
      builder: (ctx) => AlertDialog(
        title: const Text('Autoriser la localisation'),
        content: const Text(
          'QR Badge a besoin de votre position GPS pour valider votre présence '
          'sur le site de formation lors du badgeage et du suivi de session.',
        ),
        actions: [
          FilledButton(
            onPressed: () => Navigator.pop(ctx),
            child: const Text('Continuer'),
          ),
        ],
      ),
    );
  }

  perm = await Geolocator.requestPermission();
  final granted = perm == LocationPermission.always ||
      perm == LocationPermission.whileInUse;
  if (granted && context.mounted) {
    // Demande complémentaire : notifications (Android 13+) + localisation
    // en arrière-plan ("Toujours") pour permettre le suivi pendant la séance.
    await _requestBackgroundExtras(context);
  }
  return granted;
}

/// Demande rapide GPS (bandeaux « Activer ») sans dialogue explicatif préalable.
Future<bool> quickEnableLocation() async {
  final serviceOn = await Geolocator.isLocationServiceEnabled();
  if (!serviceOn) {
    await Geolocator.openLocationSettings();
    return false;
  }
  var perm = await Geolocator.checkPermission();
  if (perm == LocationPermission.deniedForever) {
    await openAppSettings();
    return false;
  }
  if (perm != LocationPermission.always &&
      perm != LocationPermission.whileInUse) {
    perm = await Geolocator.requestPermission();
  }
  return perm == LocationPermission.always ||
      perm == LocationPermission.whileInUse;
}

/// Demande les permissions complémentaires nécessaires au suivi en arrière-plan.
/// Best-effort : on ne bloque pas le flux si l'utilisateur refuse, le badgeage
/// reste possible (le suivi sera juste dégradé en arrière-plan).
Future<void> _requestBackgroundExtras(BuildContext context) async {
  if (kIsWeb) {
    return;
  }
  try {
    if (defaultTargetPlatform == TargetPlatform.android) {
      // POST_NOTIFICATIONS sur Android 13+ : indispensable pour la
      // notification persistante du foreground service.
      final notif = await Permission.notification.status;
      if (notif.isDenied) {
        await Permission.notification.request();
      }

      // ACCESS_BACKGROUND_LOCATION : doit être demandé séparément après
      // que la permission "While in use" a été accordée.
      final bg = await Permission.locationAlways.status;
      if (bg.isGranted) {
        return;
      }
      if (!context.mounted) {
        return;
      }
      await showDialog<void>(
        context: context,
        barrierDismissible: false,
        builder: (ctx) => AlertDialog(
          title: const Text('Suivi en arrière-plan'),
          content: const Text(
            'Pour valider votre présence pendant toute la séance (même écran '
            'verrouillé), QR Badge a besoin de l\u2019autorisation '
            '« Toujours autoriser » pour la position.\n\n'
            'Sur l\u2019écran suivant, choisissez « Toujours autoriser ».',
          ),
          actions: [
            FilledButton(
              onPressed: () => Navigator.pop(ctx),
              child: const Text('Continuer'),
            ),
          ],
        ),
      );
      await Permission.locationAlways.request();
    } else if (defaultTargetPlatform == TargetPlatform.iOS) {
      // iOS : la permission "always" se demande aussi via Geolocator,
      // mais permission_handler offre une API explicite.
      final bg = await Permission.locationAlways.status;
      if (bg.isDenied) {
        await Permission.locationAlways.request();
      }
    }
  } catch (_) {
    // Best-effort : ignorer les erreurs natives (Android < 10 par ex.).
  }
}
