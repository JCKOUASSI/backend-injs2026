"""GET-INJS — génération des emplois du temps d'une année académique entière.

Scénario n°1 du commanditaire : produire les emplois du temps d'une année pour
toutes les cohortes (filière, formation, groupe, vague, semestre) à partir des
inscriptions, y compris lorsque celles-ci n'ont pas suivi la chaîne de parcours.

Ce qui est vérifié :

1. une cohorte **importée** (sans affectation pédagogique) est planifiée à
   partir de la maquette active, avec son effectif réel ;
2. une cohorte issue de la chaîne interne continue d'utiliser ses affectations
   (non-régression) ;
3. la génération est **coordonnée** : deux groupes ne se voient pas attribuer
   la même salle au même créneau ;
4. l'absence de maquette est **signalée**, jamais compensée par un horaire
   fictif ;
5. la persistance crée un EDT BROUILLON par groupe, sans publication ;
6. l'échelle : plusieurs formations et plusieurs groupes sont traités en une
   opération, avec un décompte d'étudiants exact.
"""

import io

from django.test import TestCase

from edts.moteur import annee as A
from edts.moteur import generation as G
from edts.moteur import besoins_maquette as BM
from edts.moteur import import_inscrits as I
from edts.models import AffectationCreneau, EmploiDuTemps, InscriptionImportee
from edts.tests.test_lot2_moteur import FabriqueLMD
from scolarite.models import ECUE, Maquette, UE


def _csv(rows, entete='matricule;nom;formation;niveau;semestre;groupe;vague\n'):
    return (entete + '\n'.join(rows) + '\n').encode('utf-8')


class BaseAnneeTest(TestCase):
    def setUp(self):
        self.f = FabriqueLMD(self).creer_base(perimetre='INJS', filiere='F01')
        self.formation = self.f.cycle
        self.annee = self.f.annee
        self.f.creer_creneaux(jours=('LUNDI', 'MARDI'), heures=((8, 10), (10, 12)))
        self.salle = self.f.creer_salle(nom='Salle A', capacite=60)
        # Maquette ACTIVE : 2 ECUE volumées (CM 4 h, TD 2 h) → 3 séances de 2 h.
        maquette, ue, ecue = self.f.creer_maquette()
        # Volumes renseignés AVANT l'activation : une maquette ACTIVE est
        # immuable (règle R4 du lot L1), ses ECUE ne sont plus modifiables.
        ecue.volume_cm = 4
        ecue.volume_td = 2
        ecue.save()
        maquette.statut = Maquette.Statut.ACTIVE
        maquette.save()
        self.maquette, self.ue, self.ecue = maquette, ue, ecue

    def importer(self, rows, appliquer=True):
        return I.importer_inscrits(
            annee_academique_id=self.annee.pk,
            nom_fichier='inscrits.csv',
            contenu=_csv(rows),
            appliquer=appliquer,
        )


class BesoinsDepuisMaquetteTests(BaseAnneeTest):
    def test_besoins_derives_des_volumes_de_la_maquette(self):
        self.importer([
            f'INJS-{i:03d};Nom{i};{self.formation.intitule};L1;S1;L1-G1;V1'
            for i in range(30)
        ])
        resultat = BM.besoins_depuis_maquette(annee_academique_id=self.annee.pk)
        self.assertIsNone(resultat.motif_echec)
        # 1 ECUE portant CM 4 h + TD 2 h, créneaux de 2 h → 2 besoins,
        # 2 séances de CM et 1 séance de TD.
        self.assertEqual(len(resultat.besoins), 2)
        self.assertEqual(sum(b.nb_seances for b in resultat.besoins), 3)
        self.assertTrue(all(b.origine == 'MAQUETTE' for b in resultat.besoins))
        self.assertTrue(all(b.affectation_pedagogique_id is None for b in resultat.besoins))

    def test_effectif_provient_du_denombrement_reel(self):
        self.importer([
            f'INJS-{i:03d};Nom{i};{self.formation.intitule};L1;S1;L1-G1;V1'
            for i in range(42)
        ])
        resultat = BM.besoins_depuis_maquette(annee_academique_id=self.annee.pk)
        self.assertEqual({b.effectif for b in resultat.besoins}, {42})

    def test_aucun_enseignant_invente(self):
        self.importer([f'INJS-001;Nom;{self.formation.intitule};L1;S1;L1-G1;V1'])
        resultat = BM.besoins_depuis_maquette(annee_academique_id=self.annee.pk)
        self.assertTrue(all(b.enseignant_id is None for b in resultat.besoins))

    def test_sans_maquette_active_motif_explicite(self):
        self.importer([f'INJS-001;Nom;{self.formation.intitule};L1;S1;L1-G1;V1'])
        Maquette.objects.update(statut=Maquette.Statut.BROUILLON)
        resultat = BM.besoins_depuis_maquette(annee_academique_id=self.annee.pk)
        self.assertTrue(resultat.vide)
        self.assertEqual(resultat.motif_echec, BM.MOTIF_AUCUNE_MAQUETTE)
        self.assertTrue(resultat.detail['sans_maquette'])

    def test_sans_canevas_motif_explicite(self):
        from edts.models import CreneauTemplate

        self.importer([f'INJS-001;Nom;{self.formation.intitule};L1;S1;L1-G1;V1'])
        CreneauTemplate.objects.all().delete()
        resultat = BM.besoins_depuis_maquette(annee_academique_id=self.annee.pk)
        self.assertEqual(resultat.motif_echec, BM.MOTIF_CANEVAS_VIDE)


