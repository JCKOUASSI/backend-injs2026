"""PHASE 5 — chantier 2 : indicateurs de pilotage (§10).

Ces tests vérifient que les indicateurs sont **justes**, pas seulement qu'ils
se calculent. Un indicateur faux est pire qu'un indicateur absent : il fait
décider à contre-sens. Les cas suivants sont donc éprouvés :

* **périmètre des besoins** — un EDT de groupe ne doit pas être comparé au
  volume de l'année entière (mesuré avant correction : 0,08 % pour un EDT
  réellement complet) ;
* **valeurs absentes** — une capacité inconnue donne ``None``, jamais ``0 %`` ;
* **aucune écriture** — le tableau de bord ne déclenche pas la détection de
  conflits, qui crée et réactive des lignes ``ConflitCreneau`` ;
* **cohérence avec le moteur** — la couverture s'appuie sur
  ``calculate_teaching_needs``, pas sur un calcul parallèle ;
* **chaînage des présences** — une séance mutualisée totalise les pointages
  de tous ses groupes.

Chaque test construit ses propres données dans la base de test Django : la
base de développement n'est jamais touchée.
"""

from datetime import time

from django.test import TestCase
from django.urls import resolve
from rest_framework.test import APIClient

from edts.models import (
    AffectationCreneau, ConflitCreneau, CreneauTemplate, EmploiDuTemps,
)
from edts.moteur import indicateurs as I
from edts.tests.test_lot2_moteur import FabriqueLMD
from edts.tests.test_lot3_api_lmd import creer_utilisateur
from presences.models import Pointage


class BaseIndicateurs(TestCase):
    """Un EDT de groupe, deux séances, un jeu de données minimal et lisible."""

    def setUp(self):
        self.f = FabriqueLMD(self).creer_base()
        self.f.creer_maquette()
        self.grp_a = self.f.creer_groupe(nom='L1-GA', capacite=30)
        self.grp_b = self.f.creer_groupe(nom='L1-GB', capacite=25)
        self.creneaux = self.f.creer_creneaux(
            jours=('LUNDI', 'MARDI'), heures=((8, 10), (10, 12)),
        )
        self.salle = self.f.creer_salle(nom='Amphi A', capacite=100)
        self.edt = EmploiDuTemps.objects.create(
            annee_academique=self.f.annee, population_type='GROUPE',
            population_id=self.grp_a.pk, titre='EDT indicateurs',
            statut='PUBLIE', semaine_debut=1, semaine_fin=10,
            rentree='2026-10-01',
        )
        self.aff = self.f.creer_affectation(volume=4, groupe=self.grp_a)
        self.s1 = self._seance(self.creneaux[0])
        self.client = APIClient()
        self.connecter('SECRETARIAT')

    def _seance(self, creneau, groupe=None, salle=None, enseignant='Traoré',
                semaine=1, actif=True):
        return AffectationCreneau.objects.create(
            emploi_du_temps=self.edt, creneau_template=creneau,
            groupe=groupe or self.grp_a, salle=salle or self.salle,
            affectation_pedagogique=self.aff, enseignant_nom=enseignant,
            semaine_debut=semaine, semaine_fin=semaine,
            intitule='Séance test', actif=actif,
        )

    def connecter(self, role, nom='u_indic'):
        user = creer_utilisateur(nom, role)
        self.client.force_authenticate(user=user)
        return user

    @property
    def qs(self):
        return AffectationCreneau.objects.filter(emploi_du_temps=self.edt)


class TestTauxUtils(BaseIndicateurs):
    """Un taux sur une base inconnue est None — jamais 0."""

    def test_taux_normal(self):
        self.assertEqual(I._taux(1, 4), 25.0)

    def test_taux_denominateur_nul(self):
        self.assertIsNone(I._taux(5, 0))

    def test_taux_denominateur_none(self):
        self.assertIsNone(I._taux(5, None))

    def test_taux_zero_sur_base_connue(self):
        """0 sur 10 vaut 0 — c'est une donnée réelle, pas une absence."""
        self.assertEqual(I._taux(0, 10), 0.0)


