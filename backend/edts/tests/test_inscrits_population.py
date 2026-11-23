"""GET-INJS — population des étudiants inscrits (écran « Étudiants inscrits »).

``GET /api/edts/lmd/inscrits/`` fusionne les deux origines réelles d'une
année : inscriptions administratives validées (processus INJS2026) et
inscriptions lues dans un fichier externe. Ces tests vérifient la fusion,
la déduplication (la base fait foi), les filtres, les facettes et la
pagination à 25 par page — jamais de donnée inventée.
"""

from django.test import TestCase
from rest_framework.test import APIClient

from edts.models import InscriptionImportee
from edts.tests.test_lot2_moteur import FabriqueLMD
from formations.models import Participant
from scolarite.models import DossierEtudiant, InscriptionAdministrative


def _utilisateur(nom, role):
    from django.contrib.auth import get_user_model

    U = get_user_model()
    user = U.objects.create_user(username=nom, password='x')
    user.role = role
    user.save()
    return user


class PopulationInscritsTests(TestCase):
    def setUp(self):
        self.f = FabriqueLMD(self).creer_base(perimetre='INJS', filiere='F01')
        self.formation = self.f.cycle
        self.annee = self.f.annee
        self.client = APIClient()
        self.client.force_authenticate(user=_utilisateur('lecteur', 'ADMIN'))

    # ── Fabriques ──────────────────────────────────────────────────────────
    def importee(self, matricule, nom='KOUASSI', prenoms='Jean', sexe='M', **kw):
        return InscriptionImportee.objects.create(
            annee_academique=self.annee, matricule=matricule, nom=nom,
            prenoms=prenoms, sexe=sexe, ref_formation=self.formation,
            niveau=self.f.niveau, **kw,
        )

    def inscrit_base(self, matricule, nom='DIABATE', prenom='Awa',
                     sexe='FEMININ', statut='VALIDEE'):
        participant = Participant.objects.create(
            matricule=matricule, nom=nom, prenom=prenom, sexe=sexe,
        )
        dossier = DossierEtudiant.objects.create(participant=participant)
        return InscriptionAdministrative.objects.create(
            etudiant=dossier, annee_academique=self.annee,
            ref_formation=self.formation, niveau=self.f.niveau, statut=statut,
        )

    def population(self, **params):
        params.setdefault('annee', self.annee.pk)
        return self.client.get('/api/edts/lmd/inscrits/', params)

    # ── Fusion des deux origines ───────────────────────────────────────────
    def test_fusion_base_et_import(self):
        self.inscrit_base('INJS-001')
        self.importee('EXT-001', nom='YAO', prenoms='Séverin')

        reponse = self.population()
        self.assertEqual(reponse.status_code, 200)
        data = reponse.json()
        self.assertEqual(data['total'], 2)
        sources = {l['matricule']: l['source'] for l in data['resultats']}
        self.assertEqual(sources, {'INJS-001': 'Base', 'EXT-001': 'Import'})
        ligne_base = next(l for l in data['resultats'] if l['source'] == 'Base')
        # Le sexe de la base (MASCULIN/FEMININ) est normalisé comme l'import.
        self.assertEqual(ligne_base['sexe'], 'F')
        self.assertEqual(ligne_base['statut'], 'Inscrit')
        # Tri par nom : DIABATE avant YAO.
        self.assertEqual(
            [l['matricule'] for l in data['resultats']],
            ['INJS-001', 'EXT-001'],
        )

    def test_matricule_des_deux_origines_base_fait_foi(self):
        self.inscrit_base('INJS-002', nom='NOMBASE')
        self.importee('INJS-002', nom='NOMIMPORT')

        data = self.population().json()
        self.assertEqual(data['total'], 1)
        self.assertEqual(data['resultats'][0]['nom'], 'NOMBASE')
        self.assertEqual(data['resultats'][0]['source'], 'Base')

    def test_inscription_non_validee_exclue(self):
        self.inscrit_base('INJS-003', statut='SOUMISE')
        data = self.population().json()
        self.assertEqual(data['total'], 0)
        self.assertEqual(data['resultats'], [])

    def test_importe_radie_affiche_son_statut(self):
        self.importee('EXT-009', statut=InscriptionImportee.Statut.RADIE)
        data = self.population().json()
        self.assertEqual(data['resultats'][0]['statut'], 'Radié')

    # ── Filtres et facettes ────────────────────────────────────────────────
    def test_recherche_matricule_nom_prenoms(self):
        self.importee('EXT-100', nom='TRAORE', prenoms='Ismaël')
        self.importee('EXT-101', nom='KONE', prenoms='Fatou')
        for q, attendu in (('traore', 1), ('Ismaël'.lower(), 1), ('EXT-101', 1),
                           ('absent', 0)):
            data = self.population(q=q).json()
            self.assertEqual(data['total'], attendu, q)

    def test_filtres_formation_niveau_et_facettes(self):
        self.importee('EXT-200')
        data = self.population().json()
        self.assertEqual(
            data['formations'],
            [{'id': self.formation.pk, 'code': self.formation.code or '',
              'intitule': self.formation.intitule}],
        )
        self.assertEqual(
            data['niveaux'],
            [{'id': self.f.niveau.pk, 'code': 'L1', 'ordre': 1}],
        )
        self.assertEqual(self.population(formation=self.formation.pk).json()['total'], 1)
        self.assertEqual(self.population(formation=999999).json()['total'], 0)
        self.assertEqual(self.population(niveau=self.f.niveau.pk).json()['total'], 1)
        self.assertEqual(self.population(niveau=999999).json()['total'], 0)

    # ── Pagination (25 par page, format de l'écran) ────────────────────────
    def test_pagination_25_par_page(self):
        for i in range(26):
            self.importee(f'EXT-{i:03d}', nom=f'NOM{i:02d}')
        page1 = self.population().json()
        self.assertEqual(page1['total'], 26)
        self.assertEqual(page1['total_pages'], 2)
        self.assertEqual(page1['page'], 1)
        self.assertEqual(len(page1['resultats']), 25)
        page2 = self.population(page=2).json()
        self.assertEqual(page2['page'], 2)
        self.assertEqual(len(page2['resultats']), 1)
        # Une page hors bornes est ramenée à la dernière page réelle.
        self.assertEqual(self.population(page=99).json()['page'], 2)

    # ── Gardes ─────────────────────────────────────────────────────────────
    def test_annee_requise(self):
        reponse = self.client.get('/api/edts/lmd/inscrits/')
        self.assertEqual(reponse.status_code, 400)
        self.assertEqual(reponse.json()['motif_echec'], 'ANNEE_ACADEMIQUE_REQUISE')

    def test_anonyme_refuse(self):
        reponse = APIClient().get(
            '/api/edts/lmd/inscrits/', {'annee': self.annee.pk},
        )
        self.assertIn(reponse.status_code, (401, 403))
