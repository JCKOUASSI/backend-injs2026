import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../config/app_env.dart';
import '../providers/session_provider.dart';
import 'auth_navigation.dart';

/// Demande le code encadrant puis déconnecte si le code est correct.
/// Retourne `true` si la déconnexion a eu lieu.
Future<bool> performGuardedLogout(BuildContext context) async {
  final entered = await _promptSupervisorCode(context);
  if (!context.mounted || entered == null) {
    return false;
  }
  if (AppEnv.supervisorLogoutCode.isEmpty) {
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(
        content: Text(
          'Code de déconnexion non configuré. Contactez un administrateur.',
        ),
      ),
    );
    return false;
  }
  if (entered.trim() != AppEnv.supervisorLogoutCode) {
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(
        content: Text(
          'Code incorrect. Seuls un administrateur ou un chef CPFAE Admin '
          'peuvent fournir le code de déconnexion.',
        ),
      ),
    );
    return false;
  }
  resetToAuthRoot();
  await context.read<SessionProvider>().logout();
  return true;
}

Future<String?> _promptSupervisorCode(BuildContext context) {
  return showDialog<String>(
    context: context,
    barrierDismissible: false,
    builder: (ctx) => const _SupervisorCodeDialog(),
  );
}

class _SupervisorCodeDialog extends StatefulWidget {
  const _SupervisorCodeDialog();

  @override
  State<_SupervisorCodeDialog> createState() => _SupervisorCodeDialogState();
}

class _SupervisorCodeDialogState extends State<_SupervisorCodeDialog> {
  final _controller = TextEditingController();

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: const Text('Déconnexion'),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            'Saisissez le code fourni par un administrateur ou un chef CPFAE Admin.',
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _controller,
            decoration: const InputDecoration(
              labelText: 'Code encadrant',
              border: OutlineInputBorder(),
            ),
            keyboardType: TextInputType.visiblePassword,
            obscureText: true,
            autofocus: true,
            onSubmitted: (_) => Navigator.pop(context, _controller.text),
          ),
        ],
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(context),
          child: const Text('Annuler'),
        ),
        FilledButton(
          onPressed: () => Navigator.pop(context, _controller.text),
          child: const Text('Valider'),
        ),
      ],
    );
  }
}
