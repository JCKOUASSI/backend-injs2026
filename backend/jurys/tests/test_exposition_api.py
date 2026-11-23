"""Tests de l'EXPOSITION API « Délibérations » (lot jurys).

Ce lot n'implémente aucun métier : il vérifie que l'API existante est bien
exploitable par le frontend — pagination, filtres, anomalies, statistiques —
et que les garde-fous du workflow restent intacts.

Invariants vérifiés ici :
- la liste est paginée avec le format global du projet ;
- les filtres ne fuient pas les sessions d'une autre population ;
- les anomalies proviennent de contrôles RÉELS (pas d'anomalie inventée) ;
- les statistiques sont des agrégats des modèles, jamais des valeurs figées ;
- aucune permission n'est relâchée, aucun accès anonyme.
"""
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from formations.models import (
    Formation,
    Module,
    ModuleParticipant,
    NoteModule,
    NoteModuleColonne,
    Participant,
    RefFormation,
    RefModule,
)
from scolarite.models import (
    AnneeAcademique,
    DossierEtudiant,
    ECUE,
    InscriptionAdministrative,
    InscriptionPedagogique,
    Maquette,
    Niveau,
    Semestre,
    UE,
)

from jurys.models import DecisionJury, PropositionJury, SessionJury
from jurys.services import _derniere_propositions

User = get_user_model()


def make_user(username, role):
    return User.objects.create_user(username=username, password='pass', role=role)


class ExpositionApiBase(TestCase):
    """Socle : deux années, deux formations, deux niveaux, une session."""

    def setUp(self):
        self.dfrc = make_user('dfrc_expo', User.Role.INJS_ADMIN)
        self.secretariat = make_user('sec_expo', User.Role.SECRETARIAT)
        self.auditeur = make_user('aud_expo', User.Role.AUDITEUR)
        self.client = APIClient()

        self.annee = AnneeAcademique.objects.create(
            libelle='2026-2027', date_debut=date(2026, 10, 1), date_fin=date(2027, 9, 30),
        )
        self.annee_bis = AnneeAcademique.objects.create(
            libelle='2025-2026', date_debut=date(2025, 10, 1), date_fin=date(2026, 9, 30),
        )
        self.ref_formation = RefFormation.objects.create(intitule='Licence Exposé A')
        self.ref_formation_bis = RefFormation.objects.create(intitule='Licence Exposé B')
        self.niveau = Niveau.objects.create(code='LEX', libelle='Licence Ex', credits_requis=20)
        self.niveau_bis = Niveau.objects.create(code='LYX', libelle='Licence Y', credits_requis=20)
        self.maquette = Maquette.objects.create(
            annee_academique=self.annee, ref_formation=self.ref_formation,
            niveau=self.niveau, statut=Maquette.Statut.BROUILLON,
        )
        self.semestre = Semestre.objects.create(niveau=self.niveau, numero=1, libelle='S1')
        self.ue = UE.objects.create(
            maquette=self.maquette, semestre=self.semestre, code='UEX', credits=20,
        )
        self.ref_a = RefModule.objects.create(intitule='Module A')
        self.ecue_a = ECUE.objects.create(
            ue=self.ue, code='ECUE-A', intitule='ECUE A', credits=20, ref_module=self.ref_a,
        )
        # La maquette devient ACTIVE après coup : une maquette active est
        # immuable (guard `scolarite.models.UE.save`).
        self.maquette.statut = Maquette.Statut.ACTIVE
        self.maquette.save()
        self.formation_op = Formation.objects.create(formation='Licence Exposé op')

        self.client.force_authenticate(self.dfrc)

    def _inscrire(self, matricule, formation=None, niveau=None, annee=None):
        """Inscription administrative VALIDEE (source de `inscriptions_concernees`)."""
        formation = formation or self.ref_formation
        niveau = niveau or self.niveau
        annee = annee or self.annee
        participant = Participant.objects.create(
            nom='Etu', prenom=matricule, matricule=matricule,
        )
        dossier = DossierEtudiant.objects.create(participant=participant)
        return InscriptionAdministrative.objects.create(
            etudiant=dossier, annee_academique=annee, ref_formation=formation,
            niveau=niveau, statut=InscriptionAdministrative.Statut.VALIDEE,
        )

    def _noter(self, inscription, valeur=12):
        """Note VALIDEE et verrouillée : le moteur ECTS l'exige."""
        # Un module par inscription : `Module` impose (formation, intitule)
        # unique, on évite donc les collisions sur une population de test.
        module = Module.objects.create(
            formation=self.formation_op,
            intitule=f'Module {inscription.etudiant.participant.matricule}',
            ref_module=self.ref_a,
        )
        mp = ModuleParticipant.objects.create(
            module=module, participant=inscription.etudiant.participant,
        )
        InscriptionPedagogique.objects.create(
            inscription=inscription, ecue=self.ecue_a, semestre=self.semestre,
            module_participant=mp, statut=InscriptionPedagogique.Statut.VALIDEE,
        )
        colonne = NoteModuleColonne.objects.create(module=module, libelle='N', note_max=20)
        return NoteModule.objects.create(
            colonne=colonne, participant=inscription.etudiant.participant,
            note=valeur, verrouillee=True, statut_validation='VALIDEE',
        )

    def _creer_session(self, libelle='Jury exposé', **kwargs):
        defauts = {
            'annee_academique': self.annee.pk,
            'ref_formation': self.ref_formation.pk,
            'niveau': self.niveau.pk,
            'maquette': self.maquette.pk,
            'type_session': 'NORMALE',
            'libelle': libelle,
        }
        defauts.update(kwargs)
        reponse = self.client.post('/api/jurys/sessions/', defauts, format='json')
        self.assertEqual(reponse.status_code, status.HTTP_201_CREATED, reponse.data)
        return reponse.data

    def _calculer(self, session_pk):
        reponse = self.client.post(
            f'/api/jurys/sessions/{session_pk}/action/',
            {'action': 'calcul'}, format='json',
        )
        self.assertEqual(reponse.status_code, status.HTTP_200_OK, reponse.data)
        return reponse.data

    def _deliberer(self, session_pk):
        """Calcul puis transitions jusqu'à DELIBERATION (état requis pour
        saisir une décision)."""
        self._calculer(session_pk)
        for _ in range(3):
            self.client.post(
                f'/api/jurys/sessions/{session_pk}/action/',
                {'action': 'transition'}, format='json',
            )
        from jurys.models import SessionJury
        self.assertEqual(
            SessionJury.objects.get(pk=session_pk).statut,
            SessionJury.Statut.DELIBERATION,
        )


