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

    def test_besoins_maquette_sont_tries_du_plus_contraint_au_plus_simple(self):
        from unittest.mock import patch

        self.importer([
            f'INJS-{i:03d};Nom{i};{self.formation.intitule};L1;S1;L1-G1;V1'
            for i in range(5)
        ])
        with patch(
            'edts.moteur.contraintes.difficulte',
            side_effect=lambda besoin: 10 if besoin.type_enseignement == 'TD' else 0,
        ):
            resultat = BM.besoins_depuis_maquette(annee_academique_id=self.annee.pk)

        self.assertEqual(
            [besoin.type_enseignement for besoin in resultat.besoins],
            ['TD', 'CM'],
        )

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
    def test_diagnostic_couverture_reelle_sur_quatre_semaines(self):
        """Un besoin de 3 séances sur 4 semaines produit exactement 3 occurrences.

        Chaque séance doit être limitée à sa semaine (pas de fausse récurrence
        2 blocs × 4 semaines). Ceci reste un petit échantillon S1, non une
        certification d'une année multi-semestre.
        """
        from time import monotonic
        self.importer([f'INJS-{i:03d};Nom{i};{self.formation.intitule};L1;S1;L1-G1;V1'
                       for i in range(20)])
        depart = monotonic()
        bilan = A.generer_annee(
            self.annee.pk, semaines=[1, 2, 3, 4], semestre_numeros=[1],
            max_seances_par_groupe_semaine=1, persister=True,
        )
        duree_s = monotonic() - depart
        ligne = bilan['groupes'][0]
        self.assertEqual(ligne['seances_attendues'], 3)
        self.assertEqual(ligne['seances_placees'], 3)
        self.assertEqual(ligne['occurrences_recurrentes'], 3)
        self.assertEqual(ligne['heures_recurrentes'], 6)
        self.assertEqual(ligne['heures_prevues'], 6)
        self.assertTrue(ligne['repartition_verifiee'])
        self.assertEqual(ligne['statut'], G.GENERATION_OK)
        self.assertEqual(bilan['status_global'], A.ANNEE_COMPLETE)
        self.assertTrue(ligne['persistance']['effectuee'])
        seances = list(AffectationCreneau.objects.filter(actif=True)
                       .select_related('creneau_template'))
        self.assertEqual(len(seances), 3)
        self.assertEqual(sum(a.semaine_fin - a.semaine_debut + 1 for a in seances), 3)
        self.assertTrue(all(a.semaine_debut == a.semaine_fin for a in seances))
        self.assertEqual(sorted({a.semaine_debut for a in seances}), [1, 2, 3])
        self.assertTrue(all(a.ecue_id == self.ecue.pk for a in seances))
        print(f'ANNUEL_DIAGNOSTIC: 20 étudiants, 4 semaines, S1, '
              f'6h prévues, {ligne["heures_recurrentes"]:g}h persistées, '
              f'{len(seances)} occurrences, durée {duree_s:.3f}s')

    def test_generation_manuel_partielle_acceptee_persiste_uniquement_les_seances_placees(self):
        """Après consentement, un EDT brouillon peut conserver le plan partiel sûr.

        Les occurrences absentes restent dans le bilan et ne rendent jamais le
        plan publiable; elles ne doivent toutefois pas annuler les placements
        valides déjà calculés pour le semestre ciblé.
        """
        from edts.models import CreneauTemplate

        ECUE.objects.filter(pk=self.ecue.pk).update(volume_cm=10, volume_td=8)
        self.importer([f'INJS-{i:03d};Nom{i};{self.formation.intitule};L1;S1;L1-G1;V1'
                       for i in range(20)])
        premier = CreneauTemplate.objects.order_by('pk').first()
        CreneauTemplate.objects.exclude(pk=premier.pk).delete()

        bilan = A.generer_annee(
            self.annee.pk,
            semaines=[1, 2, 3, 4],
            semestre_numeros=[1],
            persister=True,
            autoriser_plan_partiel=True,
        )

        ligne = bilan['groupes'][0]
        self.assertEqual(bilan['status_global'], A.ANNEE_PARTIELLE)
        self.assertEqual(ligne['seances_attendues'], 9)
        self.assertEqual(ligne['seances_placees'], 4)
        self.assertEqual(ligne['seances_non_placees'], 5)
        self.assertEqual(ligne['motif_echec'], 'OCCURRENCES_NON_PLACEES', ligne)
        self.assertTrue(ligne['repartition_verifiee'])
        self.assertTrue(ligne['persistance']['effectuee'])
        self.assertTrue(ligne['persistance']['couverture_partielle_acceptee'])
        self.assertEqual(ligne['seances_persistees'], 4)
        self.assertEqual(EmploiDuTemps.objects.count(), 1)
        self.assertEqual(AffectationCreneau.objects.filter(actif=True).count(), 4)

    def test_automatique_sans_calendrier_semestre_refuse_l_annee_complete(self):
        self.importer([f'INJS-{i:03d};Nom{i};{self.formation.intitule};L1;S1;L1-G1;V1'
                       for i in range(5)])
        bilan = A.generer_annee(self.annee.pk, semaines=[1, 2, 3, 4], persister=True)
        self.assertNotEqual(bilan['status_global'], A.ANNEE_COMPLETE)
        self.assertEqual(bilan['groupes'][0]['motif_echec'],
                         'REPARTITION_ANNUELLE_NON_CONFORME')
        self.assertEqual(AffectationCreneau.objects.filter(actif=True).count(), 0)

    def test_annee_s1_s2_refus_auto_et_deux_perimetres_manuels_isoles(self):
        """Dates indicatives de la mission ≠ bornes S1/S2 validées en base.

        La garde ne doit jamais persister les récurrences 1..39 d'une année
        sous prétexte que les besoins sont répartis entre S1 et S2.
        """
        from scolarite.models import Semestre
        from datetime import date

        self.annee.date_debut = date(2026, 9, 1)
        self.annee.date_fin = date(2027, 5, 31)
        self.annee.save(update_fields=['date_debut', 'date_fin'])
        f2 = FabriqueLMD(self).creer_base(perimetre='INJS', filiere='F02', suffixe='S2')
        f2.semestre, _ = Semestre.objects.get_or_create(
            niveau=self.f.niveau, numero=2, defaults={'libelle': 'S2'})
        f2.creer_salle(nom='Salle B', capacite=60)
        maquette2, _, ecue2 = f2.creer_maquette()
        ecue2.volume_cm, ecue2.volume_td = 4, 2
        ecue2.save()
        maquette2.statut = Maquette.Statut.ACTIVE
        maquette2.save()
        self.importer([
            f'INJS-{i:03d};Nom{i};{self.formation.intitule};L1;S1;L1-G1;V1'
            for i in range(6)
        ] + [
            f'INJS-S2-{i:03d};Nom{i};{f2.cycle.intitule};L1;S2;L1-G2;V1'
            for i in range(6)
        ])
        bilan = A.generer_annee(self.annee.pk, semaines=list(range(1, 40)),
                                persister=True, budget=1500)
        self.assertNotEqual(bilan['status_global'], A.ANNEE_COMPLETE)
        self.assertEqual(bilan['totaux']['nb_groupes'], 2)
        self.assertEqual({g['motif_echec'] for g in bilan['groupes']},
                         {'REPARTITION_ANNUELLE_NON_CONFORME'})
        self.assertEqual(AffectationCreneau.objects.filter(actif=True).count(), 0)
        self.assertEqual(EmploiDuTemps.objects.count(), 0)

        # Démonstration technique uniquement : l'opérateur cible EXPLICITEMENT
        # chaque semestre et ses semaines dans la base de test. Ces semaines
        # illustratives ne constituent PAS un calendrier institutionnel.
        s1 = A.generer_annee(self.annee.pk, semaines=list(range(1, 18)),
                             semestre_numeros=[1], persister=True)
        s2 = A.generer_annee(self.annee.pk, semaines=list(range(18, 40)),
                             semestre_numeros=[2], persister=True)
        self.assertEqual(s1['status_global'], A.ANNEE_COMPLETE, s1)
        self.assertEqual(s2['status_global'], A.ANNEE_COMPLETE, s2)
        lignes = list(AffectationCreneau.objects.filter(actif=True)
                      .select_related('creneau_template'))
        self.assertEqual(len(lignes), 6)
        self.assertEqual({a.ecue_id for a in lignes}, {self.ecue.pk, ecue2.pk})
        self.assertEqual(len({a.groupe_id for a in lignes}), 2)
        self.assertEqual(sum(a.semaine_fin - a.semaine_debut + 1 for a in lignes), 6)
        self.assertEqual(sum(
            (a.creneau_template.heure_fin.hour - a.creneau_template.heure_debut.hour)
            * (a.semaine_fin - a.semaine_debut + 1) for a in lignes), 12)
        self.assertTrue(all(a.semaine_debut <= 17 for a in lignes if a.ecue_id == self.ecue.pk))
        self.assertTrue(all(a.semaine_debut >= 18 for a in lignes if a.ecue_id == ecue2.pk))
        from edts.moteur import validation as V
        violations = []
        V.verifier_conflits(V.placements_seances(lignes), violations, [])
        self.assertEqual(violations, [])

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

    def test_canevas_sature_ne_perd_pas_tous_les_placements(self):
        """Une impasse sur un besoin ne doit pas effacer les séances faisables."""
        from edts.models import CreneauTemplate

        self.importer([f'INJS-001;Nom;{self.formation.intitule};L1;S1;L1-G1;V1'])
        # CM et TD demandent deux blocs distincts ; un seul créneau est libre.
        premier = CreneauTemplate.objects.order_by('pk').first()
        CreneauTemplate.objects.exclude(pk=premier.pk).delete()
        bilan = A.generer_annee(self.annee.pk, semaines=[1])
        ligne = bilan['groupes'][0]
        self.assertEqual(ligne['seances_attendues'], 3)
        self.assertGreater(ligne['seances_placees'], 0)
        self.assertGreater(ligne['seances_non_placees'], 0)
        self.assertEqual(ligne['statut'], G.GENERATION_PARTIELLE)
        self.assertEqual(EmploiDuTemps.objects.count(), 0)

        besoins = BM.besoins_depuis_maquette(annee_academique_id=self.annee.pk).besoins
        resultat = G.generate_schedule(
            annee_academique_id=self.annee.pk, besoins=besoins,
            semaines=[1], creneaux=[premier], salles=[self.salle],
        )
        self.assertEqual(len(resultat.placements), 1)
        # Les deux besoins ont la même affectation_pedagogique_id=None :
        # le non-placé doit rester visible et détaillé.
        self.assertEqual(len(resultat.non_places), 1)
        self.assertEqual(resultat.metrics['seances_non_placees'],
                         resultat.non_places[0].besoin.nb_seances)

        # C10 interdit l'écriture d'un plan incomplet : ne pas créer un EDT
        # BROUILLON vide dont le bilan prétendrait qu'il est persisté.
        ecriture = A.generer_annee(self.annee.pk, semaines=[1], persister=True)
        self.assertEqual(ecriture['groupes'][0]['statut'], 'NON_PERSISTE')
        self.assertEqual(ecriture['groupes'][0]['persistance']['motif_refus'],
                         'VALIDATION_BLOQUANTE')
        self.assertGreater(ecriture['totaux']['seances_calculees'], 0)
        self.assertEqual(ecriture['totaux']['seances_placees'], 0)
        self.assertEqual(ecriture['totaux']['edts_persistes'], 0)
        self.assertEqual(ecriture['totaux']['etudiants_couverts'], 0)
        self.assertEqual(EmploiDuTemps.objects.count(), 0)
        self.assertEqual(AffectationCreneau.objects.filter(actif=True).count(), 0)

    def test_salle_cadrage_est_signalee_dans_le_bilan_et_sur_les_affectations(self):
        from datetime import date
        from edts.moteur.calendrier_previsionnel import proposer

        self.annee.date_debut = date(2026, 10, 1)
        self.annee.date_fin = date(2027, 6, 30)
        self.annee.save(update_fields=['date_debut', 'date_fin'])
        ECUE.objects.filter(pk=self.ecue.pk).update(
            volume_cm=2, volume_td=0, volume_tp=0,
        )
        self.salle.fiabilite = 'CADRAGE'
        self.salle.source_document = 'Inventaire ; Estimation heuristique completer_salles'
        self.salle.save(update_fields=['fiabilite', 'source_document'])
        self.importer([f'INJS-{i:03d};Nom{i};{self.formation.intitule};L1;S1;L1-G1;V1'
                       for i in range(5)])

        calendrier = proposer(self.annee)
        bilan = A.generer_annee(
            self.annee.pk,
            semaines=calendrier['impairs'] + calendrier['pairs'],
            calendrier_previsionnel=calendrier,
            persister=True,
        )

        ligne = bilan['groupes'][0]
        self.assertEqual(ligne['affectations_salle_cadrage'], 1)
        self.assertEqual(ligne['salles_cadrage'][0]['nom'], self.salle.nom)
        self.assertEqual(bilan['totaux']['affectations_salle_cadrage'], 1)
        self.assertEqual(
            bilan['totaux']['salles_cadrage_utilisees'][0]['source_document'],
            self.salle.source_document,
        )
        affectation = AffectationCreneau.objects.get(actif=True)
        self.assertIn('CADRAGE', affectation.commentaire)
        self.assertIn('à valider par l’INJS', affectation.commentaire)
        self.assertIn('Estimation heuristique completer_salles', affectation.commentaire)

    def test_seances_non_placees_ne_sont_pas_mal_diagnostiquees_en_repartition(self):
        from datetime import date
        from edts.moteur.calendrier_previsionnel import proposer

        self.annee.date_debut = date(2026, 10, 1)
        self.annee.date_fin = date(2027, 6, 30)
        self.annee.save(update_fields=['date_debut', 'date_fin'])
        ECUE.objects.filter(pk=self.ecue.pk).update(
            volume_cm=2, volume_td=0, volume_tp=2,
        )
        self.importer([f'INJS-{i:03d};Nom{i};{self.formation.intitule};L1;S1;L1-G1;V1'
                       for i in range(5)])
        calendrier = proposer(self.annee)

        bilan = A.generer_annee(
            self.annee.pk,
            semaines=calendrier['impairs'] + calendrier['pairs'],
            calendrier_previsionnel=calendrier,
            persister=True,
        )

        ligne = bilan['groupes'][0]
        self.assertGreater(ligne['seances_placees'], 0)
        self.assertGreater(ligne['seances_non_placees'], 0)
        self.assertEqual(ligne['statut'], 'NON_PERSISTE')
        self.assertEqual(ligne['motif_echec'], 'OCCURRENCES_NON_PLACEES')
        self.assertIsNone(ligne['repartition_verifiee'])
        self.assertEqual(EmploiDuTemps.objects.count(), 0)

        # L'accord explicite sur le calendrier provisoire permet ensuite de
        # garder les placements valides en brouillon, sans blanchir le plan.
        accepte = A.generer_annee(
            self.annee.pk,
            semaines=calendrier['impairs'] + calendrier['pairs'],
            calendrier_previsionnel=calendrier,
            persister=True,
            autoriser_plan_partiel=True,
        )
        ligne_acceptee = accepte['groupes'][0]
        self.assertEqual(accepte['status_global'], A.ANNEE_PARTIELLE)
        self.assertGreater(ligne_acceptee['seances_placees'], 0)
        self.assertGreater(ligne_acceptee['seances_non_placees'], 0)
        self.assertTrue(ligne_acceptee['persistance']['effectuee'])
        self.assertTrue(ligne_acceptee['persistance']['couverture_partielle_acceptee'])
        self.assertEqual(ligne_acceptee['seances_persistees'], ligne_acceptee['seances_placees'])
        self.assertGreater(AffectationCreneau.objects.filter(actif=True).count(), 0)

    def test_besoin_initial_impossible_ne_cache_pas_un_besoin_suivant_faisable(self):
        """Une ECUE sans salle compatible ne condamne pas les autres ECUE."""
        from dataclasses import replace
        from edts.models import CreneauTemplate

        self.importer([f'INJS-001;Nom;{self.formation.intitule};L1;S1;L1-G1;V1'])
        self.salle.type_lieu = 'COURS'
        self.salle.save(update_fields=['type_lieu'])
        besoins = BM.besoins_depuis_maquette(annee_academique_id=self.annee.pk).besoins
        tp_impossible = replace(besoins[0], nature='TP', type_enseignement='TP')
        resultat = G.generate_schedule(
            annee_academique_id=self.annee.pk,
            besoins=[tp_impossible, besoins[1]], semaines=[1],
            creneaux=[CreneauTemplate.objects.order_by('pk').first()],
            salles=[self.salle],
        )
        self.assertEqual(len(resultat.placements), 1)
        self.assertIs(resultat.placements[0].besoin, besoins[1])
        self.assertEqual(len(resultat.non_places), 1)
        self.assertEqual(resultat.status, G.GENERATION_PARTIELLE)

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

    def test_plusieurs_semestres_sans_calendrier_ne_sont_pas_persistes(self):
        from scolarite.models import Semestre

        groupe = self.f.creer_groupe(nom='L1-G1')
        self.f.creer_affectation(volume=2, groupe=groupe)
        semestre_2 = Semestre.objects.create(niveau=self.f.niveau, numero=2,
                                             libelle='S2 test')
        self.f.creer_affectation(volume=2, groupe=groupe, semestre=semestre_2)
        bilan = A.generer_annee(self.annee.pk, semaines=[1, 2, 3, 4],
                                semestre_numeros=[1, 2], persister=True)
        self.assertNotEqual(bilan['status_global'], A.ANNEE_COMPLETE)
        self.assertEqual(bilan['groupes'][0]['motif_echec'],
                         'REPARTITION_ANNUELLE_NON_CONFORME')
        self.assertFalse(AffectationCreneau.objects.filter(actif=True).exists())

    def test_deux_groupes_coordonnes_sur_quatre_semaines(self):
        """Même salle : zéro recouvrement dans une semaine, réemploi entre semaines."""
        self.importer([
            f'A-{i:03d};Nom{i};{self.formation.intitule};L1;S1;L1-G1;V1'
            for i in range(12)
        ] + [
            f'B-{i:03d};Nom{i};{self.formation.intitule};L1;S1;L1-G2;V1'
            for i in range(12)
        ])
        bilan = A.generer_annee(self.annee.pk, semaines=[1, 2, 3, 4],
                                semestre_numeros=[1], persister=True)
        self.assertEqual(bilan['status_global'], A.ANNEE_COMPLETE, bilan['groupes'])
        self.assertEqual(bilan['totaux']['seances_attendues'], 6)
        self.assertEqual(bilan['totaux']['seances_placees'], 6)
        self.assertEqual(bilan['totaux']['edts_persistes'], 2)
        for ligne in bilan['groupes']:
            self.assertEqual(ligne['heures_prevues'], 6)
            self.assertEqual(ligne['heures_recurrentes'], 6)
            self.assertTrue(ligne['persistance']['effectuee'])
        seances = list(AffectationCreneau.objects.filter(actif=True)
                       .select_related('creneau_template'))
        self.assertEqual(len(seances), 6)
        ressources = [(a.semaine_debut, a.creneau_template.jour,
                       a.creneau_template.heure_debut, a.salle_id) for a in seances]
        self.assertEqual(len(ressources), len(set(ressources)))

    def test_pas_de_publication(self):
        self.importer([f'INJS-001;Nom;{self.formation.intitule};L1;S1;L1-G1;V1'])
        bilan = A.generer_annee(self.annee.pk, semaines=[1], persister=True)
        self.assertTrue(bilan['persistence_demandee'])
        edt = EmploiDuTemps.objects.get(pk=bilan['groupes'][0]['edt_id'])
        self.assertEqual(edt.statut, 'BROUILLON')
        self.assertIsNone(edt.publie_le)

    def test_refus_annuel_preserve_un_brouillon_existant(self):
        self.importer([f'INJS-{i:03d};Nom{i};{self.formation.intitule};L1;S1;L1-G1;V1'
                       for i in range(5)])
        premier = A.generer_annee(self.annee.pk, semaines=[1], persister=True)
        self.assertTrue(premier['groupes'][0]['persistance']['effectuee'])
        avant = list(AffectationCreneau.objects.filter(actif=True)
                     .values_list('pk', 'semaine_debut', 'semaine_fin'))
        # Fixture volontairement incohérente (volume non divisible par les
        # créneaux de 2 h) : un refus ne doit pas écraser l'ancien brouillon.
        ECUE.objects.filter(pk=self.ecue.pk).update(volume_cm=5)
        essai = A.generer_annee(self.annee.pk, semaines=[1, 2, 3, 4], persister=True)
        self.assertNotEqual(essai['status_global'], A.ANNEE_COMPLETE)
        self.assertEqual(essai['groupes'][0]['motif_echec'],
                         'REPARTITION_ANNUELLE_NON_CONFORME')
        self.assertEqual(avant, list(AffectationCreneau.objects.filter(actif=True)
                                     .values_list('pk', 'semaine_debut', 'semaine_fin')))
        self.assertEqual(essai['totaux']['edts_persistes'], 0)
        self.assertEqual(essai['totaux']['seances_placees'], 0)
        self.assertGreater(essai['totaux']['seances_calculees'], 0)

    def test_seance_issue_de_maquette_conserve_ecue_jusqu_aux_presences(self):
        from presences.seances_edt_services import ecue_de_seance
        from presences.seances_supervision import _contexte_pedagogique

        self.importer([f'INJS-{i:03d};Nom{i};{self.formation.intitule};L1;S1;L1-G1;V1'
                       for i in range(5)])
        bilan = A.generer_annee(self.annee.pk, semaines=[1], persister=True)
        self.assertTrue(bilan['groupes'][0]['persistance']['effectuee'])
        seances = AffectationCreneau.objects.filter(actif=True)
        self.assertTrue(seances.exists())
        for seance in seances:
            self.assertIsNone(seance.affectation_pedagogique_id)
            self.assertEqual(seance.ecue_id, self.ecue.pk)
            self.assertEqual(ecue_de_seance(seance).pk, self.ecue.pk)
            self.assertEqual(_contexte_pedagogique(seance)['ecue_id'], self.ecue.pk)

    def test_persistance_idempotente(self):
        self.importer([f'INJS-001;Nom;{self.formation.intitule};L1;S1;L1-G1;V1'])
        premier = A.generer_annee(self.annee.pk, semaines=[1], persister=True)
        seances_1 = AffectationCreneau.objects.filter(actif=True).count()
        second = A.generer_annee(self.annee.pk, semaines=[1], persister=True)
        seances_2 = AffectationCreneau.objects.filter(actif=True).count()

        self.assertEqual(premier['groupes'][0]['edt_id'], second['groupes'][0]['edt_id'])
        self.assertEqual(seances_1, seances_2)
        self.assertEqual(EmploiDuTemps.objects.count(), 1)

    def test_refus_ne_reserve_pas_la_salle_et_ne_gonfle_pas_le_bilan(self):
        from unittest.mock import patch
        from edts.models import CreneauTemplate
        from edts.moteur import orchestration as O

        self.importer([
            f'A-{i:03d};Nom{i};{self.formation.intitule};L1;S1;L1-G1;V1'
            for i in range(5)
        ] + [
            f'B-{i:03d};Nom{i};{self.formation.intitule};L1;S1;L1-G2;V1'
            for i in range(7)
        ])
        CreneauTemplate.objects.exclude(jour='LUNDI').delete()
        self.salle.fiabilite = 'CADRAGE'
        self.salle.save(update_fields=['fiabilite'])
        persister_reel = O._persister_si_possible
        appels = []

        def refuser_premier(cible, resultat, *, remplacer, **kwargs):
            appels.append(cible)
            if len(appels) == 1:
                return {'effectuee': False, 'motif_refus': 'VALIDATION_BLOQUANTE'}
            return persister_reel(cible, resultat, remplacer=remplacer, **kwargs)

        with patch.object(O, '_persister_si_possible', side_effect=refuser_premier):
            bilan = A.generer_annee(self.annee.pk, semaines=[1], persister=True)

        premiere, seconde = bilan['groupes']
        self.assertEqual(premiere['statut'], 'NON_PERSISTE')
        self.assertEqual(premiere['seances_placees'], 3)
        self.assertEqual(premiere['seances_persistees'], 0)
        self.assertTrue(seconde['persistance']['effectuee'])
        self.assertEqual(seconde['seances_placees'], 3)
        self.assertEqual(bilan['status_global'], A.ANNEE_PARTIELLE)
        self.assertEqual(bilan['detail']['motifs_groupes'], {'VALIDATION_BLOQUANTE': 1})
        self.assertEqual(bilan['totaux']['edts_persistes'], 1)
        self.assertEqual(bilan['totaux']['seances_calculees'], 6)
        self.assertEqual(bilan['totaux']['seances_placees'], 3)
        self.assertEqual(bilan['totaux']['seances_non_placees'], 3)
        self.assertEqual(bilan['totaux']['etudiants_couverts'], 7)
        self.assertEqual(bilan['totaux']['etudiants_couverts_calcules'], 12)
        self.assertEqual(bilan['totaux']['affectations_salle_cadrage_calculees'], 4)
        self.assertEqual(bilan['totaux']['affectations_salle_cadrage'], 2)
        self.assertEqual(AffectationCreneau.objects.filter(actif=True).count(), 2)

    def test_refus_de_remplacement_conserve_les_occupations_anterieures(self):
        from unittest.mock import patch
        from edts.models import CreneauTemplate
        from edts.moteur import orchestration as O

        self.importer([
            f'A-{i:03d};Nom{i};{self.formation.intitule};L1;S1;L1-G1;V1'
            for i in range(5)
        ] + [
            f'B-{i:03d};Nom{i};{self.formation.intitule};L1;S1;L1-G2;V1'
            for i in range(5)
        ])
        CreneauTemplate.objects.exclude(jour='LUNDI').delete()
        from scolarite.models import Groupe
        groupes = list(Groupe.objects.order_by('nom'))
        premier = A.generer_annee(self.annee.pk, semaines=[1], persister=True,
                                  groupe_ids=[groupes[0].pk])
        self.assertEqual(premier['status_global'], A.ANNEE_COMPLETE)
        anciennes = set(AffectationCreneau.objects.filter(actif=True).values_list('pk', flat=True))
        persister_reel = O._persister_si_possible

        def refuser_cible(cible, resultat, *, remplacer, **kwargs):
            if cible['edt'].population_id == groupes[0].pk:
                return {'effectuee': False, 'motif_refus': 'VALIDATION_BLOQUANTE'}
            return persister_reel(cible, resultat, remplacer=remplacer, **kwargs)

        with patch.object(O, '_persister_si_possible', side_effect=refuser_cible):
            bilan = A.generer_annee(self.annee.pk, semaines=[1], persister=True)
        self.assertEqual(bilan['groupes'][0]['statut'], 'NON_PERSISTE')
        self.assertEqual(bilan['groupes'][1]['seances_placees'], 0)
        self.assertEqual(bilan['totaux']['edts_persistes'], 0)
        self.assertEqual(anciennes, set(AffectationCreneau.objects.filter(actif=True)
                                       .values_list('pk', flat=True)))

    def test_relance_remplace_ses_brouillons_sans_auto_blocage(self):
        from edts.models import CreneauTemplate

        self.importer([
            f'A-{i:03d};Nom{i};{self.formation.intitule};L1;S1;L1-G1;V1'
            for i in range(5)
        ] + [
            f'B-{i:03d};Nom{i};{self.formation.intitule};L1;S1;L1-G2;V1'
            for i in range(5)
        ])
        CreneauTemplate.objects.exclude(jour='LUNDI').delete()
        self.f.creer_salle(nom='Salle B', capacite=60)
        premier = A.generer_annee(self.annee.pk, semaines=[1], persister=True)
        self.assertEqual(premier['status_global'], A.ANNEE_COMPLETE)
        avant = set(AffectationCreneau.objects.filter(actif=True).values_list(
            'groupe_id', 'semaine_debut', 'creneau_template_id', 'salle_id'))
        second = A.generer_annee(self.annee.pk, semaines=[1], persister=True)
        apres = set(AffectationCreneau.objects.filter(actif=True).values_list(
            'groupe_id', 'semaine_debut', 'creneau_template_id', 'salle_id'))
        self.assertEqual(second['status_global'], A.ANNEE_COMPLETE)
        self.assertEqual(second['totaux']['edts_persistes'], 2)
        self.assertEqual(avant, apres)
        self.assertEqual(AffectationCreneau.objects.filter(actif=True).count(), 4)
        self.assertEqual(EmploiDuTemps.objects.count(), 2)

    def test_totaux_planifies_coherents_quand_rien_n_est_place(self):
        """Définitions du bilan : 0 placée ⇒ 0 planifié, 1 non planifié.

        Sans aucune salle au référentiel, le groupe a des besoins mais rien
        n'est placé : il ne doit pas être compté « planifié » (l'écran
        affichait 135 planifiés / 0 non planifiés dans ce cas de figure).
        """
        from formations.models import RefSalle

        self.importer([
            f'INJS-{i:03d};Nom{i};{self.formation.intitule};L1;S1;L1-G1;V1'
            for i in range(10)
        ])
        RefSalle.objects.all().delete()
        bilan = A.generer_annee(self.annee.pk, semaines=[1])

        self.assertEqual(bilan['totaux']['nb_groupes'], 1)
        self.assertEqual(bilan['totaux']['nb_groupes_planifies'], 0)
        self.assertEqual(bilan['totaux']['nb_groupes_non_planifies'], 1)
        self.assertEqual(bilan['totaux']['nb_groupes_complets'], 0)
        self.assertEqual(bilan['status_global'], A.ANNEE_IMPOSSIBLE)
        ligne = bilan['groupes'][0]
        self.assertGreater(ligne['seances_attendues'], 0)
        self.assertEqual(ligne['seances_placees'], 0)
        # Ici le motif « salle » est le vrai : aucune salle n'existe.
        self.assertEqual(ligne['motif_echec'], G.MOTIF_AUCUNE_SALLE_COMPATIBLE)

    def test_groupe_sans_besoins_ne_permet_pas_un_faux_bilan_complet(self):
        from scolarite.models import Groupe, Niveau

        self.importer([f'INJS-001;Nom;{self.formation.intitule};L1;S1;L1-G1;V1'])
        # Même périmètre, mais aucun besoin dérivable pour ce niveau : le
        # premier groupe peut être complet sans que l'année entière le soit.
        niveau, _ = Niveau.objects.get_or_create(
            code='L2', defaults={'libelle': 'Licence 2', 'ordre': 2},
        )
        Groupe.objects.create(
            annee_academique=self.annee, ref_formation=self.formation,
            niveau=niveau, nom='L2-SANS-BESOIN',
        )
        bilan = A.generer_annee(self.annee.pk, semaines=[1])
        self.assertEqual(bilan['totaux']['nb_groupes'], 2)
        self.assertEqual(bilan['totaux']['nb_groupes_complets'], 1)
        self.assertEqual(bilan['totaux']['nb_groupes_non_planifies'], 1)
        self.assertEqual(bilan['status_global'], A.ANNEE_PARTIELLE)
        # Cibler S1 ne fait pas disparaître un groupe sans aucun besoin
        # connu : son semestre ne peut pas être déduit d'un besoin inexistant.
        cible = A.generer_annee(self.annee.pk, semaines=[1], semestre_numeros=[1])
        self.assertEqual(cible['totaux']['nb_groupes_non_planifies'], 1)
        self.assertEqual(cible['status_global'], A.ANNEE_PARTIELLE)

    def test_maquette_active_sans_volumes_signalee_pour_tous_les_groupes(self):
        from scolarite.models import Groupe
        from edts.moteur.campagnes import extraire_anomalies

        # Fixture isolée : des ECUE présentes mais sans volume officiel ne
        # doivent ni inventer des séances ni être déclarées sans maquette.
        ECUE.objects.filter(pk=self.ecue.pk).update(volume_cm=0, volume_td=0)
        for numero in range(51):
            Groupe.objects.create(
                annee_academique=self.annee, ref_formation=self.formation,
                niveau=self.f.niveau, nom=f'L1-SANS-VOLUME-{numero}',
            )
        bilan = A.generer_annee(self.annee.pk, semaines=[1])
        self.assertEqual(bilan['motif_echec'], BM.MOTIF_VOLUMES_ABSENTS)
        self.assertEqual(bilan['totaux']['seances_placees'], 0)
        self.assertEqual(bilan['totaux']['nb_groupes_non_planifies'], 51)
        self.assertEqual({l['motif_echec'] for l in bilan['groupes']},
                         {BM.MOTIF_VOLUMES_ABSENTS})
        self.assertEqual(len(bilan['sources']['maquette']['detail']['sans_volume']), 50)
        self.assertEqual(len(extraire_anomalies(bilan)), 51)
        self.assertIn('volumes', extraire_anomalies(bilan)[-1]['explication'].lower())

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
        self.assertEqual(ligne['motif_echec'], BM.MOTIF_AUCUNE_MAQUETTE)
        self.assertEqual(bilan['status_global'], A.ANNEE_IMPOSSIBLE)

        # Une année impossible doit expliquer POURQUOI au niveau global, et
        # indiquer l'action à mener : « Impossible » sans motif n'est pas
        # exploitable par un secrétariat.
        self.assertEqual(bilan['motif_echec'], BM.MOTIF_AUCUNE_MAQUETTE)
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

    def test_filtre_formations_restraint_le_perimetre(self):
        """Une campagne à périmètre « formations » ne génère que ces formations.

        Sans ce filtre, ``generer_annee`` traitait toute l'année : une
        campagne ciblée régénérait (et remplaçait) les EDT des autres
        formations — incohérence corrigée par le paramètre ``formation_ids``.
        """
        autre = FabriqueLMD(self).creer_base(perimetre='INJS', filiere='F02', suffixe='2')
        maquette2, _ue2, ecue2 = autre.creer_maquette()
        ecue2.volume_cm = 4
        ecue2.volume_td = 2
        ecue2.save()
        from scolarite.models import Maquette

        maquette2.statut = Maquette.Statut.ACTIVE
        maquette2.save()

        self.importer([f'A-{i:03d};Nom;{self.formation.intitule};L1;S1;L1-G1;V1'
                       for i in range(10)])
        self.importer([f'B-{i:03d};Nom;{autre.cycle.intitule};L1;S1;L1-G1;V1'
                       for i in range(10)])

        bilan = A.generer_annee(self.annee.pk, semaines=[1],
                                formation_ids=[self.formation.pk])
        self.assertEqual(bilan['formations_filtrees'], [self.formation.pk])
        self.assertEqual(bilan['totaux']['nb_groupes'], 1)
        self.assertEqual(bilan['groupes'][0]['formation'], self.formation.intitule)

        bilan_complet = A.generer_annee(self.annee.pk, semaines=[1])
        self.assertIsNone(bilan_complet['formations_filtrees'])
        self.assertEqual(bilan_complet['totaux']['nb_groupes'], 2)


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


