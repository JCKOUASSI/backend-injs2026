import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import '../config/app_env.dart';

/// Ouvre la politique de confidentialité dans le navigateur externe.
Future<void> openPrivacyPolicy(BuildContext context, String apiBaseUrl) async {
  final uri = Uri.parse(AppEnv.privacyPolicyUrlForApiBase(apiBaseUrl));
  try {
    // Ne pas utiliser canLaunchUrl : sur Android 11+ il renvoie souvent false
    // même quand le navigateur peut ouvrir le lien (sans <queries> ou faux négatif).
    final launched = await launchUrl(
      uri,
      mode: LaunchMode.externalApplication,
    );
    if (!launched && context.mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Ouverture du lien impossible. Réessayez plus tard.'),
        ),
      );
    }
  } catch (_) {
    if (context.mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Ouverture du lien impossible. Réessayez plus tard.'),
        ),
      );
    }
  }
}