class JuryListePaginationTests(ExpositionApiBase):
    """La liste renvoie désormais une page DRF, pas une liste brute."""

    def test_liste_vide_reste_paginee(self):
        reponse = self.client.get('/api/jurys/sessions/')
        self.assertEqual(reponse.status_code, status.HTTP_200_OK)
        self.assertIn('results', reponse.data)
        self.assertIn('count', reponse.data)
        self.assertEqual(reponse.data['count'], 0)
        self.assertEqual(reponse.data['results'], [])

    def test_liste_sous_page_size(self):
        self._creer_session('Jury 1')
        reponse = self.client.get('/api/jurys/sessions/')
        self.assertEqual(reponse.data['count'], 1)
        self.assertEqual(len(reponse.data['results']), 1)

    def test_liste_au_dela_de_la_page_size(self):
        # PAGE_SIZE global = 50 : 51 sessions doivent déborder sur une page 2.
        for index in range(51):
            SessionJury.objects.create(
                annee_academique=self.annee, ref_formation=self.ref_formation,
                niveau=self.niveau, maquette=self.maquette,
                libelle=f'Jury {index:02d}',
            )
        premiere = self.client.get('/api/jurys/sessions/')
        self.assertEqual(premiere.data['count'], 51)
        self.assertEqual(len(premiere.data['results']), 50)
        self.assertIsNotNone(premiere.data['next'])

        seconde = self.client.get('/api/jurys/sessions/?page=2')
        self.assertEqual(len(seconde.data['results']), 1)
        self.assertIsNone(seconde.data['next'])

    def test_page_invalide(self):
        self._creer_session('Jury 1')
        reponse = self.client.get('/api/jurys/sessions/?page=999')
        self.assertEqual(reponse.status_code, status.HTTP_404_NOT_FOUND)

    def test_alias_juries_et_jurys_exposent_la_meme_implementation(self):
        self._creer_session('Jury commun')
        par_jurys = self.client.get('/api/jurys/sessions/')
        par_juries = self.client.get('/api/juries/sessions/')
        self.assertEqual(par_jurys.status_code, status.HTTP_200_OK)
        self.assertEqual(par_juries.status_code, status.HTTP_200_OK)
        self.assertEqual(par_jurys.data['count'], par_juries.data['count'])