class GenerationAnneeTests(BaseAnneeTest):
    def test_cohorte_importee_planifiee(self):
        self.importer([
            f'INJS-{i:03d};Nom{i};{self.formation.intitule};L1;S1;L1-G1;V1'
            for i in range(35)
        ])
        bilan = A.generer_annee(self.annee.pk, semaines=[1])

        self.assertEqual(bilan['totaux']['nb_groupes'], 1)
        ligne = bilan['groupes'][0]
        self.assertEqual(ligne['statut'], G.GENERATION_OK)
        self.assertEqual(ligne['effectif'], 35)
        # 2 blocs placés (CM récurrent 2 séances + TD 1 séance) = 3 séances.
        self.assertEqual(ligne['blocs_placees'], 2)
        self.assertEqual(ligne['seances_placees'], 3)
        self.assertEqual(ligne['seances_non_placees'], 0)
        self.assertEqual(bilan['totaux']['etudiants_couverts'], 35)

    def test_affectations_internes_conservees(self):
        """Non-régression : la chaîne LMD interne reste prioritaire."""
        groupe = self.f.creer_groupe(nom='L1-G1', capacite=30)
        self.f.creer_affectation(volume=4, type_ens='CM', groupe=groupe)

        bilan = A.generer_annee(self.annee.pk, semaines=[1])
        ligne = bilan['groupes'][0]
        self.assertEqual(ligne['statut'], G.GENERATION_OK)
        self.assertEqual(ligne['seances_attendues'], 2)  # 4 h / créneaux de 2 h
        self.assertEqual(bilan['sources']['affectations_pedagogiques']['groupes'], 1)

    def test_generation_coordonnee_deux_groupes(self):
        """Deux groupes ne partagent pas la même salle au même créneau (C3)."""
        self.importer([
            f'A-{i:03d};Nom{i};{self.formation.intitule};L1;S1;L1-G1;V1'
            for i in range(20)
        ] + [
            f'B-{i:03d};Nom{i};{self.formation.intitule};L1;S1;L1-G2;V1'
            for i in range(20)
        ])
        bilan = A.generer_annee(self.annee.pk, semaines=[1])
        self.assertEqual(bilan['totaux']['nb_groupes'], 2)
        # 2 blocs par groupe (CM + TD) = 4 blocs, soit exactement les 4 créneaux
        # du canevas (2 jours × 2 plages) avec une seule salle : tout est placé,
        # sans chevauchement de salle ni de groupe (C2/C3).
        self.assertEqual(bilan['totaux']['seances_placees'], 6)
        self.assertEqual(bilan['totaux']['seances_non_placees'], 0)
        self.assertEqual(bilan['status_global'], A.ANNEE_COMPLETE)

    def test_pas_de_publication(self):
        self.importer([f'INJS-001;Nom;{self.formation.intitule};L1;S1;L1-G1;V1'])
        bilan = A.generer_annee(self.annee.pk, semaines=[1], persister=True)
        self.assertTrue(bilan['persistence_demandee'])
        edt = EmploiDuTemps.objects.get(pk=bilan['groupes'][0]['edt_id'])
        self.assertEqual(edt.statut, 'BROUILLON')
        self.assertIsNone(edt.publie_le)

    def test_persistance_idempotente(self):
        self.importer([f'INJS-001;Nom;{self.formation.intitule};L1;S1;L1-G1;V1'])
        premier = A.generer_annee(self.annee.pk, semaines=[1], persister=True)
        seances_1 = AffectationCreneau.objects.filter(actif=True).count()
        second = A.generer_annee(self.annee.pk, semaines=[1], persister=True)
        seances_2 = AffectationCreneau.objects.filter(actif=True).count()

        self.assertEqual(premier['groupes'][0]['edt_id'], second['groupes'][0]['edt_id'])
        self.assertEqual(seances_1, seances_2)
        self.assertEqual(EmploiDuTemps.objects.count(), 1)

    def test_groupe_sans_maquette_signale(self):
        from scolarite.models import Groupe

        # Aucune maquette n'existe pour cette année : le groupe ne doit pas
        # être planifié « au hasard ».
        ECUE.objects.all().delete()
        UE.objects.all().delete()
        Maquette.objects.all().delete()
        Groupe.objects.create(
            annee_academique=self.annee, ref_formation=self.formation,
            niveau=self.f.niveau, nom='L1-SANS-MAQUETTE',
        )
        bilan = A.generer_annee(self.annee.pk, semaines=[1])
        ligne = bilan['groupes'][0]
        self.assertEqual(ligne['statut'], 'NON_PLANIFIE')
        self.assertEqual(ligne['motif_echec'], A.MOTIF_AUCUN_BESOIN)
        self.assertEqual(bilan['status_global'], A.ANNEE_IMPOSSIBLE)

        # Une année impossible doit expliquer POURQUOI au niveau global, et
        # indiquer l'action à mener : « Impossible » sans motif n'est pas
        # exploitable par un secrétariat.
        self.assertEqual(bilan['motif_echec'], A.MOTIF_AUCUN_BESOIN)
        self.assertIn('explication', bilan['detail'])
        self.assertIn('action_recommandee', bilan['detail'])
        self.assertIn('maquette', bilan['detail']['action_recommandee'].lower())

    def test_annee_sans_groupe(self):
        bilan = A.generer_annee(self.annee.pk, semaines=[1])
        self.assertEqual(bilan['status_global'], A.ANNEE_IMPOSSIBLE)
        self.assertEqual(bilan['motif_echec'], 'AUCUN_GROUPE_INJS')

    def test_formation_hors_perimetre_exclue(self):
        legacy = FabriqueLMD(self).creer_base(perimetre='LEGACY', filiere='', suffixe='-L')
        legacy.creer_maquette()
        from scolarite.models import Groupe

        Groupe.objects.create(
            annee_academique=self.annee, ref_formation=legacy.cycle,
            niveau=legacy.niveau, nom='L1-LEG',
        )
        self.importer([f'INJS-001;Nom;{self.formation.intitule};L1;S1;L1-G1;V1'])
        bilan = A.generer_annee(self.annee.pk, semaines=[1])
        self.assertEqual(bilan['totaux']['groupes_hors_perimetre'], 1)
        self.assertEqual(bilan['totaux']['nb_groupes'], 1)


