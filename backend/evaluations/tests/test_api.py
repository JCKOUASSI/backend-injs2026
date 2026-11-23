"""C1 — Tests d'API structurelle des évaluations académiques.

Couverture : authentification, permissions par rôle, pagination, erreurs
structurées, en-tête ``X-Error-Code``, contrôles de saisie, historique
append-only et absence de seed métier.
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from evaluations.models import (
    Evaluation,
    EvaluationAttendance,
    EvaluationComponent,
    EvaluationGrade,
    EvaluationGradeHistory,
    EvaluationParticipant,
    SessionEvaluation,
    TypeEvaluation,
)
from evaluations.tests import factories as f

BASE = '/api/evaluations-academiques'
User = get_user_model()


class ApiTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = f.creer_compte('ADMIN', 'admin-c1')
        cls.secretariat = f.creer_compte('SECRETARIAT', 'secretariat-c1')
        cls.encadrant = f.creer_compte('ENCADRANT', 'encadrant-c1')
        cls.auditeur = f.creer_compte('AUDITEUR', 'auditeur-c1')
        # Le formateur de référence EST celui du compte encadrant : c'est ce
        # lien qui porte l'isolation de périmètre.
        cls.ctx = f.base_lmd_complete(formateur_user=cls.encadrant)
        cls.type_eval = TypeEvaluation.objects.create(
            code='EXAMEN', libelle='Examen écrit', categorie='Examen',
        )
        cls.session = SessionEvaluation.objects.create(
            annee_academique=cls.ctx['annee'], ref_formation=cls.ctx['ref_formation'],
            niveau=cls.ctx['niveau'], semestre=cls.ctx['semestre'],
            maquette=cls.ctx['maquette'], libelle='Session normale',
        )
        cls.evaluation = Evaluation.objects.create(
            session=cls.session, ecue=cls.ctx['ecue'],
            affectation_pedagogique=cls.ctx['affectation'],
            type_evaluation=cls.type_eval, libelle='Examen final S1',
        )
        cls.composant = EvaluationComponent.objects.create(
            evaluation=cls.evaluation, code='EXAMEN', libelle='Examen final',
            poids=Decimal('100.00'), bareme=Decimal('20.00'),
        )
        cls.participant = EvaluationParticipant.objects.create(
            evaluation=cls.evaluation,
            inscription_pedagogique=cls.ctx['inscription_pedagogique'],
        )

    def api(self, user):   # « client » est un attribut de TestCase : on ne l'ecrase pas
        client = APIClient()
        client.force_authenticate(user=user)
        return client

    def _session_payload(self, **kwargs):
        payload = {
            'annee_academique': self.ctx['annee'].pk,
            'ref_formation': self.ctx['ref_formation'].pk,
            'niveau': self.ctx['niveau'].pk,
            'semestre': self.ctx['semestre'].pk,
            'maquette': self.ctx['maquette'].pk,
            'libelle': 'Nouvelle session',
        }
        payload.update(kwargs)
        return payload


class TestAuthentification(ApiTestCase):
    def test_anonyme_refuse(self):
        reponse = APIClient().get(f'{BASE}/sessions/')
        self.assertIn(reponse.status_code, (401, 403))

    def test_etudiant_refuse_meme_sur_lecture(self):
        reponse = self.api(self.auditeur).get(f'{BASE}/sessions/')
        self.assertEqual(reponse.status_code, status.HTTP_403_FORBIDDEN)

    def test_erreur_porte_le_code_machine(self):
        reponse = self.api(self.auditeur).get(f'{BASE}/sessions/')
        self.assertIn('X-Error-Code', reponse.headers)
        self.assertTrue(reponse.headers['X-Error-Code'].isupper())


class TestSessionsApi(ApiTestCase):
    def test_secretaire_lit_les_sessions(self):
        reponse = self.api(self.secretariat).get(f'{BASE}/sessions/')
        self.assertEqual(reponse.status_code, status.HTTP_200_OK)
        self.assertTrue(
            any(r['id'] == self.session.pk for r in reponse.json()['results']),
        )

    def test_creation_par_la_secretariat(self):
        # Un second semestre : la session du jeu de données occupe déjà le
        # périmètre S1 (unicité structurelle vérifiée par le modèle).
        semestre2 = f.creer_semestre(self.ctx['niveau'], numero=2, libelle='S2')
        reponse = self.api(self.secretariat).post(
            f'{BASE}/sessions/create/',
            self._session_payload(libelle='Session S2', semestre=semestre2.pk),
            format='json',
        )
        self.assertEqual(reponse.status_code, status.HTTP_201_CREATED, reponse.content)
        self.assertEqual(reponse.json()['statut'], 'BROUILLON')

    def test_creation_refusee_a_l_etudiant(self):
        reponse = self.api(self.auditeur).post(
            f'{BASE}/sessions/create/', self._session_payload(), format='json',
        )
        self.assertEqual(reponse.status_code, status.HTTP_403_FORBIDDEN)

    def test_session_verrouillee_non_modifiable(self):
        self.session.verrouillee = True
        self.session.save()
        reponse = self.api(self.admin).patch(
            f'{BASE}/sessions/{self.session.pk}/', {'libelle': 'X'}, format='json',
        )
        self.assertEqual(reponse.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(reponse.json()['code'], 'SESSION_VERROUILLEE')

    def test_session_inconnue_404(self):
        reponse = self.api(self.admin).get(f'{BASE}/sessions/999999/')
        self.assertEqual(reponse.status_code, status.HTTP_404_NOT_FOUND)

    def test_pagination_presente(self):
        reponse = self.api(self.admin).get(f'{BASE}/sessions/')
        self.assertIn('count', reponse.json())
        self.assertIn('results', reponse.json())


class TestEvaluationsApi(ApiTestCase):
    def test_creation_exige_une_affectation_explicite(self):
        reponse = self.api(self.admin).post(
            f'{BASE}/evaluations/create/',
            {
                'session': self.session.pk, 'ecue': self.ctx['ecue'].pk,
                'type_evaluation': self.type_eval.pk, 'libelle': 'Sans affectation',
            },
            format='json',
        )
        self.assertEqual(reponse.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(reponse.json()['code'], 'EVALUATION_AFFECTATION_REQUISE')

    def test_creation_avec_affectation(self):
        reponse = self.api(self.admin).post(
            f'{BASE}/evaluations/create/',
            {
                'session': self.session.pk, 'ecue': self.ctx['ecue'].pk,
                'affectation_pedagogique': self.ctx['affectation'].pk,
                'type_evaluation': self.type_eval.pk, 'libelle': 'DS janvier',
            },
            format='json',
        )
        self.assertEqual(reponse.status_code, status.HTTP_201_CREATED, reponse.content)

    def test_composition_verrouillee_bloque_la_structure(self):
        self.evaluation.composition_verrouillee = True
        self.evaluation.save()
        reponse = self.api(self.admin).patch(
            f'{BASE}/evaluations/{self.evaluation.pk}/', {'poids': '50.00'},
            format='json',
        )
        self.assertEqual(reponse.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(reponse.json()['code'], 'EVALUATION_COMPOSITION_VERROUILLEE')

    def test_composants_creation_et_lecture(self):
        reponse = self.api(self.admin).post(
            f'{BASE}/evaluations/{self.evaluation.pk}/composants/',
            {'code': 'CC', 'libelle': 'Contrôle continu', 'poids': '40.00',
             'bareme': '20.00', 'ordre': 1},
            format='json',
        )
        self.assertEqual(reponse.status_code, status.HTTP_201_CREATED, reponse.content)
        reponse = self.api(self.admin).get(
            f'{BASE}/evaluations/{self.evaluation.pk}/composants/',
        )
        self.assertEqual(len(reponse.json()), 2)


class TestParticipantsApi(ApiTestCase):
    def test_lecture_expose_le_matricule_sans_denylormalisation(self):
        reponse = self.api(self.admin).get(
            f'{BASE}/evaluations/{self.evaluation.pk}/participants/',
        )
        self.assertEqual(reponse.status_code, status.HTTP_200_OK)
        donnees = reponse.json()[0]
        expected = self.ctx['etudiant'].participant.matricule
        self.assertEqual(donnees['matricule'], expected)
        self.assertIn('KOUASSI', donnees['nom_affiche'])

    def test_doublon_participant_409(self):
        reponse = self.api(self.admin).post(
            f'{BASE}/evaluations/{self.evaluation.pk}/participants/',
            {'inscription_pedagogique': self.ctx['inscription_pedagogique'].pk},
            format='json',
        )
        self.assertEqual(reponse.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(reponse.json()['code'], 'PARTICIPANT_DOUBLON')


class TestSaisieNotes(ApiTestCase):
    def _saisir(self, valeur):
        return self.api(self.admin).put(
            f'{BASE}/composants/{self.composant.pk}/notes/',
            [{'evaluation_participant_id': self.participant.pk, 'valeur': valeur}],
            format='json',
        )

    def test_saisie_cree_note_et_historique(self):
        reponse = self._saisir('14.50')
        self.assertEqual(reponse.status_code, status.HTTP_200_OK, reponse.content)
        note = EvaluationGrade.objects.get(component=self.composant)
        self.assertEqual(note.valeur, Decimal('14.50'))
        self.assertEqual(EvaluationGradeHistory.objects.count(), 1)
        self.assertEqual(
            EvaluationGradeHistory.objects.get().action,
            EvaluationGradeHistory.Action.SAISIE,
        )

    def test_note_hors_bareme_refusee(self):
        reponse = self._saisir('25')
        self.assertEqual(reponse.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('NOTE_HORS_BAREME', [e['code'] for e in reponse.json()['erreurs']])

    def test_note_negative_refusee(self):
        reponse = self._saisir('-3')
        self.assertEqual(reponse.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('NOTE_NEGATIVE', [e['code'] for e in reponse.json()['erreurs']])

    def test_modification_tracee_dans_l_historique(self):
        self._saisir('12.00')
        self._saisir('13.00')
        self.assertEqual(EvaluationGradeHistory.objects.count(), 2)
        derniere = EvaluationGradeHistory.objects.first()
        self.assertEqual(derniere.ancienne_valeur, Decimal('12.00'))
        self.assertEqual(derniere.nouvelle_valeur, Decimal('13.00'))

    def test_note_verrouillee_non_ecrasable(self):
        EvaluationGrade.objects.create(
            evaluation_participant=self.participant, component=self.composant,
            valeur=Decimal('11.00'), bareme=self.composant.bareme,
            statut='VALIDEE', verrouillee=True,
        )
        reponse = self._saisir('05.00')
        self.assertEqual(reponse.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('NOTE_VERROUILLEE', [e['code'] for e in reponse.json()['erreurs']])

    def test_historique_lisible_et_paginé(self):
        reponse = self.api(self.admin).get(f'{BASE}/notes/historique/')
        self.assertEqual(reponse.status_code, status.HTTP_200_OK)
        self.assertIn('results', reponse.json())


class TestAbsenceInvariant(ApiTestCase):
    """ABSENT ≠ 0 : aucun code de C1 ne transforme une absence en note."""

    def test_note_non_saisie_n_est_pas_un_zero(self):
        note = EvaluationGrade.objects.create(
            evaluation_participant=self.participant, component=self.composant,
            valeur=None, bareme=self.composant.bareme,
        )
        self.assertIsNone(note.valeur)
        self.assertEqual(note.statut, 'BROUILLON')

    def test_zero_est_une_valeur_et_ne_cree_aucune_presence(self):
        EvaluationGrade.objects.create(
            evaluation_participant=self.participant, component=self.composant,
            valeur=Decimal('0.00'), bareme=self.composant.bareme,
        )
        self.assertEqual(
            EvaluationAttendance.objects.filter(
                evaluation_participant=self.participant,
            ).count(),
            0,
        )


class TestReferentielsSansSeed(ApiTestCase):
    def test_aucun_type_par_defaut(self):
        """Les types d'évaluation sont saisis, jamais inventés (DECISION-5)."""
        reponse = self.api(self.admin).get(f'{BASE}/types-evaluation/')
        self.assertEqual(reponse.status_code, status.HTTP_200_OK)
        codes = [t['code'] for t in reponse.json()]
        self.assertNotIn('CC', codes)
        self.assertNotIn('EXAMEN_FINAL', codes)

    def test_aucune_regle_par_defaut(self):
        self.assertEqual(self.api(self.admin).get(f'{BASE}/regles/').json(), [])
        self.assertEqual(
            self.api(self.admin).get(f'{BASE}/regles/versions/').json(), [],
        )

    def test_resultats_vides_et_en_lecture_seule(self):
        for chemin in ('resultats/ecue/', 'resultats/ue/', 'resultats/semestre/'):
            reponse = self.api(self.admin).get(f'{BASE}/{chemin}')
            self.assertEqual(reponse.status_code, status.HTTP_200_OK, chemin)
            self.assertEqual(reponse.json()['count'], 0)

    def test_resultats_non_vides_serialises_correctement(self):
        """Régression : une liste vide n'exerce jamais la sérialisation.

        Les champs d'un serializer ne sont construits qu'au premier élément
        sérialisé : un jeu de résultats vide ne prouve donc rien. Ce test
        verrouille la lecture d'un résultat réel (types Decimal inclus).
        """
        from decimal import Decimal

        from evaluations.models import ECUEResult

        ECUEResult.objects.create(
            inscription_pedagogique=self.ctx['inscription_pedagogique'],
            session=self.session, ecue=self.ctx['ecue'],
            moyenne=Decimal('12.50'), statut='BROUILLON',
        )
        reponse = self.api(self.admin).get(f'{BASE}/resultats/ecue/')
        self.assertEqual(reponse.status_code, status.HTTP_200_OK, reponse.content)
        resultats = reponse.json()['results']
        self.assertEqual(len(resultats), 1)
        self.assertEqual(resultats[0]['moyenne'], 12.5)
        self.assertIsInstance(resultats[0]['moyenne'], float)