import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import 'package:provider/provider.dart';

import '../providers/session_provider.dart';
import '../services/api_client.dart';
import '../services/profile_service.dart';
import '../theme/qr_badge_theme.dart';
import '../utils/auth_navigation.dart';
import '../utils/user_facing_error.dart';
import 'change_password_page.dart';
import '../widgets/home_summary_card.dart';
import '../widgets/empty_state_view.dart';
import '../widgets/qr_badge_logo.dart';

part 'profile_fiche_widgets.dart';

class ProfileFichePage extends StatefulWidget {
  const ProfileFichePage({
    super.key,
    this.embedded = false,
    this.onClose,
    this.onOpenHistory,
  });

  /// Intégré comme onglet dans [HomePage] (sans AppBar propre).
  final bool embedded;

  /// Fermeture sans détruire l'état (overlay legacy).
  final VoidCallback? onClose;
  final VoidCallback? onOpenHistory;

  @override
  State<ProfileFichePage> createState() => _ProfileFichePageState();
}

class _ProfileFichePageState extends State<ProfileFichePage> {
  final _service = ProfileService();
  final _scrollCtrl = ScrollController();
  final _modulesSectionKey = GlobalKey();
  bool _loading = true;
  String? _error;
  Map<String, dynamic>? _payload;
  int _lastRefreshTick = -1;

  @override
  void dispose() {
    _scrollCtrl.dispose();
    super.dispose();
  }

  void _scrollToModules() {
    final ctx = _modulesSectionKey.currentContext;
    if (ctx != null) {
      Scrollable.ensureVisible(
        ctx,
        duration: const Duration(milliseconds: 350),
        curve: Curves.easeOutCubic,
      );
    }
  }

  @override
  void initState() {
    super.initState();
    _load();
  }

  void _close() {
    if (widget.onClose != null) {
      widget.onClose!();
    } else if (mounted) {
      Navigator.of(context).pop();
    }
  }

  Future<void> _load({bool showSpinner = true}) async {
    final session = context.read<SessionProvider>();
    if (session.accessToken == null) {
      setState(() {
        _error = 'Non connecté.';
        _loading = false;
      });
      return;
    }
    final firstLoad = _payload == null;
    setState(() {
      if (showSpinner && firstLoad) {
        _loading = true;
      }
      _error = null;
    });
    try {
      final res = await _service.myFiche(
        baseUrl: session.baseUrl,
        accessToken: session.accessToken!,
        onRefreshToken: () => session.tryRefreshToken().then(
              (ok) => ok ? session.accessToken : null,
            ),
      );
      setState(() => _payload = res);
    } on SessionExpiredException {
      if (mounted) {
        resetToAuthRoot();
        await context.read<SessionProvider>().logout();
      }
      return;
    } catch (e, st) {
      logErrorForDebug('profile', e, st);
      setState(() => _error = userFacingErrorMessage(
            e,
            context: UserErrorContext.profile,
          ));
    } finally {
      if (mounted) {
        setState(() => _loading = false);
      }
    }
  }

  String _typeLabel(String? type) {
    switch (type) {
      case 'participant':
        return 'Étudiant';
      case 'formateur':
        return 'Enseignant';
      case 'encadrant':
        return 'Encadrant';
      default:
        return type ?? '—';
    }
  }

  String _statutModuleLabel(String? statut) {
    switch (statut) {
      case 'EN_COURS':
        return 'En cours';
      case 'PLANIFIEE':
        return 'Planifiée';
      case 'SUSPENDUE':
        return 'Suspendue';
      case 'TERMINEE':
        return 'Terminée';
      default:
        return statut ?? '—';
    }
  }

  void _maybeReloadFromTick(int tick) {
    if (tick == _lastRefreshTick) {
      return;
    }
    _lastRefreshTick = tick;
    _load(showSpinner: false);
  }

