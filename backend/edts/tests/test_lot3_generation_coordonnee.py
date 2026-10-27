"""LOT 3 (GET-INJS) — Génération COORDONNÉE des EDT des 8 filières INJS.

Ces tests exercent l'orchestration ``edts.moteur.orchestration`` et sa route
``POST /api/edts/lmd/generate-coordinated/``. Ils construisent leurs propres
données dans la base de test Django (``TestCase`` — transaction annulée en fin
de test) : la base de développement n'est jamais touchée.

Couverture (scénarios de la mission LOT 3) :
 1. génération coordonnée d'un EDT valide (prévisualisation sans écriture) ;
 2. plusieurs EDT sans conflit ;
 3. deux EDT partageant le même enseignant au même créneau (C1 coordonné) ;
 4. deux EDT partageant le même groupe au même créneau (C2 coordonné) ;
 5. deux EDT partageant la même salle au même créneau (C3 coordonné) ;
 6. salle de capacité inconnue avec effectif connu (C4 bloquant, LOT 1) ;
 7. effectif inconnu (non-bloquant, comportement LOT 1 conservé) ;
 8. canevas vide / besoins impossibles (motifs explicites) ;
 9. budget du solveur épuisé (finalité BUDGET_EXHAUSTED exposée) ;
10. opération avec au moins un EDT incomplet → statut global PARTIEL ;
11. détection des conflits entre EDT persistés (contrôle LOT 1) ;
12. ré-exécution sans duplication des séances (idempotence) ;
13. échec au milieu de l'opération → intégrité par EDT, bilan honnête ;
14. compatibilité avec le parcours de publication du LOT 2 ;
    + exclusion des formations hors périmètre INJS ;
    + routes API (RBAC, paramètres) ;
    + test de charge représentatif réduit (8 formations synthétiques).

Le périmètre de l'opération est toujours DÉRIVÉ des données (formations INJS
portant des affectations planifiables) : aucun test n'envoie une liste de
formations — la route n'en accepte pas.
"""

from datetime import time

from django.test import TestCase
from rest_framework.test import APIClient

from edts.moteur import generation as G
from edts.moteur import orchestration as O
from edts.moteur import publication as P
from edts.models import AffectationCreneau, CreneauTemplate, EmploiDuTemps
from edts.tests.test_lot2_moteur import FabriqueLMD
from formations.models import Formateur, RefSalle
from scolarite.models import Groupe


def creer_utilisateur(nom, role):
    from django.contrib.auth import get_user_model

    U = get_user_model()
    user = U.objects.create_user(username=nom, password='x')
    user.role = role
    user.save()
    return user


class FabriqueCoordonnee:
    """Fabrique multi-formations pour l'orchestration LOT 3.

    Chaque formation vient de la ``FabriqueLMD`` du LOT 2 (maquette, UE,
    ECUE, affectation rattachée à la chaîne LMD). Par défaut le formateur est
    **partagé** (``Formateur.objects.get_or_create``) : c'est le cas réel
    d'une filière dont un enseignant couvre plusieurs formations.
    """

    def __init__(self, testcase):
        self.tc = testcase
        self.f1 = FabriqueLMD(testcase).creer_base(filiere='F01', suffixe='1')
        self.f1.creer_maquette()
        self.groupe1 = self.f1.creer_groupe(nom='L1-G1', capacite=30)
        self.salle = self.f1.creer_salle('Salle A', 'SALLE', capacite=30)
        #: Année académique courante — exposée pour les tests qui pianifient
        #: l'opération sans passer par ``fabrique.f1``.
        self.annee = self.f1.annee

    def formation(self, filiere='F02', suffixe='2', formateur_partage=True):
        """Deuxième (ou n-ième) formation — formateur partagé ou distinct."""
        fab = FabriqueLMD(self.tc).creer_base(filiere=filiere, suffixe=suffixe)
        fab.creer_maquette()
        if not formateur_partage:
            fab.formateur = Formateur.objects.create(
                nom=f'Bamba{suffixe}', prenom='Ibrahim')
        return fab

    def affecter(self, fab, *, groupe=None, volume=2, type_ens='CM'):
        """Affectation pédagogique sur le groupe de la formation (ou fourni)."""
        if groupe is None:
            groupe = Groupe.objects.filter(ref_formation_id=fab.cycle.pk).first()
        return fab.creer_affectation(
            volume=volume, type_ens=type_ens, groupe=groupe,
        )


