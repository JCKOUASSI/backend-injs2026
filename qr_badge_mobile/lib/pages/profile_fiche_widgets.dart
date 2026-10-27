part of 'profile_fiche_page.dart';

class _FicheTappableCard extends StatelessWidget {
  const _FicheTappableCard({
    required this.onTap,
    required this.child,
    this.padding = const EdgeInsets.all(18),
  });

  final VoidCallback? onTap;
  final Widget child;
  final EdgeInsetsGeometry padding;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: AppColors.cardBg,
      borderRadius: BorderRadius.circular(14),
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: onTap,
        child: Container(
          padding: padding,
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(14),
            border: Border.all(
              color: AppColors.borderColor.withValues(alpha: 0.6),
            ),
          ),
          child: Row(
            children: [
              Expanded(child: child),
              if (onTap != null)
                Icon(
                  Icons.chevron_right,
                  color: AppColors.textSecondary.withValues(alpha: 0.5),
                ),
            ],
          ),
        ),
      ),
    );
  }
}

class _SectionTitle extends StatelessWidget {
  const _SectionTitle({super.key, required this.title, this.trailing});

  final String title;
  final String? trailing;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: Row(
        children: [
          Expanded(
            child: Text(
              title,
              style: Theme.of(context).textTheme.titleSmall?.copyWith(
                    fontWeight: FontWeight.w700,
                  ),
            ),
          ),
          if (trailing != null)
            Text(
              trailing!,
              style: Theme.of(context).textTheme.labelLarge?.copyWith(
                    color: AppColors.ciSuccessDark,
                    fontWeight: FontWeight.w600,
                  ),
            ),
        ],
      ),
    );
  }
}

class _InfoRow {
  const _InfoRow(this.label, this.value);
  final String label;
  final String? value;
}

class _InfoCard extends StatelessWidget {
  const _InfoCard({required this.rows});

  final List<_InfoRow> rows;

  @override
  Widget build(BuildContext context) {
    final visible = rows
        .where((r) => r.value != null && r.value!.trim().isNotEmpty)
        .toList();
    if (visible.isEmpty) {
      return const SizedBox.shrink();
    }
    return _FicheTappableCard(
      onTap: null,
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      child: Column(
        children: visible
            .map(
              (r) => Padding(
                padding: const EdgeInsets.symmetric(vertical: 10),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    SizedBox(
                      width: 110,
                      child: Text(
                        r.label,
                        style: Theme.of(context).textTheme.bodySmall?.copyWith(
                              color: AppColors.textSecondary,
                              fontWeight: FontWeight.w500,
                            ),
                      ),
                    ),
                    Expanded(
                      child: Text(
                        r.value!,
                        style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                              fontWeight: FontWeight.w600,
                            ),
                      ),
                    ),
                  ],
                ),
              ),
            )
            .toList(),
      ),
    );
  }
}

String _formatHeures(dynamic h) {
  if (h is! num) return '0 h';
  final v = h.toDouble();
  if (v == v.roundToDouble()) return '${v.round()} h';
  return '${v.toStringAsFixed(1)} h';
}

class _StatsGrid extends StatelessWidget {
  const _StatsGrid({
    required this.stats,
    required this.volumeLabel,
    required this.volumeTaux,
    required this.minutesLabel,
    required this.dernierLabel,
  });

  final Map<String, dynamic> stats;
  final String volumeLabel;
  final double volumeTaux;
  final String minutesLabel;
  final String dernierLabel;

  String _n(String key) => stats[key]?.toString() ?? '0';

