"""
Diagnostic volume contractuel (référentiel) vs fiche module vs EDT planifié.

Reproduit la logique affichée sur la fiche module (Σ planifié / objectif) et
explique d'où viennent les écarts (lien référentiel, catégorie, repli fiche…).

Usage :
  python manage.py diag_duree_contractuelle
  python manage.py diag_duree_contractuelle --intitule SIGFAE
  python manage.py diag_duree_contractuelle --groupe "GROUPE 1" --formation "FORMATION EN ADMINISTRATION DE BASE"
  python manage.py diag_duree_contractuelle --module-id 2100
  python manage.py diag_duree_contractuelle --ecarts-only
  python manage.py diag_duree_contractuelle --secretariat "FAB A" --top 20
"""

from django.core.management.base import BaseCommand

from formations.duree_prevue_resolve import (
    _get_majoritaire_categorie,
    _infer_module_categorie_code,
    _normalize_volume_categorie_code,
    _ref_module_volume_hours,
    module_edt_raw_hours,
    resolve_module_volume_contractuel_heures,
)
from formations.models import Module, RefModule


def _infer_categorie_display(module):
    """Catégorie utilisée pour le volume référentiel (auditeurs → secrétariat/grade)."""
    cat_part = _get_majoritaire_categorie(module)
    if cat_part:
        return cat_part, 'participants'
    cat_grade = _infer_module_categorie_code(module)
    if cat_grade:
        return cat_grade, 'grade/secretariat'
    return None, None


def _ref_par_intitule(module):
    return RefModule.resolve_for_intitule(module.intitule)


def _ref_volume_formation_cat(ref, module, categorie):
    if not ref or not categorie:
        return None
    from formations.duree_prevue_resolve import _resolve_ref_formation_for_module

    rf = _resolve_ref_formation_for_module(module)
    if not rf:
        return None
    vol = ref.get_volume_horaire_for_formation_categorie(
        formation_id=rf.id,
        formation_intitule=rf.intitule,
        categorie_code=categorie,
    )
    return float(vol) if vol is not None and float(vol) > 0 else None


def _diagnose(module, contractuel, source, categorie, cat_source, edt_h, ref_lie, ref_intitule):
    """Liste de messages explicatifs (anomalies détectées)."""
    msgs = []
    fiche = float(module.duree_prevue_heures or 0)
    ref_exact = _ref_par_intitule(module)

    if not ref_lie and not ref_exact:
        msgs.append('Aucun référentiel trouvé (ni FK, ni intitulé exact).')
    elif not ref_lie and ref_exact:
        msgs.append(
            f'Référentiel « {ref_exact.intitule} » trouvé par intitulé mais non lié (ref_module vide).'
        )
    elif ref_lie and ref_exact and ref_lie.id != ref_exact.id:
        msgs.append(
            f'FK référentiel « {ref_lie.intitule} » ≠ intitulé opérationnel '
            f'(attendu « {ref_exact.intitule} »).'
        )

    if not categorie:
        msgs.append('Catégorie non déduite (pas d\'auditeur inscrit, grade/secrétariat vide).')
    elif ref_lie or ref_exact:
        ref = ref_lie or ref_exact
        vol_fc = _ref_volume_formation_cat(ref, module, categorie)
        if vol_fc is None:
            msgs.append(
                f'Pas de volume formation×catégorie pour « {ref.intitule} » × cat. {categorie} '
                f'(repli volume global ou fiche).'
            )

    if source == 'module':
        msgs.append(f'Objectif contractuel repris de la fiche module ({fiche}h), pas du référentiel.')
    elif source is None and fiche <= 0:
        msgs.append('Aucun objectif contractuel (référentiel vide et fiche à 0).')

    if fiche > 0 and contractuel > 0 and abs(fiche - contractuel) >= 0.01:
        msgs.append(f'Fiche module ({fiche}h) ≠ objectif contractuel ({contractuel}h).')

    if edt_h is not None and contractuel > 0 and abs(edt_h - contractuel) >= 0.01:
        direction = 'excédent EDT' if edt_h > contractuel else 'EDT incomplet'
        msgs.append(
            f'EDT planifié ({edt_h}h) ≠ objectif ({contractuel}h) — {direction} '
            f'(affichage Σ {edt_h}h / {contractuel}h).'
        )

    intitule_u = (module.intitule or '').upper()
    sec = ''
    try:
        sec = (module.secretariat.type.libelle if module.secretariat and module.secretariat.type else '') or ''
    except AttributeError:
        pass
    sec_u = sec.upper()
    if 'FAB A' in sec_u or sec_u.endswith(' A'):
        if intitule_u == 'SIGFAE':
            msgs.append(
                'FAB A : le module opérationnel « SIGFAE » seul est inhabituel ; '
                'vérifier « SIGFAE ET TELETRAVAIL » (20h cat. A).'
            )
    if 'FAB B' in sec_u or sec_u.endswith(' B'):
        if 'TELETRAVAIL' in intitule_u:
            msgs.append(
                'FAB B : « SIGFAE ET TELETRAVAIL » est inhabituel ; '
                'vérifier le module « SIGFAE » (16h cat. B/C/D).'
            )

    return msgs


