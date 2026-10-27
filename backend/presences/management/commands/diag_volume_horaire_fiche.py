"""
Commande : python manage.py diag_volume_horaire_fiche

Diagnostique l'écart effectué / prévu affiché sur la fiche mobile (volume horaire).
Reproduit la logique de _compute_volume_horaire_stats (my_fiche) avec détail par module.

Usage :
  python manage.py diag_volume_horaire_fiche --username auditeur123
  python manage.py diag_volume_horaire_fiche --matricule 12345
  python manage.py diag_volume_horaire_fiche --participant-id 42
  python manage.py diag_volume_horaire_fiche --formateur-id 7
  python manage.py diag_volume_horaire_fiche --username x --hors-inscription-only
  python manage.py diag_volume_horaire_fiche --username x --top 15
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from formations.models import Formateur, Module, Participant
from presences.views import (
    _compute_volume_horaire_stats,
    _modules_for_personne,
    _pointages_queryset_for_personne,
)


def _resolve_target(options):
    """Retourne (personne, type_str, user_or_none)."""
    if options.get('participant_id'):
        participant = Participant.objects.filter(pk=options['participant_id']).first()
        if not participant:
            raise CommandError(f"Participant id={options['participant_id']} introuvable.")
        user = participant.user
        return participant, 'participant', user

    if options.get('formateur_id'):
        formateur = Formateur.objects.filter(pk=options['formateur_id']).first()
        if not formateur:
            raise CommandError(f"Formateur id={options['formateur_id']} introuvable.")
        user = formateur.user
        return formateur, 'formateur', user

    username = (options.get('username') or '').strip()
    matricule = (options.get('matricule') or '').strip()
    if not username and not matricule:
        raise CommandError('Indiquez --username, --matricule, --participant-id ou --formateur-id.')

    User = get_user_model()
    user = None
    if username:
        user = User.objects.filter(username__iexact=username).first()
        if not user:
            raise CommandError(f"Utilisateur « {username} » introuvable.")
    elif matricule:
        user = User.objects.filter(matricule__iexact=matricule).first()
        if not user:
            participant = Participant.objects.filter(matricule__iexact=matricule).first()
            if participant:
                return participant, 'participant', participant.user
            formateur = Formateur.objects.filter(matricule__iexact=matricule).first()
            if formateur:
                return formateur, 'formateur', formateur.user
            raise CommandError(f"Aucun compte ni fiche pour le matricule « {matricule} ».")

    from presences.views import _resolve_authenticated_personne

    personne, type_str, err = _resolve_authenticated_personne(user)
    if err:
        detail = getattr(err, 'data', {}) or {}
        raise CommandError(detail.get('detail', 'Profil introuvable pour ce compte.'))
    return personne, type_str, user


def _compute_volume_breakdown(modules_data, pointages_qs):
    """Même règles que _compute_volume_horaire_stats, avec détail module par module."""
    module_cap_minutes = {}
    module_prevu_heures = {}
    for m in modules_data:
        mid = m.get('id')
        if mid is None:
            continue
        heures = float(m.get('duree_prevue_heures') or 0)
        cap = heures * 60
        module_cap_minutes[mid] = max(module_cap_minutes.get(mid, 0.0), cap)
        module_prevu_heures[mid] = module_cap_minutes[mid] / 60
    total_heures = sum(module_prevu_heures.values())

    module_accum = {mid: 0.0 for mid in module_cap_minutes}
    module_brut = {}
    module_compte = {}
    hors_inscription_brut = 0.0
    hors_inscription_compte = 0.0
    nb_pt_hors_inscription = 0
    sans_session = 0.0

    for pt in pointages_qs.select_related('session__module'):
        mins = float(pt.duree_presence_minutes or 0)
        if mins <= 0:
            continue
        mid = pt.session.module_id if pt.session_id else None
        if mid is None:
            sans_session += mins
            continue

        module_brut[mid] = module_brut.get(mid, 0.0) + mins

        if mid in module_cap_minutes:
            remaining = module_cap_minutes[mid] - module_accum[mid]
            if remaining <= 0:
                continue
            counted = min(mins, remaining)
            module_accum[mid] += counted
            module_compte[mid] = module_compte.get(mid, 0.0) + counted
        else:
            hors_inscription_brut += mins
            hors_inscription_compte += mins
            nb_pt_hors_inscription += 1

    lignes = []
    inscrit_ids = set(module_cap_minutes)
    tous_ids = set(module_brut) | inscrit_ids

    for mid in sorted(tous_ids, key=lambda x: (x not in inscrit_ids, -(module_compte.get(x, 0) + (module_brut.get(x, 0) if x not in inscrit_ids else 0)))):
        inscrit = mid in inscrit_ids
        prevu_h = module_prevu_heures.get(mid, 0.0)
        brut_h = module_brut.get(mid, 0.0) / 60
        compte_h = module_compte.get(mid, 0.0) / 60 if inscrit else brut_h
        ecart_h = compte_h - prevu_h
        lignes.append({
            'module_id': mid,
            'inscrit': inscrit,
            'prevu_h': prevu_h,
            'brut_h': brut_h,
            'compte_h': compte_h,
            'ecart_h': ecart_h,
            'plafonne_h': max(0.0, brut_h - compte_h) if inscrit else 0.0,
        })

    effectue_minutes = sum(module_compte.values())
    effectue_heures = round(effectue_minutes / 60, 1)
    total_heures_r = round(total_heures, 1)
    if total_heures_r > 0:
        effectue_heures = min(effectue_heures, total_heures_r)
        taux = min(100.0, round((effectue_heures / total_heures_r) * 100, 1))
    else:
        taux = 0.0

    return {
        'volume_horaire_total_heures': total_heures_r,
        'volume_horaire_effectue_heures': effectue_heures,
        'volume_horaire_effectue_taux': taux,
        'hors_inscription_compte_h': round(hors_inscription_compte / 60, 1),
        'hors_inscription_brut_h': round(hors_inscription_brut / 60, 1),
        'nb_pointages_hors_inscription': nb_pt_hors_inscription,
        'sans_session_h': round(sans_session / 60, 1),
        'lignes': lignes,
    }


class Command(BaseCommand):
    help = "Diagnostique le volume horaire effectué / prévu d'une fiche mobile."

    def add_arguments(self, parser):
        parser.add_argument('--username', type=str, default=None)
        parser.add_argument('--matricule', type=str, default=None)
        parser.add_argument('--participant-id', type=int, default=None)
        parser.add_argument('--formateur-id', type=int, default=None)
        parser.add_argument(
            '--hors-inscription-only',
            action='store_true',
            help="N'affiche que les modules badgeés sans inscription.",
        )
        parser.add_argument(
            '--ecarts-only',
            action='store_true',
            help="N'affiche que les lignes avec écart compté - prévu > 0.",
        )
        parser.add_argument('--top', type=int, default=None, help="Limite le nombre de lignes affichées.")

    def handle(self, *args, **options):
        personne, type_str, user = _resolve_target(options)
        modules_data = _modules_for_personne(personne, type_str, user=user)
        pointages_qs = _pointages_queryset_for_personne(personne, type_str, user=user)

        stats_api = _compute_volume_horaire_stats(modules_data, pointages_qs)
        breakdown = _compute_volume_breakdown(modules_data, pointages_qs)

        nom = (
            f"{getattr(personne, 'prenom', '') or getattr(personne, 'first_name', '')} "
            f"{getattr(personne, 'nom', '') or getattr(personne, 'last_name', '')}"
        ).strip()
        numero = (
            getattr(personne, 'matricule', None)
            or getattr(personne, 'numerobadge', None)
            or (getattr(user, 'matricule', None) if user else None)
            or ''
        )

        self.stdout.write(self.style.MIGRATE_HEADING(
            f"Fiche {type_str} #{personne.pk} — {nom or '(sans nom)'} — {numero or 'sans n°'}"
        ))
        if user:
            self.stdout.write(f"Compte : {user.username} (id={user.pk}, rôle={getattr(user, 'role', '?')})")

        if type_str == 'participant' and user:
            from presences.participant_scope import participant_ids_for_user

            pids = sorted(participant_ids_for_user(user))
            if len(pids) > 1:
                self.stdout.write(self.style.WARNING(
                    f"⚠ {len(pids)} fiches Participant liées au compte : {pids} "
                    f"(inscriptions = fiche #{personne.pk} uniquement ; "
                    f"pointages = toutes les fiches)"
                ))

        self.stdout.write('')
        self.stdout.write(
            f"Modules inscrits : {len(modules_data)} | "
            f"Pointages : {pointages_qs.count()}"
        )
        self.stdout.write(self.style.SUCCESS(
            f"API fiche : {stats_api['volume_horaire_effectue_heures']} h effectué / "
            f"{stats_api['volume_horaire_total_heures']} h prévu "
            f"({stats_api['volume_horaire_effectue_taux']} %)"
        ))
        ecart_global = (
            stats_api['volume_horaire_effectue_heures']
            - stats_api['volume_horaire_total_heures']
        )
        if ecart_global > 0:
            self.stdout.write(self.style.WARNING(f"Écart global : +{ecart_global:.1f} h"))
        else:
            self.stdout.write(f"Écart global : {ecart_global:+.1f} h")

        if breakdown['hors_inscription_brut_h'] > 0:
            self.stdout.write(self.style.WARNING(
                f"→ {breakdown['hors_inscription_brut_h']} h badgeées hors inscription "
                f"({breakdown['nb_pointages_hors_inscription']} badgeages) — non comptées"
            ))
        if breakdown['sans_session_h'] > 0:
            self.stdout.write(self.style.WARNING(
                f"→ {breakdown['sans_session_h']} h sur badgeages sans session — non comptées"
            ))

        lignes = breakdown['lignes']
        if options['hors_inscription_only']:
            lignes = [l for l in lignes if not l['inscrit']]
        if options['ecarts_only']:
            lignes = [l for l in lignes if l['ecart_h'] > 0]
        lignes.sort(key=lambda l: l['ecart_h'], reverse=True)
        if options['top']:
            lignes = lignes[: options['top']]

        module_labels = {
            m.pk: (m.intitule or '')[:45]
            for m in Module.objects.filter(
                pk__in=[l['module_id'] for l in lignes]
            ).only('intitule')
        }

        self.stdout.write('')
        header = (
            f"{'Insc.':<6} {'Module':<46} {'Prévu':>8} {'Brut':>8} "
            f"{'Compté':>8} {'Écart':>8} {'Plaf.':>7}"
        )
        self.stdout.write(header)
        self.stdout.write('-' * len(header))

        for l in lignes:
            label = module_labels.get(l['module_id'], f"id={l['module_id']}")
            inscrit = 'oui' if l['inscrit'] else 'NON'
            row = (
                f"{inscrit:<6} {label:<46} "
                f"{l['prevu_h']:>7.1f}h {l['brut_h']:>7.1f}h "
                f"{l['compte_h']:>7.1f}h {l['ecart_h']:>+7.1f}h "
                f"{l['plafonne_h']:>6.1f}h"
            )
            if l['ecart_h'] > 0:
                self.stdout.write(self.style.WARNING(row))
            else:
                self.stdout.write(row)
        self.stdout.write('=' * len(header))
        self.stdout.write(
            "Insc.=inscription fiche | Brut=Σ duree_presence_minutes | "
            "Compté=plafond module inscrit (hors inscription ignoré) | "
            "Plaf.=brut non compté (cap module)"
        )

