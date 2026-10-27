import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../providers/session_provider.dart';
import '../services/evaluation_service.dart';
import '../theme/qr_badge_theme.dart';
import '../utils/user_facing_error.dart';
import '../widgets/empty_state_view.dart';

class EvaluationsPage extends StatefulWidget {
  const EvaluationsPage({super.key});

  @override
  State<EvaluationsPage> createState() => _EvaluationsPageState();
}

class _EvaluationsPageState extends State<EvaluationsPage>
    with AutomaticKeepAliveClientMixin {
  final _service = EvaluationService();

  bool _loading = true;
  List<Map<String, dynamic>> _questionnaires = [];
  String? _error;

  @override
  bool get wantKeepAlive => true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final session = context.read<SessionProvider>();
    if (session.accessToken == null) {
      setState(() { _loading = false; _error = 'Session expirée.'; });
      return;
    }
    setState(() { _loading = true; _error = null; });
    try {
      final list = await _service.mesQuestionnaires(
        baseUrl: session.baseUrl,
        accessToken: session.accessToken!,
        onRefreshToken: () => session.tryRefreshToken().then(
          (ok) => ok ? session.accessToken : null,
        ),
      );
      if (mounted) setState(() => _questionnaires = list);
    } catch (e, st) {
      logErrorForDebug('evaluations.load', e, st);
      if (mounted) {
        setState(() => _error = userFacingErrorMessage(
              e,
              context: UserErrorContext.evaluations,
            ));
      }
    } finally {
      if (mounted) {
        setState(() => _loading = false);
        context.read<SessionProvider>().refreshPendingEvaluationsCount();
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    super.build(context);
    return RefreshIndicator(
      onRefresh: _load,
      child: _loading
          ? const Center(child: CircularProgressIndicator())
          : _error != null
              ? _ErrorView(message: _error!, onRetry: _load)
              : _questionnaires.isEmpty
                  ? EmptyStateView(
                      icon: Icons.assignment_turned_in_outlined,
                      title: 'Aucun questionnaire en attente',
                      subtitle:
                          'Vous avez répondu à tous les questionnaires ou aucun ne vous est assigné pour le moment.',
                      action: OutlinedButton.icon(
                        onPressed: _load,
                        icon: const Icon(Icons.refresh),
                        label: const Text('Actualiser'),
                      ),
                    )
                  : ListView.separated(
                      padding: const EdgeInsets.fromLTRB(16, 12, 16, 24),
                      itemCount: _questionnaires.length,
                      separatorBuilder: (_, _) => const SizedBox(height: 12),
                      itemBuilder: (_, i) => _QuestionnaireCard(
                        data: _questionnaires[i],
                        onSubmitted: _load,
                      ),
                    ),
    );
  }
}

// ─────────────────────────────────────────────────────────────
// Card questionnaire
// ─────────────────────────────────────────────────────────────

class _QuestionnaireCard extends StatelessWidget {
  const _QuestionnaireCard({required this.data, required this.onSubmitted});

  final Map<String, dynamic> data;
  final VoidCallback onSubmitted;

  @override
  Widget build(BuildContext context) {
    final titres = (data['titres'] as List?)?.cast<String>() ?? [];
    final categories = (data['categories'] as List?)?.cast<String>() ?? [];
    final grades = (data['grades'] as List?)?.cast<String>() ?? [];
    final cible = data['cible']?.toString() ?? '';
    final nbQ = data['questions'] is List ? (data['questions'] as List).length : 0;

    return Container(
      decoration: BoxDecoration(
        color: AppColors.cardBg,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: AppColors.borderColor),
        boxShadow: const [
          BoxShadow(color: Color(0x0A000000), blurRadius: 8, offset: Offset(0, 2)),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // En-tête
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 14, 16, 0),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                // Badges
                Wrap(
                  spacing: 6,
                  runSpacing: 4,
                  children: [
                    _Pill(
                      label: cible == 'COURS' ? 'Module' : 'Enseignant',
                      color: AppColors.ciBlue,
                      bg: const Color(0xFFE3F2FD),
                      icon: cible == 'COURS' ? Icons.book_outlined : Icons.person_outline,
                    ),
                    for (final c in categories)
                      _Pill(label: c, color: AppColors.ciPurple, bg: const Color(0xFFF3E5F5)),
                    for (final g in grades)
                      _Pill(label: g, color: const Color(0xFF283593), bg: const Color(0xFFE8EAF6)),
                  ],
                ),
                const SizedBox(height: 8),
                // Titres
                Text(
                  titres.isNotEmpty ? titres.join(' · ') : '—',
                  style: const TextStyle(
                    fontSize: 15,
                    fontWeight: FontWeight.w700,
                    color: AppColors.textPrimary,
                  ),
                ),
                const SizedBox(height: 4),
                Text(
                  '$nbQ question${nbQ != 1 ? "s" : ""}',
                  style: const TextStyle(fontSize: 12, color: AppColors.textSecondary),
                ),
              ],
            ),
          ),
          const SizedBox(height: 12),
          const Divider(height: 1),
          // Bouton
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 10, 16, 14),
            child: SizedBox(
              width: double.infinity,
              child: FilledButton.icon(
                onPressed: () => _openForm(context),
                icon: const Icon(Icons.edit_note, size: 18),
                label: const Text('Répondre'),
              ),
            ),
          ),
        ],
      ),
    );
  }

  void _openForm(BuildContext context) {
    final questions = data['questions'] is List
        ? (data['questions'] as List).map((e) => Map<String, dynamic>.from(e as Map)).toList()
        : <Map<String, dynamic>>[];
    if (questions.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Ce questionnaire ne contient aucune question.')),
      );
      return;
    }
    Navigator.of(context).push(
      MaterialPageRoute(
        builder: (_) => _EvaluationFormPage(
          questionnaire: data,
          questions: questions,
          onSubmitted: onSubmitted,
        ),
      ),
    );
  }
}