  @override
  Widget build(BuildContext context) {
    final tick = context.select<SessionProvider, int>(
      (s) => s.historyRefreshTick,
    );
    _maybeReloadFromTick(tick);

    final body = Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Expanded(child: _buildBody(context)),
      ],
    );

    if (widget.embedded) {
      return body;
    }

    return PopScope(
      canPop: widget.onClose == null,
      onPopInvokedWithResult: (didPop, _) {
        if (!didPop) {
          _close();
        }
      },
      child: Scaffold(
        backgroundColor: AppColors.ciLight,
        appBar: AppBar(
          leading: IconButton(
            icon: const Icon(Icons.arrow_back),
            onPressed: _close,
          ),
          title: const Text('Fiche'),
        ),
        body: body,
      ),
    );
  }

  Widget _buildBody(BuildContext context) {
    if (_loading) {
      return const Center(child: CircularProgressIndicator());
    }
    if (_error != null) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(20),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(
                _error!,
                textAlign: TextAlign.center,
                style: TextStyle(color: Theme.of(context).colorScheme.error),
              ),
              const SizedBox(height: 12),
              FilledButton(onPressed: _load, child: const Text('Réessayer')),
            ],
          ),
        ),
      );
    }

    final user = Map<String, dynamic>.from(_payload?['utilisateur'] as Map? ?? {});
    final profil = Map<String, dynamic>.from(_payload?['profil'] as Map? ?? {});
    final stats = Map<String, dynamic>.from(_payload?['stats'] as Map? ?? {});
    final rawModules = _payload?['modules'];
    final modules = rawModules is List
        ? rawModules.map((e) => Map<String, dynamic>.from(e as Map)).toList()
        : <Map<String, dynamic>>[];

    final prenom = (profil['prenom'] ?? user['first_name'] ?? '').toString().trim();
    final nom = (profil['nom'] ?? user['last_name'] ?? '').toString().trim();
    final fullName = '$prenom $nom'.trim();
    final displayName =
        fullName.isNotEmpty ? fullName : user['username']?.toString() ?? '—';

    final dernierRaw = stats['dernier_badgeage']?.toString();
    final dernierDt = DateTime.tryParse(dernierRaw ?? '');
    final dernierLabel = dernierDt != null
        ? DateFormat('d MMMM yyyy à HH:mm', 'fr_FR').format(dernierDt.toLocal())
        : 'Aucun badgeage enregistré';

    final totalMin = stats['total_minutes_presence'];
    final minutesLabel = totalMin is num
        ? '${totalMin.round()} min de présence'
        : '0 min de présence';

    final volumeTotalRaw = stats['volume_horaire_total_heures'];
    final volumeTotal =
        volumeTotalRaw is num ? volumeTotalRaw.toDouble() : 0.0;
    final volumeEffectueRaw = stats['volume_horaire_effectue_heures'];
    final volumeEffectue = volumeEffectueRaw is num
        ? (volumeTotal > 0
            ? volumeEffectueRaw.toDouble().clamp(0.0, volumeTotal)
            : volumeEffectueRaw.toDouble())
        : 0.0;
    final volumeTauxRaw = stats['volume_horaire_effectue_taux'];
    final volumeTaux =
        volumeTauxRaw is num ? volumeTauxRaw.toDouble().clamp(0.0, 100.0) : 0.0;
    final volumeLabel =
        '${_formatHeures(volumeEffectue)} / ${_formatHeures(volumeTotal)}';

    final infoRows = _infoRowsFor(user, profil);

    return RefreshIndicator(
      onRefresh: () => _load(showSpinner: false),
      child: ListView(
        key: const PageStorageKey<String>('profile_fiche_scroll'),
        controller: _scrollCtrl,
        padding: const EdgeInsets.fromLTRB(16, 12, 16, 28),
        children: [
          _FicheTappableCard(
            onTap: null,
            child: Row(
              children: [
                const QrBadgeLogo(
                  size: 64,
                  color: AppColors.ciSuccessDark,
                  backgroundColor: AppColors.iconQrBg,
                ),
                const SizedBox(width: 16),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        displayName,
                        style: Theme.of(context).textTheme.titleLarge?.copyWith(
                              fontWeight: FontWeight.w700,
                            ),
                      ),
                      const SizedBox(height: 4),
                      Text(
                        _typeLabel(profil['type_personne']?.toString()),
                        style: Theme.of(context).textTheme.bodySmall?.copyWith(
                              color: AppColors.textSecondary,
                            ),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 20),
          _SectionTitle(title: 'Mes informations'),
          _InfoCard(rows: infoRows),
          const SizedBox(height: 12),
          OutlinedButton.icon(
            onPressed: () => _showProfileEditSheet(context, user: user, profil: profil),
            icon: const Icon(Icons.edit_outlined, size: 18),
            label: const Text('Modifier mes informations'),
          ),
          const SizedBox(height: 8),
          OutlinedButton.icon(
            onPressed: () {
              Navigator.of(context).push(
                MaterialPageRoute<void>(
                  builder: (_) => const ChangePasswordPage(),
                ),
              );
            },
            icon: const Icon(Icons.lock_outline, size: 18),
            label: const Text('Changer le mot de passe'),
          ),
          if (profil['type_personne']?.toString() == 'formateur') ...[
            const SizedBox(height: 12),
            OutlinedButton.icon(
              onPressed: () => _showBankingEditSheet(context, profil),
              icon: const Icon(Icons.account_balance_outlined, size: 18),
              label: const Text('Modifier pièce d\'identité / compte bancaire'),
            ),
          ],
          const SizedBox(height: 20),
          _SectionTitle(title: 'Statistiques'),
          _StatsGrid(
            stats: stats,
            volumeLabel: volumeLabel,
            volumeTaux: volumeTaux,
            minutesLabel: minutesLabel,
            dernierLabel: dernierLabel,
          ),
          if (modules.isNotEmpty) ...[
            const SizedBox(height: 8),
            Align(
              alignment: Alignment.centerRight,
              child: TextButton.icon(
                onPressed: _scrollToModules,
                icon: const Icon(Icons.menu_book_outlined, size: 18),
                label: Text('Voir mes ${modules.length} module${modules.length > 1 ? 's' : ''}'),
              ),
            ),
          ],
          const SizedBox(height: 20),
          _SectionTitle(
            key: _modulesSectionKey,
            title: 'Modules inscrits',
            trailing: '${modules.length}',
          ),
          if (modules.isEmpty)
            EmptyStateView(
              icon: Icons.menu_book_outlined,
              iconColor: AppColors.ciBlue,
              title: profil['type_personne'] == 'encadrant'
                  ? 'Aucun module d\u2019inscription'
                  : 'Aucun module inscrit',
              subtitle: profil['type_personne'] == 'encadrant'
                  ? 'Les comptes encadrant n\u2019ont pas de modules d\u2019inscription.'
                  : 'Vos inscriptions apparaîtront ici une fois enregistrées.',
            )
          else
            ...modules.map(
              (m) => _ModuleCard(
                data: m,
                statut: _statutModuleLabel(m['statut']?.toString()),
              ),
            ),
        ],
      ),
    );
  }

  List<_InfoRow> _infoRowsFor(
    Map<String, dynamic> user,
    Map<String, dynamic> profil,
  ) =>
      [
        _InfoRow('Matricule', profil['numero']?.toString() ?? user['matricule']?.toString()),
        _InfoRow('E-mail', user['email']?.toString()),
        _InfoRow('Téléphone', user['telephone']?.toString()),
        _InfoRow('Organisation', user['organisation']?.toString()),
        _InfoRow('Grade', user['grade']?.toString()),
        if (profil['specialite'] != null &&
            profil['specialite'].toString().isNotEmpty)
          _InfoRow('Spécialité', profil['specialite']?.toString()),
        if (profil['type_personne']?.toString() == 'formateur') ...[
          _InfoRow(
            'N° pièce d\'identité',
            profil['numero_piece_identite']?.toString(),
          ),
          _InfoRow(
            'N° compte bancaire',
            profil['numero_compte_bancaire']?.toString(),
          ),
        ],
        _InfoRow('Secrétariat', user['secretariat_nom']?.toString()),
      ];

  Future<void> _showProfileEditSheet(
    BuildContext context, {
    required Map<String, dynamic> user,
    required Map<String, dynamic> profil,
  }) async {
    final messenger = ScaffoldMessenger.of(context);
    final saved = await showModalBottomSheet<bool>(
      context: context,
      isScrollControlled: true,
      backgroundColor: AppColors.cardBg,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      builder: (_) => _ProfileEditSheet(
        user: user,
        profil: profil,
        service: _service,
      ),
    );
    if (saved == true && mounted) {
      messenger.showSnackBar(
        const SnackBar(content: Text('Profil mis à jour.')),
      );
      await _load(showSpinner: false);
    }
  }

  Future<void> _showBankingEditSheet(
    BuildContext context,
    Map<String, dynamic> profil,
  ) async {
    final saved = await showModalBottomSheet<bool>(
      context: context,
      isScrollControlled: true,
      backgroundColor: AppColors.cardBg,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      builder: (_) => _BankingEditSheet(
        profil: profil,
        service: _service,
      ),
    );
    if (saved == true && mounted) {
      await _load(showSpinner: false);
    }
  }
}
