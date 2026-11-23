"""Journal de scolarité — endpoints événements/traçabilité et reconstitution.

L'ancien écran « Journal de scolarité » listait les étudiants : ces tests
couvrent les vraies sources (événements de parcours et audit LMD), leur
pagination, leurs filtres, le panorama, et la commande qui déduit les
événements manquants des inscriptions validées (idempotente, étiquetée).
"""
from django.core.management import call_command
from django.test import TestCase
from rest_framework.test import APIClient

from authentication.models import User
from formations.models import Participant, RefFormation
from scolarite.models import (
    AnneeAcademique, DossierEtudiant, EvenementScolarite,
    InscriptionAdministrative, JournalScolarite, Niveau, journaliser,
)

IA = InscriptionAdministrative
EV = EvenementScolarite


class JournalBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.annee = AnneeAcademique.objects.create(
            libelle='2026-2027', date_debut='2026-10-01', date_fin='2027-07-31',
            courante=True,
        )
        cls.formation = RefFormation.objects.create(intitule='LICENCE STAPS')
        cls.niveau = Niveau.objects.create(code='L2', libelle='Licence 2', ordre=2)
        cls.user = User.objects.create_user(
            username='sec_journal', password='pass', role='SECRETARIAT',
        )
        participant = Participant.objects.create(
            matricule='INJS25-0500', nom='TEMOIN', prenom='Awa',
        )
        cls.dossier = DossierEtudiant.objects.create(participant=participant)
        cls.inscription = IA.objects.create(
            etudiant=cls.dossier, annee_academique=cls.annee,
            ref_formation=cls.formation, niveau=cls.niveau,
            type_inscription=IA.Type.REINSCRIPTION, statut=IA.Statut.VALIDEE,
            date_inscription='2026-09-25',
        )
        cls.evenement = EV.objects.create(
            etudiant=cls.dossier, inscription=cls.inscription,
            type_evenement=EV.Type.SUSPENSION, date_evenement='2026-11-02',
            ancienne_valeur='Inscrit', nouvelle_valeur='Suspendu',
            commentaire='Décision du conseil de discipline.',
            enregistre_par=cls.user,
        )

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.user)


class JournalEvenementsTests(JournalBase):
    def test_liste_paginee_avec_contexte_etudiant(self):
        res = self.client.get('/api/scolarite/journal/evenements/')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data['count'], 1)
        ligne = res.data['results'][0]
        self.assertEqual(ligne['etudiant'], 'TEMOIN Awa')
        self.assertEqual(ligne['matricule'], 'INJS25-0500')
        self.assertEqual(ligne['type_libelle'], 'Suspension')
        self.assertEqual(ligne['formation'], 'LICENCE STAPS')
        self.assertEqual(ligne['niveau'], 'L2')
        self.assertEqual(ligne['enregistre_par'], 'sec_journal')
        self.assertFalse(ligne['reconstitue'])

    def test_filtre_par_type_et_type_inconnu_refuse(self):
        res = self.client.get(
            '/api/scolarite/journal/evenements/', {'type_evenement': 'PASSAGE'},
        )
        self.assertEqual(res.data['count'], 0)
        res = self.client.get(
            '/api/scolarite/journal/evenements/', {'type_evenement': 'TRUC'},
        )
        self.assertEqual(res.status_code, 400)

    def test_recherche_par_nom_et_pagination_invalide(self):
        res = self.client.get('/api/scolarite/journal/evenements/', {'q': 'temoin'})
        self.assertEqual(res.data['count'], 1)
        res = self.client.get('/api/scolarite/journal/evenements/', {'page': 'x'})
        self.assertEqual(res.status_code, 400)


class JournalStatsAuditTests(JournalBase):
    def test_panorama_par_type_et_dossiers(self):
        res = self.client.get('/api/scolarite/journal/stats/')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data['total'], 1)
        self.assertEqual(res.data['dossiers_concernes'], 1)
        self.assertEqual(res.data['par_type']['SUSPENSION'], 1)
        self.assertEqual(res.data['par_type']['PASSAGE'], 0)
        self.assertEqual(res.data['par_mois'], [{'mois': '2026-11', 'total': 1}])

    def test_audit_lisible_et_filtrable(self):
        journaliser(
            JournalScolarite.Action.INSCRIPTION_CREEE,
            objet=self.inscription, acteur=self.user,
            commentaire='Créée pour le test.',
        )
        res = self.client.get('/api/scolarite/journal/audit/')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data['count'], 1)
        ligne = res.data['results'][0]
        self.assertEqual(ligne['action_libelle'], 'Inscription administrative créée')
        self.assertEqual(ligne['objet_type'], 'InscriptionAdministrative')
        self.assertIn('T', ligne['timestamp'])
        res = self.client.get(
            '/api/scolarite/journal/audit/', {'action': 'JURY_DECISION'},
        )
        self.assertEqual(res.data['count'], 0)
        res = self.client.get('/api/scolarite/journal/audit/', {'action': 'XXX'})
        self.assertEqual(res.status_code, 400)


class ReconstitutionJournalTests(JournalBase):
    def test_deduit_le_passage_depuis_inscription_validee(self):
        call_command('reconstruire_journal_parcours')
        passage = EV.objects.get(type_evenement=EV.Type.PASSAGE)
        self.assertEqual(passage.inscription_id, self.inscription.pk)
        self.assertEqual(str(passage.date_evenement), '2026-09-25')
        self.assertEqual(passage.nouvelle_valeur, 'L2')
        self.assertEqual(passage.ancienne_valeur, '')
        self.assertIsNone(passage.enregistre_par)
        self.assertTrue(passage.commentaire.startswith('[Reconstitué]'))
        # Aucune entrée d'audit fabriquée par la reconstitution.
        self.assertEqual(JournalScolarite.objects.count(), 0)

    def test_idempotente_et_premieres_inscriptions_ignorees(self):
        participant = Participant.objects.create(
            matricule='INJS26-0001', nom='NEO', prenom='Test',
        )
        dossier = DossierEtudiant.objects.create(participant=participant)
        IA.objects.create(
            etudiant=dossier, annee_academique=self.annee,
            ref_formation=self.formation, niveau=self.niveau,
            type_inscription=IA.Type.PREMIERE, statut=IA.Statut.VALIDEE,
        )
        call_command('reconstruire_journal_parcours')
        total = EV.objects.count()
        call_command('reconstruire_journal_parcours')
        self.assertEqual(EV.objects.count(), total)
        self.assertFalse(EV.objects.filter(etudiant=dossier).exists())

    def test_dry_run_ne_cree_rien(self):
        avant = EV.objects.count()
        call_command('reconstruire_journal_parcours', '--dry-run')
        self.assertEqual(EV.objects.count(), avant)

    def test_evenement_manuel_existant_non_doublonne(self):
        # Un événement PASSAGE déjà rattaché à la même inscription fait foi.
        EV.objects.create(
            etudiant=self.dossier, inscription=self.inscription,
            type_evenement=EV.Type.PASSAGE, date_evenement='2026-09-25',
        )
        call_command('reconstruire_journal_parcours')
        self.assertEqual(
            EV.objects.filter(type_evenement=EV.Type.PASSAGE).count(), 1,
        )