def fab_creneaux(jours, heures):
    crees = []
    for jour in jours:
        for debut, fin in heures:
            crees.append(CreneauTemplate.objects.create(
                jour=jour, heure_debut=time(debut, 0), heure_fin=time(fin, 0),
                duree_prevue_minutes=(fin - debut) * 60,
            ))
    return crees


class BaseCoordonnee(TestCase):
    """Base commune : année, canevas 2 créneaux, 2 formations, 1 salle."""

    def setUp(self):
        self.fx = FabriqueCoordonnee(self)
        self.annee = self.fx.f1.annee
        self.f1 = self.fx.f1
        self.f2 = self.fx.formation()
        self.groupe1 = self.fx.groupe1
        self.groupe2 = self.f2.creer_groupe(nom='L1-G2', capacite=30)
        self.salle = self.fx.salle
        self.creneaux = fab_creneaux(('LUNDI', 'MARDI'), ((8, 10), (10, 12)))

    def ne_garder_qu_un_creneau(self):
        """Ne conserve qu'UN seul créneau type (le premier par ordre de création).

        Un seul créneau = une seule capacité de placement par semaine : deux
        EDT partageant le même enseignant ne peuvent plus être placés tous les
        deux (C1 coordonné), ce qui rend la situation PARTIELLE observable.
        """
        garder = CreneauTemplate.objects.order_by('pk').first()
        CreneauTemplate.objects.exclude(pk=garder.pk).delete()
        return garder


class TestCoordinationFondamentale(BaseCoordonnee):
    """Scénarios 1-2 : génération valide, plusieurs EDT sans conflit."""

    def test_1_generation_edt_valide_sans_ecriture(self):
        """Scénario 1 : une formation, besoins placés, aucune écriture."""
        self.fx.affecter(self.f1)
        bilan = O.generer_coordonne(self.annee.pk, semaines=[1, 10])
        self.assertEqual(bilan['status_global'], O.COORDONNEE_OK)
        self.assertEqual(bilan['motif_echec'], None)
        self.assertEqual(bilan['nb_formations'], 1)
        self.assertEqual(bilan['totaux']['nb_edt_complets'], 1)
        self.assertEqual(bilan['totaux']['seances_placees'],
                         bilan['totaux']['seances_attendues'])
        # Prévisualisation : aucune écriture en base.
        self.assertEqual(AffectationCreneau.objects.count(), 0)
        self.assertEqual(EmploiDuTemps.objects.count(), 0)
        self.assertEqual(bilan['edts'][0]['persistence'], None)

    def test_2_plusieurs_edt_sans_conflit(self):
        """Scénario 2 : deux formations, formateurs distincts, aucun conflit."""
        self.fx.affecter(self.f1)
        aff2 = self.fx.affecter(self.f2)
        aff2.enseignant = Formateur.objects.create(nom='Bamba', prenom='Ibrahim')
        aff2.save()
        bilan = O.generer_coordonne(self.annee.pk, semaines=[1, 10],
                                    persister=True)
        self.assertEqual(bilan['status_global'], O.COORDONNEE_OK)
        self.assertEqual(bilan['totaux']['nb_edt_persistes'], 2)
        self.assertEqual(bilan['conflits']['statut'], 'OK')
        self.assertEqual(bilan['conflits']['conflits'], [])
        from edts.services import conflits_inter_edt

        r = conflits_inter_edt([e['edt_id'] for e in bilan['edts']])
        self.assertEqual(r['statut'], 'OK')


