import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import 'package:provider/provider.dart';

import '../providers/session_provider.dart';
import '../services/api_client.dart';
import '../services/scan_service.dart';
import '../theme/qr_badge_theme.dart';
import '../utils/auth_navigation.dart';
import '../utils/user_facing_error.dart';
import '../widgets/empty_state_view.dart';

enum _HistoryFilter { all, entrees, sorties, alertes }

enum _HistoryEventKind { entree, sortie }

class _HistoryEvent {
  _HistoryEvent({
    required this.at,
    required this.label,
    required this.success,
    required this.kind,
  });

  final DateTime at;
  final String label;
  final bool success;
  final _HistoryEventKind kind;
}

class _HistorySection {
  _HistorySection({required this.title, required this.events});

  final String title;
  final List<_HistoryEvent> events;
}

class HistoryPage extends StatefulWidget {
  const HistoryPage({super.key, this.onOpenScanner});

  final VoidCallback? onOpenScanner;

  @override
  State<HistoryPage> createState() => _HistoryPageState();
}

class _HistoryPageState extends State<HistoryPage> with AutomaticKeepAliveClientMixin {
  final _service = ScanService();
  bool _loading = true;
  String? _error;
  bool _noProfile = false;
  List<_HistoryEvent> _events = [];
  _HistoryFilter _filter = _HistoryFilter.all;
  int _lastRefreshTick = -1;

  @override
  bool get wantKeepAlive => true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  void _maybeReloadFromTick(int tick) {
    if (tick == _lastRefreshTick) {
      return;
    }
    _lastRefreshTick = tick;
    _load();
  }

  List<_HistoryEvent> _eventsFromPayload(Map<String, dynamic>? p) {
    final rawList = p?['pointages'];
    final items = rawList is List ? rawList.cast<dynamic>() : <dynamic>[];
    final events = <_HistoryEvent>[];
    for (final raw in items) {
      final m = Map<String, dynamic>.from(raw as Map);
      final entree = DateTime.tryParse((m['timestamp_entree'] ?? '').toString());
      final sortie = DateTime.tryParse((m['timestamp_sortie'] ?? '').toString());
      final statut = (m['statut'] ?? '').toString();
      const okStatuts = {
        '', 'PRESENT', 'VALIDE', 'EN_COURS', 'TERMINE', 'FORCE_DFRC',
      };
      const alertStatuts = {
        'HORS_LIGNE_SUSPECT', 'ABSENT_NON_BADGE', 'SORTIE_AUTO',
      };
      final ok = okStatuts.contains(statut) && !alertStatuts.contains(statut);
      final titre = (m['formation_titre'] ?? '').toString().trim();
      final module = (m['module_intitule'] ?? '').toString().trim();
      final contexte = [titre, module].where((s) => s.isNotEmpty).join(' · ');
      if (entree != null) {
        events.add(_HistoryEvent(
          at: entree.toLocal(),
          label: contexte.isEmpty ? 'Entrée' : '$contexte — Entrée',
          success: ok,
          kind: _HistoryEventKind.entree,
        ));
      }
      if (sortie != null) {
        final sortieLabel = statut == 'SORTIE_AUTO'
            ? 'Sortie automatique'
            : 'Sortie';
        events.add(_HistoryEvent(
          at: sortie.toLocal(),
          label: contexte.isEmpty ? sortieLabel : '$contexte — $sortieLabel',
          success: ok && statut != 'SORTIE_AUTO',
          kind: _HistoryEventKind.sortie,
        ));
      }
    }
    events.sort((a, b) => b.at.compareTo(a.at));
    return events;
  }

  List<_HistoryEvent> _filteredEvents() {
    return _events.where((e) {
      switch (_filter) {
        case _HistoryFilter.all:
          return true;
        case _HistoryFilter.entrees:
          return e.kind == _HistoryEventKind.entree;
        case _HistoryFilter.sorties:
          return e.kind == _HistoryEventKind.sortie;
        case _HistoryFilter.alertes:
          return !e.success;
      }
    }).toList();
  }

  String _dateGroupLabel(DateTime dt) {
    final now = DateTime.now();
    final today = DateTime(now.year, now.month, now.day);
    final day = DateTime(dt.year, dt.month, dt.day);
    final diff = today.difference(day).inDays;
    if (diff == 0) return 'Aujourd\u2019hui';
    if (diff == 1) return 'Hier';
    return DateFormat('d MMMM yyyy', 'fr_FR').format(dt);
  }

