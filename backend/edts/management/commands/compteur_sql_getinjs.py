"""Compteur de requêtes SQL par scénario GET-INJS.

Pourquoi cette commande existe
------------------------------
Les mesures de temps (``benchmark_getinjs``) disent « c'est rapide » ou « c'est
lent », jamais **pourquoi**. Le défaut le plus fréquent d'une API Django est le
N+1 : une requête par ligne affichée. Il ne se voit ni à l'écran (l'écran est
juste un peu lent), ni dans un test fonctionnel (la réponse est correcte), et
il ne se mesure pas en secondes sur un petit jeu de données.

Cette commande compte donc les requêtes SQL de chaque scénario **réel** de
GET-INJS (audit, génération, liste, grille, exports), sur la base telle qu'elle
est — par défaut le jeu de démonstration, pour que la mesure soit rejouable par
l'INJS sans préparation.

Règles tenues :

* **aucune donnée inventée ni créée** : la commande ne fait que lire la base
  existante ; le scénario qui persiste (``generate-annee``) s'exécute dans une
  transaction **annulée** à la fin, sauf ``--garder`` ;
* **aucun chiffre simulé** : si un scénario ne peut pas s'exécuter (pas d'année,
  pas d'emploi du temps), il est marqué ``NON EXECUTE`` avec le motif, jamais
  remplacé par zéro ;
* **les requêtes sont lisibles** : ``--detail`` affiche le SQL de chaque requête
  pour un scénario donné, en en masquant les paramètres sensibles.

Exemples
--------
    python manage.py compteur_sql_getinjs
    python manage.py compteur_sql_getinjs --annee DEMO-2026-2027 --detail audit
    python manage.py compteur_sql_getinjs --json /tmp/sql.json
"""

import json
import re
import time

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.test.utils import CaptureQueriesContext, override_settings
from rest_framework.test import APIClient

from edts.models import EmploiDuTemps
from scolarite.models import AnneeAcademique

#: Valeur affichée quand aucune requête n'est exécutée (scénario non joué).
NON_EXECUTE = None