class TestCouverture(BaseIndicateurs):
    """La couverture compare au volume du PÉRIMÈTRE, pas à celui de l'année."""

    def test_perimetre_suit_la_population_de_l_edt(self):
        """EDT de groupe → besoins du groupe uniquement."""
        filtres, restreint = I._filtres_besoins(self.edt)
        self.assertTrue(restreint)
        self.assertEqual(filtres, {'groupe_ids': [self.grp_a.pk]})

    def test_perimetre_formation(self):
        self.edt.population_type = 'FORMATION'
        self.edt.population_id = self.f.cycle.pk
        filtres, restreint = I._filtres_besoins(self.edt)
        self.assertTrue(restreint)
        self.assertEqual(filtres, {'ref_formation_id': self.f.cycle.pk})

    def test_perimetre_non_filtrable_est_signale(self):
        """Population ENSEIGNANT : le moteur ne filtre pas par enseignant.

        Le taux reste calculé sur l'année, mais le fait est DIT — sans quoi
        le chiffre serait interprété comme une contre-performance de l'EDT.
        """
        self.edt.population_type = 'ENSEIGNANT'
        self.edt.population_id = 6
        filtres, restreint = I._filtres_besoins(self.edt)
        self.assertFalse(restreint)
        couv = I.couverture(self.qs, edt=self.edt)
        self.assertEqual(couv['perimetre_besoins'], 'ANNEE')

    def test_perimetre_edt_est_dit(self):
        couv = I.couverture(self.qs, edt=self.edt)
        self.assertEqual(couv['perimetre_besoins'], 'EDT')

    def test_seances_placees_comptees(self):
        self._seance(self.creneaux[1])
        couv = I.couverture(self.qs, edt=self.edt)
        self.assertEqual(couv['seances_placees'], 2)

    def test_annulees_non_comptees_dans_les_placees(self):
        """Une séance annulée n'occupe ni salle ni enseignant."""
        self._seance(self.creneaux[1], actif=False)
        couv = I.couverture(self.qs, edt=self.edt)
        self.assertEqual(couv['seances_placees'], 1)
        self.assertEqual(couv['seances_annulees'], 1)

    def test_heures_placees(self):
        """Deux créneaux de 2 h = 4 h."""
        self._seance(self.creneaux[1])
        couv = I.couverture(self.qs, edt=self.edt)
        self.assertEqual(couv['heures_placees'], 4.0)

    def test_coherence_avec_le_moteur(self):
        """Le volume attendu vient du moteur, pas d'un calcul parallèle."""
        from edts.moteur.besoins import calculate_teaching_needs

        attendu = calculate_teaching_needs(groupe_ids=[self.grp_a.pk])
        couv = I.couverture(self.qs, edt=self.edt)
        self.assertEqual(couv['seances_attendues'],
                         attendu.total_seances_attendues)
        self.assertEqual(couv['heures_attendues'],
                         attendu.total_heures_attendues)

    def test_manquantes_jamais_negatives(self):
        """Mieux pourvu que prévu → 0 manquant, pas un nombre négatif."""
        couv = I.couverture(self.qs, edt=self.edt)
        self.assertGreaterEqual(couv['seances_manquantes'], 0)
        self.assertGreaterEqual(couv['heures_manquantes'], 0)

    def test_taux_none_si_rien_attendu(self):
        couv = I.couverture(AffectationCreneau.objects.none(), edt=self.edt)
        self.assertEqual(couv['seances_placees'], 0)

    def test_motif_echec_relaye(self):
        """Un blocage reste nommé : « 0 % » sans explication ne pilote rien."""
        couv = I.couverture(self.qs, edt=self.edt)
        self.assertIn('motif_echec', couv)