  @override
  Widget build(BuildContext context) {
    final progress = (volumeTaux / 100).clamp(0.0, 1.0);
    final tauxDisplay = volumeTaux == volumeTaux.roundToDouble()
        ? '${volumeTaux.round()} %'
        : '${volumeTaux.toStringAsFixed(1)} %';

    return Column(
      children: [
        _FicheTappableCard(
          onTap: null,
          padding: const EdgeInsets.all(14),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Icon(Icons.schedule, size: 20, color: AppColors.ciSuccessDark),
                  const SizedBox(width: 8),
                  Text(
                    'Volume horaire',
                    style: Theme.of(context).textTheme.labelLarge?.copyWith(
                          fontWeight: FontWeight.w600,
                          color: AppColors.textSecondary,
                        ),
                  ),
                  const Spacer(),
                  Text(
                    tauxDisplay,
                    style: Theme.of(context).textTheme.labelLarge?.copyWith(
                          fontWeight: FontWeight.w700,
                          color: AppColors.ciSuccessDark,
                        ),
                  ),
                ],
              ),
              const SizedBox(height: 8),
              Text(
                volumeLabel,
                style: Theme.of(context).textTheme.titleMedium?.copyWith(
                      fontWeight: FontWeight.w700,
                      color: AppColors.ciSuccessDark,
                    ),
              ),
              const SizedBox(height: 10),
              ClipRRect(
                borderRadius: BorderRadius.circular(4),
                child: LinearProgressIndicator(
                  value: progress > 0 ? progress : null,
                  minHeight: 6,
                  backgroundColor: AppColors.navIndicator,
                  color: AppColors.ciSuccessDark,
                ),
              ),
            ],
          ),
        ),
        const SizedBox(height: 12),
        Row(
          children: [
            Expanded(
              child: _StatTile(
                icon: Icons.qr_code_scanner,
                value: _n('nb_badgeages'),
                label: 'Badgeages',
                color: AppColors.ciSuccessDark,
              ),
            ),
            const SizedBox(width: 10),
            Expanded(
              child: _StatTile(
                icon: Icons.check_circle_outline,
                value: _n('nb_seances_terminees'),
                label: 'Séances terminées',
                color: AppColors.ciSuccessDark,
              ),
            ),
          ],
        ),
        const SizedBox(height: 10),
        Row(
          children: [
            Expanded(
              child: _StatTile(
                icon: Icons.menu_book_outlined,
                value: _n('nb_modules_inscrits'),
                label: 'Modules inscrits',
                color: AppColors.ciBlue,
              ),
            ),
            const SizedBox(width: 10),
            Expanded(
              child: _StatTile(
                icon: Icons.pending_outlined,
                value: _n('nb_seances_en_cours'),
                label: 'En cours',
                color: AppColors.ciBlue,
              ),
            ),
          ],
        ),
        const SizedBox(height: 12),
        _FicheTappableCard(
          onTap: null,
          padding: const EdgeInsets.all(14),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                minutesLabel,
                style: Theme.of(context).textTheme.titleSmall?.copyWith(
                      fontWeight: FontWeight.w700,
                      color: AppColors.ciSuccessDark,
                    ),
              ),
              const SizedBox(height: 6),
              Text(
                'Dernier badgeage : $dernierLabel',
                style: Theme.of(context).textTheme.bodySmall?.copyWith(
                      color: AppColors.textSecondary,
                    ),
              ),
            ],
          ),
        ),
      ],
    );
  }
}

class _StatTile extends StatelessWidget {
  const _StatTile({
    required this.icon,
    required this.value,
    required this.label,
    required this.color,
  });

  final IconData icon;
  final String value;
  final String label;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return _FicheTappableCard(
      onTap: null,
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 14),
      child: Column(
        children: [
          Icon(icon, color: color, size: 22),
          const SizedBox(height: 8),
          Text(
            value,
            style: TextStyle(
              fontSize: 22,
              fontWeight: FontWeight.w700,
              color: color,
            ),
          ),
          const SizedBox(height: 4),
          Text(
            label,
            textAlign: TextAlign.center,
            style: Theme.of(context).textTheme.labelSmall?.copyWith(
                  color: AppColors.textSecondary,
                  height: 1.2,
                ),
          ),
        ],
      ),
    );
  }
}

class _ModuleCard extends StatelessWidget {
  const _ModuleCard({
    required this.data,
    required this.statut,
  });

  final Map<String, dynamic> data;
  final String statut;

  String? _fmtDate(String? raw) {
    if (raw == null || raw.isEmpty) return null;
    final d = DateTime.tryParse(raw.length >= 10 ? raw.substring(0, 10) : raw);
    if (d == null) return raw;
    return DateFormat('d MMM yyyy', 'fr_FR').format(d);
  }