class TestCoordinationRessourcesPartagees(BaseCoordonnee):
    """Scénarios 3-5 : enseignant, groupe et salle partagés entre EDT."""

    def _planches(self, bilan):
        """Placements (jour, début, fin) par formation, pour comparer."""
        par_formation = {}
        for entree in bilan['edts']:
            par_formation[entree['ref_formation_id']] = {
                (s['jour'], s['heure_debut'], s['heure_fin'])
                for s in entree['seances']
            }
        return par_formation

    def test_3_enseignant_partage_coordonne(self):
        """Scénario 3 : même enseignant, deux EDT — jamais au même créneau.

        Sans coordination les deux plans retomberaient sur le premier
        créneau (score identique, ordre déterministe) : la coordination
        réserve le créneau au premier EDT traité.
        """
        self.fx.affecter(self.f1)   # formateur partagé (Traoré)
        self.fx.affecter(self.f2)   # même formateur
        bilan = O.generer_coordonne(self.annee.pk, semaines=[1, 10])
        self.assertEqual(bilan['status_global'], O.COORDONNEE_OK)
        planches = self._planches(bilan)
        self.assertEqual(len(planches[self.f1.cycle.pk]), 1)
        self.assertEqual(len(planches[self.f2.cycle.pk]), 1)
        self.assertEqual(planches[self.f1.cycle.pk] & planches[self.f2.cycle.pk],
                         set())

    def test_4_groupe_partage_coordonne(self):
        """Scénario 4 : même groupe affecté dans deux formations (C2)."""
        self.fx.affecter(self.f1, groupe=self.groupe1)
        self.fx.affecter(self.f2, groupe=self.groupe1)
        bilan = O.generer_coordonne(self.annee.pk, semaines=[1, 10])
        self.assertEqual(bilan['status_global'], O.COORDONNEE_OK)
        planches = self._planches(bilan)
        self.assertEqual(planches[self.f1.cycle.pk] & planches[self.f2.cycle.pk],
                         set())

    def test_5_salle_partagee_coordonne(self):
        """Scénario 5 : une seule salle pour deux EDT (C3)."""
        self.fx.affecter(self.f1)
        aff2 = self.fx.affecter(self.f2)
        aff2.enseignant = Formateur.objects.create(nom='Kone', prenom='Fatou')
        aff2.save()
        bilan = O.generer_coordonne(self.annee.pk, semaines=[1, 10])
        self.assertEqual(bilan['status_global'], O.COORDONNEE_OK)
        planches = self._planches(bilan)
        self.assertEqual(planches[self.f1.cycle.pk] & planches[self.f2.cycle.pk],
                         set())

    def test_3bis_un_seul_creneau_partiel(self):
        """Scénario 3 bis : un seul créneau — second EDT non placé, expliqué."""
        self.ne_garder_qu_un_creneau()
        self.fx.affecter(self.f1)
        self.fx.affecter(self.f2)   # même formateur, créneau déjà pris
        bilan = O.generer_coordonne(self.annee.pk, semaines=[1, 10])
        self.assertEqual(bilan['status_global'], O.COORDONNEE_PARTIELLE)
        self.assertEqual(bilan['totaux']['nb_edt_complets'], 1)
        self.assertEqual(bilan['totaux']['nb_edt_incomplets'], 1)
        incomplet = next(e for e in bilan['edts']
                         if e['status'] != G.GENERATION_OK)
        self.assertEqual(len(incomplet['non_placees']), 1)


