import 'package:flutter/material.dart';
import 'package:flutter_dotenv/flutter_dotenv.dart';
import 'package:intl/date_symbol_data_local.dart';
import 'package:provider/provider.dart';

import 'providers/session_provider.dart';
import 'pages/splash_page.dart';
import 'utils/app_log.dart';
import 'utils/auth_navigation.dart';
import 'services/background_keepalive.dart';
import 'theme/qr_badge_theme.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  try {
    await initializeDateFormatting('fr_FR', null);
  } catch (e, st) {
    debugPrint('intl locale: $e\n$st');
  }
  try {
    await dotenv.load(fileName: 'assets/app.env');
  } catch (e, st) {
    debugPrint('app.env introuvable ou invalide: $e\n$st');
  }
  // Foreground task Android / flux iOS (no-op Web : pas de heartbeat arrière-plan natif).
  try {
    await BackgroundKeepalive.instance.initialize();
  } catch (e, st) {
    debugPrint('background keepalive init: $e\n$st');
  }
  AppLog.d('app', 'QR Badge démarré');
  runApp(const QRBadgeApp());
}

class QRBadgeApp extends StatelessWidget {
  const QRBadgeApp({super.key});

  @override
  Widget build(BuildContext context) {
    return ChangeNotifierProvider(
      create: (_) => SessionProvider()..bootstrap(),
      child: MaterialApp(
        navigatorKey: appNavigatorKey,
        title: 'QR Badge',
        debugShowCheckedModeBanner: false,
        theme: buildQrBadgeTheme(),
        home: const SplashPage(),
      ),
    );
  }
}