// ─────────────────────────────────────────────────────────────
// Formulaire de réponse
// ─────────────────────────────────────────────────────────────

class _EvaluationFormPage extends StatefulWidget {
  const _EvaluationFormPage({
    required this.questionnaire,
    required this.questions,
    required this.onSubmitted,
  });

  final Map<String, dynamic> questionnaire;
  final List<Map<String, dynamic>> questions;
  final VoidCallback onSubmitted;

  @override
  State<_EvaluationFormPage> createState() => _EvaluationFormPageState();
}

class _EvaluationFormPageState extends State<_EvaluationFormPage> {
  final _service = EvaluationService();
  bool _submitting = false;

  // Réponses indexées par question id
  final Map<int, int?> _notes = {};
  final Map<int, String> _textes = {};
  final Map<int, int?> _choixUnique = {};
  final Map<int, Set<int>> _choixMultiple = {};

  bool _validate() {
    for (final q in widget.questions) {
      final id = q['id'] as int;
      final type = q['type_question']?.toString() ?? '';
      final obligatoire = q['obligatoire'] == true;
      if (!obligatoire) continue;
      if (type == 'NOTE' && (_notes[id] == null)) return false;
      if (type == 'TEXTE' && (_textes[id] ?? '').trim().isEmpty) return false;
      if (type == 'CHOIX_UN' && _choixUnique[id] == null) return false;
      if (type == 'CHOIX_MUL' && (_choixMultiple[id]?.isEmpty ?? true)) return false;
    }
    return true;
  }

  Future<void> _submit() async {
    if (!_validate()) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Veuillez répondre à toutes les questions obligatoires.')),
      );
      return;
    }
    setState(() => _submitting = true);
    final session = context.read<SessionProvider>();
    try {
      final reponses = <Map<String, dynamic>>[];
      for (final q in widget.questions) {
        final id = q['id'] as int;
        final type = q['type_question']?.toString() ?? '';
        final rep = <String, dynamic>{'question': id};
        if (type == 'NOTE') rep['note'] = _notes[id];
        if (type == 'TEXTE') rep['texte'] = _textes[id] ?? '';
        if (type == 'CHOIX_UN') rep['choix'] = _choixUnique[id];
        if (type == 'CHOIX_MUL') rep['choix_multiples'] = (_choixMultiple[id] ?? {}).toList();
        reponses.add(rep);
      }
      await _service.soumettre(
        baseUrl: session.baseUrl,
        accessToken: session.accessToken!,
        questionnaireId: widget.questionnaire['id'] as int,
        reponses: reponses,
        onRefreshToken: () => session.tryRefreshToken().then(
          (ok) => ok ? session.accessToken : null,
        ),
      );
      if (mounted) {
        Navigator.of(context).pop();
        widget.onSubmitted();
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('Évaluation soumise avec succès !'),
            backgroundColor: AppColors.ciSuccessDark,
          ),
        );
      }
    } catch (e, st) {
      logErrorForDebug('evaluations.submit', e, st);
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(
              userFacingErrorMessage(
                e,
                context: UserErrorContext.evaluations,
                fallback: 'Impossible d\u2019envoyer l\u2019évaluation.',
              ),
            ),
            backgroundColor: AppColors.ciDanger,
          ),
        );
      }
    } finally {
      if (mounted) setState(() => _submitting = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final titres = (widget.questionnaire['titres'] as List?)?.cast<String>() ?? [];
    return Scaffold(
      appBar: AppBar(
        title: Text(
          titres.isNotEmpty ? titres.first : 'Évaluation',
          overflow: TextOverflow.ellipsis,
        ),
      ),
      body: ListView.separated(
        padding: const EdgeInsets.fromLTRB(16, 16, 16, 100),
        itemCount: widget.questions.length,
        separatorBuilder: (_, _) => const SizedBox(height: 16),
        itemBuilder: (_, i) => _QuestionWidget(
          question: widget.questions[i],
          index: i,
          note: _notes[widget.questions[i]['id'] as int],
          texte: _textes[widget.questions[i]['id'] as int] ?? '',
          choixUnique: _choixUnique[widget.questions[i]['id'] as int],
          choixMultiple: _choixMultiple[widget.questions[i]['id'] as int] ?? {},
          onNoteChanged: (v) => setState(() => _notes[widget.questions[i]['id'] as int] = v),
          onTexteChanged: (v) => setState(() => _textes[widget.questions[i]['id'] as int] = v),
          onChoixUniqueChanged: (v) => setState(() => _choixUnique[widget.questions[i]['id'] as int] = v),
          onChoixMultipleChanged: (v) => setState(() => _choixMultiple[widget.questions[i]['id'] as int] = v),
        ),
      ),
      bottomNavigationBar: SafeArea(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(16, 8, 16, 12),
          child: SizedBox(
            width: double.infinity,
            height: 52,
            child: FilledButton(
              onPressed: _submitting ? null : _submit,
              child: _submitting
                  ? const SizedBox(
                      width: 20, height: 20,
                      child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                    )
                  : const Text('Soumettre l\'évaluation', style: TextStyle(fontSize: 16)),
            ),
          ),
        ),
      ),
    );
  }
}

