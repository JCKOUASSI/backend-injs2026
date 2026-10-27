import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../providers/session_provider.dart';
import '../utils/confirm_dialog.dart';
import '../utils/auth_navigation.dart';
import '../utils/guarded_logout.dart';
import '../utils/user_facing_error.dart';

class ChangePasswordPage extends StatefulWidget {
  const ChangePasswordPage({super.key});

  @override
  State<ChangePasswordPage> createState() => _ChangePasswordPageState();
}

class _ChangePasswordPageState extends State<ChangePasswordPage> {
  final _formKey = GlobalKey<FormState>();
  final _oldCtrl = TextEditingController();
  final _newCtrl = TextEditingController();
  final _confirmCtrl = TextEditingController();
  bool _loading = false;
  String? _error;
  bool _oldVisible = false;
  bool _newVisible = false;
  bool _confirmVisible = false;

  @override
  void dispose() {
    _oldCtrl.dispose();
    _newCtrl.dispose();
    _confirmCtrl.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (!_formKey.currentState!.validate()) {
      return;
    }
    final ok = await confirm(
      context,
      title: 'Changer le mot de passe',
      message:
          'Confirmer la modification de votre mot de passe ?\n'
          'Vous devrez utiliser le nouveau mot de passe lors de la prochaine connexion.',
      confirmLabel: 'Confirmer',
    );
    if (!ok || !mounted) {
      return;
    }
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      await context.read<SessionProvider>().changePassword(
            oldPassword: _oldCtrl.text,
            newPassword: _newCtrl.text,
          );
      if (!mounted) {
        return;
      }
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Mot de passe mis à jour.')),
      );
      resetToAuthRoot();
    } catch (e, st) {
      logErrorForDebug('password', e, st);
      setState(() => _error = userFacingErrorMessage(
            e,
            fallback: 'Impossible de mettre à jour le mot de passe.',
          ));
    } finally {
      if (mounted) {
        setState(() => _loading = false);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final session = context.watch<SessionProvider>();
    return Scaffold(
      appBar: AppBar(
        title: const Text('Changer le mot de passe'),
        actions: [
          TextButton(
            onPressed: _loading
                ? null
                : () async {
                    await performGuardedLogout(context);
                  },
            child: const Text('Déconnexion'),
          ),
        ],
      ),
      resizeToAvoidBottomInset: true,
      body: SafeArea(
        child: SingleChildScrollView(
          keyboardDismissBehavior: ScrollViewKeyboardDismissBehavior.onDrag,
          padding: EdgeInsets.fromLTRB(
            16,
            16,
            16,
            24 + MediaQuery.viewInsetsOf(context).bottom,
          ),
          child: Align(
            alignment: Alignment.topCenter,
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 420),
              child: Form(
                key: _formKey,
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                  Text(
                    'Première connexion',
                    style: Theme.of(context).textTheme.headlineSmall,
                  ),
                  const SizedBox(height: 8),
                  Text(
                    'Vous devez choisir un nouveau mot de passe avant de pouvoir utiliser le badgeage.',
                    style: Theme.of(context).textTheme.bodyMedium,
                    textAlign: TextAlign.center,
                  ),
                  const SizedBox(height: 8),
                  Text(
                    'Compte: ${session.user?['username'] ?? session.username ?? '-'}',
                    style: Theme.of(context).textTheme.bodySmall,
                  ),
                  const SizedBox(height: 20),
                  TextFormField(
                    controller: _oldCtrl,
                    obscureText: !_oldVisible,
                    decoration: InputDecoration(
                      labelText: 'Mot de passe actuel',
                      border: const OutlineInputBorder(),
                      suffixIcon: IconButton(
                        tooltip:
                            _oldVisible ? 'Masquer' : 'Afficher',
                        icon: Icon(_oldVisible
                            ? Icons.visibility_off_outlined
                            : Icons.visibility_outlined),
                        onPressed: () =>
                            setState(() => _oldVisible = !_oldVisible),
                      ),
                    ),
                    validator: (v) =>
                        (v == null || v.isEmpty) ? 'Champ requis' : null,
                  ),
                  const SizedBox(height: 12),
                  TextFormField(
                    controller: _newCtrl,
                    obscureText: !_newVisible,
                    decoration: InputDecoration(
                      labelText: 'Nouveau mot de passe (min. 8 caractères)',
                      border: const OutlineInputBorder(),
                      suffixIcon: IconButton(
                        tooltip:
                            _newVisible ? 'Masquer' : 'Afficher',
                        icon: Icon(_newVisible
                            ? Icons.visibility_off_outlined
                            : Icons.visibility_outlined),
                        onPressed: () =>
                            setState(() => _newVisible = !_newVisible),
                      ),
                    ),
                    validator: (v) {
                      if (v == null || v.isEmpty) {
                        return 'Champ requis';
                      }
                      if (v.length < 8) {
                        return 'Au moins 8 caractères';
                      }
                      return null;
                    },
                  ),
                  const SizedBox(height: 12),
                  TextFormField(
                    controller: _confirmCtrl,
                    obscureText: !_confirmVisible,
                    decoration: InputDecoration(
                      labelText: 'Confirmer le nouveau mot de passe',
                      border: const OutlineInputBorder(),
                      suffixIcon: IconButton(
                        tooltip:
                            _confirmVisible ? 'Masquer' : 'Afficher',
                        icon: Icon(_confirmVisible
                            ? Icons.visibility_off_outlined
                            : Icons.visibility_outlined),
                        onPressed: () => setState(
                            () => _confirmVisible = !_confirmVisible),
                      ),
                    ),
                    validator: (v) {
                      if (v == null || v.isEmpty) {
                        return 'Champ requis';
                      }
                      if (v != _newCtrl.text) {
                        return 'Les mots de passe ne correspondent pas';
                      }
                      return null;
                    },
                  ),
                  if (_error != null) ...[
                    const SizedBox(height: 12),
                    Text(
                      _error!,
                      style: TextStyle(color: Theme.of(context).colorScheme.error),
                    ),
                  ],
                  const SizedBox(height: 16),
                  SizedBox(
                    width: double.infinity,
                    child: FilledButton(
                      onPressed: _loading ? null : _submit,
                      child: _loading
                          ? const SizedBox(
                              height: 18,
                              width: 18,
                              child: CircularProgressIndicator(strokeWidth: 2),
                            )
                          : const Text('Enregistrer'),
                    ),
                  ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}