class JuryFiltresTests(ExpositionApiBase):
    """Filtres réels, sans fuite entre populations."""

    def setUp(self):
        super().setUp()
        self.session_a = self._creer_session('Jury Alpha')
        maquette_bis = Maquette.objects.create(
            annee_academique=self.annee_bis, ref_formation=self.ref_formation_bis,
            niveau=self.niveau_bis, statut=Maquette.Statut.ACTIVE,
        )
        self.session_b = self._creer_session(
            'Jury Beta',
            annee_academique=self.annee_bis.pk,
            ref_formation=self.ref_formation_bis.pk,
            niveau=self.niveau_bis.pk,
            maquette=maquette_bis.pk,
        )

    def _ids(self, **params):
        reponse = self.client.get('/api/jurys/sessions/', params)
        self.assertEqual(reponse.status_code, status.HTTP_200_OK, reponse.data)
        return sorted(row['id'] for row in reponse.data['results'])

    def test_filtre_par_libelle(self):
        self.assertEqual(self._ids(q='Alpha'), [self.session_a['id']])
        self.assertEqual(self._ids(q='Beta'), [self.session_b['id']])

    def test_filtre_par_annee_academique(self):
        self.assertEqual(self._ids(annee_academique=self.annee.pk), [self.session_a['id']])

    def test_filtre_par_formation(self):
        self.assertEqual(self._ids(formation=self.ref_formation_bis.pk), [self.session_b['id']])

    def test_filtre_par_niveau(self):
        self.assertEqual(self._ids(niveau=self.niveau_bis.pk), [self.session_b['id']])

    def test_filtre_par_type_session(self):
        attendu = sorted([self.session_a['id'], self.session_b['id']])
        self.assertEqual(self._ids(type_session='NORMALE'), attendu)

    def test_filtre_par_statut_ne_fuit_pas(self):
        SessionJury.objects.filter(pk=self.session_a['id']).update(statut='PUBLIE')
        self.assertEqual(self._ids(statut='PUBLIE'), [self.session_a['id']])
        # Une session d'une autre population ne doit pas fuiter via le filtre.
        self.assertEqual(self._ids(statut='DELIBERATION'), [])

    def test_tri_par_annee_academique(self):
        self.assertEqual(
            self._ids(ordering='annee_academique__libelle'),
            [self.session_a['id'], self.session_b['id']],
        )

    def test_ordering_non_autorise_ignore(self):
        # Un champ non listé ne doit pas devenir un vecteur d'injection.
        reponse = self.client.get('/api/jurys/sessions/?ordering=creee_par__password')
        self.assertEqual(reponse.status_code, status.HTTP_200_OK)


