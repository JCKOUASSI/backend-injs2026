"""Rattachement additif des comptes legacy sans profil CURP (LOT 5 / U8, étape 1).

La séquence de bascule (``docs/architecture/IAM.md`` §10) commence par doter
chaque compte legacy d'un profil gouverné **additif et idempotent** :

* l'utilisateur ``User``, son rôle legacy et ses droits existants ne sont
  **jamais** modifiés (règle S5 : aucun retrait, aucune révocation) ;
* le profil ``CompteUtilisateur`` est créé avec le miroir de ``is_active`` ;
* les attributions CURP sont déduites de la table A6
  (``referentiel.catalogue_matrice.CORRESPONDANCE_LEGACY``) : les rôles non
  sensibles sont posés ``ACTIVE`` ; les rôles sensibles sont posés
  ``PROPOSEE`` — la seconde signature reste à faire dans la console, le
  rattachement n'auto-accorde jamais un rôle sensible (règle J2-1 assumée).

Un compte dont le rôle legacy ne correspond à rien d'installable est
signalé et laissé non gouverné (l'ancien dispositif reste seul décideur).

Par prudence, la commande s'exécute en **simulation** (``--dry-run`` est le
défaut) ; ``--appliquer`` écrit, une transaction par utilisateur, et un
second passage ne fait rien (idempotence par l'absence de compte).

Usage :

    python manage.py rattacher_comptes_legacy              # rapport
    python manage.py rattacher_comptes_legacy --appliquer  # pose
"""
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from habilitations.models import (
    AttributionRole,
    CompteUtilisateur,
    JournalHabilitation,
    RoleMetier,
)
from habilitations.referentiel.catalogue_matrice import CORRESPONDANCE_LEGACY
from habilitations.services.journalisation import journaliser

User = get_user_model()

MOTIF_RATTACHEMENT = (
    'Rattachement LOT 5 / U8 — compte legacy sans profil CURP '
    '(additif, table A6).'
)


class Command(BaseCommand):
    help = ("Rattache les comptes legacy sans profil CURP (simulation par "
            "défaut ; --appliquer pour écrire).")

    def add_arguments(self, parser):
        parser.add_argument(
            '--appliquer', action='store_true',
            help='Écrit les profils et attributions (défaut : simulation).',
        )
        parser.add_argument(
            '--role', default='',
            help='Limiter le rattachement à un rôle legacy donné (ex. SECRETARIAT).',
        )

    def handle(self, *args, **options):
        jouer = options['appliquer']
        role_filtre = options['role'].strip().upper()

        sans_compte = (
            User.objects.filter(profil_habilitation__isnull=True)
            .order_by('role', 'username')
        )
        if role_filtre:
            sans_compte = sans_compte.filter(role=role_filtre)

        lignes = []
        for user in sans_compte.iterator():
            lignes.append(self._traiter(user, jouer=jouer))

        n_ok = sum(1 for l in lignes if l[1])
        n_skip = sum(1 for l in lignes if not l[1])
        entete = 'Rattachement appliqué' if jouer else 'Rattachement simulé'
        self.stdout.write(self.style.SUCCESS(
            f'{entete} : {n_ok} compte(s) — ignoré(s)/à traiter : {n_skip}.'
        ))
        for user_label, agit, detail in lignes:
            marque = 'POSÉ' if (agit and jouer) else ('SIMULÉ' if agit else '—')
            self.stdout.write(f'[{marque}] {user_label} — {detail}')

    # ------------------------------------------------------------------
    def _codes_installables(self, role_legacy):
        """Codes CURP issus de A6, filtrés sur le catalogue installé/actif."""
        codes = CORRESPONDANCE_LEGACY.get(role_legacy, [])
        if not codes:
            return None, []
        roles = list(RoleMetier.objects.filter(code__in=codes, actif=True))
        trouves = {r.code for r in roles}
        manquants = [c for c in codes if c not in trouves]
        return roles, manquants

    def _traiter(self, user, *, jouer):
        label = f'{user.username} ({user.role})'
        roles, manquants = self._codes_installables(user.role)
        if roles is None:
            return (label, False,
                    f'rôle legacy « {user.role} » sans correspondance A6 — '
                    'laissé non gouverné.')
        non_sensibles = [r for r in roles if not r.sensible]
        sensibles = [r for r in roles if r.sensible]
        if not non_sensibles:
            return (label, False,
                    'correspondances A6 uniquement sensibles '
                    f'({", ".join(r.code for r in sensibles)}) — à créer dans '
                    'la console (double validation), pas d’auto-élévation.')
        if jouer:
            with transaction.atomic():
                compte = self._poser(user, non_sensibles, sensibles)
            detail = (
                f'profil + {len(non_sensibles)} attribution(s) active(s)'
                + (f', {len(sensibles)} proposition(s) sensible(s)'
                   if sensibles else '')
                + (' ; rôles A6 manquants : ' + ', '.join(manquants)
                   if manquants else '')
            )
            return (label, True, detail)
        detail = (
            f'profil + attributions {", ".join(r.code for r in non_sensibles)}'
            + (f' (+ propositions {", ".join(r.code for r in sensibles)})'
               if sensibles else '')
            + (f' ; rôles A6 manquants : {", ".join(manquants)}'
               if manquants else '')
        )
        return (label, True, detail)

    def _poser(self, user, non_sensibles, sensibles):
        compte = CompteUtilisateur.objects.create(
            user=user,
            statut=(CompteUtilisateur.Statut.ACTIF if user.is_active
                    else CompteUtilisateur.Statut.DESACTIVE),
            canal='LES_DEUX',
            motif_statut=MOTIF_RATTACHEMENT,
            date_activation=(timezone.now() if user.is_active else None),
        )
        journaliser(
            JournalHabilitation.TypeEvenement.COMPTE_CREE,
            compte=compte,
            nouvelle_valeur={
                'username': user.username, 'role_legacy': user.role,
                'origine': 'RATTACHEMENT_LOT5',
            },
            motif=MOTIF_RATTACHEMENT,
        )
        for role in non_sensibles:
            attribution = AttributionRole.objects.create(
                compte=compte, role=role,
                niveau_effectif=role.niveau_defaut,
                statut=AttributionRole.Statut.ACTIVE,
                motif=MOTIF_RATTACHEMENT,
            )
            journaliser(
                JournalHabilitation.TypeEvenement.ROLE_ATTRIBUE,
                compte=compte, cible=attribution,
                nouvelle_valeur={'role': role.code,
                                 'origine': 'RATTACHEMENT_LOT5'},
                motif=MOTIF_RATTACHEMENT,
            )
        for role in sensibles:
            attribution = AttributionRole.objects.create(
                compte=compte, role=role,
                niveau_effectif=role.niveau_defaut,
                statut=AttributionRole.Statut.PROPOSEE,
                motif=MOTIF_RATTACHEMENT + ' Seconde signature requise.',
            )
            journaliser(
                JournalHabilitation.TypeEvenement.PROPOSITION_DEPOSEE,
                compte=compte, cible=attribution,
                nouvelle_valeur={'role': role.code,
                                 'origine': 'RATTACHEMENT_LOT5'},
                motif=MOTIF_RATTACHEMENT,
            )
        return compte