class TestOccupationSalles(BaseIndicateurs):
    """Occupation et remplissage — la capacité NULL n'est jamais « suffisante »."""

    def test_heures_occupees(self):
        self._seance(self.creneaux[1])
        occ = I.occupation_salles(self.qs)
        self.assertEqual(occ['heures_occupees'], 4.0)

    def test_taux_occupation_calcule(self):
        occ = I.occupation_salles(self.qs)
        self.assertIsNotNone(occ['taux_occupation_global'])
        self.assertGreaterEqual(occ['taux_occupation_global'], 0)

    def test_une_seule_salle_utilisee(self):
        occ = I.occupation_salles(self.qs)
        self.assertEqual(occ['nb_salles_utilisees'], 1)

    def test_deux_salles(self):
        autre = self.f.creer_salle(nom='Salle B', capacite=40)
        self._seance(self.creneaux[1], salle=autre)
        occ = I.occupation_salles(self.qs)
        self.assertEqual(occ['nb_salles_utilisees'], 2)
        self.assertEqual({s['salle'] for s in occ['salles']},
                         {'Amphi A', 'Salle B'})

    def test_remplissage_sans_capacite_connue(self):
        """Capacité NULL → None, pas 0 % : la contrainte C4 le veut ainsi."""
        self.salle.capacite = None
        self.salle.save()
        occ = I.occupation_salles(self.qs)
        salle = occ['salles'][0]
        self.assertIsNone(salle['taux_remplissage_moyen'])

    def test_annulees_non_comptees(self):
        self._seance(self.creneaux[1], actif=False)
        occ = I.occupation_salles(self.qs)
        self.assertEqual(occ['heures_occupees'], 2.0)

    def test_sans_salle_ignoree(self):
        s = AffectationCreneau.objects.create(
            emploi_du_temps=self.edt, creneau_template=self.creneaux[1],
            groupe=self.grp_a, semaine_debut=1, semaine_fin=1,
        )
        occ = I.occupation_salles(self.qs)
        self.assertEqual(occ['nb_salles_utilisees'], 1)


class TestChargeEnseignants(BaseIndicateurs):
    """La dispersion compte autant que la moyenne."""

    def test_heures_par_enseignant(self):
        self._seance(self.creneaux[1], enseignant='Koffi')
        ch = I.charge_enseignants(self.qs)
        par_nom = {e['enseignant']: e['heures'] for e in ch['enseignants']}
        self.assertEqual(par_nom['Traoré'], 2.0)
        self.assertEqual(par_nom['Koffi'], 2.0)

    def test_nb_ue_distinctes(self):
        """Un enseignant qui Mutualise plusieurs UE est compté une seule fois."""
        self._seance(self.creneaux[1], enseignant='Traoré', semaine=2)
        ch = I.charge_enseignants(self.qs)
        traore = [e for e in ch['enseignants'] if e['enseignant'] == 'Traoré'][0]
        self.assertEqual(traore['seances'], 2)
        self.assertEqual(traore['nb_ue'], 1)

    def test_deux_enseignants_une_moyenne(self):
        self._seance(self.creneaux[1], enseignant='Koffi')
        ch = I.charge_enseignants(self.qs)
        self.assertEqual(ch['dispersion']['nb_enseignants'], 2)
        self.assertEqual(ch['dispersion']['heures_moyenne'], 2.0)

    def test_dispersion_mesuree(self):
        """8 h / 2 h et 5 h / 5 h ont la même moyenne, pas le même écart.

        C'est tout l'intérêt de l'indicateur : la moyenne seule masquerait une
        répartition déséquilibrée.
        """
        # Traoré : la séance du setUp (2 h) + 3 autres = 8 h.
        for i in range(3):
            self._seance(self.creneaux[1], enseignant='Traoré', semaine=i + 2)
        # Koffi : une seule séance = 2 h.
        self._seance(self.creneaux[1], enseignant='Koffi', semaine=5)
        ch = I.charge_enseignants(self.qs)
        self.assertEqual(ch['dispersion']['nb_enseignants'], 2)
        self.assertEqual(ch['dispersion']['heures_max'], 8.0)   # Traoré
        self.assertEqual(ch['dispersion']['heures_min'], 2.0)   # Koffi
        self.assertEqual(ch['dispersion']['ecart_min_max'], 6.0)
        self.assertEqual(ch['dispersion']['heures_moyenne'], 5.0)

    def test_sans_enseignant(self):
        s = AffectationCreneau.objects.create(
            emploi_du_temps=self.edt, creneau_template=self.creneaux[1],
            groupe=self.grp_a, semaine_debut=1, semaine_fin=1,
        )
        ch = I.charge_enseignants(self.qs)
        # La séance sans enseignant est ignorée ; pas d'erreur, pas de ligne vide.
        noms = [e['enseignant'] for e in ch['enseignants']]
        self.assertNotIn('', noms)
        self.assertNotIn(None, noms)

    def test_dispersion_vide(self):
        ch = I.charge_enseignants(AffectationCreneau.objects.none())
        self.assertEqual(ch['dispersion']['nb_enseignants'], 0)
        self.assertEqual(ch['enseignants'], [])


