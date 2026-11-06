"""``rbac_initialisation`` — prévisualisation et initialisation du socle RBAC.

Emplacement : **application ``habilitations``** (``backend/habilitations/
management/commands/``), conformément à la convention du projet : les 17
applications Django déclarent leurs commandes dans leur propre arborescence et
il n'existe aucun dossier ``backend/management/``. Un fichier placé au niveau
projet **ne serait pas découvert** par Django (le paquet ``backend`` n'est pas
dans ``INSTALLED_APPS``).

Mode par défaut : **prévisualisation strictement sans écriture**.

    python manage.py rbac_initialisation
    python manage.py rbac_initialisation --json rapport.json
    python manage.py rbac_initialisation --inclure-superutilisateurs
    python manage.py rbac_initialisation --username agent1

Écriture (après validation du rapport et sauvegarde exploitable) :

    python manage.py rbac_initialisation --apply
    python manage.py rbac_initialisation --apply --ignorer-drapeaux   # recette

Ce que fait ``--apply`` : **créer uniquement les comptes RBAC manquants**
(``CompteUtilisateur``), un par transaction, avec journalisation.

Ce qu'il ne fait jamais : attribuer un rôle (sensible ou non, aucun rôle n'est
déduit de ``User.role``), modifier un utilisateur Django, modifier un compte
ou une attribution existante, réimporter le catalogue, supprimer quoi que ce
soit.
"""
from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError

from habilitations.services.initialisation_rbac import (
    appliquer_rapport,
    construire_rapport,
    ecriture_autorisee,
)


class Command(BaseCommand):
    help = ("Prévisualise (défaut, sans écriture) ou initialise (--apply) "
            "les comptes RBAC manquants.")

    def add_arguments(self, parser):
        parser.add_argument(
            '--apply', action='store_true', dest='appliquer',
            help='Écrit réellement les comptes manquants (défaut : prévisualisation).',
        )
        parser.add_argument(
            '--ignorer-drapeaux', action='store_true',
            help='Autorise l’écriture même si les drapeaux ne sont pas ouverts (recette).',
        )
        parser.add_argument(
            '--inclure-superutilisateurs', action='store_true',
            help='Inclut les superutilisateurs dans les comptes à créer.',
        )
        parser.add_argument(
            '--username', default='',
            help='Limite le traitement à un nom d’utilisateur.',
        )
        parser.add_argument(
            '--json', dest='json_path', default='',
            help='Écrit aussi le rapport au format JSON à ce chemin.',
        )

    def handle(self, *args, **options):
        appliquer = options['appliquer']
        ignorer = options['ignorer_drapeaux']

        if appliquer:
            autorise, motifs = ecriture_autorisee(ignorer_drapeaux=ignorer)
            if not autorise:
                raise CommandError(
                    'Écriture refusée — drapeaux non réunis :\n  - '
                    + '\n  - '.join(motifs)
                    + '\nOuvrir les deux drapeaux, ou --ignorer-drapeaux en recette.'
                )

        rapport = construire_rapport(
            inclure_superutilisateurs=options['inclure_superutilisateurs'],
            filtre_username=options['username'],
            ignorer_drapeaux=ignorer,
        )
        if appliquer:
            appliquer_rapport(rapport, acteur=None)

        self._ecrire(rapport, applique=appliquer)
        chemin = options['json_path']
        if chemin:
            with open(chemin, 'w', encoding='utf-8') as fp:
                json.dump(rapport.vers_dict(), fp, ensure_ascii=False, indent=2)
            self.stdout.write(self.style.SUCCESS(f'Rapport JSON : {chemin}'))

    # ------------------------------------------------------------------
    def _ecrire(self, rapport, *, applique: bool) -> None:
        out = self.stdout.write
        style = self.style.SUCCESS if applique else self.style.WARNING
        out(style(
            ('INITIALISATION APPLIQUÉE' if applique else 'PRÉVISUALISATION (aucune écriture)')
            + f' — {rapport.horodatage}'))
        out(f'  Base                    : {rapport.base}')
        out(f'  Écriture autorisée      : {rapport.ecriture_autorisee}')
        for motif in rapport.motifs_ecriture:
            out(f'    · {motif}')

        u = rapport.utilisateurs
        out(self.style.MIGRATE_HEADING('  UTILISATEURS DJANGO (authentification)'))
        out(f'    total {u["total"]} · actifs {u["actifs"]} · inactifs {len(u["inactifs"])}')
        if u['inactifs']:
            out(f'    inactifs : {", ".join(u["inactifs"][:15])}')
        out(f'    superutilisateur(s) : {", ".join(u["superutilisateurs"]) or "aucun"}')

        c = rapport.comptes
        out(self.style.MIGRATE_HEADING('  COMPTES RBAC (habilitation)'))
        out(f'    existants {c["existants"]} · manquants {c["manquants"]}')
        if c['a_creer']:
            out(f'    à créer   : {", ".join(c["a_creer"][:15])}'
                + ('…' if len(c['a_creer']) > 15 else ''))
        out(f'    superutilisateurs exclus : {c["superutilisateurs_exclus"]}')

        a = rapport.attributions
        out(self.style.MIGRATE_HEADING('  ATTRIBUTIONS DE RÔLE (droits effectifs)'))
        out(f'    total {a["total"]} · par statut {a["par_statut"] or "—"}')
        if a['sensibles_actives_sans_seconde_signature']:
            out(self.style.ERROR(
                '    sensibles ACTIVES sans seconde signature : '
                + ', '.join(a['sensibles_actives_sans_seconde_signature'])))
        for violation in a['violations_contraintes'][:10]:
            out(f'    ! {violation}')

        r = rapport.roles
        out(self.style.MIGRATE_HEADING('  CATALOGUE'))
        out(f'    rôles {r["total"]} (actifs {r["actifs"]}, sensibles {r["sensibles"]}) '
            f'· permissions {r["permissions"]}')
        cmp_fichier = r['comparaison_fichier']
        out(f'    fichier catalogue_roles.py : {cmp_fichier["roles_fichier"]} rôles '
            f'({cmp_fichier["sensibles_fichier"]} sensibles)')
        if cmp_fichier['codes_absents_de_la_base'] or cmp_fichier['codes_absents_du_fichier'] \
                or cmp_fichier['attributs_divergents']:
            out(self.style.ERROR('    DIVERGENCE catalogue fichier ↔ base — voir le JSON'))

        for rubrique, libelle in ((rapport.coherence, 'COHÉRENCE UTILISATEUR ↔ COMPTE'),
                                  (rapport.doublons, 'DOUBLONS PROBABLES'),
                                  (rapport.anomalies_perimetre, 'ANOMALIES DE PÉRIMÈTRE')):
            if rubrique:
                out(self.style.MIGRATE_HEADING(f'  {libelle} ({len(rubrique)})'))
                for ligne in rubrique[:12]:
                    out(f'    · {ligne}')
                if len(rubrique) > 12:
                    out(f'    … et {len(rubrique) - 12} autre(s) — voir le JSON')

        out(self.style.MIGRATE_HEADING('  OPÉRATIONS'
                                       + (' RÉALISÉES' if applique else ' PRÉVUES')))
        for ligne in rapport.operations:
            out(f'    · {ligne}')
        for ligne in rapport.realise:
            out(f'    → {ligne}')
        out(style(
            'Aucune attribution de rôle n’est créée : aucun rôle n’est déduit '
            'du champ historique User.role.'))
