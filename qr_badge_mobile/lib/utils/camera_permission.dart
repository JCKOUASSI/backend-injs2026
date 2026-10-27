import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:permission_handler/permission_handler.dart';

/// Demande l’autorisation caméra (runtime Android / iOS). Retourne false si refus définitif.
Future<bool> ensureCameraPermission(BuildContext context) async {
  if (kIsWeb) {
    // Le navigateur déclenche getUserMedia à l’ouverture du scanner.
    return true;
  }
  var status = await Permission.camera.status;
  if (status.isGranted || status.isLimited) {
    return true;
  }
  if (status.isPermanentlyDenied) {
    if (!context.mounted) {
      return false;
    }
    await showDialog<void>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Caméra refusée'),
        content: const Text(
          'L’accès à la caméra est nécessaire pour scanner le QR. '
          'Vous pouvez l’activer dans les réglages de l’application.',
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

  status = await Permission.camera.request();
  if (status.isGranted || status.isLimited) {
    return true;
  }

  if (!context.mounted) {
    return false;
  }
  ScaffoldMessenger.of(context).showSnackBar(
    const SnackBar(
      content: Text('Autorisation caméra refusée : le scan QR est impossible.'),
    ),
  );
  return false;
}
