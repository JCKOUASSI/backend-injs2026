"""Le nombre de requêtes SQL ne doit pas dépendre du volume de données.

Un N+1 ne casse rien : la réponse est correcte, l'écran s'affiche, aucun test
fonctionnel ne bronche. Il coûte seulement une requête par ligne — et il est
invisible tant qu'on ne compte pas. Ces tests comptent.

Ils sont nés d'une mesure réelle (``manage.py compteur_sql_getinjs``) sur le jeu
de démonstration, qui a révélé un N+1 dans la grille hebdomadaire et dans
l'export PDF : ``groupe.__str__`` lit ``annee_academique``, et la jointure
manquait. Résultat mesuré : 4 requêtes pour 2 séances, **24 pour 22** (une par
séance). Après correctif : **2 requêtes**, quel que soit le nombre de séances.

Chaque test compare deux volumes et exige un nombre de requêtes identique. Le
seuil n'est pas « à peu près » : une tolérance rendrait le test incapable de
détecter le défaut qu'il est censé surveiller.
"""

import io

from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from edts.models import AffectationCreneau, CreneauTemplate, EmploiDuTemps
from edts.tests.test_api_getinjs import BaseApiTest


class CompteurRequetesMixin:
    def requetes(self, appel):
        """(nombre de requêtes SQL, code HTTP) d'un appel — sans rien avaler."""
        with CaptureQueriesContext(connection) as capture:
            reponse = appel()
        return len(capture.captured_queries), getattr(reponse, 'status_code', None)


class PasDeNPlusUnTests(CompteurRequetesMixin, BaseApiTest):
    """Les écrans de GET-INJS ne font pas une requête par ligne."""

    def creer_edt(self, version, titre=None):
        return EmploiDuTemps.objects.create(
            annee_academique=self.annee, version=version,
            titre=titre or f'EDT {version}', semaine_debut=1, semaine_fin=4,
            population_type='FORMATION', population_id=self.formation.pk,
        )

    def test_l_audit_ne_fait_pas_une_requete_par_groupe(self):
        self.f.creer_groupe(nom='L1-G1')
        petit, code_petit = self.requetes(lambda: self.client.get(
            '/api/edts/lmd/audit/', {'annee_academique_id': self.annee.pk}))
        for i in range(2, 7):
            self.f.creer_groupe(nom=f'L1-G{i}')
        grand, code_grand = self.requetes(lambda: self.client.get(
            '/api/edts/lmd/audit/', {'annee_academique_id': self.annee.pk}))

        self.assertEqual((code_petit, code_grand), (200, 200))
        self.assertEqual(
            grand, petit,
            'L’audit émet une requête de plus par groupe : mesuré '
            f'{petit} requêtes pour 1 groupe, {grand} pour 6. Une requête par '
            'groupe est un N+1 (précharger groupes et besoins).',
        )

    def test_la_liste_des_emplois_du_temps_ne_fait_pas_une_requete_par_ligne(self):
        self.creer_edt(1)
        petit, _ = self.requetes(lambda: self.client.get(
            '/api/edts/emplois/', {'annee_academique_id': self.annee.pk}))
        for i in range(2, 7):
            self.creer_edt(i)
        grand, code = self.requetes(lambda: self.client.get(
            '/api/edts/emplois/', {'annee_academique_id': self.annee.pk}))

        self.assertEqual(code, 200)
        self.assertEqual(
            grand, petit,
            'La liste des EDT émet une requête par ligne : '
            f'{petit} requêtes pour 1 EDT, {grand} pour 6.',
        )

    def _remplir(self, edt, nombre, groupe, creneaux):
        affectations = [
            self.f.creer_affectation(volume=2, groupe=groupe)
            for _ in range(nombre)
        ]
        for i in range(nombre):
            AffectationCreneau.objects.create(
                emploi_du_temps=edt,
                creneau_template=creneaux[i % len(creneaux)],
                semaine_debut=1, semaine_fin=1,
                affectation_pedagogique=affectations[i], groupe=groupe,
            )

    def test_la_grille_ne_fait_pas_une_requete_par_seance(self):
        """Le défaut réellement mesuré (24 requêtes pour 22 séances)."""
        groupe = self.f.creer_groupe(nom='L1-G1')
        creneaux = list(CreneauTemplate.objects.all()[:4])
        edt = self.creer_edt(1)

        self._remplir(edt, 2, groupe, creneaux)
        petit, code_petit = self.requetes(lambda: self.client.get(
            f'/api/edts/emplois/{edt.pk}/grille/', {'semaine': 1}))

        self._remplir(edt, 20, groupe, creneaux)
        grand, code_grand = self.requetes(lambda: self.client.get(
            f'/api/edts/emplois/{edt.pk}/grille/', {'semaine': 1}))

        self.assertEqual((code_petit, code_grand), (200, 200))
        self.assertEqual(
            grand, petit,
            'La grille émet une requête par séance : '
            f'{petit} requêtes pour 2 séances, {grand} pour 22. '
            'Cause connue : `groupe.__str__` lit `annee_academique` '
            '(ajouter `groupe__annee_academique` au select_related).',
        )

    def test_l_export_pdf_ne_fait_pas_une_requete_par_seance(self):
        groupe = self.f.creer_groupe(nom='L1-G1')
        creneaux = list(CreneauTemplate.objects.all()[:4])
        edt = self.creer_edt(1)

        self._remplir(edt, 2, groupe, creneaux)
        petit, code_petit = self.requetes(lambda: self.client.get(
            f'/api/edts/lmd/{edt.pk}/export.pdf/'))

        self._remplir(edt, 20, groupe, creneaux)
        grand, code_grand = self.requetes(lambda: self.client.get(
            f'/api/edts/lmd/{edt.pk}/export.pdf/'))

        self.assertEqual((code_petit, code_grand), (200, 200))
        self.assertEqual(
            grand, petit,
            'L’export PDF émet une requête par séance : '
            f'{petit} requêtes pour 2 séances, {grand} pour 22.',
        )


    def test_l_export_csv_ne_fait_pas_une_requete_par_seance(self):
        groupe = self.f.creer_groupe(nom='L1-G1')
        creneaux = list(CreneauTemplate.objects.all()[:4])
        edt = self.creer_edt(1)

        self._remplir(edt, 2, groupe, creneaux)
        petit, code_petit = self.requetes(lambda: self.client.get(
            f'/api/edts/emplois/{edt.pk}/export.csv/'))

        self._remplir(edt, 20, groupe, creneaux)
        grand, code_grand = self.requetes(lambda: self.client.get(
            f'/api/edts/emplois/{edt.pk}/export.csv/'))

        self.assertEqual((code_petit, code_grand), (200, 200))
        self.assertEqual(
            grand, petit,
            'L’export CSV émet une requête par séance : '
            f'{petit} requêtes pour 2 séances, {grand} pour 22.',
        )

    def test_l_export_xlsx_ne_fait_pas_une_requete_par_seance(self):
        groupe = self.f.creer_groupe(nom='L1-G1')
        creneaux = list(CreneauTemplate.objects.all()[:4])
        edt = self.creer_edt(1)

        self._remplir(edt, 2, groupe, creneaux)
        petit, code_petit = self.requetes(lambda: self.client.get(
            f'/api/edts/lmd/{edt.pk}/export.xlsx/'))

        self._remplir(edt, 20, groupe, creneaux)
        grand, code_grand = self.requetes(lambda: self.client.get(
            f'/api/edts/lmd/{edt.pk}/export.xlsx/'))

        self.assertEqual((code_petit, code_grand), (200, 200))
        self.assertEqual(
            grand, petit,
            'L’export XLSX émet des requêtes par séance (contexte pédagogique '
            f'non joint) : {petit} requêtes pour 2 séances, {grand} pour 22.',
        )


