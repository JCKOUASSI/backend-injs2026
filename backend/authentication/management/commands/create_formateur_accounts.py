"""
Crée (ou met à jour) les comptes utilisateurs pour les formateurs assignés à au moins un module.

Usage typique:
  python manage.py create_formateur_accounts --dry-run
  python manage.py create_formateur_accounts
  python manage.py create_formateur_accounts --password 'MotDePasseTemporaire'

Le username est le numéro de badge du formateur (ex. F0042).
Sans --password, chaque compte reçoit un mot de passe aléatoire unique (envoyé par email).
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from authentication.badge_accounts import (
    ensure_formateur_account,
    provision_formateur_accounts,
)
from formations.models import Formateur, ModuleFormateur

User = get_user_model()


class Command(BaseCommand):
    help = "Crée des comptes User (rôle FORMATEUR) pour les formateurs assignés à au moins un module."

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
            help='Ne pas modifier les utilisateurs déjà liés au formateur.',
        )
        parser.add_argument(
            '--formation-id',
            type=int,
            default=None,
            help='Limiter aux assignations dont le module appartient à cette formation.',
        )

    def handle(self, *args, **options):
        password = options['password']
        dry_run = options['dry_run']
        skip_existing = options['skip_existing']
        formation_id = options['formation_id']

        qs = ModuleFormateur.objects.select_related('formateur', 'module__formation').order_by('formateur_id')
        if formation_id is not None:
            qs = qs.filter(module__formation_id=formation_id)

        formateur_ids = qs.values_list('formateur_id', flat=True).distinct()
        formateurs = (
            Formateur.objects.filter(pk__in=formateur_ids)
            .select_related('user')
            .order_by('nom', 'prenom', 'numerobadge')
        )

        if dry_run:
            for formateur in formateurs:
                self.stdout.write(
                    f"[DRY-RUN] {formateur.numerobadge} → {formateur.prenom} {formateur.nom}"
                )
            self.stdout.write(self.style.SUCCESS(f"Terminé — {formateurs.count()} formateur(s) (dry-run)"))
            return

        if skip_existing:
            created = updated = skipped = errors = emails_sent = 0
            for formateur in formateurs:
                try:
                    action = ensure_formateur_account(
                        formateur,
                        password=password,
                        send_email=True,
                        skip_existing=True,
                        log=self.stdout.write,
                    )
                    if action == 'created':
                        created += 1
                        if formateur.email:
                            emails_sent += 1
                    elif action == 'updated':
                        updated += 1
                    else:
                        skipped += 1
                except Exception as exc:
                    errors += 1
                    self.stderr.write(
                        self.style.ERROR(
                            f"ERREUR {formateur.numerobadge} {formateur.nom} {formateur.prenom}: {exc}"
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
            stats = provision_formateur_accounts(
                formateur_ids,
                password=password,
                send_email=True,
                log=self.stdout.write,
            )

        self.stdout.write(
            self.style.SUCCESS(
                "Terminé — créés: {created}, mis à jour: {updated}, ignorés: {skipped}, "
                "emails: {emails_sent}, erreurs: {errors}".format(**stats)
            )
        )
