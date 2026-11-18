"""Rapprochement des volumes : aucune écriture, aucun emprunt approximatif."""
from datetime import date
from decimal import Decimal

from django.test import TestCase

from edts.tests.test_lot2_moteur import FabriqueLMD
from referentiels.models import RefVolumeHoraireFormation
from scolarite.models import AnneeAcademique, ECUE, Maquette
from scolarite.volumes_audit import rapprocher


class AuditVolumesTests(TestCase):
    def setUp(self):
        f = FabriqueLMD(self).creer_base(perimetre='INJS', filiere='F01')
        self.annee = f.annee
        self.formation = f.cycle
        maquette, _, self.source = f.creer_maquette()
        self.source.volume_cm = 20
        self.source.volume_td = 10
        self.source.save(update_fields=['volume_cm', 'volume_td'])
        maquette.statut = Maquette.Statut.ACTIVE
        maquette.save()
        self.cible_annee = AnneeAcademique.objects.create(
            libelle='2029-2030', date_debut=date(2029, 10, 1),
            date_fin=date(2030, 7, 31),
        )
        clone = maquette.cloner()
        clone.annee_academique = self.cible_annee
        clone.save(update_fields=['annee_academique'])
        self.cible = ECUE.objects.get(ue__maquette=clone)
        self.cible.volume_cm = Decimal('0')
        self.cible.volume_td = Decimal('0')
        self.cible.save(update_fields=['volume_cm', 'volume_td'])

    def test_source_exacte_reste_candidat_non_copie(self):
        rapport = rapprocher('2029-2030')
        ligne = next(l for l in rapport['ecues_cible'] if l['ecue_id'] == self.cible.pk)
        self.assertEqual(ligne['statut'], 'CANDIDAT_EXACT_A_VALIDER')
        self.assertEqual(ligne['sources_exactes'][0]['ecue_id'], self.source.pk)
        self.cible.refresh_from_db()
        self.assertEqual(self.cible.volume_cm, 0)
        self.assertEqual(ligne['cm'], '0.00')

    def test_contradictions_signalees_et_formation_differente_non_rattachee(self):
        # Deuxième version historique avec la même identité, autre volume.
        copie = self.source.ue.maquette.cloner()
        ecue = ECUE.objects.get(ue__maquette=copie)
        ecue.volume_cm = 12
        ecue.save(update_fields=['volume_cm'])
        rapport = rapprocher('2029-2030')
        ligne = next(l for l in rapport['ecues_cible'] if l['ecue_id'] == self.cible.pk)
        self.assertEqual(ligne['statut'], 'CONTRADICTION_A_ARBITRER')
        self.assertEqual(len(ligne['sources_exactes']), 2)

    def test_reference_module_modelisee_est_indicative_seulement(self):
        # Prépare une base historique sans source positive (fixture seulement).
        ECUE.objects.filter(pk=self.source.pk).update(volume_cm=0, volume_td=0)
        RefVolumeHoraireFormation.objects.create(
            formation=self.formation, intitule_module=self.cible.intitule,
            heures_cm=Decimal('24'), fiabilite='MODELISE',
            source_document='Cadrage non officiel',
        )
        rapport = rapprocher('2029-2030')
        ligne = next(l for l in rapport['ecues_cible'] if l['ecue_id'] == self.cible.pk)
        self.assertEqual(ligne['statut'], 'REFERENCE_MODULE_INDICATIVE_A_VERIFIER')
        self.assertEqual(ligne['references_module_indicatives'][0]['fiabilite'], 'MODELISE')
        self.assertEqual(self.cible.volume_cm, 0)