// ─────────────────────────────────────────────────────────────
// Widget question individuelle
// ─────────────────────────────────────────────────────────────

class _QuestionWidget extends StatelessWidget {
  const _QuestionWidget({
    required this.question,
    required this.index,
    required this.note,
    required this.texte,
    required this.choixUnique,
    required this.choixMultiple,
    required this.onNoteChanged,
    required this.onTexteChanged,
    required this.onChoixUniqueChanged,
    required this.onChoixMultipleChanged,
  });

  final Map<String, dynamic> question;
  final int index;
  final int? note;
  final String texte;
  final int? choixUnique;
  final Set<int> choixMultiple;
  final ValueChanged<int?> onNoteChanged;
  final ValueChanged<String> onTexteChanged;
  final ValueChanged<int?> onChoixUniqueChanged;
  final ValueChanged<Set<int>> onChoixMultipleChanged;

  @override
  Widget build(BuildContext context) {
    final type = question['type_question']?.toString() ?? '';
    final obligatoire = question['obligatoire'] == true;
    final choix = question['choix'] is List
        ? (question['choix'] as List).map((e) => Map<String, dynamic>.from(e as Map)).toList()
        : <Map<String, dynamic>>[];

    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppColors.cardBg,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: AppColors.borderColor),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Intitulé
          RichText(
            text: TextSpan(
              style: const TextStyle(fontSize: 14, color: AppColors.textPrimary, height: 1.4),
              children: [
                TextSpan(
                  text: '${index + 1}. ',
                  style: const TextStyle(fontWeight: FontWeight.w700, color: AppColors.ciSuccessDark),
                ),
                TextSpan(text: question['intitule']?.toString() ?? ''),
                if (obligatoire)
                  const TextSpan(text: ' *', style: TextStyle(color: AppColors.ciDanger, fontWeight: FontWeight.w700)),
              ],
            ),
          ),
          const SizedBox(height: 14),
          // Champ de réponse selon le type
          if (type == 'NOTE') _NoteSelector(value: note, onChanged: onNoteChanged),
          if (type == 'TEXTE') _TexteField(value: texte, onChanged: onTexteChanged),
          if (type == 'CHOIX_UN') _ChoixUniqueSelector(
            choix: choix, selected: choixUnique, onChanged: onChoixUniqueChanged,
          ),
          if (type == 'CHOIX_MUL') _ChoixMultipleSelector(
            choix: choix, selected: choixMultiple, onChanged: onChoixMultipleChanged,
          ),
        ],
      ),
    );
  }
}

// ─────────────────────────────────────────────────────────────
// Sélecteur de note 1–5 étoiles
// ─────────────────────────────────────────────────────────────

