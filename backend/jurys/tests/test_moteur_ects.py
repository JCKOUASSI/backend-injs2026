"""Tests du moteur de validation ECTS (lot L3 — Prompt 13).

Calculs : moyenne ECUE (notes verrouillées uniquement), moyenne UE pondérée,
compensation semestrielle, seuil éliminatoire, arrondis, reproductibilité,
complétude. Jeu de données minimal : 1 étudiant, 2 ECUE dans 1 UE.

Utilise ``setUp`` (instance) : les objets sont recréés frais à chaque test.
``setUpTestData`` (cls) est évité car le rollback Django entre tests rend les
pk des objets partagés incohérents lors des recréations partielles d'UE.
"""
from datetime import date
from decimal import Decimal

from django.test import TestCase

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
    RegleValidationLMD,
    Semestre,
    UE,
)
from scolarite.validation_services import (
    calculer_validation_etudiant,
    regle_pour,
)


def _empreinte(resultat):
    import hashlib
    import json
    brut = json.dumps(resultat, sort_keys=True, default=str).encode()
    return hashlib.sha256(brut).hexdigest()


class MoteurBase(TestCase):
    """Jeu de données : maquette ACTIVE, 1 UE (2 ECUE), 1 étudiant inscrit."""

    def setUp(self):
        self.ref_formation = RefFormation.objects.create(intitule='Licence Test')
        self.annee = AnneeAcademique.objects.create(
            libelle='2026-2027',
            date_debut=date(2026, 10, 1),
            date_fin=date(2027, 9, 30),
        )
        self.niveau = Niveau.objects.create(
            code='L1', libelle='Licence 1', credits_requis=20,
        )
        self.semestre = Semestre.objects.create(niveau=self.niveau, numero=1, libelle='S1')
        # BROUILLON : les UE/ECUE sont ajoutées avant passage en ACTIVE (R4).
        self.maquette = Maquette.objects.create(
            annee_academique=self.annee,
            ref_formation=self.ref_formation,
            niveau=self.niveau,
            statut=Maquette.Statut.BROUILLON,
        )
        self.ue1 = UE.objects.create(
            maquette=self.maquette, semestre=self.semestre, code='UE1', credits=20,
        )
        self.ref_a = RefModule.objects.create(intitule='Module A')
        self.ref_b = RefModule.objects.create(intitule='Module B')
        self.ecue_a = ECUE.objects.create(
            ue=self.ue1, code='ECUE-A', intitule='ECUE A', credits=10,
            ref_module=self.ref_a,
        )
        self.ecue_b = ECUE.objects.create(
            ue=self.ue1, code='ECUE-B', intitule='ECUE B', credits=10,
            ref_module=self.ref_b,
        )

        self.formation_op = Formation.objects.create(formation='Licence Test opérationnelle')
        self.participant = Participant.objects.create(
            nom='Dup', prenom='Jean', matricule='M001',
        )
        self.dossier = DossierEtudiant.objects.create(participant=self.participant)
        self.inscription = InscriptionAdministrative.objects.create(
            etudiant=self.dossier,
            annee_academique=self.annee,
            ref_formation=self.ref_formation,
            niveau=self.niveau,
            statut=InscriptionAdministrative.Statut.VALIDEE,
        )

    def _activer_maquette(self):
        """Passe la maquette en ACTIVE (immuable) — à appeler après les UE."""
        self.maquette.statut = Maquette.Statut.ACTIVE
        self.maquette.save()

    @staticmethod
    def _creer_branche_ecue(ecue, participant, inscription, semestre, formation_op):
        """Module opérationnel + inscription module + IP pour une ECUE."""
        from formations.models import Module
        module = Module.objects.create(
            formation=formation_op, intitule=ecue.code, ref_module=ecue.ref_module,
        )
        mp = ModuleParticipant.objects.create(module=module, participant=participant)
        InscriptionPedagogique.objects.create(
            inscription=inscription, ecue=ecue, semestre=semestre,
            module_participant=mp,
            statut=InscriptionPedagogique.Statut.VALIDEE,
        )
        return module

    @staticmethod
    def _noter(module, participant, valeur, verrouillee=True):
        colonne = NoteModuleColonne.objects.create(
            module=module, libelle='Note /20', note_max=20,
        )
        return NoteModule.objects.create(
            colonne=colonne, participant=participant,
            note=Decimal(str(valeur)) if valeur is not None else None,
            statut_validation='VALIDEE' if verrouillee else 'BROUILLON',
            verrouillee=verrouillee,
        )

    def _calculer(self, **kwargs):
        return calculer_validation_etudiant(
            self.inscription, self.maquette, **kwargs,
        )

    def _resultat_ue(self, resultat, index=0):
        return resultat['semestres'][0]['ues'][index]