class BilanContraintesSouplesTests(BaseAnneeTest):
    """Le bilan annuel doit refléter les règles souples, sinon elles sont invisibles.

    L'INJS arbitre au niveau de l'année, pas du groupe. Une politique activée
    dans l'administration doit donc apparaître dans ce que la direction lit :
    nombre de trous, de séries trop longues, de journées surchargées, et
    pénalités produites. Le contrôle est fait dans les deux régimes.
    """

    def setUp(self):
        super().setUp()
        from edts.models import PolitiqueContraintesSouples

        self.Politique = PolitiqueContraintesSouples

    def _bilan(self):
        self.importer([
            f'INJS-{i:03d};Nom{i};{self.formation.intitule};L1;S1;L1-G1;V1'
            for i in range(30)
        ])
        return A.generer_annee(self.annee.pk, semaines=[1])

    def test_regime_inactif_par_defaut_ne_signale_rien(self):
        bilan = self._bilan()
        souples = bilan['totaux']['contraintes_souples']
        self.assertFalse(souples['active'])
        self.assertEqual(souples['trous'], 0)
        self.assertEqual(souples['penalites'], 0)
        # La ligne par groupe porte aussi le détail (utile au diagnostic).
        self.assertFalse(bilan['groupes'][0]['contraintes_souples']['active'])

    def test_politique_activee_dans_l_admin_remonte_dans_le_bilan(self):
        # Borne à 1 h : toute séance de 2 h dépasse, donc chaque journée
        # travaillée est signalée. Un bloc récurrent ne compte qu'une fois par
        # semaine (c'est un créneau), c'est pourquoi la borne doit être basse.
        self.Politique.objects.update_or_create(
            pk=1, defaults={'actives': True, 'max_heures_par_jour': 1,
                            'motif': 'Test bilan annuel.'})
        bilan = self._bilan()
        souples = bilan['totaux']['contraintes_souples']
        self.assertTrue(souples['active'])
        self.assertGreaterEqual(souples['journees_surchargees'], 1)
        self.assertGreaterEqual(souples['penalites'], 1)
        self.assertEqual(bilan['groupes'][0]['penalites_souples'],
                         souples['penalites'])

    def test_les_penalites_ne_retirent_aucune_seance_du_bilan(self):
        """Preuve à l'échelle annuelle : la politique ne bloque jamais."""
        temoin = self._bilan()
        self.Politique.objects.update_or_create(
            pk=1, defaults={'actives': True, 'max_heures_par_jour': 1,
                            'max_heures_consecutives': 1})
        avec = self._bilan()
        self.assertEqual(avec['totaux']['seances_placees'],
                         temoin['totaux']['seances_placees'])
        self.assertEqual(avec['totaux']['seances_non_placees'],
                         temoin['totaux']['seances_non_placees'])
        self.assertEqual(avec['status_global'], temoin['status_global'])

