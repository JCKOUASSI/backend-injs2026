"""U0 (CURP-INJS) — scénario de fumée d'authentification sur comptes témoins.

Rejoue, sur la base de démonstration/recette peuplée par
``creer_comptes_temoins``, les invariants du dispositif d'authentification
ACTUEL que le chantier CURP ne doit jamais rompre :

* les 10 rôles web obtiennent un jeton en se connectant sans ``device_id`` ;
* FORMATEUR et AUDITEUR sont REFUSÉS sur le web (HTTP 403, message explicite),
  mais acceptés en canal mobile avec ``device_id`` (HTTP 200) ;
* pour tout jeton obtenu, les routes de référence /api/auth/me/,
  /api/auth/capabilities/ (projection française des capacités) et
  /api/auth/roles/ répondent 200 ;
* le cloisonnement par secrétariat est prouvé par un test CROISÉ : le compte
  du secrétariat A ne voit jamais le participant du secrétariat B (et
  inversement), via le queryset de service qui filtre à la source.

Une seule ligne rouge suffit à faire échouer la commande (code de sortie 1) :
la fumée est une barrière, pas un indicateur.

Usage :
    python manage.py fumee_authentification --tous
    python manage.py fumee_authentification --creer      # crée les témoins d'abord
"""
import os
import sys

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.test import Client

from authentication.role_groups import (
    ALLOWED_WEB_ROLES,
    MOBILE_ONLY_ROLES,
)
from formations.access import participants_queryset_for_user

User = get_user_model()

MOT_DE_PASSE_DEFAUT = "Temoin#2026"

# username témoin -> (rôle, libellé court de la vérification de cloisonnement)
TEMOINS_WEB = [
    ("temoin_admin", "ADMIN"),
    ("temoin_chef_cpfae_admin", "CHEF_INJS_ADMIN"),
    ("temoin_cpfae_admin", "INJS_ADMIN"),
    ("temoin_direction", "DIRECTION"),
    ("temoin_chef_secretariat_a", "CHEF_SECRETARIAT"),
    ("temoin_chef_secretariat_b", "CHEF_SECRETARIAT"),
    ("temoin_secretariat_a", "SECRETARIAT"),
    ("temoin_secretariat_b", "SECRETARIAT"),
    ("temoin_finance", "FINANCE"),
    ("temoin_archive", "ARCHIVE"),
    ("temoin_encadrant", "ENCADRANT"),
    ("temoin_superviseur", "SUPERVISEUR"),
]
TEMOINS_MOBILE = [
    ("temoin_formateur", "FORMATEUR"),
    ("temoin_auditeur", "AUDITEUR"),
]

ROUTES_AUTH = ["/api/auth/me/", "/api/auth/capabilities/", "/api/auth/roles/"]