class MoteurTests(MoteurBase):
    """Calculs du moteur : ECUE → UE → décision, complétude, verrouillage."""

    def test_ue_validee_et_decision_admis(self):
        self._activer_maquette()
        module_a = self._creer_branche_ecue(
            self.ecue_a, self.participant, self.inscription, self.semestre, self.formation_op,
        )
        module_b = self._creer_branche_ecue(
            self.ecue_b, self.participant, self.inscription, self.semestre, self.formation_op,
        )
        self._noter(module_a, self.participant, 12)
        self._noter(module_b, self.participant, 8)

        resultat = self._calculer()

        ue = self._resultat_ue(resultat)
        # Moyenne UE pondérée par coefficients (1 et 1) : (12+8)/2 = 10.00.
        self.assertEqual(ue['moyenne'], Decimal('10.00'))
        self.assertTrue(ue['acquise'])
        self.assertFalse(ue['par_compensation'])
        self.assertEqual(resultat['credits_acquis'], 20)
        self.assertEqual(resultat['decision_proposee'], 'ADMIS')
        self.assertTrue(resultat['complet'])

    def test_notes_non_verrouillees_ignorees(self):
        self._activer_maquette()
        module_a = self._creer_branche_ecue(
            self.ecue_a, self.participant, self.inscription, self.semestre, self.formation_op,
        )
        module_b = self._creer_branche_ecue(
            self.ecue_b, self.participant, self.inscription, self.semestre, self.formation_op,
        )
        self._noter(module_a, self.participant, 15, verrouillee=False)
        self._noter(module_b, self.participant, 15, verrouillee=False)

        resultat = self._calculer()

        # Aucune note verrouillée : ECUE non complètes, décision AJOURNÉ.
        self.assertFalse(resultat['complet'])
        self.assertEqual(resultat['credits_acquis'], 0)
        self.assertEqual(resultat['decision_proposee'], 'AJOURNE')
        ue = self._resultat_ue(resultat)
        self.assertFalse(ue['acquise'])
        self.assertIsNone(ue['moyenne'])

    def test_ecue_absente_incomplete_ajourne_meme_avec_credits(self):
        self._activer_maquette()
        module_a = self._creer_branche_ecue(
            self.ecue_a, self.participant, self.inscription, self.semestre, self.formation_op,
        )
        # ECUE B inscrite (IP) mais non notée → incomplet.
        self._creer_branche_ecue(
            self.ecue_b, self.participant, self.inscription, self.semestre, self.formation_op,
        )
        self._noter(module_a, self.participant, 20)

        resultat = self._calculer()

        ue = self._resultat_ue(resultat)
        self.assertTrue(ue['acquise'])  # moyenne UE = 20 (ECUE A seule notée)
        self.assertEqual(resultat['credits_acquis'], 20)
        # Complétude : la décision reste AJOURNÉ malgré les crédits suffisants.
        self.assertFalse(resultat['complet'])
        self.assertEqual(resultat['decision_proposee'], 'AJOURNE')

    def test_arrondi_deux_decimales(self):
        self._activer_maquette()
        module_a = self._creer_branche_ecue(
            self.ecue_a, self.participant, self.inscription, self.semestre, self.formation_op,
        )
        module_b = self._creer_branche_ecue(
            self.ecue_b, self.participant, self.inscription, self.semestre, self.formation_op,
        )
        self._noter(module_a, self.participant, 13.456)
        self._noter(module_b, self.participant, 13)

        resultat = self._calculer()

        ue = self._resultat_ue(resultat)
        # (13.456 + 13) / 2 = 13.228 → arrondi 2 décimales.
        self.assertEqual(ue['moyenne'], Decimal('13.23'))

    def test_reproductibilite_empreintes_identiques(self):
        self._activer_maquette()
        module_a = self._creer_branche_ecue(
            self.ecue_a, self.participant, self.inscription, self.semestre, self.formation_op,
        )
        module_b = self._creer_branche_ecue(
            self.ecue_b, self.participant, self.inscription, self.semestre, self.formation_op,
        )
        self._noter(module_a, self.participant, 12)
        self._noter(module_b, self.participant, 8)

        resultat1 = self._calculer()
        resultat2 = self._calculer()

        self.assertEqual(_empreinte(resultat1), _empreinte(resultat2))

    def test_regle_pour_niveau_puis_defaut(self):
        regle_niveau = RegleValidationLMD.objects.create(
            ref_formation=self.ref_formation, niveau=self.niveau,
        )
        self.assertEqual(regle_pour(self.maquette), regle_niveau)
        regle_niveau.actif = False
        regle_niveau.save()
        regle_defaut = RegleValidationLMD.objects.create(
            ref_formation=self.ref_formation, niveau=None,
        )
        self.assertEqual(regle_pour(self.maquette), regle_defaut)
        regle_defaut.delete()
        self.assertIsNone(regle_pour(self.maquette))


