import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import 'package:provider/provider.dart';

import '../providers/session_provider.dart';
import '../services/scan_service.dart';
import '../theme/qr_badge_theme.dart';
import '../widgets/home_summary_card.dart';
import '../widgets/qr_badge_logo.dart';

String _displayName(SessionProvider session) {
  final u = session.user;
  if (u != null) {
    final fn = (u['first_name'] ?? '').toString().trim();
    final ln = (u['last_name'] ?? '').toString().trim();
    final full = '$fn $ln'.trim();
    if (full.isNotEmpty) {
      return full;
    }
  }
  return session.user?['username']?.toString() ?? session.username ?? '\u2014';
}

class HomeDashboardPage extends StatefulWidget {
  const HomeDashboardPage({
    super.key,
    this.onOpenHistory,
    this.onOpenScanner,
  });

  final VoidCallback? onOpenHistory;
  final VoidCallback? onOpenScanner;

  @override
  State<HomeDashboardPage> createState() => _HomeDashboardPageState();
}

class _HomeDashboardPageState extends State<HomeDashboardPage>
    with AutomaticKeepAliveClientMixin {
  final _service = ScanService();
  bool _loading = true;
  Map<String, dynamic>? _payload;
  int _lastRefreshTick = -1;

  @override
  bool get wantKeepAlive => true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  void reload() => _load();

  void _maybeReloadFromTick(int tick) {
    if (tick == _lastRefreshTick) {
      return;
    }
    _lastRefreshTick = tick;
    _load();
  }

  Future<void> _load() async {
    final session = context.read<SessionProvider>();
    if (session.accessToken == null) {
      setState(() => _loading = false);
      return;
    }
    setState(() => _loading = true);
    try {
      final res = await _service.myHistory(
        baseUrl: session.baseUrl,
        accessToken: session.accessToken!,
        onRefreshToken: () => session.tryRefreshToken().then(
              (ok) => ok ? session.accessToken : null,
            ),
      );
      if (mounted) {
        setState(() => _payload = res);
      }
    } catch (_) {
      // Tableau de bord dégradé sans historique.
    } finally {
      if (mounted) {
        setState(() => _loading = false);
      }
    }
  }

  List<Map<String, dynamic>> _pointages() {
    final raw = _payload?['pointages'];
    if (raw is! List) {
      return [];
    }
    return raw.map((e) => Map<String, dynamic>.from(e as Map)).toList();
  }

  Map<String, dynamic>? _dernierPointage(List<Map<String, dynamic>> items) {
    if (items.isEmpty) {
      return null;
    }
    final sorted = [...items];
    sorted.sort((a, b) {
      final ta = DateTime.tryParse(
            (a['timestamp_entree'] ?? a['timestamp_sortie'] ?? '').toString(),
          ) ??
          DateTime.fromMillisecondsSinceEpoch(0);
      final tb = DateTime.tryParse(
            (b['timestamp_entree'] ?? b['timestamp_sortie'] ?? '').toString(),
          ) ??
          DateTime.fromMillisecondsSinceEpoch(0);
      return tb.compareTo(ta);
    });
    return sorted.first;
  }

  @override
  Widget build(BuildContext context) {
    super.build(context);
    final tick = context.select<SessionProvider, int>(
      (s) => s.historyRefreshTick,
    );
    _maybeReloadFromTick(tick);
    final session = context.read<SessionProvider>();
    final items = _pointages();
    final dernier = _dernierPointage(items);

    String dernierSousTitre = 'Aucun scan enregistré.';
    if (dernier != null) {
      final dt = DateTime.tryParse(
        (dernier['timestamp_entree'] ?? dernier['timestamp_sortie'] ?? '')
            .toString(),
      );
      if (dt != null) {
        final now = DateTime.now();
        final sameDay = dt.year == now.year &&
            dt.month == now.month &&
            dt.day == now.day;
        final prefix =
            sameDay ? 'Aujourd\'hui' : DateFormat('d MMMM', 'fr_FR').format(dt);
        dernierSousTitre =
            '$prefix à ${DateFormat.Hm('fr_FR').format(dt.toLocal())}';
      }
    }

    return RefreshIndicator(
      onRefresh: _load,
      child: ListView(
        padding: const EdgeInsets.fromLTRB(16, 8, 16, 24),
        children: [
          Row(
            children: [
              const QrBadgeLogo(
                size: 52,
                color: AppColors.ciSuccessDark,
                backgroundColor: AppColors.iconQrBg,
              ),
              const SizedBox(width: 14),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'Bonjour, ${_displayName(session)}',
                      style: Theme.of(context).textTheme.titleMedium?.copyWith(
                            fontWeight: FontWeight.w700,
                            color: AppColors.textPrimary,
                          ),
                    ),
                  ],
                ),
              ),
            ],
          ),
          const SizedBox(height: 16),
          if (session.isSecureHeartbeatRunning && widget.onOpenScanner != null)
            FilledButton.icon(
              onPressed: widget.onOpenScanner,
              icon: const Icon(Icons.logout),
              label: const Text('Badger ma sortie'),
              style: FilledButton.styleFrom(
                padding: const EdgeInsets.symmetric(vertical: 14),
              ),
            ),
          const SizedBox(height: 20),
          if (_loading)
            const Padding(
              padding: EdgeInsets.symmetric(vertical: 24),
              child: Center(child: CircularProgressIndicator()),
            )
          else ...[
            HomeSummaryCard(
              icon: Icons.phonelink_lock,
              iconBg: AppColors.iconQrBg,
              iconColor: AppColors.ciSuccessDark,
              title: 'Dernier scan',
              subtitle: dernierSousTitre,
              trailing: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  if (dernier != null)
                    const StatusPill(
                      label: 'Enregistré',
                      color: AppColors.ciSuccessDark,
                      backgroundColor: AppColors.navIndicator,
                      icon: Icons.check,
                    ),
                  if (widget.onOpenHistory != null) ...[
                    const SizedBox(width: 4),
                    Icon(Icons.chevron_right, color: AppColors.textSecondary.withValues(alpha: 0.6)),
                  ],
                ],
              ),
              onTap: widget.onOpenHistory,
            ),
          ],
        ],
      ),
    );
  }
}