class Command(BaseCommand):
    help = "Scénario de fumée : les 14 comptes témoins atteignent leurs écrans de référence."

    def add_arguments(self, parser):
        parser.add_argument('--tous', action='store_true', help="Exécute tout le scénario.")
        parser.add_argument('--creer', action='store_true',
                            help="Crée d'abord les comptes et données témoins.")

    def handle(self, *args, **options):
        if not options['tous']:
            self.print_help(sys.argv[0], 'fumee_authentification')
            return
        # La commande joue le rôle d'un client HTTP via django.test.Client :
        # son hôte canonique est 'testserver', que les TestCase activent
        # automatiquement mais pas les commandes de gestion. On l'autorise
        # pour la durée de la fumée, sans toucher aux réglages versionnés.
        from django.conf import settings
        if 'testserver' not in settings.ALLOWED_HOSTS:
            settings.ALLOWED_HOSTS.append('testserver')
        if options['creer']:
            call_command('creer_comptes_temoins')
            self._creer_participants_temoins()

        # Le scénario enchaîne ~16 connexions depuis une seule adresse ;
        # on démarre d'un compteur de limitation propre afin que la fumée
        # soit rejouable à volonté (y compris juste après un autre parcours)
        # sans hériter d'un quota déjà consommé. Commande de recette uniquement.
        self._purger_compteurs_limitation()

        mdp = os.environ.get('COMPTE_TEMOIN_MOT_DE_PASSE', MOT_DE_PASSE_DEFAUT)
        self.lignes = []
        self.echecs = 0

        for username, role in TEMOINS_WEB:
            self._fumee_compte_web(username, role, mdp)
        for username, role in TEMOINS_MOBILE:
            self._fumee_compte_mobile(username, role, mdp)
        self._fumee_cloisonnement(mdp)

        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING("FUMÉE D'AUTHENTIFICATION"))
        for ligne in self.lignes:
            self.stdout.write(ligne)
        self.stdout.write("")
        if self.echecs:
            self.stdout.write(self.style.ERROR(
                f"ÉCHEC — {self.echecs} ligne(s) rouge(s) : fusion interdite."
            ))
            sys.exit(1)
        self.stdout.write(self.style.SUCCESS(
            f"SUCCÈS — {len(self.lignes)} vérifications vertes."
        ))

    # ─────────────────────────────────────────────────────────────────────
    def _purger_compteurs_limitation(self):
        """Remet à zéro les compteurs du limiteur de connexion (recette)."""
        from django.core.cache import cache
        # Le client de test utilise 127.0.0.1 comme adresse source.
        cache.delete('login:127.0.0.1')
        # Redis (futur) expose delete_pattern ; on élargit alors la purge.
        if hasattr(cache, 'delete_pattern'):
            cache.delete_pattern('login:*')

    # ─────────────────────────────────────────────────────────────────────
    def _ok(self, texte):
        self.lignes.append(self.style.SUCCESS("  VERT  ") + texte)

    def _ko(self, texte):
        self.lignes.append(self.style.ERROR("  ROUGE ") + texte)
        self.echecs += 1

    def _constater(self, condition, texte):
        if condition:
            self._ok(texte)
        else:
            self._ko(texte)

    def _compte(self, username):
        return User.objects.filter(username=username).first()

    def _routes_de_reference(self, jeton, username, role_attendu):
        client = Client()
        for route in ROUTES_AUTH:
            reponse = client.get(route, HTTP_AUTHORIZATION=f"Bearer {jeton}")
            self._constater(
                reponse.status_code == 200,
                f"{username} GET {route} -> {reponse.status_code} (attendu 200)",
            )
        # Le rôle effectif doit être exposé par l'endpoint de capacités.
        reponse = client.get("/api/auth/capabilities/", HTTP_AUTHORIZATION=f"Bearer {jeton}")
        if reponse.status_code == 200:
            roles = reponse.json().get('roles') or []
            self._constater(
                role_attendu in roles,
                f"{username} capacités exposent le rôle {role_attendu} (vu : {roles})",
            )

    def _fumee_compte_web(self, username, role, mdp):
        compte = self._compte(username)
        if compte is None:
            self._ko(f"{username} : compte témoin absent (lancer --creer)")
            return
        client = Client()
        reponse = client.post(
            "/api/auth/login/",
            data={"username": username, "password": mdp},
            content_type="application/json",
        )
        if reponse.status_code != 200:
            self._ko(f"{username} login web -> {reponse.status_code} (attendu 200)")
            return
        self._ok(f"{username} ({role}) login web -> 200")
        jeton = reponse.json().get('access')
        self._constater(bool(jeton), f"{username} reçoit un jeton d'accès")
        self._routes_de_reference(jeton, username, role)

    def _fumee_compte_mobile(self, username, role, mdp):
        compte = self._compte(username)
        if compte is None:
            self._ko(f"{username} : compte témoin absent (lancer --creer)")
            return
        client = Client()
        # Canal web sans device : REFUS explicite, c'est le comportement gelé.
        reponse_web = client.post(
            "/api/auth/login/",
            data={"username": username, "password": mdp},
            content_type="application/json",
        )
        self._constater(
            reponse_web.status_code == 403,
            f"{username} login web SANS device -> {reponse_web.status_code} (attendu 403)",
        )
        if reponse_web.status_code == 403:
            detail = reponse_web.json().get('detail', '')
            attendu = "application mobile"
            self._constater(
                attendu in detail,
                f"{username} message de refus web explicite : {detail!r}",
            )
        # Canal mobile avec device : ACCEPTÉ.
        device_id = f"DEMO-DEVICE-{role}"
        reponse_mob = client.post(
            "/api/auth/login/",
            data={"username": username, "password": mdp, "device_id": device_id},
            content_type="application/json",
        )
        if reponse_mob.status_code != 200:
            self._ko(f"{username} login MOBILE avec device -> {reponse_mob.status_code} (attendu 200)")
            return
        self._ok(f"{username} ({role}) login mobile avec device -> 200")
        jeton = reponse_mob.json().get('access')
        self._routes_de_reference(jeton, username, role)

    def _creer_participants_temoins(self):
        from formations.models import Participant, Secretariat
        sec_a = Secretariat.objects.filter(numero="SECR-DEMO-A").first()
        sec_b = Secretariat.objects.filter(numero="SECR-DEMO-B").first()
        if not sec_a or not sec_b:
            self._ko("secrétariats témoins absents ; cloisonnement non testé")
            return
        Participant.objects.get_or_create(
            matricule="TEMOIN-PART-A",
            defaults={"nom": "TEMOIN", "prenom": "PARTICIPANT A", "secretariat": sec_a},
        )
        Participant.objects.get_or_create(
            matricule="TEMOIN-PART-B",
            defaults={"nom": "TEMOIN", "prenom": "PARTICIPANT B", "secretariat": sec_b},
        )

    def _fumee_cloisonnement(self, mdp):
        from formations.models import Participant, Secretariat
        sec_a = Secretariat.objects.filter(numero="SECR-DEMO-A").first()
        sec_b = Secretariat.objects.filter(numero="SECR-DEMO-B").first()
        part_a = Participant.objects.filter(matricule="TEMOIN-PART-A").first()
        part_b = Participant.objects.filter(matricule="TEMOIN-PART-B").first()
        if not all([sec_a, sec_b, part_a, part_b]):
            self._ko("données de cloisonnement absentes (lancer --creer)")
            return

        for username, autre in (("temoin_secretariat_a", part_b),
                                ("temoin_secretariat_b", part_a)):
            compte = self._compte(username)
            if compte is None:
                self._ko(f"{username} absent pour le test de cloisonnement")
                continue
            visibles = participants_queryset_for_user(compte)
            self._constater(
                autre not in visibles,
                f"{username} ne voit PAS le participant de l'autre secrétariat "
                f"({autre.matricule})",
            )
        # Les rôles globaux, eux, voient les deux participants.
        admin = self._compte("temoin_admin")
        if admin is not None:
            visibles = participants_queryset_for_user(admin)
            self._constater(
                part_a in visibles and part_b in visibles,
                "temoin_admin (périmètre global) voit les participants des deux secrétariats",
            )

        # Contrôle du nombre de rôles web couverts par le scénario.
        manquants = {str(r) for r in ALLOWED_WEB_ROLES} - {
            r for _, r in TEMOINS_WEB
        }
        self._constater(not manquants, f"les {len(ALLOWED_WEB_ROLES)} rôles web sont couverts")
        self._constater(
            {r for _, r in TEMOINS_MOBILE} == {str(r) for r in MOBILE_ONLY_ROLES},
            "les 2 rôles mobile-only sont couverts (FORMATEUR, AUDITEUR)",
        )