class EchelleTests(BaseAnneeTest):
    """Passage à l'échelle : plusieurs filières, plusieurs groupes, ≥ 3 500 étudiants."""

    def test_trois_milles_cinq_cents_etudiants(self):
        from scolarite.models import Groupe

        filieres = []
        for index in range(4):
            fabrique = FabriqueLMD(self).creer_base(
                perimetre='INJS', filiere=f'F0{index + 2}', suffixe=f'-{index + 2}',
            )
            maquette, ue, ecue = fabrique.creer_maquette()
            ecue.volume_cm = 4
            ecue.save()
            maquette.statut = Maquette.Statut.ACTIVE
            maquette.save()
            filieres.append(fabrique.cycle)

        # Effectifs de 175 étudiants : il faut des salles capacitaires, sinon
        # C4 bloque légitimement toute affectation (aucune salle compatible).
        self.f.creer_salle(nom='Amphi 200', capacite=250)
        self.f.creer_salle(nom='Amphi 250', capacite=250)
        # Canevas hebdomadaire réaliste : 5 jours × 5 plages = 25 créneaux.
        # On remplace le canevas minimal du setUp (jour + horaire unique).
        from edts.models import CreneauTemplate

        CreneauTemplate.objects.all().delete()
        self.f.creer_creneaux(
            jours=('LUNDI', 'MARDI', 'MERCREDI', 'JEUDI', 'VENDREDI'),
            heures=((8, 10), (10, 12), (12, 14), (14, 16), (16, 18)),
        )

        lignes = []
        # 5 groupes par filière × 5 filières = 25 cohortes, 175 étudiants chacune.
        for index, formation in enumerate(filieres + [self.formation]):
            for groupe in range(5):
                code = f'L1-G{groupe + 1}-{index}'
                for etudiant in range(175):
                    lignes.append(
                        f'M{index}-{groupe}-{etudiant};Nom;{formation.intitule};'
                        f'L1;S1;{code};V1'
                    )

        rapport = I.importer_inscrits(
            annee_academique_id=self.annee.pk,
            nom_fichier='rentree.csv',
            contenu=_csv(lignes),
            appliquer=True,
        )
        self.assertEqual(rapport.lignes_valides, 25 * 175)
        self.assertEqual(InscriptionImportee.objects.count(), 4375)

        bilan = A.generer_annee(self.annee.pk, semaines=[1])
        self.assertEqual(bilan['totaux']['nb_groupes'], 25)
        self.assertEqual(bilan['totaux']['etudiants_couverts'], 4375)
        # 25 cohortes × 2 blocs = 50 blocs ; 25 créneaux × 3 salles = 75 places.
        self.assertGreaterEqual(bilan['totaux']['seances_placees'], 50)
        self.assertEqual(bilan['status_global'], A.ANNEE_COMPLETE)
