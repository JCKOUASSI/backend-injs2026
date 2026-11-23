"""Revalidation conservatrice de la proposition après un commit antérieur."""
from dataclasses import replace
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase, override_settings

from edts.moteur.application_v2 import appliquer_ligne, appliquer_proposition_automatique, proposer_ligne
from edts.moteur.planification_v2 import DecisionLigne, TravailSeance
from edts.tests import test_moteur_v2_phase3 as fixture_module


class RevalidationAutomatiqueTests(SimpleTestCase):
    def setUp(self):
        self.travail = TravailSeance(1, 2, 0, 'CM', 1, 120, 20)
        self.candidat = DecisionLigne('PLACEE', 'PLACEMENT_POSSIBLE', self.travail.cle())

    @patch('edts.moteur.application_v2.proposer_ligne')
    @patch('edts.moteur.application_v2.appliquer_ligne')
    def test_proposition_expiree_replanifie_sans_forcer(self, appliquer, proposer):
        appliquer.side_effect = [DecisionLigne('ECHEC', 'PROPOSITION_EXPIREE', self.travail.cle()),
                                self.candidat]
        proposer.return_value = self.candidat
        res = appliquer_proposition_automatique(self.travail, self.candidat, revision=1, graine=7)
        self.assertEqual(res.statut, 'PLACEE')
        self.assertEqual(appliquer.call_count, 2)
        proposer.assert_called_once_with(self.travail, revision=1, graine=7)

    @patch('edts.moteur.application_v2.proposer_ligne')
    @patch('edts.moteur.application_v2.appliquer_ligne')
    def test_qr_protege_ne_reprogramme_jamais(self, appliquer, proposer):
        appliquer.return_value = DecisionLigne('A_REVOIR', 'QR_PROTEGE', self.travail.cle())
        res = appliquer_proposition_automatique(self.travail, self.candidat, revision=1)
        self.assertEqual(res.code, 'QR_PROTEGE')
        proposer.assert_not_called()


@override_settings(DEBUG=True, GETINJS_V2_EXPERIMENTAL_WRITE=True)
class ValidationDureCandidatAnnuelTests(TestCase):
    def setUp(self):
        fixture_module.MoteurV2BenchTests.setUp(self)

    def test_candidat_classe_hors_top4_accepte_si_valide_et_dispo_dure_refuse(self):
        from formations.models import RefSalle
        from edts.models import DisponibiliteHoraire
        from edts.models_interop import SeanceRegistre
        for numero in range(6):
            RefSalle.objects.create(site=self.site, nom=f'BENCH-SALLE-{numero}', capacite=50)
        premier = proposer_ligne(self.travail, revision=1, jour=self.jour)
        salles = list(RefSalle.objects.filter(actif=True).order_by('pk'))
        top = {(premier.jour, premier.creneau_id, premier.salle_id), *premier.alternatives}
        cible = next(s for s in salles if (premier.jour, premier.creneau_id, s.pk) not in top)
        self.assertNotIn((premier.jour, premier.creneau_id, cible.pk), top)
        # Garde dure, indépendante du classement : une salle indisponible reste refusée.
        dispo = DisponibiliteHoraire.objects.create(annee_academique=self.annee,
            salle=cible, jour=self.slot.jour, heure_debut=self.slot.heure_debut,
            heure_fin=self.slot.heure_fin, statut='INDISPONIBLE')
        candidat = replace(premier, salle_id=cible.pk)
        self.assertEqual(appliquer_ligne(self.travail, candidat, revision=1).code,
                         'INDISPONIBILITE')
        self.assertEqual(SeanceRegistre.objects.count(), 0)
        dispo.delete()
        resultat = appliquer_ligne(self.travail, candidat, revision=1)
        self.assertEqual(resultat.statut, 'PLACEE')
        self.assertEqual(SeanceRegistre.objects.count(), 1)