class Command(BaseCommand):
    help = (
        'Diagnostique objectif contractuel (référentiel), fiche module et EDT planifié.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--module-id', type=int, default=None, help='ID module opérationnel.')
        parser.add_argument('--intitule', type=str, default=None, help='Filtre intitulé (contient).')
        parser.add_argument('--formation', type=str, default=None, help='Filtre formation (contient).')
        parser.add_argument('--groupe', type=str, default=None, help='Filtre groupe (exact, insensible à la casse).')
        parser.add_argument('--grade', type=str, default=None, help='Filtre grade (exact).')
        parser.add_argument('--secretariat', type=str, default=None, help='Type secrétariat (ex. FAB A).')
        parser.add_argument(
            '--ecarts-only',
            action='store_true',
            help='Uniquement les modules avec écart EDT/objectif ou fiche/objectif.',
        )
        parser.add_argument('--top', type=int, default=None, help='Limiter aux N premiers écarts.')

    def handle(self, *args, **options):
        qs = Module.objects.select_related(
            'formation', 'secretariat__type', 'ref_module',
        ).order_by('formation__formation', 'groupe', 'intitule')

        if options['module_id']:
            qs = qs.filter(pk=options['module_id'])
        if options['intitule']:
            qs = qs.filter(intitule__icontains=options['intitule'])
        if options['formation']:
            qs = qs.filter(formation__formation__icontains=options['formation'])
        if options['groupe']:
            qs = qs.filter(groupe__iexact=options['groupe'])
        if options['grade']:
            qs = qs.filter(grade__iexact=options['grade'])
        if options['secretariat']:
            qs = qs.filter(secretariat__type__libelle__iexact=options['secretariat'])

        rows = []
        for module in qs.iterator():
            contractuel, source = resolve_module_volume_contractuel_heures(module)
            edt_h = module_edt_raw_hours(module) or None
            categorie, cat_source = _infer_categorie_display(module)
            ref_lie = module.ref_module
            ref_h = _ref_module_volume_hours(module, categorie) if categorie else _ref_module_volume_hours(module)
            fiche = float(module.duree_prevue_heures or 0)
            msgs = _diagnose(module, contractuel, source, categorie, cat_source, edt_h, ref_lie, _ref_par_intitule(module))

            ecart_edt = None
            if edt_h is not None and contractuel > 0:
                ecart_edt = round(edt_h - contractuel, 2)

            row = {
                'module': module,
                'fiche': fiche,
                'contractuel': contractuel,
                'source': source,
                'edt': edt_h,
                'ecart_edt': ecart_edt,
                'categorie': categorie,
                'cat_source': cat_source,
                'ref_h': ref_h,
                'msgs': msgs,
            }
            if options['ecarts_only']:
                has_ecart = (
                    (ecart_edt is not None and abs(ecart_edt) >= 0.01)
                    or (fiche > 0 and contractuel > 0 and abs(fiche - contractuel) >= 0.01)
                    or bool(msgs)
                )
                if not has_ecart:
                    continue
            rows.append(row)

        rows.sort(
            key=lambda r: abs(r['ecart_edt'] or 0) if r['ecart_edt'] is not None else 0,
            reverse=True,
        )
        if options['top']:
            rows = rows[: options['top']]

        if not rows:
            self.stdout.write(self.style.WARNING('Aucun module ne correspond aux filtres.'))
            return

        self.stdout.write(self.style.HTTP_INFO(
            f'\n=== Diagnostic durée contractuelle ({len(rows)} module(s)) ===\n'
        ))

        for r in rows:
            m = r['module']
            sec = ''
            try:
                sec = (m.secretariat.type.libelle if m.secretariat and m.secretariat.type else '') or '—'
            except AttributeError:
                sec = '—'
            ref_label = m.ref_module.intitule if m.ref_module_id else '—'
            ref_id = m.ref_module_id or '—'
            cat_disp = r['categorie'] or '—'
            if r['cat_source']:
                cat_disp = f'{cat_disp} ({r["cat_source"]})'

            self.stdout.write(self.style.MIGRATE_HEADING(
                f'#{m.id}  {m.intitule}  |  {m.formation.formation}'
            ))
            self.stdout.write(
                f'  Groupe: {m.groupe or "—"}  |  Grade: {m.grade or "—"}  |  '
                f'Secrétariat: {sec}'
            )
            self.stdout.write(
                f'  Réf. lié: {ref_label} (id {ref_id})'
            )
            self.stdout.write(
                f'  Catégorie volume: {cat_disp}'
            )
            self.stdout.write(
                f'  Fiche module:     {r["fiche"]:.1f}h'
            )
            self.stdout.write(
                f'  Objectif (API):   {r["contractuel"]:.1f}h  '
                f'[source: {r["source"] or "—"}]'
            )
            if r['categorie']:
                self.stdout.write(
                    f'  Réf. résolu:      {r["ref_h"]:.1f}h  (formation × cat. {r["categorie"]})'
                )
            edt_s = f'{r["edt"]:.1f}h' if r['edt'] is not None else '—'
            sigma = '—'
            if r['edt'] is not None and r['contractuel'] > 0:
                sigma = f'Σ {r["edt"]:.0f}h / {r["contractuel"]:.0f}h'
            self.stdout.write(
                f'  EDT planifié:     {edt_s}  |  Affichage séances: {sigma}'
            )
            if r['ecart_edt'] is not None and abs(r['ecart_edt']) >= 0.01:
                style = self.style.WARNING if r['ecart_edt'] < 0 else self.style.NOTICE
                self.stdout.write(style(
                    f'  Écart EDT/objectif: {r["ecart_edt"]:+.1f}h'
                ))

            if r['msgs']:
                for msg in r['msgs']:
                    self.stdout.write(self.style.WARNING(f'  ⚠ {msg}'))
            else:
                self.stdout.write(self.style.SUCCESS('  ✓ Cohérent (référentiel / fiche / EDT).'))
            self.stdout.write('')

        # Synthèse
        avec_msgs = sum(1 for r in rows if r['msgs'])
        self.stdout.write('=' * 60)
        self.stdout.write(
            f'Modules analysés: {len(rows)}  |  Avec anomalie(s): {avec_msgs}'
        )
