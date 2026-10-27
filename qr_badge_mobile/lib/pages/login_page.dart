import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../providers/session_provider.dart';
import '../theme/qr_badge_theme.dart';
import '../utils/open_privacy_policy.dart';
import '../utils/user_facing_error.dart';
import '../widgets/qr_badge_logo.dart';

class LoginPage extends StatefulWidget {
  const LoginPage({super.key});

  @override
  State<LoginPage> createState() => _LoginPageState();
}

class _LoginPageState extends State<LoginPage> {
  final _formKey = GlobalKey<FormState>();
  final _usernameCtrl = TextEditingController();
  final _passwordCtrl = TextEditingController();
  bool _loading = false;
  bool _submitInFlight = false;
  bool _obscurePassword = true;
  String? _error;

  @override
  void dispose() {
    _usernameCtrl.dispose();
    _passwordCtrl.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (_submitInFlight || _loading) {
      return;
    }
    if (!_formKey.currentState!.validate()) {
      return;
    }
    _submitInFlight = true;
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final session = context.read<SessionProvider>();
      await session.login(
        usernameInput: _usernameCtrl.text,
        passwordInput: _passwordCtrl.text,
      );
      if (!mounted) {
        return;
      }
      // SplashPage se reconstruit via SessionProvider.notifyListeners().
    } catch (e, st) {
      logErrorForDebug('login', e, st);
      final session = context.read<SessionProvider>();
      setState(() => _error = userFacingErrorMessage(
            e,
            context: UserErrorContext.login,
            serverBaseUrl: session.baseUrl,
          ));
    } finally {
      _submitInFlight = false;
      if (mounted) {
        setState(() => _loading = false);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.ciLight,
      appBar: AppBar(
        centerTitle: false,
        title: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            const QrBadgeLogo(size: 28, color: Colors.white),
            const SizedBox(width: 10),
            Text(
              'QR Badge',
              style: Theme.of(context).appBarTheme.titleTextStyle,
            ),
          ],
        ),
      ),
      resizeToAvoidBottomInset: true,
      body: SafeArea(
        child: LayoutBuilder(
          builder: (context, constraints) {
            return SingleChildScrollView(
              keyboardDismissBehavior: ScrollViewKeyboardDismissBehavior.onDrag,
              padding: EdgeInsets.fromLTRB(
                20,
                8,
                20,
                24 + MediaQuery.viewInsetsOf(context).bottom,
              ),
              child: ConstrainedBox(
                constraints: BoxConstraints(minHeight: constraints.maxHeight),
                child: Column(
                  mainAxisAlignment: MainAxisAlignment.center,
                  crossAxisAlignment: CrossAxisAlignment.center,
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    ConstrainedBox(
                      constraints: const BoxConstraints(maxWidth: 420),
                      child: Material(
                        elevation: 2,
                        shadowColor: Colors.black12,
                        borderRadius: BorderRadius.circular(20),
                        color: AppColors.cardBg,
                        child: Padding(
                        padding: const EdgeInsets.fromLTRB(24, 28, 24, 24),
                        child: Form(
                          key: _formKey,
                          child: Column(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              const QrBadgeLogo(
                                size: 72,
                                color: AppColors.ciSuccessDark,
                                backgroundColor: AppColors.iconQrBg,
                              ),
                              const SizedBox(height: 24),
                              TextFormField(
                                controller: _usernameCtrl,
                                decoration: const InputDecoration(
                                  labelText: 'Identifiant',
                                ),
                                textInputAction: TextInputAction.next,
                                validator: (v) =>
                                    (v == null || v.trim().isEmpty)
                                        ? 'Champ requis'
                                        : null,
                              ),
                              const SizedBox(height: 16),
                              TextFormField(
                                controller: _passwordCtrl,
                                obscureText: _obscurePassword,
                                decoration: InputDecoration(
                                  labelText: 'Mot de passe',
                                  suffixIcon: IconButton(
                                    tooltip: _obscurePassword
                                        ? 'Afficher'
                                        : 'Masquer',
                                    icon: Icon(
                                      _obscurePassword
                                          ? Icons.visibility_off_outlined
                                          : Icons.visibility_outlined,
                                      color: AppColors.textSecondary,
                                    ),
                                    onPressed: () => setState(
                                      () => _obscurePassword = !_obscurePassword,
                                    ),
                                  ),
                                ),
                                validator: (v) => (v == null || v.isEmpty)
                                    ? 'Champ requis'
                                    : null,
                                onFieldSubmitted: (_) {
                                  if (!_submitInFlight && !_loading) {
                                    _submit();
                                  }
                                },
                              ),
                              if (_error != null) ...[
                                const SizedBox(height: 8),
                                Text(
                                  _error!,
                                  style: TextStyle(
                                    color: Theme.of(context).colorScheme.error,
                                    fontSize: 13,
                                  ),
                                ),
                              ],
                              const SizedBox(height: 8),
                              SizedBox(
                                width: double.infinity,
                                child: FilledButton(
                                  onPressed: _loading ? null : _submit,
                                  child: _loading
                                      ? const SizedBox(
                                          height: 22,
                                          width: 22,
                                          child: CircularProgressIndicator(
                                            strokeWidth: 2,
                                            color: Colors.white,
                                          ),
                                        )
                                      : const Text('Connexion'),
                                ),
                              ),
                            ],
                          ),
                        ),
                      ),
                    ),
                    ),
                    const SizedBox(height: 20),
                    TextButton.icon(
                      onPressed: () => openPrivacyPolicy(
                        context,
                        context.read<SessionProvider>().baseUrl,
                      ),
                      icon: const Icon(
                        Icons.verified_user_outlined,
                        size: 18,
                        color: AppColors.ciSuccessDark,
                      ),
                      label: const Text(
                        'Confidentialité',
                        style: TextStyle(
                          color: AppColors.ciSuccessDark,
                          decoration: TextDecoration.underline,
                          decorationColor: AppColors.ciSuccessDark,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            );
          },
        ),
      ),
    );
  }
}
