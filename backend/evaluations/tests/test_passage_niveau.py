"""L1/L2 — Non-régression des cas métier du passage de niveau.

Couvre : semestres validés, semestre non validé, ECTS insuffisants, résultat
manquant, décision `EXCLUSION` bloquante, et la séparation stricte entre
l'éligibilité technique (ce service) et la décision officielle du jury (qui
n'est jamais produite ici).
"""
from django.test import TestCase


class PassageNiveauTests(TestCase):
    def _base(self):
        from datetime import date

        from evaluations.models import SessionEvaluation
        from formations.models import Participant, RefFormation
        from scolarite.models import (
            AnneeAcademique, DossierEtudiant, InscriptionAdministrative,
            Maquette, Niveau, Semestre,
        )

        annee = AnneeAcademique.objects.create(
            libelle='2025-2026', date_debut=date(2025, 9, 1),
            date_fin=date(2026, 7, 31),
        )
        l1 = Niveau.objects.create(
            code='L1', libelle='Licence 1', ordre=1, credits_requis=60,
        )
        l2 = Niveau.objects.create(
            code='L2', libelle='Licence 2', ordre=2, credits_requis=60,
        )
        s1 = Semestre.objects.create(niveau=l1, numero=1, libelle='S1')
        s2 = Semestre.objects.create(niveau=l1, numero=2, libelle='S2')
        Semestre.objects.create(niveau=l2, numero=3, libelle='S3')
        ref_formation = RefFormation.objects.create(intitule='Formation 1')
        maquette = Maquette.objects.create(
            annee_academique=annee, ref_formation=ref_formation,
            niveau=l1, version=1,
        )
        participant = Participant.objects.create(
            matricule='PASSAGE-TEST-1', nom='Nom', prenom='Prenom',
        )
        dossier = DossierEtudiant.objects.create(participant=participant)
        inscription = InscriptionAdministrative.objects.create(
            etudiant=dossier, annee_academique=annee,
            ref_formation=ref_formation, niveau=l1, statut='BROUILLON',
        )
        session = SessionEvaluation.objects.create(
            annee_academique=annee, ref_formation=ref_formation,
            niveau=l1, maquette=maquette, libelle='Session 1',
            type_session='NORMALE', statut='CLOTUREE',
        )
        return inscription, session, l1, l2, s1, s2, maquette

    def _resultats(self, inscription, session, s1, s2, statut1, statut2,
                   credits1=30, credits2=30):
        from evaluations.models import SemesterResult

        for semestre, statut, credits in (
            (s1, statut1, credits1), (s2, statut2, credits2),
        ):
            SemesterResult.objects.create(
                inscription=inscription, session=session, semestre=semestre,
                credits_attendus=30, credits_acquis=credits,
                statut_semestre=statut,
            )

    def _decision(self, inscription, valeur, maquette, niveau):
        """Décision officielle de jury (le moteur ne la produit jamais)."""
        from jurys.models import DecisionJury, SessionJury
        from scolarite.models import AnneeAcademique

        session_jury = SessionJury.objects.create(
            annee_academique=AnneeAcademique.objects.first(),
            libelle='Jury de test', type_session='NORMALE', statut='CLOTUREE',
            maquette=maquette, niveau=niveau,
            ref_formation=maquette.ref_formation,
        )
        DecisionJury.objects.create(
            session=session_jury, inscription=inscription,
            participant=inscription.etudiant.participant,
            decision=valeur, credits_acquis=60,
        )

    def test_01_niveau_complet_60_ects_eligible(self):
        from evaluations.services.passage import passage_niveau

        inscription, session, l1, _l2, s1, s2, maquette = self._base()
        self._resultats(inscription, session, s1, s2, 'VALIDE', 'VALIDE', 30, 30)
        sortie = passage_niveau(inscription, session, niveau_cible=l1)
        self.assertEqual(sortie['eligibilite'], 'ELIGIBLE')
        self.assertEqual(sortie['credits_acquis'], 60)
        self.assertEqual(sortie['credits_requis'], 60)

    def test_02_ects_insuffisants_non_eligible(self):
        from evaluations.services.passage import passage_niveau

        inscription, session, l1, _l2, s1, s2, maquette = self._base()
        self._resultats(inscription, session, s1, s2, 'VALIDE', 'VALIDE', 30, 15)
        sortie = passage_niveau(inscription, session, niveau_cible=l1)
        self.assertEqual(sortie['eligibilite'], 'NON_ELIGIBLE')
        self.assertEqual(sortie['code'], 'CREDITS_INSUFFISANTS')
        # 45 ECTS : jamais complété artificiellement à 60.
        self.assertEqual(sortie['credits_acquis'], 45)

    def test_03_semestre_non_valide_non_eligible(self):
        from evaluations.services.passage import passage_niveau

        inscription, session, l1, _l2, s1, s2, maquette = self._base()
        self._resultats(inscription, session, s1, s2, 'VALIDE', 'NON_VALIDE')
        sortie = passage_niveau(inscription, session, niveau_cible=l1)
        self.assertEqual(sortie['eligibilite'], 'NON_ELIGIBLE')
        self.assertEqual(sortie['code'], 'SEMESTRE_NON_VALIDE')

    def test_04_resultat_manquant_indeterminable(self):
        from evaluations.services.passage import passage_niveau

        inscription, session, l1, _l2, s1, s2, maquette = self._base()
        self._resultats(inscription, session, s1, s2, 'EN_ATTENTE', 'EN_ATTENTE')
        sortie = passage_niveau(inscription, session, niveau_cible=l1)
        # Une donnée manquante ne vaut jamais validation.
        self.assertEqual(sortie['eligibilite'], 'INDETERMINABLE')

    def test_05_aucun_resultat_indeterminable(self):
        from evaluations.services.passage import passage_niveau

        inscription, session, l1, _l2, _s1, _s2, _maquette = self._base()
        sortie = passage_niveau(inscription, session, niveau_cible=l1)
        self.assertEqual(sortie['eligibilite'], 'INDETERMINABLE')
        self.assertEqual(sortie['code'], 'AUCUN_RESULTAT')

    def test_06_decision_exclusion_bloque_le_passage(self):
        from evaluations.services.passage import passage_niveau

        inscription, session, l1, _l2, s1, s2, maquette = self._base()
        self._resultats(inscription, session, s1, s2, 'VALIDE', 'VALIDE', 30, 30)
        self._decision(inscription, maquette=maquette, niveau=l1, valeur='EXCLUSION')
        sortie = passage_niveau(inscription, session, niveau_cible=l1)
        # EXCLUSION reste une décision officielle : aucun passage proposé.
        self.assertEqual(sortie['eligibilite'], 'BLOQUE')
        self.assertEqual(sortie['code'], 'DECISION_JURY_BLOQUANTE')
        self.assertEqual(sortie['decision_jury']['valeur'], 'EXCLUSION')

    def test_07_decision_ajourne_reprise_telle_quelle(self):
        from evaluations.services.passage import passage_niveau

        inscription, session, l1, _l2, s1, s2, maquette = self._base()
        self._resultats(inscription, session, s1, s2, 'VALIDE', 'VALIDE', 30, 30)
        self._decision(inscription, maquette=maquette, niveau=l1, valeur='AJOURNE')
        sortie = passage_niveau(inscription, session, niveau_cible=l1)
        # AJOURNE est reprise telle quelle, sans bloquer le calcul technique.
        self.assertEqual(sortie['decision_jury']['valeur'], 'AJOURNE')
        self.assertNotEqual(sortie['eligibilite'], 'BLOQUE')

    def test_08_service_ne_produit_jamais_de_decision(self):
        from evaluations.services.passage import passage_niveau

        inscription, session, l1, _l2, s1, s2, maquette = self._base()
        self._resultats(inscription, session, s1, s2, 'VALIDE', 'VALIDE', 30, 30)
        sortie = passage_niveau(inscription, session, niveau_cible=l1)
        # Aucune clé de décision officielle n'est produite par le moteur.
        self.assertNotIn('decision', sortie)
        self.assertIsNone(sortie['decision_jury'])

    def test_09_empreinte_deterministe(self):
        from evaluations.services.passage import passage_niveau

        inscription, session, l1, _l2, s1, s2, maquette = self._base()
        self._resultats(inscription, session, s1, s2, 'VALIDE', 'VALIDE', 30, 30)
        a = passage_niveau(inscription, session, niveau_cible=l1)['empreinte']
        b = passage_niveau(inscription, session, niveau_cible=l1)['empreinte']
        self.assertEqual(a, b)

    def test_10_niveau_suivant_determine_automatiquement(self):
        from evaluations.services.passage import passage_niveau

        inscription, session, _l1, _l2, s1, s2, _maquette = self._base()
        self._resultats(inscription, session, s1, s2, 'VALIDE', 'VALIDE', 30, 30)
        sortie = passage_niveau(inscription, session)  # sans niveau_cible
        # L1 complet (60 ECTS) → le niveau cible déduit est L2.
        self.assertEqual(sortie['niveau_cible'], 'L2')
        self.assertEqual(sortie['eligibilite'], 'INDETERMINABLE')
        self.assertEqual(sortie['code'], 'AUCUN_RESULTAT')