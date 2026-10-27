import 'dart:async';

import 'package:flutter/material.dart';
import 'package:geolocator/geolocator.dart';
import 'package:provider/provider.dart';

import '../providers/session_provider.dart';
import '../theme/qr_badge_theme.dart';
import '../utils/guarded_logout.dart';
import '../utils/location_permission.dart';
import '../utils/open_privacy_policy.dart';
import '../widgets/session_status_banner.dart';
import 'evaluations_page.dart';
import 'history_page.dart';
import 'home_dashboard_page.dart';
import 'profile_fiche_page.dart';
import 'scan_page.dart';

class HomePage extends StatefulWidget {
  const HomePage({super.key});

  @override
  State<HomePage> createState() => _HomePageState();
}

class _HomePageState extends State<HomePage> with WidgetsBindingObserver {
  static const _tabScanner = 0;
  static const _tabAccueil = 1;
  static const _tabHistorique = 2;
  static const _tabProfil = 3;

  int _index = _tabAccueil;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) {
        return;
      }
      final session = context.read<SessionProvider>();
      session.refreshPendingEvaluationsCount();
      final restored = session.consumeOpenSessionRestoredSnack();
      if (restored != null) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(restored)),
        );
      }
    });
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) {
      final session = context.read<SessionProvider>();
      unawaited(_recheckGpsOnResume(session));
      session.pulseHeartbeatNow();
      session.refreshPendingEvaluationsCount();
    }
  }

  Future<void> _recheckGpsOnResume(SessionProvider session) async {
    final perm = await Geolocator.checkPermission();
    if (!mounted) {
      return;
    }
    final granted = perm == LocationPermission.always ||
        perm == LocationPermission.whileInUse;
    session.setGpsGranted(granted);
    if (granted && session.heartbeatGpsBlocked) {
      session.pulseHeartbeatNow();
    }
  }

  void _selectTab(int index) {
    setState(() => _index = index);
  }

  Future<void> _requestGps(SessionProvider session) async {
    final granted = await quickEnableLocation();
    if (mounted) {
      session.setGpsGranted(granted);
      if (granted && session.isSecureHeartbeatRunning) {
        session.pulseHeartbeatNow();
      }
    }
  }

  String get _title {
    switch (_index) {
      case _tabScanner:
        return 'Scanner';
      case _tabAccueil:
        return 'Accueil';
      case _tabHistorique:
        return 'Historique';
      case _tabProfil:
        return 'Profil';
      default:
        return 'QR Badge';
    }
  }

  Future<void> _openEvaluations() async {
    await Navigator.of(context).push(
      MaterialPageRoute<void>(
        builder: (_) => Scaffold(
          backgroundColor: AppColors.ciLight,
          appBar: AppBar(title: const Text('Évaluations')),
          body: const EvaluationsPage(),
        ),
      ),
    );
    if (mounted) {
      await context.read<SessionProvider>().refreshPendingEvaluationsCount();
    }
  }

  Future<void> _onMoreMenuSelected(String value) async {
    final session = context.read<SessionProvider>();
    switch (value) {
      case 'evaluations':
        await _openEvaluations();
      case 'gps':
        await _requestGps(session);
      case 'privacy':
        await openPrivacyPolicy(context, session.baseUrl);
      case 'logout':
        await performGuardedLogout(context);
    }
  }

  List<PopupMenuEntry<String>> _moreMenuItems({
    required bool showEvaluations,
    required int pendingEval,
  }) {
    return [
      if (showEvaluations)
        PopupMenuItem(
          value: 'evaluations',
          child: ListTile(
            contentPadding: EdgeInsets.zero,
            leading: const Icon(Icons.assignment_outlined),
            title: const Text('Évaluations'),
            trailing: pendingEval > 0
                ? Badge(
                    label: Text('$pendingEval'),
                    backgroundColor: AppColors.ciWarningDark,
                  )
                : null,
          ),
        ),
      const PopupMenuItem(
        value: 'gps',
        child: ListTile(
          contentPadding: EdgeInsets.zero,
          leading: Icon(Icons.location_on_outlined),
          title: Text('Autoriser le GPS'),
        ),
      ),
      const PopupMenuItem(
        value: 'privacy',
        child: ListTile(
          contentPadding: EdgeInsets.zero,
          leading: Icon(Icons.policy_outlined),
          title: Text('Confidentialité'),
        ),
      ),
      const PopupMenuDivider(),
      const PopupMenuItem(
        value: 'logout',
        child: ListTile(
          contentPadding: EdgeInsets.zero,
          leading: Icon(Icons.logout, color: AppColors.ciDanger),
          title: Text('Déconnexion', style: TextStyle(color: AppColors.ciDanger)),
        ),
      ),
    ];
  }

  @override
  Widget build(BuildContext context) {
    final pendingEvaluationsCount = context.select<SessionProvider, int>(
      (s) => s.pendingEvaluationsCount,
    );
    final heartbeatGpsBlocked = context.select<SessionProvider, bool>(
      (s) => s.heartbeatGpsBlocked,
    );
    final gpsGranted = context.select<SessionProvider, bool>(
      (s) => s.gpsGranted,
    );
    final heartbeatRunning = context.select<SessionProvider, bool>(
      (s) => s.isSecureHeartbeatRunning,
    );
    final evaluationsEnabled = context.select<SessionProvider, bool>(
      (s) => s.evaluationsEnabled,
    );

    return Scaffold(
      backgroundColor: AppColors.ciLight,
      appBar: AppBar(
        centerTitle: _index == _tabHistorique,
        title: Text(_title),
        actions: [
          Badge(
            isLabelVisible: pendingEvaluationsCount > 0,
            label: Text('$pendingEvaluationsCount'),
            backgroundColor: AppColors.ciWarningDark,
            child: PopupMenuButton<String>(
              icon: const Icon(Icons.more_vert),
              tooltip: 'Plus',
              onSelected: _onMoreMenuSelected,
              itemBuilder: (_) => _moreMenuItems(
                showEvaluations: evaluationsEnabled,
                pendingEval: pendingEvaluationsCount,
              ),
            ),
          ),
        ],
      ),
      body: Column(
        children: [
          if (heartbeatGpsBlocked && heartbeatRunning)
            Material(
              color: Colors.orange.shade50,
              child: Padding(
                padding:
                    const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
                child: Row(
                  children: [
                    Icon(Icons.location_off,
                        color: Colors.orange.shade700, size: 20),
                    const SizedBox(width: 8),
                    Expanded(
                      child: Text(
                        'GPS indisponible — suivi suspendu.',
                        style: TextStyle(
                          fontSize: 12,
                          color: Colors.orange.shade900,
                        ),
                      ),
                    ),
                    TextButton(
                      style: TextButton.styleFrom(
                        padding: const EdgeInsets.symmetric(horizontal: 8),
                        foregroundColor: Colors.orange.shade800,
                      ),
                      onPressed: () =>
                          _requestGps(context.read<SessionProvider>()),
                      child: const Text('Activer',
                          style: TextStyle(fontSize: 12)),
                    ),
                  ],
                ),
              ),
            )
          else if (!gpsGranted)
            Material(
              color: Colors.orange.shade50,
              child: Padding(
                padding:
                    const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
                child: Row(
                  children: [
                    Icon(Icons.location_off,
                        color: Colors.orange.shade700, size: 20),
                    const SizedBox(width: 8),
                    Expanded(
                      child: Text(
                        'GPS non autorisé.',
                        style: TextStyle(
                          fontSize: 12,
                          color: Colors.orange.shade900,
                        ),
                      ),
                    ),
                    TextButton(
                      style: TextButton.styleFrom(
                        padding: const EdgeInsets.symmetric(horizontal: 8),
                        foregroundColor: Colors.orange.shade800,
                      ),
                      onPressed: () =>
                          _requestGps(context.read<SessionProvider>()),
                      child: const Text('Activer',
                          style: TextStyle(fontSize: 12)),
                    ),
                  ],
                ),
              ),
            ),
          if (heartbeatRunning) const SessionStatusBanner(),
          Expanded(
            child: IndexedStack(
              index: _index,
              children: [
                ScanPage(isActive: _index == _tabScanner),
                HomeDashboardPage(
                  onOpenHistory: () => _selectTab(_tabHistorique),
                  onOpenScanner: () => _selectTab(_tabScanner),
                ),
                HistoryPage(
                  onOpenScanner: () => _selectTab(_tabScanner),
                ),
                ProfileFichePage(
                  embedded: true,
                  onOpenHistory: () => _selectTab(_tabHistorique),
                ),
              ],
            ),
          ),
        ],
      ),
      bottomNavigationBar: NavigationBar(
        selectedIndex: _index,
        onDestinationSelected: _selectTab,
        destinations: const [
          NavigationDestination(
            icon: Icon(Icons.qr_code_scanner_outlined),
            selectedIcon: Icon(Icons.qr_code_scanner),
            label: 'Scanner',
          ),
          NavigationDestination(
            icon: Icon(Icons.home_outlined),
            selectedIcon: Icon(Icons.home),
            label: 'Accueil',
          ),
          NavigationDestination(
            icon: Icon(Icons.history_outlined),
            selectedIcon: Icon(Icons.history),
            label: 'Historique',
          ),
          NavigationDestination(
            icon: Icon(Icons.person_outline),
            selectedIcon: Icon(Icons.person),
            label: 'Profil',
          ),
        ],
      ),
    );
  }
}