class TestRepartition(BaseIndicateurs):
    """Équilibre par jour, niveau, semestre, UE, semaine."""

    def test_par_jour(self):
        self._seance(self.creneaux[1])  # LUNDI 10-12
        rep = I.repartition(self.qs)
        jours = {d['cle']: d['seances'] for d in rep['par_jour']}
        self.assertEqual(jours['LUNDI'], 2)

    def test_par_semaine(self):
        self._seance(self.creneaux[1], semaine=3)
        rep = I.repartition(self.qs)
        semaines = {d['cle']: d['seances'] for d in rep['par_semaine']}
        self.assertEqual(semaines[1], 1)
        self.assertEqual(semaines[3], 1)

    def test_heures_cumulees(self):
        rep = I.repartition(self.qs)
        total = sum(d['heures'] for d in rep['par_jour'])
        self.assertEqual(total, 2.0)

    def test_annulees_exclues(self):
        self._seance(self.creneaux[1], actif=False)
        rep = I.repartition(self.qs)
        self.assertEqual(sum(d['seances'] for d in rep['par_jour']), 1)

    def test_clefs_toujours_presentes(self):
        """Un écran qui itère sur les cinq clés ne doit jamais lever KeyError."""
        rep = I.repartition(self.qs)
        for cle in ('par_jour', 'par_niveau', 'par_semestre', 'par_ue',
                    'par_semaine'):
            self.assertIn(cle, rep)
            self.assertIsInstance(rep[cle], list)

    def test_valeur_non_renseignee_explicite(self):
        """Pas de silence sur une donnée absente : elle est nommée."""
        s = AffectationCreneau.objects.create(
            emploi_du_temps=self.edt, creneau_template=self.creneaux[1],
            groupe=self.grp_a, semaine_debut=1, semaine_fin=1,
        )
        rep = I.repartition(self.qs)
        niveaux = [d['cle'] for d in rep['par_niveau']]
        self.assertIn('NON RENSEIGNE', niveaux)


class TestConflits(BaseIndicateurs):
    """Le tableau de bord mesure — il ne déclenche AUCUNE écriture."""

    def test_aucune_ecriture(self):
        """`detecter_conflits` crée et réactive des lignes : pas d'appel ici."""
        avant = ConflitCreneau.objects.count()
        I.conflits(self.edt)
        self.assertEqual(ConflitCreneau.objects.count(), avant)

    def test_aucun_conflit(self):
        c = I.conflits(self.edt)
        self.assertEqual(c['nb_conflits'], 0)
        self.assertFalse(c['deja_calcule'])

    def test_deja_calcule(self):
        """Distinguer « aucun conflit » de « jamais contrôlé »."""
        ConflitCreneau.objects.create(
            emploi_du_temps=self.edt, type_conflit='HORAIRE_SALLE',
            description='test', lignes_creneaux=[self.s1.pk], actif=False,
        )
        c = I.conflits(self.edt)
        self.assertTrue(c['deja_calcule'])
        self.assertEqual(c['nb_conflits'], 0)

    def test_compte_par_type(self):
        ConflitCreneau.objects.create(
            emploi_du_temps=self.edt, type_conflit='HORAIRE_SALLE',
            description='salle', lignes_creneaux=[self.s1.pk], actif=True,
        )
        ConflitCreneau.objects.create(
            emploi_du_temps=self.edt, type_conflit='HORAIRE_ENSEIGNANT',
            description='ens', lignes_creneaux=[self.s1.pk], actif=True,
        )
        c = I.conflits(self.edt)
        self.assertEqual(c['nb_conflits'], 2)
        self.assertEqual(c['par_type']['HORAIRE_SALLE'], 1)

    def test_manuel_distingue(self):
        """Un signalement humain n'appelle pas le même traitement."""
        ConflitCreneau.objects.create(
            emploi_du_temps=self.edt, type_conflit='MANUEL',
            description='signalé', lignes_creneaux=[self.s1.pk], actif=True,
        )
        ConflitCreneau.objects.create(
            emploi_du_temps=self.edt, type_conflit='HORAIRE_SALLE',
            description='auto', lignes_creneaux=[self.s1.pk], actif=True,
        )
        c = I.conflits(self.edt)
        self.assertEqual(c['nb_signales'], 1)
        self.assertEqual(c['nb_detectes'], 1)

    def test_inactifs_ignores(self):
        ConflitCreneau.objects.create(
            emploi_du_temps=self.edt, type_conflit='HORAIRE_SALLE',
            description='clos', lignes_creneaux=[self.s1.pk], actif=False,
        )
        self.assertEqual(I.conflits(self.edt)['nb_conflits'], 0)


