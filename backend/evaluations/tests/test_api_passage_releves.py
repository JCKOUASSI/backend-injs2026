"""API Passage de niveau & Relevés de notes — non-régression HTTP.

Vérifie le contrat exposed : RBAC, paramètres, statuts, et surtout que le
moteur de passage ne produit **jamais** de décision de jury (D10) et qu'un
relevé EXCLUSION reproduit la décision telle quelle.
"""
import tempfile

from django.test import override_settings
from rest_framework.test import APITestCase

BASE = '/api/evaluations-academiques'
MEDIA = tempfile.mkdtemp(prefix='l_releves_')


@override_settings(MEDIA_ROOT=MEDIA)
class ApiPassageEtRelevesTests(APITestCase):
    def _jeu(self):
        from datetime import date

        from django.contrib.auth import get_user_model

        from evaluations.models import SessionEvaluation
        from formations.models import Participant, RefFormation
        from scolarite.models import (
            AnneeAcademique, DossierEtudiant, InscriptionAdministrative,
            Maquette, Niveau, Semestre,
        )

        User = get_user_model()
        gestionnaire = User.objects.create_user(
            username='gestion_releve', password='x', role='SECRETARIAT',
        )
        lecteur = User.objects.create_user(
            username='lecteur_releve', password='x', role='FINANCE',
        )
        etudiant = User.objects.create_user(
            username='etudiant_releve', password='x', role='AUDITEUR',
        )
        annee = AnneeAcademique.objects.create(
            libelle='2025-2026', date_debut=date(2025, 9, 1),
            date_fin=date(2026, 7, 31),
        )
        niveau = Niveau.objects.create(
            code='L1', libelle='Licence 1', ordre=1, credits_requis=60,
        )
        s1 = Semestre.objects.create(niveau=niveau, numero=1, libelle='S1')
        ref_formation = RefFormation.objects.create(intitule='Formation 1')
        maquette = Maquette.objects.create(
            annee_academique=annee, ref_formation=ref_formation,
            niveau=niveau, version=1,
        )
        participant = Participant.objects.create(
            matricule='API-RELEVE-1', nom='Nom', prenom='Prenom',
        )
        dossier = DossierEtudiant.objects.create(participant=participant)
        inscription = InscriptionAdministrative.objects.create(
            etudiant=dossier, annee_academique=annee,
            ref_formation=ref_formation, niveau=niveau, statut='BROUILLON',
        )
        session = SessionEvaluation.objects.create(
            annee_academique=annee, ref_formation=ref_formation,
            niveau=niveau, maquette=maquette, libelle='Session API',
            type_session='NORMALE', statut='CLOTUREE',
        )
        # Le périmètre du projet expose une session via ses évaluations
        # rattachées à une affectation : on crée donc ce maillon.
        from evaluations.models import Evaluation, TypeEvaluation
        from formations.models import Formateur
        from scolarite.models import AffectationPedagogique, ECUE, UE

        enseignant = Formateur.objects.create(
            numerobadge='ENS-API-1', nom='Enseignant', prenom='API',
        )
        ue = UE.objects.create(
            maquette=maquette, semestre=s1, code='UE-API', intitule='UE API',
            credits=30,
        )
        ecue = ECUE.objects.create(
            ue=ue, code='ECUE-API', intitule='ECUE API', credits=30,
        )
        affectation = AffectationPedagogique.objects.create(
            annee_academique=annee, ref_formation=ref_formation,
            niveau=niveau, semestre=s1, enseignant=enseignant, ue=ue, ecue=ecue,
        )
        type_eval = TypeEvaluation.objects.create(
            code='EXAM', libelle='Examen', categorie='ECRIT',
        )
        Evaluation.objects.create(
            session=session, affectation_pedagogique=affectation, ecue=ecue,
            type_evaluation=type_eval, libelle='Evaluation API',
            statut='PUBLIEE',
        )
        return {
            'gestionnaire': gestionnaire, 'lecteur': lecteur,
            'etudiant': etudiant, 'inscription': inscription,
            'session': session, 'niveau': niveau, 's1': s1,
            'maquette': maquette, 'participant': participant,
        }

    def _resultats(self, j, statut='VALIDE', credits=30):
        from evaluations.models import SemesterResult

        SemesterResult.objects.create(
            inscription=j['inscription'], session=j['session'],
            semestre=j['s1'], credits_attendus=30, credits_acquis=credits,
            statut_semestre=statut,
        )

    def _decision(self, j, valeur):
        from jurys.models import DecisionJury, SessionJury

        session_jury = SessionJury.objects.create(
            annee_academique=j['session'].annee_academique,
            libelle='Jury API', type_session='NORMALE', statut='CLOTUREE',
            maquette=j['maquette'], niveau=j['niveau'],
            ref_formation=j['maquette'].ref_formation,
        )
        DecisionJury.objects.create(
            session=session_jury, inscription=j['inscription'],
            participant=j['participant'], decision=valeur, credits_acquis=0,
        )

    # ── Passage de niveau ──────────────────────────────────────────────

    def test_01_passage_parametres_manquants(self):
        self.client.force_authenticate(self._jeu()['gestionnaire'])
        reponse = self.client.get(f'{BASE}/resultats/passage/')
        self.assertEqual(reponse.status_code, 400)
        self.assertEqual(reponse.json()['code'], 'PARAMETRES_MANQUANTS')

    def test_02_passage_inscription_inexistante(self):
        j = self._jeu()
        self.client.force_authenticate(j['gestionnaire'])
        reponse = self.client.get(f'{BASE}/resultats/passage/', {
            'inscription_id': 999999, 'session_id': j['session'].pk,
        })
        self.assertEqual(reponse.status_code, 404)
        self.assertEqual(reponse.json()['code'], 'INSCRIPTION_INTROUVABLE')

    def test_03_passage_utilisateur_non_autorise(self):
        j = self._jeu()
        self._resultats(j)
        self.client.force_authenticate(j['etudiant'])
        reponse = self.client.get(f'{BASE}/resultats/passage/', {
            'inscription_id': j['inscription'].pk, 'session_id': j['session'].pk,
        })
        # L'étudiant est exclu du socle d'évaluation (§ permissions).
        self.assertEqual(reponse.status_code, 403)

    def test_04_passage_calcul_valide_sans_donnee(self):
        j = self._jeu()
        self.client.force_authenticate(j['gestionnaire'])
        reponse = self.client.get(f'{BASE}/resultats/passage/', {
            'inscription_id': j['inscription'].pk, 'session_id': j['session'].pk,
            'niveau_id': j['niveau'].pk,
        })
        self.assertEqual(reponse.status_code, 200)
        donnees = reponse.json()
        # Aucune donnée → indéterminable, jamais 0 ECTS ni validation.
        self.assertEqual(donnees['eligibilite'], 'INDETERMINABLE')
        self.assertIsNone(donnees['credits_acquis'])

    def test_05_passage_60_ects_eligible(self):
        j = self._jeu()
        self._resultats(j, 'VALIDE', 60)
        self.client.force_authenticate(j['gestionnaire'])
        reponse = self.client.get(f'{BASE}/resultats/passage/', {
            'inscription_id': j['inscription'].pk, 'session_id': j['session'].pk,
            'niveau_id': j['niveau'].pk,
        })
        donnees = reponse.json()
        self.assertEqual(donnees['eligibilite'], 'ELIGIBLE')
        self.assertEqual(donnees['credits_acquis'], 60)
        self.assertEqual(donnees['credits_requis'], 60)

    def test_06_passage_exclusion_bloque(self):
        j = self._jeu()
        self._resultats(j, 'VALIDE', 60)
        self._decision(j, 'EXCLUSION')
        self.client.force_authenticate(j['gestionnaire'])
        reponse = self.client.get(f'{BASE}/resultats/passage/', {
            'inscription_id': j['inscription'].pk, 'session_id': j['session'].pk,
            'niveau_id': j['niveau'].pk,
        })
        donnees = reponse.json()
        self.assertEqual(donnees['eligibilite'], 'BLOQUE')
        self.assertEqual(donnees['decision_jury']['valeur'], 'EXCLUSION')

    def test_07_passage_ne_produit_pas_de_decision(self):
        j = self._jeu()
        self._resultats(j, 'VALIDE', 60)
        self.client.force_authenticate(j['gestionnaire'])
        reponse = self.client.get(f'{BASE}/resultats/passage/', {
            'inscription_id': j['inscription'].pk, 'session_id': j['session'].pk,
            'niveau_id': j['niveau'].pk,
        })
        # D10 : le moteur ne fabrique aucune décision de jury.
        self.assertIsNone(reponse.json()['decision_jury'])

    # ── Relevés de notes ───────────────────────────────────────────────

    def test_08_releve_generation_initiale_version_1(self):
        j = self._jeu()
        self.client.force_authenticate(j['gestionnaire'])
        reponse = self.client.post(f'{BASE}/releves/generer/', {
            'inscription_id': j['inscription'].pk, 'session_id': j['session'].pk,
        }, format='json')
        self.assertEqual(reponse.status_code, 201)
        donnees = reponse.json()
        self.assertEqual(donnees['version'], 1)
        self.assertEqual(len(donnees['sha256']), 64)
        self.assertEqual(donnees['participant_matricule'], 'API-RELEVE-1')
        self.assertIsNotNone(donnees['contenu'])

    def test_09_releve_version_suivante_max_plus_1(self):
        j = self._jeu()
        self.client.force_authenticate(j['gestionnaire'])
        corps = {'inscription_id': j['inscription'].pk,
                 'session_id': j['session'].pk}
        self.assertEqual(
            self.client.post(f'{BASE}/releves/generer/', corps,
                             format='json').json()['version'], 1)
        self.assertEqual(
            self.client.post(f'{BASE}/releves/generer/', corps,
                             format='json').json()['version'], 2)
        self.assertEqual(
            self.client.post(f'{BASE}/releves/generer/', corps,
                             format='json').json()['version'], 3)

    def test_10_releve_contenu_expose_ue_et_semestre(self):
        j = self._jeu()
        self._resultats(j, 'VALIDE', 60)
        self.client.force_authenticate(j['gestionnaire'])
        donnees = self.client.post(f'{BASE}/releves/generer/', {
            'inscription_id': j['inscription'].pk, 'session_id': j['session'].pk,
        }, format='json').json()
        contenu = donnees['contenu']
        self.assertEqual(contenu['inscription'], j['inscription'].pk)
        self.assertEqual(contenu['niveau'], 'L1')
        self.assertEqual(len(contenu['semestres']), 1)
        self.assertEqual(contenu['semestres'][0]['semestre'], 'S1')

    def test_11_releve_exclusion_reproduite_telle_quelle(self):
        j = self._jeu()
        self._decision(j, 'EXCLUSION')
        self.client.force_authenticate(j['gestionnaire'])
        donnees = self.client.post(f'{BASE}/releves/generer/', {
            'inscription_id': j['inscription'].pk, 'session_id': j['session'].pk,
        }, format='json').json()
        # EXCLUSION n'est jamais réduite à un statut technique.
        self.assertEqual(donnees['decision_valeur'], 'EXCLUSION')
        self.assertEqual(donnees['contenu']['decision']['valeur'], 'EXCLUSION')

    def test_12_releve_parametres_manquants(self):
        self.client.force_authenticate(self._jeu()['gestionnaire'])
        reponse = self.client.post(f'{BASE}/releves/generer/', {}, format='json')
        self.assertEqual(reponse.status_code, 400)
        self.assertEqual(reponse.json()['code'], 'PARAMETRES_MANQUANTS')

    def test_13_releve_inscription_inexistante(self):
        j = self._jeu()
        self.client.force_authenticate(j['gestionnaire'])
        reponse = self.client.post(f'{BASE}/releves/generer/', {
            'inscription_id': 999999, 'session_id': j['session'].pk,
        }, format='json')
        self.assertEqual(reponse.status_code, 404)

    def test_14_generation_reservee_a_la_gestion(self):
        j = self._jeu()
        self.client.force_authenticate(j['lecteur'])
        reponse = self.client.post(f'{BASE}/releves/generer/', {
            'inscription_id': j['inscription'].pk, 'session_id': j['session'].pk,
        }, format='json')
        # FINANCE est en consultation seule : génération refusée.
        self.assertEqual(reponse.status_code, 403)

    def test_15_consultation_ouverte_aux_roles_de_lecture(self):
        j = self._jeu()
        self.client.force_authenticate(j['gestionnaire'])
        self.client.post(f'{BASE}/releves/generer/', {
            'inscription_id': j['inscription'].pk, 'session_id': j['session'].pk,
        }, format='json')
        # Un rôle de gestion voit le relevé produit.
        liste = self.client.get(f'{BASE}/releves/')
        self.assertEqual(liste.status_code, 200)
        self.assertEqual(liste.json()['count'], 1)
        # Un rôle de consultation seule passe la permission d'API mais son
        # périmètre d'affectations est vide (convention `perimetre_
        # affectations`) : aucune fuite, réponse paginée vide.
        self.client.force_authenticate(j['lecteur'])
        lecteur = self.client.get(f'{BASE}/releves/')
        self.assertEqual(lecteur.status_code, 200)
        self.assertEqual(lecteur.json()['count'], 0)

    def test_16_detail_releve_et_404(self):
        j = self._jeu()
        self.client.force_authenticate(j['gestionnaire'])
        cree = self.client.post(f'{BASE}/releves/generer/', {
            'inscription_id': j['inscription'].pk, 'session_id': j['session'].pk,
        }, format='json').json()
        detail = self.client.get(f'{BASE}/releves/{cree["id"]}/')
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()['version'], 1)
        absent = self.client.get(f'{BASE}/releves/999999/')
        self.assertEqual(absent.status_code, 404)