class _NoteSelector extends StatelessWidget {
  const _NoteSelector({required this.value, required this.onChanged});
  final int? value;
  final ValueChanged<int?> onChanged;

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisAlignment: MainAxisAlignment.spaceEvenly,
      children: List.generate(5, (i) {
        final star = i + 1;
        final selected = value != null && star <= value!;
        return GestureDetector(
          onTap: () => onChanged(value == star ? null : star),
          child: Column(
            children: [
              Icon(
                selected ? Icons.star_rounded : Icons.star_outline_rounded,
                color: selected ? AppColors.ciWarning : AppColors.borderColor,
                size: 36,
              ),
              Text(
                '$star',
                style: TextStyle(
                  fontSize: 11,
                  fontWeight: selected ? FontWeight.w700 : FontWeight.w400,
                  color: selected ? AppColors.ciWarning : AppColors.textSecondary,
                ),
              ),
            ],
          ),
        );
      }),
    );
  }
}

// ─────────────────────────────────────────────────────────────
// Champ texte libre
// ─────────────────────────────────────────────────────────────

class _TexteField extends StatefulWidget {
  const _TexteField({required this.value, required this.onChanged});
  final String value;
  final ValueChanged<String> onChanged;
  @override
  State<_TexteField> createState() => _TexteFieldState();
}

class _TexteFieldState extends State<_TexteField> {
  late final TextEditingController _ctrl;
  @override
  void initState() {
    super.initState();
    _ctrl = TextEditingController(text: widget.value);
  }
  @override
  void dispose() { _ctrl.dispose(); super.dispose(); }
  @override
  Widget build(BuildContext context) {
    return TextField(
      controller: _ctrl,
      maxLines: 3,
      decoration: const InputDecoration(hintText: 'Votre réponse…'),
      onChanged: widget.onChanged,
    );
  }
}

// ─────────────────────────────────────────────────────────────
// Choix unique (radio)
// ─────────────────────────────────────────────────────────────

class _ChoixUniqueSelector extends StatelessWidget {
  const _ChoixUniqueSelector({required this.choix, required this.selected, required this.onChanged});
  final List<Map<String, dynamic>> choix;
  final int? selected;
  final ValueChanged<int?> onChanged;

  @override
  Widget build(BuildContext context) {
    return RadioGroup<int>(
      groupValue: selected,
      onChanged: onChanged,
      child: Column(
        children: choix.map((c) {
          final id = c['id'] as int;
          return RadioListTile<int>(
            value: id,
            title: Text(c['libelle']?.toString() ?? '', style: const TextStyle(fontSize: 14)),
            contentPadding: EdgeInsets.zero,
            dense: true,
            activeColor: AppColors.ciSuccessDark,
          );
        }).toList(),
      ),
    );
  }
}

// ─────────────────────────────────────────────────────────────
// Choix multiples (checkbox)
// ─────────────────────────────────────────────────────────────

class _ChoixMultipleSelector extends StatelessWidget {
  const _ChoixMultipleSelector({required this.choix, required this.selected, required this.onChanged});
  final List<Map<String, dynamic>> choix;
  final Set<int> selected;
  final ValueChanged<Set<int>> onChanged;

  @override
  Widget build(BuildContext context) {
    return Column(
      children: choix.map((c) {
        final id = c['id'] as int;
        final checked = selected.contains(id);
        return CheckboxListTile(
          value: checked,
          onChanged: (_) {
            final next = Set<int>.from(selected);
            if (checked) {
              next.remove(id);
            } else {
              next.add(id);
            }
            onChanged(next);
          },
          title: Text(c['libelle']?.toString() ?? '', style: const TextStyle(fontSize: 14)),
          contentPadding: EdgeInsets.zero,
          dense: true,
          activeColor: AppColors.ciSuccessDark,
        );
      }).toList(),
    );
  }
}

// ─────────────────────────────────────────────────────────────
// Vues utilitaires
// ─────────────────────────────────────────────────────────────

class _ErrorView extends StatelessWidget {
  const _ErrorView({required this.message, required this.onRetry});
  final String message;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(32),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.error_outline, size: 52, color: AppColors.ciDanger),
            const SizedBox(height: 12),
            Text(message, style: const TextStyle(color: AppColors.textSecondary, fontSize: 13), textAlign: TextAlign.center),
            const SizedBox(height: 16),
            FilledButton.icon(onPressed: onRetry, icon: const Icon(Icons.refresh), label: const Text('Réessayer')),
          ],
        ),
      ),
    );
  }
}

// ─────────────────────────────────────────────────────────────
// Badge pill réutilisable
// ─────────────────────────────────────────────────────────────

class _Pill extends StatelessWidget {
  const _Pill({required this.label, required this.color, required this.bg, this.icon});
  final String label;
  final Color color;
  final Color bg;
  final IconData? icon;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(color: bg, borderRadius: BorderRadius.circular(20)),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (icon != null) ...[Icon(icon, size: 11, color: color), const SizedBox(width: 3)],
          Text(label, style: TextStyle(fontSize: 11, fontWeight: FontWeight.w600, color: color)),
        ],
      ),
    );
  }
}