  @override
  Widget build(BuildContext context) {
    final formation = data['formation']?.toString() ?? '';
    final module = data['module']?.toString() ?? 'Module';
    final grade = data['grade']?.toString();
    final groupe = data['groupe']?.toString();
    final vague = data['vague']?.toString();
    final site = data['site']?.toString();
    final dateDebut = data['date_debut']?.toString();
    final dateFin = data['date_fin']?.toString();
    final secretariat = data['secretariat_nom']?.toString();
    final inscritLe = data['inscrit_le']?.toString();

    final periode = [
      if (_fmtDate(dateDebut) != null) 'Du ${_fmtDate(dateDebut)}',
      if (_fmtDate(dateFin) != null) 'au ${_fmtDate(dateFin)}',
    ].join(' ');

    final meta = [
      if (grade != null && grade.isNotEmpty) 'Grade $grade',
      if (groupe != null && groupe.isNotEmpty) 'Groupe $groupe',
      if (vague != null && vague.isNotEmpty) 'Vague $vague',
      if (site != null && site.isNotEmpty) site,
    ].join(' · ');

    final inscritDt = DateTime.tryParse(inscritLe ?? '');
    final inscritLabel = inscritDt != null
        ? 'Inscrit le ${DateFormat('d MMM yyyy', 'fr_FR').format(inscritDt.toLocal())}'
        : null;

    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: _FicheTappableCard(
        onTap: null,
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      if (formation.isNotEmpty)
                        Text(
                          formation,
                          style: Theme.of(context).textTheme.labelMedium?.copyWith(
                                color: AppColors.ciSuccessDark,
                                fontWeight: FontWeight.w600,
                              ),
                        ),
                      const SizedBox(height: 4),
                      Text(
                        module,
                        style: Theme.of(context).textTheme.titleSmall?.copyWith(
                              fontWeight: FontWeight.w700,
                            ),
                      ),
                    ],
                  ),
                ),
                StatusPill(
                  label: statut,
                  color: AppColors.ciSuccessDark,
                  backgroundColor: AppColors.navIndicator,
                ),
              ],
            ),
            if (meta.isNotEmpty) ...[
              const SizedBox(height: 8),
              Text(
                meta,
                style: Theme.of(context).textTheme.bodySmall?.copyWith(
                      color: AppColors.textSecondary,
                    ),
              ),
            ],
            if (periode.isNotEmpty) ...[
              const SizedBox(height: 4),
              Text(
                periode,
                style: Theme.of(context).textTheme.bodySmall?.copyWith(
                      color: AppColors.textSecondary,
                    ),
              ),
            ],
            if (secretariat != null && secretariat.isNotEmpty) ...[
              const SizedBox(height: 4),
              Text(
                secretariat,
                style: Theme.of(context).textTheme.bodySmall?.copyWith(
                      color: AppColors.textSecondary,
                    ),
              ),
            ],
            if (inscritLabel != null) ...[
              const SizedBox(height: 6),
              Text(
                inscritLabel,
                style: Theme.of(context).textTheme.labelSmall?.copyWith(
                      color: AppColors.textMuted,
                    ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class _ProfileEditSheet extends StatefulWidget {
  const _ProfileEditSheet({
    required this.user,
    required this.profil,
    required this.service,
  });

  final Map<String, dynamic> user;
  final Map<String, dynamic> profil;
  final ProfileService service;

  @override
  State<_ProfileEditSheet> createState() => _ProfileEditSheetState();
}

class _ProfileEditSheetState extends State<_ProfileEditSheet> {
  late final TextEditingController _prenomCtrl;
  late final TextEditingController _nomCtrl;
  late final TextEditingController _emailCtrl;
  late final TextEditingController _telCtrl;
  bool _saving = false;

  @override
  void initState() {
    super.initState();
    final user = widget.user;
    final profil = widget.profil;
    _prenomCtrl = TextEditingController(
      text: (user['first_name'] ?? profil['prenom'] ?? '').toString(),
    );
    _nomCtrl = TextEditingController(
      text: (user['last_name'] ?? profil['nom'] ?? '').toString(),
    );
    _emailCtrl = TextEditingController(text: user['email']?.toString() ?? '');
    _telCtrl = TextEditingController(text: user['telephone']?.toString() ?? '');
  }

  @override
  void dispose() {
    _prenomCtrl.dispose();
    _nomCtrl.dispose();
    _emailCtrl.dispose();
    _telCtrl.dispose();
    super.dispose();
  }

  Future<void> _onSessionExpired(SessionProvider session) async {
    if (!mounted) {
      return;
    }
    Navigator.of(context).pop();
    resetToAuthRoot();
    await session.logout();
  }

  Future<void> _save() async {
    if (_saving) {
      return;
    }
    setState(() => _saving = true);
    final session = context.read<SessionProvider>();
    try {
      final res = await widget.service.updateMyProfile(
        baseUrl: session.baseUrl,
        accessToken: session.accessToken!,
        data: {
          'first_name': _prenomCtrl.text.trim(),
          'last_name': _nomCtrl.text.trim(),
          'email': _emailCtrl.text.trim(),
          'telephone': _telCtrl.text.trim(),
        },
        onRefreshToken: () => session.tryRefreshToken().then(
              (ok) => ok ? session.accessToken : null,
            ),
      );
      session.applyUserProfile(res);
      if (mounted) {
        Navigator.of(context).pop(true);
      }
    } on SessionExpiredException {
      await _onSessionExpired(session);
    } catch (e, st) {
      logErrorForDebug('profile.update', e, st);
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(
              userFacingErrorMessage(
                e,
                context: UserErrorContext.profile,
                fallback: 'Impossible de mettre à jour le profil.',
              ),
            ),
          ),
        );
      }
    } finally {
      if (mounted) {
        setState(() => _saving = false);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.only(
        left: 20,
        right: 20,
        top: 20,
        bottom: MediaQuery.viewInsetsOf(context).bottom + 20,
      ),
      child: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(
              'Modifier mes informations',
              style: Theme.of(context).textTheme.titleMedium?.copyWith(
                    fontWeight: FontWeight.w700,
                  ),
            ),
            const SizedBox(height: 16),
            TextField(
              controller: _prenomCtrl,
              textCapitalization: TextCapitalization.words,
              decoration: const InputDecoration(
                labelText: 'Prénom',
                border: OutlineInputBorder(),
              ),
            ),
            const SizedBox(height: 12),
            TextField(
              controller: _nomCtrl,
              textCapitalization: TextCapitalization.words,
              decoration: const InputDecoration(
                labelText: 'Nom',
                border: OutlineInputBorder(),
              ),
            ),
            const SizedBox(height: 12),
            TextField(
              controller: _emailCtrl,
              keyboardType: TextInputType.emailAddress,
              decoration: const InputDecoration(
                labelText: 'E-mail',
                border: OutlineInputBorder(),
              ),
            ),
            const SizedBox(height: 12),
            TextField(
              controller: _telCtrl,
              keyboardType: TextInputType.phone,
              decoration: const InputDecoration(
                labelText: 'Téléphone',
                border: OutlineInputBorder(),
              ),
            ),
            const SizedBox(height: 16),
            FilledButton(
              onPressed: _saving ? null : _save,
              child: Text(_saving ? 'Enregistrement…' : 'Enregistrer'),
            ),
          ],
        ),
      ),
    );
  }
}