class JuryAnomaliesTests(ExpositionApiBase):
    """Anomalies dérivées des contrôles réels du workflow."""

    def test_derniere_proposition_par_inscription(self):
        session_data = self._creer_session('Jury propositions')
        session = SessionJury.objects.get(pk=session_data['id'])
        inscription = self._inscrire('E001')
        champs = {
            'session': session,
            'inscription': inscription,
            'participant': inscription.etudiant.participant,
            'resultat': {},
            'empreinte': 'a' * 64,
        }
        ancienne = PropositionJury.objects.create(**champs)
        recente = PropositionJury.objects.create(**champs)
        PropositionJury.objects.filter(pk=ancienne.pk).update(
            calcule_le=timezone.now() - timedelta(minutes=1),
        )
        PropositionJury.objects.filter(pk=recente.pk).update(calcule_le=timezone.now())

        ids = list(_derniere_propositions(session).values_list('pk', flat=True))
        self.assertEqual(ids, [recente.pk])

    def test_session_inexistante(self):
        reponse = self.client.get('/api/jurys/sessions/999999/anomalies/')
        self.assertEqual(reponse.status_code, status.HTTP_404_NOT_FOUND)

    def test_anomalies_sans_proposition_bloquante(self):
        session = self._creer_session('Jury sans calcul')
        self._inscrire('E001')
        reponse = self.client.get(f"/api/jurys/sessions/{session['id']}/anomalies/")
        self.assertEqual(reponse.status_code, status.HTTP_200_OK, reponse.data)
        codes = [a['code'] for a in reponse.data['anomalies']]
        self.assertIn('PROPOSITIONS_ABSENTES', codes)
        self.assertIn('DECISION_ABSENTE', codes)
        self.assertFalse(reponse.data['verrouillage_possible'])
        # Contrat stable pour le frontend.
        for anomalie in reponse.data['anomalies']:
            for champ in ('code', 'gravite', 'message', 'participant_id', 'bloquante'):
                self.assertIn(champ, anomalie)

    def test_population_vide_signalee(self):
        session = self._creer_session('Jury sans étudiant')
        reponse = self.client.get(f"/api/jurys/sessions/{session['id']}/anomalies/")
        codes = [a['code'] for a in reponse.data['anomalies']]
        self.assertIn('POPULATION_VIDE', codes)

    def test_absence_de_decision_est_bloquante(self):
        session = self._creer_session('Jury calculé')
        inscription = self._inscrire('E001')
        self._noter(inscription)
        self._calculer(session['id'])
        reponse = self.client.get(f"/api/jurys/sessions/{session['id']}/anomalies/")
        codes = [a['code'] for a in reponse.data['anomalies']]
        self.assertNotIn('PROPOSITIONS_ABSENTES', codes)
        self.assertIn('DECISION_ABSENTE', codes)
        self.assertFalse(reponse.data['verrouillage_possible'])

    def test_justification_obligatoire_exposee_par_l_api(self):
        session = self._creer_session('Jury justifié')
        inscription = self._inscrire('E001')
        self._noter(inscription)
        self._deliberer(session['id'])
        self.client.force_authenticate(self.secretariat)
        reponse = self.client.post(
            f"/api/jurys/sessions/{session['id']}/decisions/",
            {'inscription_id': inscription.pk, 'decision': 'AJOURNE'},
            format='json',
        )
        # Décision divergente du calcul sans motif : refusée par le service.
        self.assertEqual(reponse.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('justification', str(reponse.data).lower())

    def test_aucune_anomalie_apres_decision_conforme(self):
        session = self._creer_session('Jury complet')
        inscription = self._inscrire('E001')
        self._noter(inscription)
        self._deliberer(session['id'])
        self.client.force_authenticate(self.secretariat)
        reponse_decision = self.client.post(
            f"/api/jurys/sessions/{session['id']}/decisions/",
            {'inscription_id': inscription.pk, 'decision': 'ADMIS'},
            format='json',
        )
        self.assertEqual(reponse_decision.status_code, status.HTTP_201_CREATED, reponse_decision.data)
        self.client.force_authenticate(self.dfrc)
        reponse = self.client.get(f"/api/jurys/sessions/{session['id']}/anomalies/")
        codes = [a['code'] for a in reponse.data['anomalies']]
        self.assertNotIn('DECISION_ABSENTE', codes)
        self.assertNotIn('PROPOSITIONS_ABSENTES', codes)


class JuryStatistiquesTests(ExpositionApiBase):
    """Agrégats calculés à la demande, jamais figés."""

    def test_session_inexistante(self):
        reponse = self.client.get('/api/jurys/sessions/999999/statistiques/')
        self.assertEqual(reponse.status_code, status.HTTP_404_NOT_FOUND)

    def test_agregats_refletent_exactement_les_modeles(self):
        session = self._creer_session('Jury stats')
        inscriptions = [self._inscrire(f'E{i:03d}') for i in range(10)]
        for inscription in inscriptions:
            self._noter(inscription)
        self._calculer(session['id'])

        # 6 ADMIS, 3 AJOURNE, 1 ADMIS_RESERVES : valeurs décimales, donc
        # réellement produites par DecisionJury, jamais codées en dur.
        decisions = (
            [DecisionJury.Decision.ADMIS] * 6
            + [DecisionJury.Decision.AJOURNE] * 3
            + [DecisionJury.Decision.ADMIS_AVEC_RESERVES]
        )
        for inscription, decision in zip(inscriptions, decisions):
            DecisionJury.objects.create(
                session_id=session['id'], inscription=inscription,
                participant=inscription.etudiant.participant, decision=decision,
            )

        reponse = self.client.get(f"/api/jurys/sessions/{session['id']}/statistiques/")
        self.assertEqual(reponse.status_code, status.HTTP_200_OK, reponse.data)
        data = reponse.data
        self.assertEqual(data['participants'], 10)
        self.assertEqual(data['decisions']['enregistrees'], 10)
        self.assertTrue(data['decisions']['completes'])
        self.assertEqual(data['decisions']['manquantes'], 0)
        # ADMIS_RESERVES est compté avec ADMIS (convention du lot).
        self.assertEqual(data['admis'], 7)
        self.assertEqual(data['ajournes'], 3)
        self.assertEqual(data['autres_decisions'], 0)
        self.assertEqual(data['repartition'][DecisionJury.Decision.ADMIS], 6)

    def test_population_partielle_comptabilisee(self):
        session = self._creer_session('Jury partiel')
        inscriptions = [self._inscrire(f'P{i:03d}') for i in range(4)]
        for inscription in inscriptions:
            self._noter(inscription)
        self._calculer(session['id'])
        DecisionJury.objects.create(
            session_id=session['id'], inscription=inscriptions[0],
            participant=inscriptions[0].etudiant.participant,
            decision=DecisionJury.Decision.ADMIS,
        )
        reponse = self.client.get(f"/api/jurys/sessions/{session['id']}/statistiques/")
        data = reponse.data
        self.assertEqual(data['participants'], 4)
        self.assertEqual(data['decisions']['enregistrees'], 1)
        self.assertFalse(data['decisions']['completes'])
        self.assertEqual(data['decisions']['manquantes'], 3)
        self.assertEqual(data['admis'], 1)


class JuryExpositionRbacTests(ExpositionApiBase):
    """Aucune permission n'est relâchée par le complément API."""

    def test_anonyme_refuse(self):
        self.client.force_authenticate(user=None)
        for url in (
            '/api/jurys/sessions/',
            '/api/jurys/sessions/1/anomalies/',
            '/api/jurys/sessions/1/statistiques/',
        ):
            reponse = self.client.get(url)
            self.assertIn(
                reponse.status_code,
                (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN), url,
            )

    def test_role_non_autorise_refuse(self):
        # La session est créée par le DFRC (autorisé), puis on vérifie qu'un
        # rôle hors périmètre ne peut ni la lire ni atteindre les actions.
        session = self._creer_session('Jury RBAC')
        self.client.force_authenticate(self.auditeur)
        for url in (
            '/api/jurys/sessions/',
            f"/api/jurys/sessions/{session['id']}/anomalies/",
            f"/api/jurys/sessions/{session['id']}/statistiques/",
        ):
            reponse = self.client.get(url)
            self.assertIn(
                reponse.status_code,
                (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN), url,
            )

    def test_secretaire_peut_consulter_en_lecture(self):
        session = self._creer_session('Jury secretariat')
        self.client.force_authenticate(self.secretariat)
        self.assertEqual(
            self.client.get('/api/jurys/sessions/').status_code, status.HTTP_200_OK,
        )
        self.assertEqual(
            self.client.get(f"/api/jurys/sessions/{session['id']}/anomalies/").status_code,
            status.HTTP_200_OK,
        )
        self.assertEqual(
            self.client.get(f"/api/jurys/sessions/{session['id']}/statistiques/").status_code,
            status.HTTP_200_OK,
        )

    def test_anomalies_et_statistiques_ne_mutent_rien(self):
        session = self._creer_session('Jury lecture seule')
        inscription = self._inscrire('E001')
        self._noter(inscription)
        avant = SessionJury.objects.get(pk=session['id']).statut
        self.client.get(f"/api/jurys/sessions/{session['id']}/anomalies/")
        self.client.get(f"/api/jurys/sessions/{session['id']}/statistiques/")
        self.assertEqual(SessionJury.objects.get(pk=session['id']).statut, avant)
