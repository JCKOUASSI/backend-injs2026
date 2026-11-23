import 'package:flutter/material.dart';

import 'app_log.dart';

/// Clé du [Navigator] racine de [MaterialApp] — navigation auth sans [BuildContext]
/// potentiellement invalidé après [SessionProvider.logout].
final GlobalKey<NavigatorState> appNavigatorKey = GlobalKey<NavigatorState>();

/// Ferme dialogs / bottom sheets / routes poussées au-dessus de [SplashPage].
///
/// À appeler **avant** [SessionProvider.logout] pour éviter de manipuler le
/// navigateur avec un contexte déjà démonté (GlobalKey Navigator dupliquées).
///
/// L'écran login / accueil est géré par le [Consumer] de [SplashPage] sur
/// l'état [SessionProvider] — ne jamais empiler une nouvelle [SplashPage].
void resetToAuthRoot() {
  final nav = appNavigatorKey.currentState;
  if (nav != null && nav.canPop()) {
    AppLog.nav('resetToAuthRoot popUntil(isFirst)');
    nav.popUntil((route) => route.isFirst);
  }
}