  List<_HistorySection> _groupEvents(List<_HistoryEvent> events) {
    if (events.isEmpty) {
      return [];
    }
    final sections = <_HistorySection>[];
    String? currentTitle;
    final buffer = <_HistoryEvent>[];
    for (final event in events) {
      final title = _dateGroupLabel(event.at);
      if (title != currentTitle) {
        if (buffer.isNotEmpty) {
          sections.add(_HistorySection(title: currentTitle!, events: [...buffer]));
          buffer.clear();
        }
        currentTitle = title;
      }
      buffer.add(event);
    }
    if (buffer.isNotEmpty && currentTitle != null) {
      sections.add(_HistorySection(title: currentTitle, events: [...buffer]));
    }
    return sections;
  }

  Future<void> _load() async {
    final session = context.read<SessionProvider>();
    if (session.accessToken == null) {
      setState(() {
        _error = 'Non connecté.';
        _loading = false;
      });
      return;
    }
    setState(() {
      _loading = true;
      _error = null;
      _noProfile = false;
    });
    try {
      final res = await _service.myHistory(
        baseUrl: session.baseUrl,
        accessToken: session.accessToken!,
        onRefreshToken: () => session.tryRefreshToken().then(
              (ok) => ok ? session.accessToken : null,
            ),
      );
      setState(() => _events = _eventsFromPayload(res));
    } on NoProfileException {
      setState(() => _noProfile = true);
    } on SessionExpiredException {
      if (mounted) {
        resetToAuthRoot();
        await context.read<SessionProvider>().logout();
      }
      return;
    } catch (e, st) {
      logErrorForDebug('history', e, st);
      setState(() => _error = userFacingErrorMessage(
            e,
            context: UserErrorContext.history,
          ));
    } finally {
      if (mounted) {
        setState(() => _loading = false);
      }
    }
  }

  Widget _buildFilterChips() {
    return SingleChildScrollView(
      scrollDirection: Axis.horizontal,
      padding: const EdgeInsets.fromLTRB(16, 8, 16, 4),
      child: Row(
        children: [
          _FilterChip(
            label: 'Tous',
            selected: _filter == _HistoryFilter.all,
            onSelected: () => setState(() => _filter = _HistoryFilter.all),
          ),
          const SizedBox(width: 8),
          _FilterChip(
            label: 'Entrées',
            selected: _filter == _HistoryFilter.entrees,
            onSelected: () => setState(() => _filter = _HistoryFilter.entrees),
          ),
          const SizedBox(width: 8),
          _FilterChip(
            label: 'Sorties',
            selected: _filter == _HistoryFilter.sorties,
            onSelected: () => setState(() => _filter = _HistoryFilter.sorties),
          ),
          const SizedBox(width: 8),
          _FilterChip(
            label: 'Alertes',
            selected: _filter == _HistoryFilter.alertes,
            onSelected: () => setState(() => _filter = _HistoryFilter.alertes),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    super.build(context);
    final tick = context.select<SessionProvider, int>(
      (s) => s.historyRefreshTick,
    );
    _maybeReloadFromTick(tick);
    if (_loading) {
      return const Center(child: CircularProgressIndicator());
    }
    if (_noProfile) {
      return _NoProfileState(onRetry: _load);
    }
    if (_error != null) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(
                _error!,
                style: TextStyle(color: Theme.of(context).colorScheme.error),
              ),
              const SizedBox(height: 8),
              OutlinedButton(onPressed: _load, child: const Text('Réessayer')),
            ],
          ),
        ),
      );
    }

    if (_events.isEmpty) {
      return EmptyStateView(
        icon: Icons.history,
        title: 'Aucun pointage enregistré',
        subtitle:
            'Scannez un QR code de séance pour voir vos badgeages ici.',
        action: widget.onOpenScanner != null
            ? FilledButton.icon(
                onPressed: widget.onOpenScanner,
                icon: const Icon(Icons.qr_code_scanner),
                label: const Text('Aller au scanner'),
              )
            : null,
      );
    }