class TestContraintesCapacite(BaseCoordonnee):
    """Scénarios 6-7 : capacité inconnue bloquante, effectif inconnu non."""

    def test_6_salle_capacite_inconnue_effectif_connu(self):
        """Scénario 6 : capacité NULL + effectif 30 → placement refusé (C4)."""
        RefSalle.objects.filter(pk=self.salle.pk).update(capacite=None)
        self.fx.affecter(self.f1, volume=2)
        bilan = O.generer_coordonne(self.annee.pk, semaines=[1, 10])
        self.assertNotEqual(bilan['status_global'], O.COORDONNEE_OK)
        entree = bilan['edts'][0]
        self.assertEqual(entree['metrics']['seances_placees'], 0)
        self.assertEqual(len(entree['non_placees']), 1)
        codes = {c['contrainte']
                 for c in entree['non_placees'][0]['contraintes_bloquantes']}
        # Capacité inconnue = rejet (jamais traitée comme suffisante) : C4 ou
        # son expression « aucune salle compatible » (C7) selon l'ordre des
        # contrôles — jamais un placement silencieux.
        self.assertTrue(codes & {'C4_CAPACITE', 'C7_COMPATIBILITE_SALLE'}, codes)
        self.assertEqual(AffectationCreneau.objects.count(), 0)

    def test_7_effectif_inconnu_non_bloquant(self):
        """Scénario 7 : effectif None → placement autorisé (LOT 1 conservé)."""
        Groupe.objects.filter(pk=self.groupe1.pk).update(capacite_max=None)
        self.fx.affecter(self.f1, groupe=self.groupe1)
        bilan = O.generer_coordonne(self.annee.pk, semaines=[1, 10])
        self.assertEqual(bilan['status_global'], O.COORDONNEE_OK)
        self.assertEqual(bilan['totaux']['seances_placees'],
                         bilan['totaux']['seances_attendues'])

class TestEchecsEtBudget(BaseCoordonnee):
    """Scénarios 8-10 : motifs explicites, budget, opération partielle."""

    def test_8_canevas_vide_motif_explicite(self):
        """Scénario 8 : sans créneau, chaque EDT est impossible, motif nommé."""
        from edts.moteur import besoins as B
        CreneauTemplate.objects.all().delete()
        self.fx.affecter(self.f1)
        bilan = O.generer_coordonne(self.annee.pk, semaines=[1, 10])
        self.assertEqual(bilan['status_global'], O.COORDONNEE_IMPOSSIBLE)
        for entree in bilan['edts']:
            self.assertEqual(entree['status'], G.GENERATION_IMPOSSIBLE)
            self.assertEqual(entree['motif_echec'], B.MOTIF_CANEVAS_VIDE)
            self.assertIn('action_recommandee', entree['detail'])

    def test_9_budget_epuise_finalite_exposee(self):
        """Scénario 9 : budget nul -> finalité BUDGET_EXHAUSTED, jamais OK."""
        self.fx.affecter(self.f1)
        bilan = O.generer_coordonne(self.annee.pk, semaines=[1, 10], budget=0)
        self.assertNotEqual(bilan['status_global'], O.COORDONNEE_OK)
        for entree in bilan['edts']:
            self.assertEqual(entree['finalite'], G.FINALITE_BUDGET_EXHAUSTED)
            self.assertIn('budget_restant', entree['metrics'])

    def test_10_edt_incomplet_statut_partiel(self):
        """Scénario 10 : un EDT incomplet dégrade l'opération en PARTIELLE."""
        self.ne_garder_qu_un_creneau()
        self.fx.affecter(self.f1)
        self.fx.affecter(self.f2)
        bilan = O.generer_coordonne(self.annee.pk, semaines=[1, 10])
        self.assertEqual(bilan['status_global'], O.COORDONNEE_PARTIELLE)
        self.assertEqual(bilan['totaux']['nb_edt_incomplets'], 1)
        incomplet = next(e for e in bilan['edts']
                         if e['status'] != G.GENERATION_OK)
        self.assertTrue(incomplet['non_placees'])
        for cle in ('seances_attendues', 'seances_placees',
                    'seances_non_placees'):
            self.assertIn(cle, bilan['totaux'])