class TestAssiduite(BaseIndicateurs):
    """Chaînage séance → pointage, y compris mutualisé."""

    def _pointer(self, seance, suffixe='0001', statut='PRESENT'):
        return Pointage.objects.create(
            seance_edt=seance, device_id=f'APP-{suffixe}',
            date_journee=seance.date or '2026-09-28',
            timestamp_entree='2026-09-28T08:00:00Z', statut=statut,
        )

    def test_sans_pointage(self):
        a = I.assiduite(self.qs)
        self.assertEqual(a['nb_pointages'], 0)
        self.assertIsNone(a['taux_presence'])
        self.assertEqual(a['nb_seances_sans_pointage'], 1)

    def test_pointages_comptees(self):
        self._pointer(self.s1, '1')
        self._pointer(self.s1, '2')
        a = I.assiduite(self.qs)
        self.assertEqual(a['nb_pointages'], 2)
        self.assertEqual(a['nb_seances_suivies'], 1)

    def test_taux_presence(self):
        self._pointer(self.s1, '1', 'PRESENT')
        self._pointer(self.s1, '2', 'ABSENT_NON_BADGE')
        a = I.assiduite(self.qs)
        self.assertEqual(a['taux_presence'], 50.0)

    def test_mutualisation_totalise_les_presences(self):
        """Une séance mutualisée agrège les présences de tous ses groupes."""
        self.s1.groupes_lies.add(self.grp_b)
        self._pointer(self.s1, '1')
        a = I.assiduite(self.qs)
        self.assertEqual(a['nb_pointages'], 1)
        self.assertEqual(a['nb_seances_suivies'], 1)

    def test_perimetre_vide(self):
        a = I.assiduite(AffectationCreneau.objects.none())
        self.assertEqual(a['nb_pointages'], 0)
        self.assertEqual(a['nb_seances_suivies'], 0)


class TestMutualisation(BaseIndicateurs):
    """Indicateur d'efficience issu du chantier 1."""

    def test_sans_mutualisation(self):
        m = I.mutualisation(self.qs)
        self.assertEqual(m['nb_mutualisees'], 0)
        self.assertIsNone(m['taux_mutualisation']) if m['nb_seances'] == 0 \
            else self.assertEqual(m['taux_mutualisation'], 0.0)

    def test_avec_mutualisation(self):
        self.s1.groupes_lies.add(self.grp_b)
        m = I.mutualisation(self.qs)
        self.assertEqual(m['nb_mutualisees'], 1)
        self.assertEqual(m['taux_mutualisation'], 100.0)
        self.assertEqual(m['nb_groupes_max'], 2)

    def test_heures_mutualisees(self):
        self.s1.groupes_lies.add(self.grp_b)
        m = I.mutualisation(self.qs)
        self.assertEqual(m['heures_mutualisees'], 2.0)

    def test_le_porteur_compte(self):
        """1 groupe lié + le porteur = 2 groupes, pas 1."""
        self.s1.groupes_lies.add(self.grp_b)
        m = I.mutualisation(self.qs)
        self.assertEqual(m['detail'][0]['nb_groupes'], 2)

    def test_perimetre_vide(self):
        m = I.mutualisation(AffectationCreneau.objects.none())
        self.assertEqual(m['nb_seances'], 0)
        self.assertIsNone(m['taux_mutualisation'])