class CalendrierProvisoireTests(BaseAnneeTest):
    def test_un_groupe_ne_genere_quune_salle_candidate_par_creneau(self):
        from unittest.mock import patch

        from edts.moteur.besoins import TeachingNeed
        from edts.models import CreneauTemplate

        besoin = TeachingNeed(
            affectation_pedagogique_id=1,
            annee_academique_id=self.annee.pk,
            ref_formation_id=self.formation.pk,
            parcours_id=None,
            niveau_id=self.f.niveau.pk,
            semestre_id=None,
            groupe_id=1,
            ue_id=1,
            ecue_id=1,
            enseignant_id=None,
            type_enseignement='CM',
            nature='COURS',
            intitule='ECUE test',
            volume_horaire=2,
            credits=0,
            effectif=20,
            duree_seance_heures=2,
            nb_seances=1,
        )
        creneaux = list(CreneauTemplate.objects.order_by('jour', 'heure_debut'))
        salles = [
            self.salle,
            self.f.creer_salle(nom='Salle B', capacite=60),
        ]
        candidats_observes = []
        generer_candidats = G.candidats

        def observer_candidats(*args):
            resultat = generer_candidats(*args)
            contexte = args[1]
            candidats_observes.append((
                contexte['salle_unique_par_creneau'],
                len(resultat[0]),
                resultat[3],
            ))
            return resultat

        with patch.object(G, 'candidats', side_effect=observer_candidats):
            resultat = G.generate_schedule(
                annee_academique_id=self.annee.pk,
                semaines=[1],
                besoins=[besoin],
                creneaux=creneaux,
                salles=salles,
            )

        self.assertEqual(resultat.status, G.GENERATION_OK)
        self.assertEqual(len(resultat.placements), 1)
        self.assertEqual(candidats_observes, [
            (True, len(creneaux), len(creneaux)),
        ])

    def test_occurrences_sont_equilibrees_entre_les_semaines_du_semestre(self):
        from types import SimpleNamespace
        from unittest.mock import patch

        from edts.moteur.besoins import TeachingNeed

        def besoin(index, nb_seances):
            return TeachingNeed(
                affectation_pedagogique_id=index,
                annee_academique_id=self.annee.pk,
                ref_formation_id=self.formation.pk,
                parcours_id=None,
                niveau_id=self.f.niveau.pk,
                semestre_id=self.f.semestre.pk,
                groupe_id=1,
                ue_id=1,
                ecue_id=index,
                enseignant_id=None,
                type_enseignement='CM',
                nature='COURS',
                intitule=f'ECUE {index}',
                volume_horaire=nb_seances * 2,
                credits=0,
                effectif=20,
                duree_seance_heures=2,
                nb_seances=nb_seances,
            )

        semaines = list(range(1, 23))
        besoins = [besoin(index, 1) for index in range(32)]
        besoins.append(besoin(33, 2))
        resultat_factice = SimpleNamespace(
            placements=[], non_places=[], warnings=[],
            metrics={'creneaux_explores': 0},
        )
        with patch.object(G, 'generate_schedule', return_value=resultat_factice) as generer:
            A._generer_occurrences_par_semaine(
                annee_id=self.annee.pk,
                groupe_id=1,
                semaines=semaines,
                besoins=besoins,
                occupations=[],
                creneaux=[],
                budget=100,
                politique={},
            )

        occurrences_par_semaine = {
            appel.kwargs['semaines'][0]: len(appel.kwargs['besoins'])
            for appel in generer.call_args_list
        }
        self.assertEqual(set(occurrences_par_semaine), set(semaines))
        self.assertEqual(sum(occurrences_par_semaine.values()), 34)
        self.assertLessEqual(max(occurrences_par_semaine.values()), 2)

    def test_deux_semestres_restent_dans_deux_brouillons_sans_ecrasement(self):
        from datetime import date
        from scolarite.models import Semestre
        from edts.moteur.calendrier_previsionnel import proposer

        self.annee.date_debut = date(2026, 9, 1)
        self.annee.date_fin = date(2027, 5, 31)
        self.annee.save(update_fields=['date_debut', 'date_fin'])
        f2 = FabriqueLMD(self).creer_base(perimetre='INJS', filiere='F02', suffixe='S2')
        f2.semestre, _ = Semestre.objects.get_or_create(
            niveau=self.f.niveau, numero=2, defaults={'libelle': 'S2'})
        f2.creer_salle(nom='Salle B', capacite=60)
        maquette2, _, ecue2 = f2.creer_maquette()
        ecue2.volume_cm, ecue2.volume_td = 4, 2
        ecue2.save()
        maquette2.statut = Maquette.Statut.ACTIVE
        maquette2.save()
        self.importer([
            f'INJS-{i:03d};Nom{i};{self.formation.intitule};L1;S1;L1-G1;V1'
            for i in range(6)
        ] + [
            f'INJS-S2-{i:03d};Nom{i};{f2.cycle.intitule};L1;S2;L1-G2;V1'
            for i in range(6)
        ])
        calendrier = proposer(self.annee)
        bilan = A.generer_annee(
            self.annee.pk, semaines=calendrier['impairs'] + calendrier['pairs'],
            calendrier_previsionnel=calendrier, persister=True, budget=1500,
        )
        self.assertEqual(bilan['status_global'], A.ANNEE_COMPLETE, bilan)
        self.assertEqual(bilan['totaux']['edts_persistes'], 2)
        seances = list(AffectationCreneau.objects.filter(actif=True))
        self.assertEqual(len(seances), 6)
        self.assertEqual({a.emploi_du_temps_id for a in seances},
                         set(EmploiDuTemps.objects.values_list('id', flat=True)))
        self.assertTrue(all(a.semaine_debut == a.semaine_fin for a in seances))
        self.assertTrue(all(a.semaine_debut in calendrier['impairs']
                            for a in seances if a.ecue_id == self.ecue.pk))
        self.assertTrue(all(a.semaine_debut in calendrier['pairs']
                            for a in seances if a.ecue_id == ecue2.pk))
        self.assertEqual(set(EmploiDuTemps.objects.values_list('statut', flat=True)),
                         {'BROUILLON'})
        # Une relance ne doit jamais modifier un EDT déjà validé.
        EmploiDuTemps.objects.update(statut='VALIDE')
        ids_avant = set(AffectationCreneau.objects.filter(actif=True)
                        .values_list('id', flat=True))
        refus = A.generer_annee(self.annee.pk,
                               semaines=calendrier['impairs'] + calendrier['pairs'],
                               calendrier_previsionnel=calendrier, persister=True)
        self.assertEqual(ids_avant, set(AffectationCreneau.objects.filter(actif=True)
                                        .values_list('id', flat=True)))
        self.assertEqual(refus['totaux']['edts_persistes'], 0)
        self.assertEqual(refus['totaux']['seances_placees'], 0)
        self.assertEqual(refus['totaux']['etudiants_couverts'], 0)
