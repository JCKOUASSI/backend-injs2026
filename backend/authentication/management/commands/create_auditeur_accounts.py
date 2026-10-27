"""
Crée (ou met à jour) les comptes utilisateurs pour tous les auditeurs inscrits à au moins un module.

Usage typique:
  python manage.py create_auditeur_accounts --dry-run
  python manage.py create_auditeur_accounts
  python manage.py create_auditeur_accounts --password 'MotDePasseTemporaire'

Le username est le numéro d'inscription (matricule) de l'auditeur.
Sans --password, chaque compte reçoit un mot de passe aléatoire unique (envoyé par email).
Le changement est obligatoire à la première connexion.
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from authentication.badge_accounts import (
    ensure_auditeur_account,
    provision_auditeur_accounts,
)
from formations.models import ModuleParticipant, Participant

User = get_user_model()


class Command(BaseCommand):
    help = "Crée des comptes User (rôle AUDITEUR) pour les auditeurs inscrits à au moins un module."

    def add_arguments(self, parser):
        parser.add_argument(
            '--password',
            default=None,
            help=(
                'Mot de passe unique à appliquer à tous les comptes. '
                'Sans cette option, un mot de passe aléatoire est généré par compte.'
            ),
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Affiche les actions sans écrire en base.',
        )
        parser.add_argument(
            '--skip-existing',
            action='store_true',
            help='Ne pas modifier les utilisateurs déjà liés au participant.',
        )
        parser.add_argument(
            '--formation-id',
            type=int,
            default=None,
            help='Limiter aux inscriptions dont le module appartient à cette formation.',
        )

    def handle(self, *args, **options):
        password = options['password']
        dry_run = options['dry_run']
        skip_existing = options['skip_existing']
        formation_id = options['formation_id']

        qs = (
            ModuleParticipant.objects.select_related('participant', 'module__formation')
            .order_by('participant_id')
        )
        if formation_id is not None:
            qs = qs.filter(module__formation_id=formation_id)

        participant_ids = qs.values_list('participant_id', flat=True).distinct()
        participants = (
            Participant.objects.filter(pk__in=participant_ids)
            .select_related('user', 'secretariat')
            .order_by('nom', 'prenom', 'matricule')
        )

        if dry_run:
            for participant in participants:
                self.stdout.write(
                    f"[DRY-RUN] {participant.matricule} → {participant.prenom} {participant.nom}"
                )
            self.stdout.write(self.style.SUCCESS(f"Terminé — {participants.count()} auditeur(s) (dry-run)"))
            return

        if skip_existing:
            created = updated = skipped = errors = emails_sent = 0
            for participant in participants:
                try:
                    action = ensure_auditeur_account(
                        participant,
                        password=password,
                        send_email=True,
                        skip_existing=True,
                        reset_password=True,
                        log=self.stdout.write,
                    )
                    if action == 'created':
                        created += 1
                        if participant.email:
                            emails_sent += 1
                    elif action == 'updated':
                        updated += 1
                    else:
                        skipped += 1
                except Exception as exc:
                    errors += 1
                    self.stderr.write(
                        self.style.ERROR(
                            f"ERREUR {participant.matricule} {participant.nom} {participant.prenom}: {exc}"
                        )
                    )
            stats = {
                'created': created,
                'updated': updated,
                'skipped': skipped,
                'emails_sent': emails_sent,
                'errors': errors,
            }
        else:
            stats = provision_auditeur_accounts(
                participant_ids,
                password=password,
                send_email=True,
                reset_password=True,
                log=self.stdout.write,
            )

        self.stdout.write(
            self.style.SUCCESS(
                "Terminé — créés: {created}, mis à jour: {updated}, ignorés: {skipped}, "
                "emails: {emails_sent}, erreurs: {errors}".format(**stats)
            )
        )
