"""Clôture les occurrences publiées d'EDT/LMD dont la fenêtre est échue.

À appeler par l'ordonnanceur existant, par exemple toutes les cinq minutes :
  python manage.py auto_close_seances_edt

La commande ne cible que la date locale courante par défaut, les EDT VALIDÉ/PUBLIÉ
et les occurrences explicitement planifiées ce jour. ``--dry-run`` n'écrit rien.
"""
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from django.utils.dateparse import parse_date

from edts.models import AffectationCreneau
from presences import seances_edt_services as service


class Command(BaseCommand):
    help = "Clôture les séances QR LMD publiées après la fin de leur fenêtre de badgeage."

    def add_arguments(self, parser):
        parser.add_argument(
            '--date',
            default=None,
            help='Date ISO (AAAA-MM-JJ) à traiter ; par défaut, date locale courante.',
        )
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Affiche les occurrences éligibles sans clôturer ni modifier les QR.',
        )

    def handle(self, *args, **options):
        date_arg = options['date']
        date = parse_date(date_arg) if date_arg else timezone.localdate()
        if date is None:
            raise CommandError('--date doit être une date valide au format AAAA-MM-JJ.')
        if date > timezone.localdate():
            raise CommandError('La date de clôture ne peut pas être dans le futur.')

        maintenant = timezone.now()
        eligibles = []
        affectations = (AffectationCreneau.objects
                        .filter(actif=True, emploi_du_temps__statut__in=('VALIDE', 'PUBLIE'))
                        .select_related('creneau_template', 'emploi_du_temps',
                                        'emploi_du_temps__annee_academique', 'groupe', 'formation')
                        .order_by('pk'))
        for affectation in affectations.iterator():
            if not service.est_seance_du_jour(affectation, date):
                continue
            _, heure_cloture = service.fenetre_scan(affectation, date)
            if maintenant >= heure_cloture:
                eligibles.append((affectation, heure_cloture))

        if options['dry_run']:
            for affectation, heure_cloture in eligibles:
                self.stdout.write(
                    f'[dry-run] clôturerait séance EDT #{affectation.pk} '
                    f'({affectation.intitule or affectation.creneau_template}) '
                    f'à partir de {heure_cloture.isoformat()}'
                )
            self.stdout.write(f'{len(eligibles)} occurrence(s) éligible(s) ; aucune écriture.')
            return

        cloturees = 0
        for affectation, _ in eligibles:
            resultat = service.auto_clore(None, affectation, date)
            cloturees += 1
            self.stdout.write(
                f"Séance EDT #{affectation.pk} clôturée : "
                f"{resultat['pointages_clotures']} sortie(s), "
                f"{resultat['absents_marques']} absence(s)."
            )
        self.stdout.write(self.style.SUCCESS(
            f'{cloturees} occurrence(s) EDT/LMD traitée(s) pour le {date.isoformat()}.'
        ))
