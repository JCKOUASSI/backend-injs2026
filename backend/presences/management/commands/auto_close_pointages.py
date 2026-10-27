"""
Commande : python manage.py auto_close_pointages

Pour chaque pointage EN_COURS dont la séance est terminée depuis plus d'1 heure
(ou dont heure_fin_prevue + 1h est dépassée) :
  - timestamp_sortie = timestamp_entree  (durée = 0)
  - duree_presence_minutes = 0
  - statut = ABSENT_NON_BADGE
  - motif tracé en AuditLog (AUTO_ABSENT)

Applique aussi les sanctions heartbeat via process_mobile_heartbeats (même logique).

À planifier via cron toutes les 5-15 minutes :
  */10 * * * * /path/to/venv/bin/python /path/to/manage.py auto_close_pointages

Pour n'exécuter que la surveillance heartbeat :
  python manage.py process_mobile_heartbeats
"""

from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from presences.heartbeat_sanctions import process_mobile_heartbeat_sanctions
from presences.models import AuditLog, Pointage

MOTIF = "N'a pas badgé à la sortie de la séance"


class Command(BaseCommand):
    help = (
        "Marque ABSENT les pointages non soldés après fin de séance "
        "et surveille les heartbeats mobiles."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help="Affiche les pointages concernés sans les modifier.",
        )
        parser.add_argument(
            '--delai',
            type=int,
            default=None,
            help="Délai en minutes après la fin de séance avant marquage absent "
                 "(défaut : valeur AUTO_ABSENT_DELAI_MINUTES du .env).",
        )
        parser.add_argument(
            '--skip-heartbeat',
            action='store_true',
            help="Ne pas exécuter la surveillance heartbeat (utiliser process_mobile_heartbeats).",
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        delai = (
            options['delai']
            if options['delai'] is not None
            else getattr(settings, 'AUTO_ABSENT_DELAI_MINUTES', 60)
        )
        now = timezone.now()

        absents = self._process_absent_non_badge(delai=delai, now=now, dry_run=dry_run)

        heartbeats = 0
        if not options['skip_heartbeat']:
            heartbeats = process_mobile_heartbeat_sanctions(
                dry_run=dry_run,
                write=self.stdout.write,
            )

        label = "simulés" if dry_run else "traités"
        self.stdout.write(
            self.style.SUCCESS(
                f"{absents} absent(s) non badgé(s) {label}, "
                f"{heartbeats} pointage(s) heartbeat {label}."
            )
        )

    def _process_absent_non_badge(self, *, delai, now, dry_run):
        pointages_ouverts = (
            Pointage.objects
            .filter(
                statut__in=[Pointage.Statut.EN_COURS, Pointage.Statut.HORS_LIGNE_SUSPECT],
                timestamp_sortie__isnull=True,
            )
            .select_related(
                'session__module__formation',
                'participant',
                'formateur',
                'encadrant',
            )
            # Lot C : les séances LMD se clôturent par leur propre endpoint
            # (fenêtre EDT) ; ce commando ne traite que le flux legacy.
            .filter(session__isnull=False)
        )

        traites = 0
        for pt in pointages_ouverts:
            seance = pt.session
            fin_seance = self._fin_seance(seance)
            if not fin_seance or fin_seance + timedelta(minutes=delai) > now:
                continue

            personne = pt.participant or pt.formateur or pt.encadrant
            if personne:
                nom = (
                    f"{getattr(personne, 'nom', '')} {getattr(personne, 'prenom', '')}".strip()
                    or f"{getattr(personne, 'last_name', '')} {getattr(personne, 'first_name', '')}".strip()
                    or getattr(personne, 'username', '?')
                )
            else:
                nom = "?"
            numero = (
                getattr(personne, 'numerobadge', None)
                or getattr(personne, 'matricule', None)
                or getattr(personne, 'numero', '?')
            ) if personne else '?'
            type_str = (
                'formateur' if pt.formateur_id
                else 'encadrant' if pt.encadrant_id
                else 'participant'
            )

            if dry_run:
                self.stdout.write(
                    f"[DRY-RUN] ABSENT_NON_BADGE {numero} {nom} — séance {seance}"
                )
                traites += 1
                continue

            pt.timestamp_sortie = pt.timestamp_entree
            pt.duree_presence_minutes = 0
            pt.statut = Pointage.Statut.ABSENT_NON_BADGE
            pt.save(update_fields=['timestamp_sortie', 'duree_presence_minutes', 'statut', 'updated_at'])

            AuditLog.objects.create(
                action=AuditLog.Action.AUTO_ABSENT,
                acteur=None,
                acteur_label='Système',
                cible_type=type_str,
                cible_numero=numero,
                cible_nom=nom,
                formation=seance.module.formation,
                formation_titre=seance.module.formation.formation,
                pointage=pt,
                ip_address=None,
                device_id='SYSTEM',
                extra={
                    'motif': MOTIF,
                    'delai_minutes': delai,
                    'fin_seance': fin_seance.isoformat(),
                },
            )

            traites += 1
            self.stdout.write(
                self.style.WARNING(
                    f"ABSENT_NON_BADGE : {numero} {nom} — {seance.module.formation.formation}"
                )
            )

        return traites

    def _fin_seance(self, seance):
        if seance.terminee_le:
            return seance.terminee_le

        if seance.date_journee and seance.heure_fin_prevue:
            from datetime import datetime
            from zoneinfo import ZoneInfo

            tz = ZoneInfo('Africa/Abidjan')
            return timezone.make_aware(
                datetime.combine(seance.date_journee, seance.heure_fin_prevue),
                tz,
            )

        return None