class CompensationTests(MoteurBase):
    """Compensation semestrielle paramétrable + seuil éliminatoire.

    Second UE du même semestre (10 crédits) avec une moyenne faible. UE2 est
    ajoutée AVANT activation de la maquette (garde-fou R4).
    """

    def _ajouter_ue2(self):
        ue2 = UE.objects.create(
            maquette=self.maquette, semestre=self.semestre, code='UE2', credits=10,
        )
        ref_c = RefModule.objects.create(intitule='Module C')
        ecue_c = ECUE.objects.create(
            ue=ue2, code='ECUE-C', intitule='ECUE C', credits=10, ref_module=ref_c,
        )
        module_c = Module.objects.create(
            formation=self.formation_op, intitule='ECUE C', ref_module=ref_c,
        )
        mp = ModuleParticipant.objects.create(module=module_c, participant=self.participant)
        InscriptionPedagogique.objects.create(
            inscription=self.inscription, ecue=ecue_c, semestre=self.semestre,
            module_participant=mp,
            statut=InscriptionPedagogique.Statut.VALIDEE,
        )
        return module_c

    def _noter_trois_ecues(self):
        module_a = self._creer_branche_ecue(
            self.ecue_a, self.participant, self.inscription, self.semestre, self.formation_op,
        )
        module_b = self._creer_branche_ecue(
            self.ecue_b, self.participant, self.inscription, self.semestre, self.formation_op,
        )
        module_c = self._ajouter_ue2()
        self._noter(module_a, self.participant, 11)
        self._noter(module_b, self.participant, 11)
        self._noter(module_c, self.participant, 9.5)
        return module_c

    def test_compensation_semestre_acquiert_ue_faible(self):
        self._noter_trois_ecues()
        self._activer_maquette()

        resultat = self._calculer()

        ues = {u['code']: u for u in resultat['semestres'][0]['ues']}
        self.assertTrue(ues['UE1']['acquise'])
        self.assertTrue(ues['UE2']['acquise'])
        self.assertTrue(ues['UE2']['par_compensation'])
        # Moyenne semestre = (11*20 + 9.5*10) / 30 = 10.50 ≥ 10.
        self.assertEqual(resultat['semestres'][0]['moyenne'], Decimal('10.50'))
        self.assertTrue(resultat['semestres'][0]['compense'])
        self.assertEqual(resultat['credits_acquis'], 30)
        self.assertEqual(resultat['decision_proposee'], 'ADMIS')

    def test_sans_compensation_ue_faible_non_acquise(self):
        regle = RegleValidationLMD.objects.create(
            ref_formation=self.ref_formation, niveau=self.niveau,
            compensation=RegleValidationLMD.Compensation.AUCUNE,
        )
        self._noter_trois_ecues()
        self._activer_maquette()

        resultat = self._calculer()

        ues = {u['code']: u for u in resultat['semestres'][0]['ues']}
        self.assertTrue(ues['UE1']['acquise'])
        self.assertFalse(ues['UE2']['acquise'])
        self.assertFalse(ues['UE2']['par_compensation'])
        self.assertEqual(resultat['credits_acquis'], 20)

    def test_seuil_elim_bloque_compensation(self):
        RegleValidationLMD.objects.create(
            ref_formation=self.ref_formation, niveau=self.niveau,
            seuil_elim=Decimal('8'),
        )
        module_a = self._creer_branche_ecue(
            self.ecue_a, self.participant, self.inscription, self.semestre, self.formation_op,
        )
        module_b = self._creer_branche_ecue(
            self.ecue_b, self.participant, self.inscription, self.semestre, self.formation_op,
        )
        module_c = self._ajouter_ue2()
        self._noter(module_a, self.participant, 12)
        self._noter(module_b, self.participant, 12)
        self._noter(module_c, self.participant, 7.5)
        self._activer_maquette()

        resultat = self._calculer()

        # Moyenne semestre = (12*20 + 7.5*10) / 30 = 10.5 ≥ 10, mais la
        # moyenne UE2 (7.50) est sous le seuil éliminatoire (8) : pas de
        # compensation pour cette UE.
        ues = {u['code']: u for u in resultat['semestres'][0]['ues']}
        self.assertTrue(ues['UE1']['acquise'])
        self.assertFalse(ues['UE2']['acquise'])
        self.assertEqual(resultat['credits_acquis'], 20)