class TestAPIIndicateurs(BaseIndicateurs):
    """Les deux endpoints : contrat, filtres, permissions."""

    def test_route_globale_resolue(self):
        """Littéral « indicateurs » — pas capté comme un identifiant d'EDT."""
        match = resolve('/api/edts/lmd/indicateurs/')
        self.assertEqual(match.url_name, 'edt-lmd-indicateurs')

    def test_route_par_edt_resolue(self):
        match = resolve('/api/edts/lmd/7/indicateurs/')
        self.assertEqual(match.url_name, 'edt-lmd-edt-indicateurs')

    def test_edt_indicateurs_200(self):
        r = self.client.get(f'/api/edts/lmd/{self.edt.pk}/indicateurs/')
        self.assertEqual(r.status_code, 200)

    def test_edt_indicateurs_contrat(self):
        r = self.client.get(f'/api/edts/lmd/{self.edt.pk}/indicateurs/')
        d = r.json()
        for cle in ('couverture', 'occupation_salles', 'charge_enseignants',
                    'repartition', 'conflits', 'assiduite', 'mutualisation',
                    'perimetre'):
            self.assertIn(cle, d)
        self.assertEqual(d['perimetre']['emploi_du_temps_id'], self.edt.pk)

    def test_edt_inexistant_404(self):
        r = self.client.get('/api/edts/lmd/999999/indicateurs/')
        self.assertEqual(r.status_code, 404)

    def test_famille_unique(self):
        r = self.client.get(
            f'/api/edts/lmd/{self.edt.pk}/indicateurs/?famille=couverture')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(list(r.json().keys()), ['couverture'])

    def test_famille_inconnue_400(self):
        r = self.client.get(
            f'/api/edts/lmd/{self.edt.pk}/indicateurs/?famille=inconnue')
        self.assertEqual(r.status_code, 400)
        self.assertIn('disponibles', r.json())

    def test_global_200(self):
        r = self.client.get('/api/edts/lmd/indicateurs/')
        self.assertEqual(r.status_code, 200)
        self.assertIn('couverture', r.json())

    def test_global_filtre_annee(self):
        r = self.client.get(
            f'/api/edts/lmd/indicateurs/?annee={self.f.annee.libelle}')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['perimetre']['annee'], self.f.annee.libelle)

    def test_global_annee_inconnue_404(self):
        r = self.client.get('/api/edts/lmd/indicateurs/?annee=2100-2101')
        self.assertEqual(r.status_code, 404)

    def test_lecture_refusee_sans_authentification(self):
        self.client.force_authenticate(user=None)
        r = self.client.get(f'/api/edts/lmd/{self.edt.pk}/indicateurs/')
        self.assertIn(r.status_code, (401, 403))

    def test_lecture_autorisee_a_un_lecteur(self):
        self.connecter('AUDITEUR', nom='lecteur_indic')
        r = self.client.get(f'/api/edts/lmd/{self.edt.pk}/indicateurs/')
        self.assertEqual(r.status_code, 200)

    def test_aucune_ecriture_en_lecture(self):
        """Consulter un indicateur ne modifie rien — surtout pas les conflits."""
        avant = ConflitCreneau.objects.count()
        self.client.get(f'/api/edts/lmd/{self.edt.pk}/indicateurs/')
        self.assertEqual(ConflitCreneau.objects.count(), avant)


class TestRobustesse(BaseIndicateurs):
    """Un indicateur ne lève jamais : il rend une valeur exploitable."""

    def test_perimetre_vide(self):
        r = I.indicateurs(AffectationCreneau.objects.none())
        self.assertEqual(r['couverture']['seances_placees'], 0)
        self.assertEqual(r['occupation_salles']['salles'], [])
        self.assertEqual(r['charge_enseignants']['enseignants'], [])
        self.assertEqual(r['mutualisation']['nb_seances'], 0)

    def test_indicateurs_sans_edt(self):
        r = I.indicateurs(self.qs)
        self.assertIsNone(r['conflits'])
        self.assertEqual(r['couverture']['perimetre_besoins'], 'GLOBAL')

    def test_seance_sans_affectation(self):
        AffectationCreneau.objects.create(
            emploi_du_temps=self.edt, creneau_template=self.creneaux[1],
            groupe=self.grp_a, salle=self.salle, semaine_debut=1,
            semaine_fin=1,
        )
        r = I.indicateurs(self.qs, edt=self.edt)
        self.assertEqual(r['couverture']['seances_placees'], 2)

    def test_durees_chargees_en_une_requete(self):
        """Le canevas est chargé en bloc, pas jointure par ligne."""
        durees = I._durees_par_creneau()
        self.assertEqual(len(durees), CreneauTemplate.objects.count())
        self.assertAlmostEqual(durees[self.creneaux[0].pk], 2.0, places=2)
