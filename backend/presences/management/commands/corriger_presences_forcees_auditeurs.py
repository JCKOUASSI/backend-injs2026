"""
Commande : python manage.py corriger_presences_forcees_auditeurs

Corrige les pointages auditeur déjà forcés (FORCE_DFRC) avant la règle
« présence forcée = durée planifiée de la séance » :
  - pose entrée/sortie sur heure_debut_prevue → heure_fin_prevue ;
  - recalcule duree_presence_minutes.

Par défaut : uniquement les pointages incomplets (sans sortie ou durée ≤ 0).

Exemples :
  python manage.py corriger_presences_forcees_auditeurs --dry-run
  python manage.py corriger_presences_forcees_auditeurs
  python manage.py corriger_presences_forcees_auditeurs --module-id 42
  python manage.py corriger_presences_forcees_auditeurs --formation-id 3 --date 2026-03-15
  python manage.py corriger_presences_forcees_auditeurs --all --dry-run
"""

from django.core.management.base import BaseCommand
from django.db.models import Q

from presences.duree import clamp_to_seance, pointage_minutes_clampees, rattrapage_creneau_timestamps
from presences.models import Pointage


class Command(BaseCommand):
    help = (
        "Corrige les présences forcées auditeur (FORCE_DFRC) : "
        "entrée/sortie = créneau planifié de la séance + durée recalculée."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help="Affiche les corrections sans modifier la base.",
        )
        parser.add_argument(
            '--all',
            action='store_true',
            help="Recalcule tous les pointages FORCE_DFRC auditeur, pas seulement les incomplets.",
        )
        parser.add_argument('--formation-id', type=int, default=None)
        parser.add_argument('--module-id', type=int, default=None)
        parser.add_argument('--session-id', type=int, default=None)
        parser.add_argument('--date', type=str, default=None, help="Date séance (AAAA-MM-JJ).")
        parser.add_argument('--limit', type=int, default=None, help="Nombre max de pointages à traiter.")

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        fix_all = options['all']

        qs = (
            Pointage.objects
            .filter(participant__isnull=False)
            .filter(
                Q(statut=Pointage.Statut.FORCE_DFRC) | Q(device_id='FORCE_DFRC'),
            )
            .select_related('session', 'session__module', 'participant')
            .order_by('date_journee', 'id')
        )

        if options['formation_id']:
            qs = qs.filter(session__module__formation_id=options['formation_id'])
        if options['module_id']:
            qs = qs.filter(session__module_id=options['module_id'])
        if options['session_id']:
            qs = qs.filter(session_id=options['session_id'])
        if options['date']:
            qs = qs.filter(date_journee=options['date'])

        total = qs.count()
        if options['limit']:
            qs = qs[: options['limit']]

        corriges = 0
        ignores = 0

        for pt in qs.iterator(chunk_size=200):
            if not self._a_corriger(pt, fix_all=fix_all):
                ignores += 1
                continue

            seance = pt.session
            ts_entree, ts_sortie = rattrapage_creneau_timestamps(seance)
            new_entree = clamp_to_seance(ts_entree, seance)
            new_sortie = clamp_to_seance(ts_sortie, seance)

            ancienne_duree = float(pt.duree_presence_minutes or 0)
            pt.timestamp_entree = new_entree
            pt.timestamp_sortie = new_sortie
            pt.statut = Pointage.Statut.FORCE_DFRC
            nouvelle_duree = pointage_minutes_clampees(pt)

            participant = pt.participant
            label = f"{getattr(participant, 'matricule', '')} {participant.nom} {participant.prenom}".strip()
            seance_label = seance.intitule or f"Séance {seance.numero}"
            msg = (
                f"#{pt.pk} {label} — {seance_label} ({pt.date_journee}) : "
                f"{ancienne_duree:.0f} → {nouvelle_duree:.0f} min"
            )

            if dry_run:
                self.stdout.write(f"[DRY-RUN] {msg}")
            else:
                pt.duree_presence_minutes = nouvelle_duree
                pt.save(update_fields=[
                    'timestamp_entree', 'timestamp_sortie',
                    'duree_presence_minutes', 'statut', 'updated_at',
                ])
                self.stdout.write(msg)

            corriges += 1

        verbe = 'seraient corrigés' if dry_run else 'corrigés'
        self.stdout.write(self.style.SUCCESS(
            f"{corriges} pointage(s) {verbe}, {ignores} ignoré(s) "
            f"(sur {total} FORCE_DFRC auditeur dans le périmètre)."
        ))

    @staticmethod
    def _a_corriger(pointage, *, fix_all=False):
        if fix_all:
            return True
        if pointage.timestamp_sortie is None:
            return True
        if float(pointage.duree_presence_minutes or 0) <= 0:
            return True
        return False