class _BankingEditSheet extends StatefulWidget {
  const _BankingEditSheet({
    required this.profil,
    required this.service,
  });

  final Map<String, dynamic> profil;
  final ProfileService service;

  @override
  State<_BankingEditSheet> createState() => _BankingEditSheetState();
}

class _BankingEditSheetState extends State<_BankingEditSheet> {
  late final TextEditingController _pieceCtrl;
  late final TextEditingController _compteCtrl;
  bool _saving = false;

  @override
  void initState() {
    super.initState();
    final profil = widget.profil;
    _pieceCtrl = TextEditingController(
      text: profil['numero_piece_identite']?.toString() ?? '',
    );
    _compteCtrl = TextEditingController(
      text: profil['numero_compte_bancaire']?.toString() ?? '',
    );
  }

  @override
  void dispose() {
    _pieceCtrl.dispose();
    _compteCtrl.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    if (_saving) {
      return;
    }
    setState(() => _saving = true);
    final session = context.read<SessionProvider>();
    try {
      await widget.service.updateMySensitiveData(
        baseUrl: session.baseUrl,
        accessToken: session.accessToken!,
        numeroPieceIdentite: _pieceCtrl.text.trim(),
        numeroCompteBancaire: _compteCtrl.text.trim(),
        onRefreshToken: () => session.tryRefreshToken().then(
              (ok) => ok ? session.accessToken : null,
            ),
      );
      if (mounted) {
        Navigator.of(context).pop(true);
      }
    } catch (e, st) {
      logErrorForDebug('profile.finance', e, st);
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(
              userFacingErrorMessage(
                e,
                context: UserErrorContext.profile,
                fallback: 'Impossible d\u2019enregistrer les informations.',
              ),
            ),
          ),
        );
      }
    } finally {
      if (mounted) {
        setState(() => _saving = false);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.only(
        left: 20,
        right: 20,
        top: 20,
        bottom: MediaQuery.viewInsetsOf(context).bottom + 20,
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(
            'Informations bancaires',
            style: Theme.of(context).textTheme.titleMedium?.copyWith(
                  fontWeight: FontWeight.w700,
                ),
          ),
          const SizedBox(height: 16),
          TextField(
            controller: _pieceCtrl,
            decoration: const InputDecoration(
              labelText: 'N° pièce d\'identité',
              border: OutlineInputBorder(),
            ),
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _compteCtrl,
            decoration: const InputDecoration(
              labelText: 'N° compte bancaire',
              border: OutlineInputBorder(),
            ),
          ),
          const SizedBox(height: 16),
          FilledButton(
            onPressed: _saving ? null : _save,
            child: Text(_saving ? 'Enregistrement…' : 'Enregistrer'),
          ),
        ],
      ),
    );
  }
}