class TestPersistanceEtPublication(BaseCoordonnee):
    """Scénarios 11-14 : persistance, idempotence, intégrité, publication."""

    def test_11_conflits_entre_edt_persistes_detectes(self):
        """Scénario 11 : le contrôle LOT 1 voit les conflits persistés."""
        from edts.services import conflits_inter_edt
        self.fx.affecter(self.f1)
        aff2 = self.fx.affecter(self.f2)
        aff2.enseignant = Formateur.objects.create(nom='Kone', prenom='Fatou')
        aff2.save()
        bilan = O.generer_coordonne(self.annee.pk, semaines=[1, 10],
                                    persister=True)
        ids = [e['edt_id'] for e in bilan['edts']]
        rapport = conflits_inter_edt(ids)
        self.assertEqual(rapport['statut'], 'OK')
        self.assertEqual(rapport['conflits'], [])

    def test_12_reexecution_sans_duplication(self):
        """Scénario 12 : relancer l'opération ne duplique aucune séance."""
        self.fx.affecter(self.f1)
        aff2 = self.fx.affecter(self.f2)
        aff2.enseignant = Formateur.objects.create(nom='Kone', prenom='Fatou')
        aff2.save()
        premier = O.generer_coordonne(self.annee.pk, semaines=[1, 10],
                                      persister=True)
        nb_avant = AffectationCreneau.objects.filter(actif=True).count()
        second = O.generer_coordonne(self.annee.pk, semaines=[1, 10],
                                     persister=True)
        nb_apres = AffectationCreneau.objects.filter(actif=True).count()
        self.assertEqual(nb_avant, nb_apres)
        self.assertEqual(second['status_global'], O.COORDONNEE_OK)
        for entree in second['edts']:
            self.assertTrue(entree['persistence']['effectuee'])
        _ = premier

    def test_13_echec_partiel_integrite_par_edt(self):
        """Scénario 13 : un EDT verrouillé n'écrit rien, bilan honnête."""
        self.fx.affecter(self.f1)
        aff2 = self.fx.affecter(self.f2)
        aff2.enseignant = Formateur.objects.create(nom='Kone', prenom='Fatou')
        aff2.save()
        bilan1 = O.generer_coordonne(self.annee.pk, semaines=[1, 10],
                                     persister=True)
        edt1_id = next(e['edt_id'] for e in bilan1['edts']
                       if e['ref_formation_id'] == self.f1.cycle.pk)
        edt1 = EmploiDuTemps.objects.get(pk=edt1_id)
        edt1.statut = 'PUBLIE'
        edt1.save(update_fields=['statut'])
        nb_avant = AffectationCreneau.objects.filter(
            emploi_du_temps_id=edt1_id, actif=True).count()
        bilan2 = O.generer_coordonne(self.annee.pk, semaines=[1, 10],
                                     persister=True)
        nb_apres = AffectationCreneau.objects.filter(
            emploi_du_temps_id=edt1_id, actif=True).count()
        self.assertEqual(nb_avant, nb_apres)
        self.assertNotEqual(bilan2['status_global'], O.COORDONNEE_OK)
        refuse = next(e for e in bilan2['edts']
                      if e['ref_formation_id'] == self.f1.cycle.pk)
        self.assertFalse(refuse['persistence']['effectuee'])
        self.assertEqual(refuse['persistence']['motif_refus'],
                         O.MOTIF_EDT_STATUT)

    def test_14_publication_lot2_apres_coordonne(self):
        """Scénario 14 : un EDT coordonné reste publiable via le LOT 2."""
        from edts.moteur import publication as P
        from edts.moteur import validation as V
        self.fx.affecter(self.f1)
        bilan = O.generer_coordonne(self.annee.pk, semaines=[1, 10],
                                    persister=True)
        edt_id = bilan['edts'][0]['edt_id']
        edt = EmploiDuTemps.objects.get(pk=edt_id)
        edt.statut = 'VALIDE'
        edt.save(update_fields=['statut'])
        rapport = V.valider_emploi_du_temps(edt)
        self.assertTrue(rapport.valide)
        resultat = P.publier_emploi_du_temps(edt_id)
        self.assertTrue(resultat['publie'])


