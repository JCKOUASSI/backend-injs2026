"""U0 (CURP-INJS) — état des droits et inventaire des comptes existants.

Commande strictement en LECTURE, introduite par l'unité U0 du chantier
« Comptes utilisateurs, rôles & permissions ». Elle fige, à une date donnée,
la photographie du dispositif d'habilitation *actuel* (les 12 rôles, les
groupes synchronisés, la politique de permissions et les ensembles de rôles
côté serveur) ainsi que le parc de comptes en base.

Elle ne modifie aucune donnée : c'est la source de ``docs/curp/01-etat-des-droits.md``
et ``docs/curp/02-inventaire-comptes.md``. La rejouer après évolution fait
apparaître les écarts par simple différence de texte.

Usage :
    python manage.py inventaire_habilitation [--comptes] [--sortie FICHIER]
"""
from collections import Counter
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from authentication import role_groups as rg


class Command(BaseCommand):
    help = "Photographie l'état réel des rôles, groupes, permissions et comptes (lecture seule)."

    def add_arguments(self, parser):
        parser.add_argument(
            '--comptes', action='store_true',
            help="Ajoute l'inventaire chiffré du parc de comptes en base.",
        )
        parser.add_argument(
            '--sortie', type=str, default=None,
            help="Écrit le rapport dans ce fichier au lieu de l'afficher.",
        )

    def handle(self, *args, **options):
        lignes = []
        lignes.append(self._etat_droits())
        if options['comptes']:
            lignes.append(self._inventaire_comptes())
        rapport = "\n".join(lignes).rstrip() + "\n"

        if options['sortie']:
            chemin = Path(options['sortie'])
            chemin.parent.mkdir(parents=True, exist_ok=True)
            chemin.write_text(rapport, encoding='utf-8')
            self.stdout.write(self.style.SUCCESS(f"Rapport écrit dans {chemin}"))
        else:
            self.stdout.write(rapport)

    # ─────────────────────────────────────────────────────────────────────
    # L1 : matrice réelle des droits actuels, extraite du code serveur
    # ─────────────────────────────────────────────────────────────────────
    def _etat_droits(self):
        L = []
        L.append("# ÉTAT DES DROITS EXISTANTS — extrait automatiquement du code serveur")
        L.append("# Généré par : manage.py inventaire_habilitation")
        L.append("# Source : authentication/role_groups.py (les groupes Django sont la")
        L.append("# source de vérité des rôles ; le champ User.role est synchronisé).")
        L.append("")
        L.append("## Les 12 rôles et leurs groupes")
        L.append("")
        L.append("| Code rôle | Libellé | Groupe Django |")
        L.append("|---|---|---|")
        for code, label in get_user_model().Role.choices:
            L.append(f"| {code} | {label} | {rg.ROLE_GROUP_NAMES.get(code, '?')} |")
        L.append("")

        L.append("## Ensembles de rôles effectifs (constantes serveur)")
        L.append("")
        ensembles = (
            ("Rôles web autorisés (ALLOWED_WEB_ROLES)", rg.ALLOWED_WEB_ROLES),
            ("Rôles réservés mobile/PWA (MOBILE_ONLY_ROLES)", rg.MOBILE_ONLY_ROLES),
            ("Rôles d'encadrement mobile", rg.MOBILE_ENCADRANT_ROLES),
            ("Accès global (GLOBAL_ACCESS_ROLES)", rg.GLOBAL_ACCESS_ROLES),
            ("Rôles de secrétariat cloisonnés", rg.SECRETARIAT_ROLES),
            ("Rôles du module Finance", rg.FINANCE_MODULE_ROLES),
            ("Rôles pouvant muter les comptes", rg.USER_MUTATION_ROLES),
        )
        for titre, ensemble in ensembles:
            codes = ", ".join(sorted(str(c) for c in ensemble)) or "(vide)"
            L.append(f"- **{titre}** : {codes}")
        L.append("")

        L.append("## Politique de permissions par rôle (ROLE_POLICY)")
        L.append("")
        for role, politique in rg.ROLE_POLICY.items():
            apps = ", ".join(politique.get('apps', ()))
            actions = ", ".join(politique.get('actions', ()))
            custom = ", ".join(politique.get('custom', ())) or "—"
            exclusions = ", ".join(politique.get('exclude_codenames', ())) or "—"
            L.append(f"### {role}")
            L.append(f"- applications : {apps}")
            L.append(f"- actions modèles : {actions}")
            L.append(f"- permissions métier : {custom}")
            L.append(f"- permissions exclues : {exclusions}")
            L.append("")

        L.append("## Permissions métier personnalisées du modèle utilisateur")
        for codename, libelle in dict(get_user_model()._meta.permissions).items():
            L.append(f"- `authentication.{codename}` — {libelle}")
        L.append("")
        L.append("## Règles de transport")
        L.append("- FORMATEUR et AUDITEUR : connexion web REFUSÉE (HTTP 403,")
        L.append("  message « réservé à l'application mobile ») ; device_id requis et")
        L.append("  vérification d'appairage presences.DeviceBinding côté mobile.")
        L.append("- Le cloisonnement par secrétariat est appliqué dans formations.access")
        L.append("  (modules/participants filtrés sur user.secretariat) et les permissions")
        L.append("  DRF IsSecretariat* ; il doit être préservé par le chantier CURP.")
        return "\n".join(L)

    # ─────────────────────────────────────────────────────────────────────
    # L2 : photographie chiffrée du parc de comptes
    # ─────────────────────────────────────────────────────────────────────
    def _inventaire_comptes(self):
        User = get_user_model()
        L = []
        L.append("# INVENTAIRE DES COMPTES — photographie chiffrée")
        L.append("")
        total = User.objects.count()
        actifs = User.objects.filter(is_active=True).count()
        staff = User.objects.filter(is_staff=True).count()
        superusers = User.objects.filter(is_superuser=True).count()
        L.append(f"- total des comptes : **{total}**")
        L.append(f"- comptes actifs : **{actifs}**")
        L.append(f"- comptes inactifs : **{total - actifs}**")
        L.append(f"- accès admin Django (is_staff) : **{staff}**")
        L.append(f"- super-utilisateurs : **{superusers}**")
        L.append("")

        L.append("## Répartition par rôle (champ User.role)")
        L.append("")
        L.append("| Rôle | Nombre |")
        L.append("|---|---:|")
        par_role = Counter(User.objects.values_list('role', flat=True))
        for code, _label in User.Role.choices:
            L.append(f"| {code} | {par_role.get(code, 0)} |")
        sans_role = User.objects.filter(role='').count()
        if sans_role:
            L.append(f"| (rôle vide) | {sans_role} |")
        L.append("")

        # NB (écart E11) : la connexion JWT actuelle (authentication.views.login_view)
        # n'appelle pas django.contrib.auth.update_last_login ; last_login n'est donc
        # alimenté que par une ouverture de session d'admin Django. Cette métrique ne
        # mesure PAS les connexions applicatives web/mobiles tant que U4/U8 n'a pas
        # branché une trace de dernière connexion.
        jamais = User.objects.filter(last_login__isnull=True).count()
        L.append(
            f"- comptes sans last_login (note : non alimenté par le flux JWT, "
            f"voir écart E11) : **{jamais}**"
        )
        sans_secretariat = User.objects.filter(
            role__in=[str(r) for r in rg.SECRETARIAT_ROLES], secretariat__isnull=True
        ).count()
        L.append(
            f"- comptes de secrétariat SANS rattachement (anomalie potentielle) : "
            f"**{sans_secretariat}**"
        )
        multi_groupes = 0
        for user in User.objects.prefetch_related('groups'):
            if len({g.name for g in user.groups.all() if g.name.startswith('ROLE_')}) > 1:
                multi_groupes += 1
        L.append(f"- comptes portant plusieurs groupes de rôles : **{multi_groupes}**")
        L.append("")
        L.append(
            "> Les comptes partagés, doublons d'identité et comptes sans titulaire "
            "sont à instruire en U8 ; cette commande les SIGNALE, elle ne les corrige pas."
        )
        # Le réglage DATABASES n'est pas garanti d'avoir une cle 'NAME' en test,
        # mais en exploitation réelle c'est toujours le cas.
        base = settings.DATABASES.get('default', {}).get('NAME', '(base inconnue)')
        L.append("")
        L.append(f"_Base inspectée : `{base}`_")
        return "\n".join(L)