class CommandeCompteurTests(CompteurRequetesMixin, BaseApiTest):
    """La commande de mesure dit la vérité et ne modifie rien."""

    def test_la_commande_compte_sans_ecrire(self):
        self.f.creer_groupe(nom='L1-G1')
        edt = EmploiDuTemps.objects.create(
            annee_academique=self.annee, version=1, titre='EDT mesuré',
            semaine_debut=1, semaine_fin=4,
            population_type='FORMATION', population_id=self.formation.pk,
        )
        avant = (EmploiDuTemps.objects.count(), AffectationCreneau.objects.count())

        sortie = io.StringIO()
        call_command('compteur_sql_getinjs', annee=self.annee.libelle,
                     emploi_du_temps=edt.pk, stdout=sortie)

        texte = sortie.getvalue()
        apres = (EmploiDuTemps.objects.count(), AffectationCreneau.objects.count())

        self.assertEqual(avant, apres, 'La mesure ne doit rien écrire en base.')
        self.assertIn('Requêtes SQL par scénario', texte)
        self.assertIn('audit (GET /api/edts/lmd/audit/)', texte)
        # Aucun scénario ne doit être « en échec » sur un jeu valide : un code
        # HTTP d'erreur donnerait un compteur artificiellement bas.
        self.assertNotIn('ECHEC', texte)
        self.assertIn('Total mesuré', texte)

    def test_scenario_impossible_est_nomme_et_non_compte_zero(self):
        """Une année sans emploi du temps : les scénarios sont NOMMÉS, pas « 0 »."""
        from scolarite.models import AnneeAcademique

        vide = AnneeAcademique.objects.create(
            libelle='2099-2100', date_debut='2099-10-01', date_fin='2100-06-30')

        sortie = io.StringIO()
        call_command('compteur_sql_getinjs', annee=vide.libelle, stdout=sortie)
        texte = sortie.getvalue()

        self.assertIn('NON EXECUTE', texte)
        self.assertIn('Aucun emploi du temps', texte)
        self.assertIn('Scénarios NON EXECUTES', texte)

    def test_annee_inconnue_refusee_avec_la_liste_des_annees(self):
        with self.assertRaises(CommandError) as contexte:
            call_command('compteur_sql_getinjs', annee='ANNEE-QUI-N-EXISTE-PAS',
                         stdout=io.StringIO())
        self.assertIn('introuvable', str(contexte.exception))
