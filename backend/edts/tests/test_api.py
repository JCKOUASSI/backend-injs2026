"""Tests du module GET-INJS — API (lot L8, audit du 2026-09-15).

Couvre les défauts relevés par l'audit : sérialiseurs (plus de 500 sur les
champs fantômes), validation d'entrée (400/409 au lieu de 500), filtres de
listes effectifs, verrouillage du workflow (escalade par PATCH statut),
gel d'édition après validation, droits par rôle, export CSV et grille.
"""

from datetime import date, time

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from edts.models import AffectationCreneau, ConflitCreneau, CreneauTemplate, EmploiDuTemps
from scolarite.models import AnneeAcademique, JournalScolarite

User = get_user_model()


def make_client(role='ADMIN', username=None):
    user = User.objects.create_user(username=username or f'u-{role.lower()}',
                                    password='pass', role=role)
    client = APIClient()
    client.force_authenticate(user=user)
    return client, user


class EdtApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.annee = AnneeAcademique.objects.create(
            libelle='2026-2027', date_debut=date(2026, 10, 1), date_fin=date(2027, 9, 30),
        )
        cls.creneau = CreneauTemplate.objects.create(
            jour='LUNDI', heure_debut=time(8, 0), heure_fin=time(10, 0),
        )
        cls.admin, cls.admin_user = make_client('ADMIN')
        cls.secretariat, _ = make_client('SECRETARIAT', 'sec-test')
        cls.encadrant, cls.encadrant_user = make_client('ENCADRANT', 'enc-test')
        cls.formateur, _ = make_client('FORMATEUR', 'form-test')
        cls.auditeur, _ = make_client('AUDITEUR', 'aud-test')

    # -- utilitaires -------------------------------------------------------
    def _edt(self, client=None, **surcharges):
        donnees = {
            'annee_academique_id': self.annee.pk,
            'population_type': 'ENSEIGNANT',
            'population_id': self.encadrant_user.pk,
            'titre': 'EDT test',
            'semaine_debut': 1,
            'semaine_fin': 12,
        }
        donnees.update(surcharges)
        return (client or self.admin).post('/api/edts/emplois/', donnees, format='json')

    # -- liste & détail : plus de 500 même avec des lignes -----------------
    def test_liste_et_detail_serialisent_proprement(self):
        reponse = self._edt()
        self.assertEqual(reponse.status_code, 201, reponse.data)
        cle = reponse.json()['id']
        reponse = self.admin.get('/api/edts/emplois/')
        self.assertEqual(reponse.status_code, 200)
        ligne = next(x for x in reponse.json() if x['id'] == cle)
        self.assertEqual(ligne['population_label'],
                         self.encadrant_user.get_full_name() or self.encadrant_user.username)
        self.assertEqual(ligne['affectations_count'], 0)
        self.assertEqual(ligne['conflits_count'], 0)
        reponse = self.admin.get(f'/api/edts/emplois/{cle}/')
        self.assertEqual(reponse.status_code, 200)
        self.assertEqual(reponse.json()['semaine_fin'], 12)

    # -- validation d'entrée ------------------------------------------------
    def test_creation_invalide_renv_oir_400(self):
        for payload in (
            {'population_type': 'FORMATION'},                                     # annee + population_id manquants
            {'annee_academique_id': 999999, 'population_type': 'FORMATION', 'population_id': 1},  # annee inconnue -> 400
            {'annee_academique_id': self.annee.pk, 'population_type': 'INEXISTANT', 'population_id': 1},
            {'annee_academique_id': self.annee.pk, 'population_type': 'FORMATION', 'population_id': 'abc'},
        ):
            reponse = self.admin.post('/api/edts/emplois/', payload, format='json')
            self.assertIn(reponse.status_code, (400, 404), payload)
            self.assertLess(reponse.status_code, 500)

    def test_doublon_population_renvoie_409(self):
        self.assertEqual(self._edt().status_code, 201)
        reponse = self._edt(titre='doublon')
        self.assertEqual(reponse.status_code, 409)
        self.assertIn('existe déjà', reponse.json()['detail'])

    # -- escalade de workflow fermée -----------------------------------------
    def test_patch_ne_peut_plus_ecrire_le_statut(self):
        cle = self._edt().json()['id']
        reponse = self.secretariat.patch(f'/api/edts/emplois/{cle}/',
                                         {'statut': 'PUBLIE'}, format='json')
        self.assertEqual(reponse.status_code, 400)
        self.assertEqual(EmploiDuTemps.objects.get(pk=cle).statut, 'BROUILLON')

    def test_workflow_complet_et_role_validation(self):
        cle = self._edt().json()['id']
        # Vider le workflow au premier jet : pas de validation sans affectation soumise.
        reponse = self.admin.post(f'/api/edts/emplois/{cle}/valider/', {'statut': 'VALIDE'}, format='json')
        self.assertEqual(reponse.status_code, 409)  # BROUILLON -> VALIDE interdit (transition manquante)

        # Ajout d'une affectation puis soumission.
        reponse = self.secretariat.post('/api/edts/affectations/', {
            'emploi_du_temps_id': cle, 'creneau_template_id': self.creneau.pk,
            'semaine_debut': 1, 'semaine_fin': 12, 'nature': 'COURS', 'intitule': 'Module A',
        }, format='json')
        self.assertEqual(reponse.status_code, 201, reponse.data)
        reponse = self.secretariat.post(f'/api/edts/emplois/{cle}/soumettre/', {}, format='json')
        self.assertEqual(reponse.status_code, 200, reponse.data)
        self.assertEqual(EmploiDuTemps.objects.get(pk=cle).statut, 'EN_VALIDATION')

        # Secréariat ne peut pas valider.
        reponse = self.secretariat.post(f'/api/edts/emplois/{cle}/valider/',
                                        {'statut': 'VALIDE'}, format='json')
        self.assertEqual(reponse.status_code, 403)
        # ADMIN valide, puis publie.
        self.assertEqual(self.admin.post(f'/api/edts/emplois/{cle}/valider/',
                                         {'statut': 'VALIDE'}, format='json').status_code, 200)
        self.assertEqual(self.admin.post(f'/api/edts/emplois/{cle}/publier/', {}, format='json').status_code, 200)
        self.assertEqual(EmploiDuTemps.objects.get(pk=cle).statut, 'PUBLIE')

        # Gel : le secrétariat ne touche plus aux affectations d'un EDT publié.
        reponse = self.secretariat.patch(
            f'/api/edts/affectations/{AffectationCreneau.objects.first().pk}/',
            {'intitule': 'piraté'}, format='json'
        )
        self.assertEqual(reponse.status_code, 409)

        # Dépublication par la Direction qui débloque l'édition.
        self.assertEqual(self.admin.post(f'/api/edts/emplois/{cle}/depublier/', {}, format='json').status_code, 200)
        reponse = self.secretariat.patch(f'/api/edts/affectations/{AffectationCreneau.objects.first().pk}/',
                                         {'intitule': 'corrigé'}, format='json')
        self.assertEqual(reponse.status_code, 200)

        # Traces d'audit présentes.
        for action in ('EDT_PUBLIE', 'EDT_DEPUBLIE', 'EDT_VALIDE', 'EDT_AFFECTATION_MODIFIEE'):
            self.assertTrue(JournalScolarite.objects.filter(action=action).exists(), action)

    # -- filtres de listes (bug d'affichage croisée) -------------------------
    def test_filtres_affectations_et_conflits(self):
        autre_pop = User.objects.create_user(username='autre-pop', password='p', role='AUDITEUR')
        cle_a = self._edt(titre='A').json()['id']
        # Second EDT (autre population) pour vérifier que le filtre n'est pas ignoré.
        cle_b = self.admin.post('/api/edts/emplois/', {
            'annee_academique_id': self.annee.pk, 'population_type': 'ENSEIGNANT',
            'population_id': autre_pop.pk, 'titre': 'B',
        }, format='json').json()['id']
        for cle in (cle_a, cle_b):
            reponse = self.secretariat.post('/api/edts/affectations/', {
                'emploi_du_temps_id': cle, 'creneau_template_id': self.creneau.pk,
                'semaine_debut': 1, 'semaine_fin': 5, 'nature': 'TD',
            }, format='json')
            self.assertEqual(reponse.status_code, 201)
        reponse = self.secretariat.get(f'/api/edts/affectations/?emploi_du_temps_id={cle_a}')
        self.assertEqual(reponse.status_code, 200)
        data = reponse.json()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]['emploi_du_temps_id'], cle_a)
        # semaine hors période -> vide
        reponse = self.secretariat.get(f'/api/edts/affectations/?emploi_du_temps_id={cle_a}&semaine=9')
        self.assertEqual(reponse.json(), [])
        # conflits filtrés par EDT
        self.assertEqual(self.secretariat.get('/api/edts/conflits/').status_code, 200)

    def test_affectation_sur_edt_valide_refusee(self):
        cle = self._edt().json()['id']
        EmploiDuTemps.objects.filter(pk=cle).update(statut='EN_VALIDATION')
        reponse = self.secretariat.post('/api/edts/affectations/', {
            'emploi_du_temps_id': cle, 'creneau_template_id': self.creneau.pk,
            'semaine_debut': 1, 'semaine_fin': 2,
        }, format='json')
        self.assertEqual(reponse.status_code, 409)

    def test_affectation_invalide_renvoie_400(self):
        cle = self._edt().json()['id']
        reponse = self.secretariat.post('/api/edts/affectations/',
                                        {'emploi_du_temps_id': cle}, format='json')
        self.assertEqual(reponse.status_code, 400)
        reponse = self.secretariat.post('/api/edts/affectations/', {
            'emploi_du_temps_id': cle, 'creneau_template_id': self.creneau.pk,
            'semaine_debut': 8, 'semaine_fin': 2,
        }, format='json')
        self.assertEqual(reponse.status_code, 400)
        reponse = self.secretariat.post('/api/edts/affectations/', {
            'emploi_du_temps_id': cle, 'creneau_template_id': self.creneau.pk,
            'semaine_debut': 1, 'semaine_fin': 2, 'nature': 'INVENTAIRE',
        }, format='json')
        self.assertEqual(reponse.status_code, 400)

    # -- permissions ----------------------------------------------------------
    def test_lectures_seules_et_anonymes(self):
        self.assertEqual(self.auditeur.get('/api/edts/emplois/').status_code, 200)
        self.assertEqual(self.auditeur.get('/api/edts/creneaux-types/').status_code, 200)
        self.assertEqual(self.auditeur.get(f'/api/edts/creneaux-types/{self.creneau.pk}/').status_code, 200)
        self.assertEqual(self.auditeur.get('/api/edts/publics/').status_code, 200)
        anonyme = APIClient()
        self.assertEqual(anonyme.get('/api/edts/emplois/').status_code, 401)
        self.assertEqual(anonyme.get('/api/edts/publics/').status_code, 401)
        reponse = self.formateur.post('/api/edts/emplois/', {}, format='json')
        self.assertEqual(reponse.status_code, 403)

    def test_role_injs_admin_peut_planifier(self):
        """Régularisation CURP : INJS_ADMIN (ex-compte 'dfrc') est planificateur."""
        client, _ = make_client('INJS_ADMIN', 'ex-dfrc')
        reponse = client.post('/api/edts/emplois/', {
            'annee_academique_id': self.annee.pk, 'population_type': 'ENSEIGNANT',
            'population_id': self.encadrant_user.pk, 'titre': 'par INJS-Admin',
        }, format='json')
        self.assertEqual(reponse.status_code, 201, reponse.data)

    # -- référentiel créneaux --------------------------------------------------
    def test_creneau_types_curd_et_protection(self):
        reponse = self.secretariat.post('/api/edts/creneaux-types/', {
            'jour': 'MARDI', 'heure_debut': '10:00', 'heure_fin': '12:00',
        }, format='json')
        self.assertEqual(reponse.status_code, 201, reponse.data)
        nouveau = reponse.json()['id']
        reponse = self.secretariat.post('/api/edts/creneaux-types/', {
            'jour': 'MARDI', 'heure_debut': '10:00', 'heure_fin': '12:00',
        }, format='json')
        self.assertEqual(reponse.status_code, 409)
        reponse = self.secretariat.post('/api/edts/creneaux-types/', {
            'jour': 'MARDI', 'heure_debut': '14:00', 'heure_fin': '12:00',
        }, format='json')
        self.assertEqual(reponse.status_code, 400)
        # Le créneau utilisé est protégé (affectation créée dans un test du workflow :
        # ici on le crée et l'utilise explicitement).
        cle = self._edt(titre='protect').json()['id']
        self.secretariat.post('/api/edts/affectations/', {
            'emploi_du_temps_id': cle, 'creneau_template_id': self.creneau.pk,
            'semaine_debut': 1, 'semaine_fin': 2,
        }, format='json')
        reponse = self.secretariat.delete(f'/api/edts/creneaux-types/{self.creneau.pk}/')
        self.assertEqual(reponse.status_code, 409)
        reponse = self.secretariat.delete(f'/api/edts/creneaux-types/{nouveau}/')
        self.assertEqual(reponse.status_code, 204)

    # -- suppression ------------------------------------------------------------
    def test_suppression_seulement_brouillon_et_archive(self):
        cle = self._edt(titre='à supprimer').json()['id']
        # publié -> refus de suppression (il faut archiver d'abord)
        EmploiDuTemps.objects.filter(pk=cle).update(statut='PUBLIE')
        reponse = self.secretariat.delete(f'/api/edts/emplois/{cle}/')
        self.assertEqual(reponse.status_code, 409)
        supp_pop = User.objects.create_user(username='supp-pop', password='p', role='AUDITEUR')
        cle_vide = self._edt(titre='vide', population_id=supp_pop.pk).json()['id']
        reponse = self.secretariat.delete(f'/api/edts/emplois/{cle_vide}/')
        self.assertEqual(reponse.status_code, 204)

    # -- export & grille ----------------------------------------------------------
    def test_grille_et_export_csv(self):
        cle = self._edt().json()['id']
        self.secretariat.post('/api/edts/affectations/', {
            'emploi_du_temps_id': cle, 'creneau_template_id': self.creneau.pk,
            'semaine_debut': 1, 'semaine_fin': 12, 'intitule': 'Algèbre', 'salle_nom': 'A101',
        }, format='json')
        reponse = self.auditeur.get(f'/api/edts/emplois/{cle}/grille/?semaine=3')
        self.assertEqual(reponse.status_code, 200)
        jours = reponse.json()['jours']
        self.assertEqual(jours[0]['jour'], 'LUNDI')
        self.assertEqual(jours[0]['creneaux'][0]['affectations'][0]['intitule'], 'Algèbre')
        reponse = self.auditeur.get(f'/api/edts/emplois/{cle}/export.csv/')
        self.assertEqual(reponse.status_code, 200)
        self.assertIn('text/csv', reponse['Content-Type'])
        contenu = reponse.content.decode('utf-8-sig')
        self.assertIn('Algèbre', contenu)

    def test_alias_timetable(self):
        reponse = self.admin.get('/api/timetable/emplois/')
        self.assertEqual(reponse.status_code, 200)