    final filtered = _filteredEvents();
    final sections = _groupEvents(filtered);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        _buildFilterChips(),
        Expanded(
          child: filtered.isEmpty
              ? EmptyStateView(
                  icon: Icons.filter_list_off,
                  iconColor: AppColors.textSecondary,
                  title: 'Aucun pointage pour ce filtre',
                  subtitle: 'Essayez un autre filtre ou actualisez la liste.',
                  action: OutlinedButton.icon(
                    onPressed: _load,
                    icon: const Icon(Icons.refresh),
                    label: const Text('Actualiser'),
                  ),
                )
              : RefreshIndicator(
                  onRefresh: _load,
                  child: ListView(
                    padding: const EdgeInsets.fromLTRB(16, 8, 16, 24),
                    children: [
                      for (var i = 0; i < sections.length; i++) ...[
                        Padding(
                          padding:
                              EdgeInsets.only(bottom: 10, top: i == 0 ? 0 : 16),
                          child: Text(
                            sections[i].title,
                            style: Theme.of(context).textTheme.titleSmall?.copyWith(
                                  fontWeight: FontWeight.w700,
                                  color: AppColors.textSecondary,
                                ),
                          ),
                        ),
                        for (final event in sections[i].events)
                          Padding(
                            padding: const EdgeInsets.only(bottom: 10),
                            child: _HistoryEntryCard(event: event),
                          ),
                      ],
                    ],
                  ),
                ),
        ),
      ],
    );
  }
}

class _FilterChip extends StatelessWidget {
  const _FilterChip({
    required this.label,
    required this.selected,
    required this.onSelected,
  });

  final String label;
  final bool selected;
  final VoidCallback onSelected;

  @override
  Widget build(BuildContext context) {
    return FilterChip(
      label: Text(label),
      selected: selected,
      onSelected: (_) => onSelected(),
      selectedColor: AppColors.navIndicator,
      checkmarkColor: AppColors.ciSuccessDark,
      labelStyle: TextStyle(
        fontWeight: selected ? FontWeight.w700 : FontWeight.w500,
        color: selected ? AppColors.ciSuccessDark : AppColors.textPrimary,
      ),
      side: BorderSide(
        color: selected ? AppColors.ciSuccessDark : AppColors.borderColor,
      ),
    );
  }
}

class _HistoryEntryCard extends StatelessWidget {
  const _HistoryEntryCard({required this.event});

  final _HistoryEvent event;

  @override
  Widget build(BuildContext context) {
    final timeFmt = DateFormat.Hm('fr_FR');
    return Material(
      color: AppColors.cardBg,
      borderRadius: BorderRadius.circular(14),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(14),
          border: Border.all(color: AppColors.borderColor.withValues(alpha: 0.7)),
          boxShadow: const [
            BoxShadow(
              color: Color(0x08000000),
              blurRadius: 6,
              offset: Offset(0, 2),
            ),
          ],
        ),
        child: Row(
          children: [
            Container(
              width: 44,
              height: 44,
              decoration: const BoxDecoration(
                color: AppColors.iconQrBg,
                shape: BoxShape.circle,
              ),
              child: Icon(
                event.success ? Icons.check : Icons.info_outline,
                color: event.success ? AppColors.ciSuccessDark : AppColors.ciWarning,
                size: 24,
              ),
            ),
            const SizedBox(width: 14),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    timeFmt.format(event.at),
                    style: Theme.of(context).textTheme.titleSmall?.copyWith(
                          fontWeight: FontWeight.w700,
                          color: AppColors.textPrimary,
                        ),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    event.label,
                    style: TextStyle(
                      color: event.success
                          ? AppColors.ciSuccessDark
                          : AppColors.ciWarningDark,
                      fontWeight: FontWeight.w600,
                      fontSize: 13,
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _NoProfileState extends StatelessWidget {
  const _NoProfileState({required this.onRetry});

  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.person_off, size: 56, color: Colors.grey),
            const SizedBox(height: 16),
            Text(
              'Aucun profil trouvé.',
              textAlign: TextAlign.center,
              style: Theme.of(context).textTheme.titleMedium,
            ),
            const SizedBox(height: 8),
            const Text(
              'Vérifiez votre compte et réessayez.',
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 18),
            OutlinedButton(onPressed: onRetry, child: const Text('Réessayer')),
          ],
        ),
      ),
    );
  }
}
