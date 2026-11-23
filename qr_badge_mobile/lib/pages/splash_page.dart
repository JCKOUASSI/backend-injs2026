import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../providers/session_provider.dart';
import '../utils/location_permission.dart';
import 'change_password_page.dart';
import 'home_page.dart';
import 'login_page.dart';

class SplashPage extends StatefulWidget {
  const SplashPage({super.key});

  @override
  State<SplashPage> createState() => _SplashPageState();
}

class _SplashPageState extends State<SplashPage> {
  bool _locationAsked = false;

  Future<void> _maybeAskLocation(SessionProvider session) async {
    if (_locationAsked) {
      return;
    }
    _locationAsked = true;
    // Laisse la première frame se dessiner avant le prompt natif.
    await Future<void>.delayed(const Duration(milliseconds: 300));
    if (!mounted) {
      return;
    }
    final granted = await ensureLocationPermission(context);
    if (mounted) {
      session.setGpsGranted(granted);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<SessionProvider>(
      builder: (_, session, _) {
        if (session.isBootstrapping) {
          return const Scaffold(
            body: Center(child: CircularProgressIndicator()),
          );
        }
        if (!_locationAsked) {
          WidgetsBinding.instance.addPostFrameCallback(
            (_) => _maybeAskLocation(session),
          );
        }
        if (session.isAuthenticated) {
          if (session.mustChangePassword) {
            return const ChangePasswordPage();
          }
          return const HomePage();
        }
        return const LoginPage();
      },
    );
  }
}