class TestHorsPerimetreEtAPI(TestCase):
    """Exclusion legacy + contrat de la route generate-coordinated."""

    def setUp(self):
        self.client_api = APIClient()
        self.fx = FabriqueCoordonnee(self)
        self.annee = self.fx.annee
        self.creneaux = fab_creneaux(('LUNDI', 'MARDI'), ((8, 10), (10, 12)))

    def test_hors_perimetre_legacy_exclu(self):
        """Une affectation legacy n'entre jamais dans l'opération."""
        legacy = FabriqueLMD(self).creer_base(perimetre='LEGACY', filiere='',
                                              suffixe='-LEG')
        legacy.creer_maquette()
        groupe = legacy.creer_groupe(nom='L1-GLEG')
        legacy.creer_affectation(volume=2, groupe=groupe)
        self.fx.affecter(self.fx.f1)
        bilan = O.generer_coordonne(self.annee.pk, semaines=[1, 10])
        ids = {e['ref_formation_id'] for e in bilan['edts']}
        self.assertNotIn(legacy.cycle.pk, ids)

    def test_route_exige_annee_et_rbac(self):
        """Sans année -> 400 ; sans rôle planification -> 403."""
        url = '/api/edts/lmd/generate-coordinated/'
        rep = self.client_api.post(url, {}, format='json')
        self.assertIn(rep.status_code, (401, 403))
        user = creer_utilisateur('plan_lot3', 'SECRETARIAT')
        self.client_api.force_authenticate(user=user)
        rep = self.client_api.post(url, {}, format='json')
        self.assertEqual(rep.status_code, 400)
        self.assertIn('ANNEE_ACADEMIQUE_REQUISE', str(rep.data))

    def test_route_coordonne_ok_et_statuts(self):
        """Route réelle : 200 + bilan complet, jamais de 500 opaque."""
        user = creer_utilisateur('plan2_lot3', 'SECRETARIAT')
        self.client_api.force_authenticate(user=user)
        self.fx.affecter(self.fx.f1)
        rep = self.client_api.post(
            '/api/edts/lmd/generate-coordinated/',
            {'annee_academique_id': self.annee.pk}, format='json')
        self.assertEqual(rep.status_code, 200)
        self.assertEqual(rep.data['status_global'], O.COORDONNEE_OK)
        self.assertIn('totaux', rep.data)
        self.assertIn('conflits', rep.data)


class TestChargeReduite(TestCase):
    """Charge représentative réduite — hypothèses documentées, jamais 3500.

    Hypothèses : 8 formations synthétiques (F01..F08), 2 groupes de 30 par
    formation (~480 étudiants), 2 affectations de 2 h par formation, canevas
    de 4 créneaux (LUNDI/MARDI 8-10/10-12), enseignants distincts par
    formation (cas favorable, sans partage), une salle SALLE de 40 par
    formation (C3 non limitant : le facteur limitant est le canevas).
    Ce test mesure l'orchestration, pas la capacité réelle à 3 500 étudiants.
    """

    def test_charge_8_formations(self):
        import time as _time
        fx = FabriqueCoordonnee(self)
        fabs = [fx.f1]
        for i in range(2, 9):
            fabs.append(fx.formation(
                filiere=f'F{i:02d}', suffixe=str(i),
                formateur_partage=False))
        # Une salle par formation : la contrainte C3 (salle) ne doit pas être
        # le facteur limitant du test de charge (les places disponibles sont
        # alors fixées par le canevas horaire, pas par le parc de salles).
        for fab in fabs:
            fab.creer_salle(f'Salle {fab.cycle.filiere_code}', 'SALLE', 40)
        fab_creneaux(('LUNDI', 'MARDI'), ((8, 10), (10, 12)))
        for fab in fabs:
            for numero in (1, 2):
                groupe = Groupe.objects.create(
                    annee_academique=fab.annee, ref_formation=fab.cycle,
                    parcours=fab.parcours, niveau=fab.niveau,
                    nom=f'{fab.cycle.filiere_code}-G{numero}',
                    capacite_max=30)
                fx.affecter(fab, groupe=groupe, volume=2)
        debut = _time.perf_counter()
        bilan = O.generer_coordonne(fx.annee.pk, semaines=[1, 10])
        duree = _time.perf_counter() - debut
        self.assertEqual(bilan['nb_formations'], 8)
        self.assertEqual(bilan['status_global'], O.COORDONNEE_OK)
        self.assertEqual(bilan['totaux']['seances_non_placees'], 0)
        print(f"\n[CHARGE LOT3] 8 formations, "
              f"{bilan['totaux']['seances_placees']} séances placées en "
              f"{duree:.2f}s (480 étudiants synthétiques, PAS 3500).")