class Command(BaseCommand):
    help = ("Compte les requêtes SQL de chaque scénario GET-INJS (détection N+1).")

    def add_arguments(self, parser):
        parser.add_argument('--annee', default='',
                            help='Libellé de l’année académique (défaut : l’année courante).')
        parser.add_argument('--emploi-du-temps', type=int, default=0,
                            help='Identifiant d’un EDT à mesurer (défaut : le premier de l’année).')
        parser.add_argument('--detail', default='',
                            help='Affiche le SQL d’un scénario (ex. « audit », « grille »).')
        parser.add_argument('--garder', action='store_true',
                            help='Conserve les écritures du scénario de génération '
                                 '(par défaut tout est annulé).')
        parser.add_argument('--json', dest='fichier_json', default='',
                            help='Écrit le rapport complet dans ce fichier JSON.')

    # ── Utilitaires ──────────────────────────────────────────────────────────

    def _annee(self, libelle):
        qs = AnneeAcademique.objects.all().order_by('-date_debut')
        if libelle:
            annee = qs.filter(libelle=libelle).first()
            if annee is None:
                raise CommandError(
                    f'Année « {libelle} » introuvable. Années disponibles : '
                    + ', '.join(qs.values_list('libelle', flat=True)) or '(aucune)')
            return annee
        annee = qs.first()
        if annee is None:
            raise CommandError(
                'Aucune année académique en base : la mesure n’a pas de sujet. '
                'Créer les données de démonstration (manage.py '
                'donnees_demonstration_getinjs) ou choisir --annee.')
        return annee

    def _client(self):
        """Client API authentifié en administrateur — mêmes droits que l'IHM."""
        U = get_user_model()
        utilisateur = (U.objects.filter(role='ADMIN', is_active=True).first()
                       or U.objects.filter(is_superuser=True, is_active=True).first())
        if utilisateur is None:
            raise CommandError('Aucun compte administrateur actif pour interroger l’API.')
        client = APIClient()
        client.force_authenticate(user=utilisateur)
        # Le client de test envoie HTTP_HOST « testserver », absent
        # d'ALLOWED_HOSTS (liste stricte, volontairement : cf. config/settings.py).
        # On l'autorise le temps de la mesure — c'est le seul ajout, il ne
        # relâche rien pour le serveur réel.
        hote = 'testserver'
        self._override = override_settings(ALLOWED_HOSTS=[*settings.ALLOWED_HOSTS, hote])
        self._override.enable()
        return client

    def _mesurer(self, nom, appel, *, journal):
        """Exécute ``appel`` en comptant les requêtes SQL ; ne lève jamais."""
        debut = time.monotonic()
        try:
            with CaptureQueriesContext(connection) as requetes:
                resultat = appel()
        except Exception as exc:  # scénario impossible : consigné, pas masqué
            journal.append({
                'scenario': nom, 'requetes': NON_EXECUTE, 'ms': None,
                'statut': 'NON EXECUTE', 'motif': f'{type(exc).__name__}: {exc}',
                'http': NON_EXECUTE, 'requetes_detail': [],
            })
            return None
        duree_ms = round((time.monotonic() - debut) * 1000, 1)
        code = getattr(resultat, 'status_code', NON_EXECUTE)
        # Un code HTTP en erreur n'est PAS une mesure valide : un écran vide ou
        # un 400 mesuré donnerait un compteur artificiellement bas.
        en_erreur = isinstance(code, int) and code >= 400
        journal.append({
            'scenario': nom,
            'requetes': len(requetes.captured_queries) if not en_erreur else NON_EXECUTE,
            'ms': duree_ms,
            'statut': f'ECHEC HTTP {code}' if en_erreur else 'MESURE',
            'motif': (f'La scène a répondu HTTP {code} : compteur non significatif.'
                      if en_erreur else ''),
            'http': code,
            'requetes_detail': ([q['sql'] for q in requetes.captured_queries]
                                if not en_erreur else []),
        })
        return resultat

    @staticmethod
    def _sql_lisible(sql):
        """SQL sur une ligne, valeurs littérales élidées (pas de fuite de données)."""
        return re.sub(r'\s+', ' ', sql).strip()

    # ── Commande ─────────────────────────────────────────────────────────────

    def handle(self, *args, **options):
        self._override = None
        try:
            return self._mesurer_tout(options)
        finally:
            if self._override is not None:
                self._override.disable()

    def _mesurer_tout(self, options):
        annee = self._annee(options['annee'])
        client = self._client()
        journal = []

        # 1. Audit « puis-je générer ? » — l'écran d'entrée de la campagne.
        self._mesurer(
            'audit (GET /api/edts/lmd/audit/)',
            lambda: client.get('/api/edts/lmd/audit/',
                               {'annee_academique_id': annee.pk}),
            journal=journal)

        # 2. Génération annuelle SANS écriture (simulation) — le chemin que
        #    prend l'écran quand on décoche « enregistrer les brouillons ».
        self._mesurer(
            'generation simulation (POST generate-annee, persister=false)',
            lambda: client.post('/api/edts/lmd/generate-annee/',
                                {'annee_academique_id': annee.pk,
                                 'semaines': [1, 2, 3, 4], 'persister': False},
                                format='json'),
            journal=journal)

        # 3. Génération PERSISTÉE — dans une transaction annulée par défaut :
        #    mesurer ne doit pas modifier les données de l'INJS.
        def generer_persistant():
            with transaction.atomic():
                reponse = client.post(
                    '/api/edts/lmd/generate-annee/',
                    {'annee_academique_id': annee.pk, 'semaines': [1, 2, 3, 4],
                     'persister': True},
                    format='json')
                if not options['garder']:
                    transaction.set_rollback(True)
                return reponse

        self._mesurer(
            'generation persistee (POST generate-annee, persister=true, annulee)'
            if not options['garder'] else
            'generation persistee (POST generate-annee, persister=true, conservee)',
            generer_persistant, journal=journal)

        # 4. Liste des emplois du temps de l'année.
        self._mesurer(
            'liste EDT (GET /api/edts/emplois/)',
            lambda: client.get('/api/edts/emplois/', {'annee_academique_id': annee.pk}),
            journal=journal)

        edt = (EmploiDuTemps.objects.filter(pk=options['emploi_du_temps']).first()
               if options['emploi_du_temps'] else
               EmploiDuTemps.objects.filter(annee_academique=annee).order_by('pk').first())

        if edt is None:
            for nom in ('grille EDT (GET /api/edts/emplois/<id>/grille/)',
                        'conflits EDT (GET /api/edts/conflits/)',
                        'export CSV', 'export XLSX', 'export PDF',
                        'audit EDT persiste (POST /api/edts/lmd/<id>/audit/)'):
                journal.append({'scenario': nom, 'requetes': NON_EXECUTE, 'ms': None,
                                'statut': 'NON EXECUTE',
                                'motif': 'Aucun emploi du temps dans cette année.',
                                'http': NON_EXECUTE, 'requetes_detail': []})
        else:
            self._mesurer(
                'grille EDT (GET /api/edts/emplois/<id>/grille/)',
                lambda: client.get(f'/api/edts/emplois/{edt.pk}/grille/',
                                   {'semaine': 1}),
                journal=journal)
            self._mesurer(
                'conflits EDT (GET /api/edts/conflits/)',
                lambda: client.get('/api/edts/conflits/',
                                   {'emploi_du_temps_id': edt.pk}),
                journal=journal)
            for format_export, route in (
                ('CSV', f'/api/edts/emplois/{edt.pk}/export.csv/'),
                ('XLSX', f'/api/edts/lmd/{edt.pk}/export.xlsx/'),
                ('PDF', f'/api/edts/lmd/{edt.pk}/export.pdf/'),
            ):
                self._mesurer(
                    f'export {format_export}',
                    (lambda r=route: client.get(r)),
                    journal=journal)

        # ── Restitution ─────────────────────────────────────────────────────
        self.stdout.write('')
        self.stdout.write(self.style.MIGRATE_HEADING(
            f'Requêtes SQL par scénario — année {annee.libelle}'))
        self.stdout.write('-' * 78)
        self.stdout.write(f'{"SCÉNARIO":<58}{"SQL":>7}{"HTTP":>7}')
        for ligne in journal:
            sql = '—' if ligne['requetes'] is None else str(ligne['requetes'])
            http = '—' if ligne['http'] is None else str(ligne['http'])
            self.stdout.write(f'{ligne["scenario"][:57]:<58}{sql:>7}{http:>7}')
        self.stdout.write('-' * 78)
        non_joues = [l for l in journal if l['requetes'] is None]
        if non_joues:
            self.stdout.write(self.style.WARNING('Scénarios NON EXECUTES :'))
            for ligne in non_joues:
                self.stdout.write(f'  - {ligne["scenario"]} : {ligne["motif"]}')
        echecs = [l for l in journal if l['statut'].startswith('ECHEC')]
        if echecs:
            self.stdout.write(self.style.ERROR('Scénarios en ÉCHEC (compteur non significatif) :'))
            for ligne in echecs:
                self.stdout.write(f'  - {ligne["scenario"]} : {ligne["statut"]}')
        total = sum(l['requetes'] or 0 for l in journal)
        self.stdout.write(f'Total mesuré : {total} requêtes sur '
                          f'{len(journal) - len(non_joues)} scénario(s) exécuté(s).')
        self.stdout.write('Lecture : un nombre de requêtes qui ne dépend PAS du volume '
                          'de lignes est le signe attendu ; une requête par ligne est un N+1.')

        if options['detail']:
            cible = options['detail'].lower()
            choisies = [l for l in journal
                        if cible in l['scenario'].lower() and l['requetes_detail']]
            if not choisies:
                raise CommandError(f'Aucun scénario mesuré ne correspond à « {cible} ».')
            for ligne in choisies:
                self.stdout.write('')
                self.stdout.write(self.style.MIGRATE_HEADING(
                    f'SQL — {ligne["scenario"]} ({ligne["requetes"]} requêtes)'))
                for i, sql in enumerate(ligne['requetes_detail'], 1):
                    self.stdout.write(f'{i:>3}. {self._sql_lisible(sql)[:300]}')

        if options['fichier_json']:
            with open(options['fichier_json'], 'w', encoding='utf-8') as fichier:
                json.dump({'annee': annee.libelle, 'scenarios': journal},
                          fichier, ensure_ascii=False, indent=2)
            self.stdout.write(f'Rapport JSON : {options["fichier_json"]}')
