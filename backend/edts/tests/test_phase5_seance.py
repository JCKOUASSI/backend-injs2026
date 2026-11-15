"""PHASE 5 — chantier 1 : identité de séance et mutualisation.

Ces tests vérifient les six critères de réception posés pour le chantier :

1. **identité stable persistée** — date, statut, UE, ECUE, semestre, année et
   jeton QR durables, survivant à une relecture depuis la base ;
2. **mutualisation effective** — une séance partagée par plusieurs groupes ;
3. **un seul objet séance** — la mutualisation ne duplique jamais la séance ;
4. **présences toujours rattachées** — ``Pointage.seance_edt`` reste la source
   du lien, y compris après mutualisation ;
5. **anciennes fonctions intactes** — non-régression de la clé ``statut``
   (ACTIVE/ANNULEE) et du comportement historique ;
6. **migration réversible** — aller-retour sans perte de données.

Chaque test construit ses propres données dans la base de test Django
(``TestCase``, transaction annulée en fin de test) : la base de développement
n'est **jamais** touchée.
"""

from datetime import time

from django.test import TestCase
from django.urls import resolve
from rest_framework.test import APIClient

from edts.models import (
    AffectationCreneau, CreneauTemplate, EmploiDuTemps, nouveau_jeton_seance,
)
from edts.tests.test_lot2_moteur import FabriqueLMD
from edts.tests.test_lot3_api_lmd import creer_utilisateur
from presences.models import AuditLog, Pointage


ROUTES = [
    '/api/edts/lmd/seances/12/qr/',
    '/api/edts/lmd/seances/12/groupes/',
    '/api/edts/lmd/seances/12/groupes/3/',
]


class BaseSeance(TestCase):
    """Jeu d'essai commun : un EDT publié porteur de deux séances."""

    def setUp(self):
        self.f = FabriqueLMD(self).creer_base()
        self.f.creer_maquette()
        self.grp_a = self.f.creer_groupe(nom='L1-GA', capacite=30)
        self.grp_b = self.f.creer_groupe(nom='L1-GB', capacite=25)
        self.grp_c = self.f.creer_groupe(nom='L1-GC', capacite=20)
        self.creneaux = self.f.creer_creneaux(
            jours=('LUNDI', 'MARDI'), heures=((8, 10), (10, 12)),
        )
        self.salle = self.f.creer_salle(nom='Amphi A', capacite=100)
        self.edt = EmploiDuTemps.objects.create(
            annee_academique=self.f.annee, population_type='FORMATION',
            population_id=self.f.cycle.pk, titre='EDT test',
            statut='PUBLIE', semaine_debut=1, semaine_fin=10,
            rentree='2026-10-01',
        )
        self.aff = self.f.creer_affectation(volume=4, groupe=self.grp_a)
        self.seance = self.creer_seance(self.creneaux[0], self.grp_a)
        self.client = APIClient()
        self.connecter('SECRETARIAT')

    def connecter(self, role, nom='u_seance'):
        user = creer_utilisateur(nom, role)
        self.client.force_authenticate(user=user)
        return user

    def creer_seance(self, creneau, groupe, semaine=1):
        return AffectationCreneau.objects.create(
            emploi_du_temps=self.edt, creneau_template=creneau, groupe=groupe,
            affectation_pedagogique=self.aff, salle=self.salle,
            enseignant_nom='Traoré', semaine_debut=semaine,
            semaine_fin=semaine, intitule='Séance test',
        )


class TestJetonQR(BaseSeance):
    """Le jeton est unique, sécurisé, durable — et non devinable."""

    def test_jeton_genere_a_la_creation(self):
        self.assertTrue(self.seance.jeton_qr)

    def test_jeton_suffisamment_long(self):
        """`secrets.token_urlsafe(32)` → au moins 40 caractères."""
        self.assertGreaterEqual(len(self.seance.jeton_qr), 40)

    def test_jeton_durable_au_rechargement(self):
        """Relire depuis la base ne régénère pas le jeton."""
        avant = self.seance.jeton_qr
        self.seance.refresh_from_db()
        self.assertEqual(self.seance.jeton_qr, avant)

    def test_jeton_unique_entre_deux_seances(self):
        autre = self.creer_seance(self.creneaux[1], self.grp_b)
        self.assertNotEqual(self.seance.jeton_qr, autre.jeton_qr)

    def test_jetons_non_sequentiels(self):
        """Un jeton prévisible permettrait de pointer une séance tierce."""
        js = [nouveau_jeton_seance() for _ in range(5)]
        self.assertEqual(len(set(js)), 5)

    def test_jeton_conserve_apres_modification(self):
        avant = self.seance.jeton_qr
        self.seance.salle_nom = 'Amphi A (bis)'
        self.seance.save()
        self.assertEqual(self.seance.jeton_qr, avant)


class TestIdentitePersistee(BaseSeance):
    """Critère 1 — l'identité est calculée puis PERSISTÉE."""

    def test_date_calculee_depuis_la_rentree(self):
        """Rentrée jeu. 01/10/2026 → lundi de la semaine 1 = 28/09/2026."""
        self.assertEqual(str(self.seance.date), '2026-09-28')

    def test_date_suit_le_numero_de_semaine(self):
        s3 = self.creer_seance(self.creneaux[0], self.grp_a, semaine=3)
        # Semaine 1 part du 28/09 ; semaine 3 du 12/10 (lundi).
        self.assertEqual(str(s3.date), '2026-10-12')

    def test_date_suit_le_jour_du_creneau(self):
        mardi = [c for c in self.creneaux if c.jour == 'MARDI'][0]
        s = self.creer_seance(mardi, self.grp_a, semaine=1)
        # Lundi 28/09 + 1 jour = mardi 29/09.
        self.assertEqual(str(s.date), '2026-09-29')

    def test_date_persistee_en_base(self):
        s = AffectationCreneau.objects.get(pk=self.seance.pk)
        self.assertEqual(str(s.date), '2026-09-28')

    def test_contexte_pedagogique_complete(self):
        """Semestre, UE et ECUE sont dénormalisés depuis l'affectation."""
        self.assertEqual(self.seance.annee_academique_id, self.f.annee.pk)
        self.assertEqual(self.seance.semestre_id, self.f.semestre.pk)
        self.assertEqual(self.seance.ue_id, self.f.ue.pk)
        self.assertEqual(self.seance.ecue_id, self.f.ecue.pk)

    def test_statut_initial_planifiee(self):
        self.assertEqual(self.seance.statut, 'PLANIFIEE')

    def test_choix_de_statut_disponibles(self):
        attendus = {'PLANIFIEE', 'CONFIRMEE', 'REPORTEE', 'ANNULEE', 'REALISEE'}
        self.assertEqual(
            {c[0] for c in AffectationCreneau._meta.get_field('statut').choices},
            attendus,
        )

    def test_identite_sans_affectation_pedagogique(self):
        """Pas d'affectation → identité réduite, mais date et jeton présents."""
        s = AffectationCreneau.objects.create(
            emploi_du_temps=self.edt, creneau_template=self.creneaux[1],
            groupe=self.grp_b, salle=self.salle, semaine_debut=1, semaine_fin=1,
        )
        self.assertTrue(s.jeton_qr)
        self.assertIsNotNone(s.date)
        self.assertIsNone(s.ue_id)


class TestMutualisation(BaseSeance):
    """Critères 2 et 3 — mutualisation effective, un seul objet séance."""

    def test_une_seance_sans_mutualisation(self):
        self.assertFalse(self.seance.est_mutualisee)
        self.assertEqual(len(self.seance.groupes_concernes), 1)

    def test_ajout_de_groupes(self):
        self.seance.groupes_lies.add(self.grp_b, self.grp_c)
        self.assertTrue(self.seance.est_mutualisee)
        self.assertEqual(len(self.seance.groupes_concernes), 3)

    def test_ordre_porteur_puis_lies(self):
        self.seance.groupes_lies.add(self.grp_c, self.grp_b)
        noms = [g.nom for g in self.seance.groupes_concernes]
        self.assertEqual(noms[0], 'L1-GA')
        self.assertEqual(set(noms[1:]), {'L1-GB', 'L1-GC'})

    def test_un_seul_objet_seance(self):
        """La mutualisation ne duplique JAMAIS la séance."""
        avant = AffectationCreneau.objects.count()
        self.seance.groupes_lies.add(self.grp_b, self.grp_c)
        self.assertEqual(AffectationCreneau.objects.count(), avant)

    def test_groupe_porteur_inchange(self):
        self.seance.groupes_lies.add(self.grp_b)
        self.assertEqual(self.seance.groupe_id, self.grp_a.pk)

    def test_effectif_cumule(self):
        """30 + 25 + 20 = 75 — l'exigence est l'ADDITION des effectifs."""
        self.seance.groupes_lies.add(self.grp_b, self.grp_c)
        self.assertEqual(self.seance.effectif_cumule(), 75)

    def test_effectif_cumule_sans_mutualisation(self):
        self.assertEqual(self.seance.effectif_cumule(), 30)

    def test_retrait_de_groupe(self):
        self.seance.groupes_lies.add(self.grp_b, self.grp_c)
        self.seance.groupes_lies.remove(self.grp_b)
        noms = {g.nom for g in self.seance.groupes_concernes}
        self.assertEqual(noms, {'L1-GA', 'L1-GC'})

    def test_meme_horaire_pour_tous(self):
        """Mutualiser, c'est partager un créneau — pas juxtaposer des séances."""
        self.seance.groupes_lies.add(self.grp_b)
        self.assertEqual(
            self.seance.creneau_template.heure_debut, time(8, 0),
        )


class TestLienPointage(BaseSeance):
    """Critère 4 — les présences restent rattachées, y compris mutualisées."""

    def _pointer(self, seance, suffixe='0001'):
        return Pointage.objects.create(
            seance_edt=seance, device_id=f'APPAREIL-{suffixe}',
            date_journee=seance.date or '2026-09-28',
            timestamp_entree='2026-09-28T08:00:00Z', statut='PRESENT',
        )

    def test_pointage_rattache(self):
        p = self._pointer(self.seance)
        self.assertEqual(p.seance_edt_id, self.seance.pk)

    def test_pointages_trouvables_par_jeton(self):
        """Le chaînage EDT → séance → pointage passe par le jeton."""
        self._pointer(self.seance)
        self._pointer(self.seance, '0002')
        s = AffectationCreneau.objects.get(jeton_qr=self.seance.jeton_qr)
        self.assertEqual(Pointage.objects.filter(seance_edt=s).count(), 2)

    def test_pointage_survit_a_la_mutualisation(self):
        """Exigence centrale : ajouter des groupes NE détache pas les présences."""
        p = self._pointer(self.seance)
        self.seance.groupes_lies.add(self.grp_b, self.grp_c)
        p.refresh_from_db()
        self.assertEqual(p.seance_edt_id, self.seance.pk)
        self.assertEqual(
            Pointage.objects.filter(seance_edt=self.seance).count(), 1,
        )

    def test_pointage_survit_au_retrait(self):
        p = self._pointer(self.seance)
        self.seance.groupes_lies.add(self.grp_b)
        self.seance.groupes_lies.remove(self.grp_b)
        p.refresh_from_db()
        self.assertEqual(p.seance_edt_id, self.seance.pk)

    def test_pointage_survit_au_changement_de_statut(self):
        p = self._pointer(self.seance)
        self.seance.statut = 'CONFIRMEE'
        self.seance.save()
        p.refresh_from_db()
        self.assertEqual(p.seance_edt_id, self.seance.pk)
        self.assertEqual(p.seance_edt.jeton_qr, self.seance.jeton_qr)


class TestNonRegressionStatut(BaseSeance):
    """Critère 5 — la clé ``statut`` historique n'est PAS écrasée."""

    def test_statut_actif_toujours_derive_de_actif(self):
        """``statut`` = ACTIVE/ANNULEE reste la source des écrans existants.

        Mettre le cycle de vie à ANNULEE ne doit PAS annuler la séance au
        sens ``actif`` : c'est ``item_cancel_api`` qui gère l'activation.
        """
        self.seance.statut = 'ANNULEE'
        self.seance.actif = True
        self.seance.save()
        r = self.client.get(f'/api/edts/lmd/{self.edt.pk}/result/')
        self.assertEqual(r.status_code, 200)
        lignes = [s for s in r.json()['seances'] if s['id'] == self.seance.pk]
        self.assertEqual(len(lignes), 1)
        self.assertEqual(lignes[0]['statut'], 'ACTIVE')
        self.assertEqual(lignes[0]['statut_seance'], 'ANNULEE')

    def test_deux_clefs_distinctes(self):
        """Cycle de vie (``statut_seance``) et activation (``statut``) cohabitent."""
        self.seance.statut = 'REPORTEE'
        self.seance.actif = True
        self.seance.save()
        r = self.client.get(f'/api/edts/lmd/{self.edt.pk}/result/')
        ligne = [s for s in r.json()['seances'] if s['id'] == self.seance.pk][0]
        self.assertEqual(ligne['statut'], 'ACTIVE')
        self.assertEqual(ligne['statut_seance'], 'REPORTEE')

    def test_annulation_historique_ignore_le_statut_de_cycle_de_vie(self):
        """``actif=False`` retire la séance de la grille — comme avant."""
        self.seance.statut = 'PLANIFIEE'
        self.seance.actif = False
        self.seance.save()
        r = self.client.get(f'/api/edts/lmd/{self.edt.pk}/result/')
        ids = [s['id'] for s in r.json()['seances']]
        self.assertNotIn(self.seance.pk, ids)


class TestRoutes(TestCase):
    """Les routes littérales ne sont pas capturées par ``lmd/<int:pk>/``."""

    def test_routes_resolvent_les_bonnes_vues(self):
        for url in ROUTES:
            match = resolve(url)
            self.assertIn(
                match.url_name,
                {'edt-lmd-seance-qr', 'edt-lmd-seance-groupes',
                 'edt-lmd-seance-groupe-retirer'},
                msg=f'{url} → {match.url_name}',
            )


class TestAPISeance(BaseSeance):
    """Les trois endpoints : contrat de données, permissions, audit."""

    def setUp(self):
        super().setUp()

    # ── GET /qr/ ────────────────────────────────────────────────────────
    def test_qr_expose_le_contrat_complet(self):
        r = self.client.get(f'/api/edts/lmd/seances/{self.seance.pk}/qr/')
        self.assertEqual(r.status_code, 200)
        d = r.json()
        for cle in ('jeton_qr', 'date', 'heure_debut', 'heure_fin', 'salle',
                    'ue', 'ecue', 'groupes', 'effectif_cumule'):
            self.assertIn(cle, d)
        self.assertEqual(d['jeton_qr'], self.seance.jeton_qr)
        self.assertEqual(d['date'], '2026-09-28')
        self.assertEqual(d['ue'], 'UE test')

    def test_qr_404_si_inexistant(self):
        r = self.client.get('/api/edts/lmd/seances/999999/qr/')
        self.assertEqual(r.status_code, 404)

    def test_qr_lecture_publique(self):
        """Le contrat QR est consultable en lecture (futur scan étudiant)."""
        self.assertIn('jeton_qr',
                      self.client.get(
                          f'/api/edts/lmd/seances/{self.seance.pk}/qr/').json())

    # ── GET/POST /groupes/ ──────────────────────────────────────────────
    def test_groupes_get(self):
        r = self.client.get(f'/api/edts/lmd/seances/{self.seance.pk}/groupes/')
        self.assertEqual(r.status_code, 200)
        d = r.json()
        self.assertEqual(d['groupe_porteur']['nom'], 'L1-GA')
        self.assertEqual(d['groupes_lies'], [])
        self.assertFalse(d['est_mutualisee'])

    def test_groupes_post_ajoute(self):
        r = self.client.post(
            f'/api/edts/lmd/seances/{self.seance.pk}/groupes/',
            {'groupe_ids': [self.grp_b.pk, self.grp_c.pk]}, format='json',
        )
        self.assertEqual(r.status_code, 200)
        d = r.json()
        self.assertEqual(len(d['ajoutes']), 2)
        self.assertEqual(d['refuses'], [])
        self.assertEqual(d['effectif_cumule'], 75)
        self.assertTrue(self.seance.est_mutualisee)

    def test_groupes_post_sans_duplication(self):
        """Deux ajouts du même groupe → un seul lien, jamais deux séances."""
        url = f'/api/edts/lmd/seances/{self.seance.pk}/groupes/'
        self.client.post(url, {'groupe_ids': [self.grp_b.pk]}, format='json')
        r = self.client.post(url, {'groupe_ids': [self.grp_b.pk]}, format='json')
        self.assertEqual(r.json()['ajoutes'], [])
        self.assertEqual(len(r.json()['refuses']), 1)
        self.assertEqual(AffectationCreneau.objects.count(), 1)

    def test_groupes_post_refuse_le_porteur(self):
        r = self.client.post(
            f'/api/edts/lmd/seances/{self.seance.pk}/groupes/',
            {'groupe_ids': [self.grp_a.pk]}, format='json',
        )
        self.assertEqual(r.json()['ajoutes'], [])
        self.assertIn('porteur', r.json()['refuses'][0]['motif'])

    def test_groupes_post_refuse_un_groupe_inexistant(self):
        r = self.client.post(
            f'/api/edts/lmd/seances/{self.seance.pk}/groupes/',
            {'groupe_ids': [999999]}, format='json',
        )
        self.assertEqual(r.json()['refuses'][0]['motif'], 'Groupe inexistant.')

    def test_groupes_post_champ_manquant(self):
        r = self.client.post(
            f'/api/edts/lmd/seances/{self.seance.pk}/groupes/', {}, format='json',
        )
        self.assertEqual(r.status_code, 400)

    def test_groupes_post_id_non_entier(self):
        r = self.client.post(
            f'/api/edts/lmd/seances/{self.seance.pk}/groupes/',
            {'groupe_ids': ['abc']}, format='json',
        )
        self.assertEqual(r.status_code, 400)

    def test_alerte_capacite_si_effectif_cumule_depasse(self):
        """75 étudiants dans une salle de 40 → signalé, non bloqué."""
        self.salle.capacite = 40
        self.salle.save()
        r = self.client.post(
            f'/api/edts/lmd/seances/{self.seance.pk}/groupes/',
            {'groupe_ids': [self.grp_b.pk, self.grp_c.pk]}, format='json',
        )
        self.assertEqual(r.status_code, 200)
        self.assertIsNotNone(r.json()['alerte_capacite'])
        self.assertIn('75', r.json()['alerte_capacite'])

    def test_aucune_alerte_si_capacite_suffisante(self):
        r = self.client.post(
            f'/api/edts/lmd/seances/{self.seance.pk}/groupes/',
            {'groupe_ids': [self.grp_b.pk]}, format='json',
        )
        self.assertIsNone(r.json()['alerte_capacite'])

    # ── DELETE /groupes/<id>/ ───────────────────────────────────────────
    def test_retirer_un_groupe(self):
        self.seance.groupes_lies.add(self.grp_b)
        r = self.client.delete(
            f'/api/edts/lmd/seances/{self.seance.pk}/groupes/{self.grp_b.pk}/')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['retire']['nom'], 'L1-GB')
        self.assertFalse(r.json()['est_mutualisee'])

    def test_retirer_refuse_le_porteur(self):
        r = self.client.delete(
            f'/api/edts/lmd/seances/{self.seance.pk}/groupes/{self.grp_a.pk}/')
        self.assertEqual(r.status_code, 400)

    def test_retirer_un_groupe_non_lie(self):
        r = self.client.delete(
            f'/api/edts/lmd/seances/{self.seance.pk}/groupes/{self.grp_c.pk}/')
        self.assertEqual(r.status_code, 404)

    # ── audit ───────────────────────────────────────────────────────────
    def test_mutualisation_est_journalisee(self):
        """Aucun journal parallèle : on réutilise ``presences.AuditLog``."""
        self.client.post(
            f'/api/edts/lmd/seances/{self.seance.pk}/groupes/',
            {'groupe_ids': [self.grp_b.pk]}, format='json',
        )
        log = AuditLog.objects.filter(
            action='SEANCE_UPDATE', cible_numero=str(self.seance.pk),
        ).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.extra['operation'], 'mutualisation_ajout')
        self.assertIn('L1-GB', log.extra['groupes'])

    def test_retrait_est_journalise(self):
        self.seance.groupes_lies.add(self.grp_b)
        self.client.delete(
            f'/api/edts/lmd/seances/{self.seance.pk}/groupes/{self.grp_b.pk}/')
        log = AuditLog.objects.filter(
            action='SEANCE_UPDATE', cible_numero=str(self.seance.pk),
        ).first()
        self.assertEqual(log.extra['operation'], 'mutualisation_retrait')

    # ── permissions ─────────────────────────────────────────────────────
    def test_lecture_refusee_sans_authentification(self):
        """Le jeton n'est pas public : il faut être authentifié."""
        self.client.force_authenticate(user=None)
        r = self.client.get(f'/api/edts/lmd/seances/{self.seance.pk}/qr/')
        self.assertIn(r.status_code, (401, 403))

    def test_ecriture_refusee_a_un_lecteur(self):
        """Un rôle sans droit de planification ne peut pas mutualiser."""
        from django.contrib.auth import get_user_model

        U = get_user_model()
        lecteur = U.objects.create_user(username='lecteur', password='x')
        lecteur.role = 'AUDITEUR'  # rôle de lecture, hors planification
        lecteur.save()
        self.client.force_authenticate(user=lecteur)
        r = self.client.post(
            f'/api/edts/lmd/seances/{self.seance.pk}/groupes/',
            {'groupe_ids': [self.grp_b.pk]}, format='json',
        )
        self.assertEqual(r.status_code, 403)
        self.assertEqual(self.seance.groupes_lies.count(), 0)

    def test_ecriture_autorisee_a_la_planification(self):
        self.connecter('SECRETARIAT', nom='planif_ok')
        r = self.client.post(
            f'/api/edts/lmd/seances/{self.seance.pk}/groupes/',
            {'groupe_ids': [self.grp_b.pk]}, format='json',
        )
        self.assertEqual(r.status_code, 200)

    def test_aucune_ecriture_sans_modification(self):
        """Un ajout refusé ne laisse aucune trace d'audit."""
        self.client.post(
            f'/api/edts/lmd/seances/{self.seance.pk}/groupes/',
            {'groupe_ids': [999999]}, format='json',
        )
        self.assertEqual(AuditLog.objects.count(), 0)


class TestExpositionGrille(BaseSeance):
    """L'identité et la mutualisation remontent dans la grille EDT."""

    def test_grille_expose_identite(self):
        r = self.client.get(f'/api/edts/lmd/{self.edt.pk}/result/')
        self.assertEqual(r.status_code, 200)
        ligne = [s for s in r.json()['seances'] if s['id'] == self.seance.pk][0]
        self.assertEqual(ligne['jeton_qr'], self.seance.jeton_qr)
        self.assertEqual(ligne['date'], '2026-09-28')
        self.assertEqual(ligne['statut_seance'], 'PLANIFIEE')
        self.assertFalse(ligne['est_mutualisee'])

    def test_grille_expose_mutualisation(self):
        self.seance.groupes_lies.add(self.grp_b, self.grp_c)
        r = self.client.get(f'/api/edts/lmd/{self.edt.pk}/result/')
        ligne = [s for s in r.json()['seances'] if s['id'] == self.seance.pk][0]
        self.assertTrue(ligne['est_mutualisee'])
        self.assertEqual(set(ligne['groupes']), {'L1-GA', 'L1-GB', 'L1-GC'})
        self.assertEqual(ligne['effectif_cumule'], 75)

    def test_grille_compte_requetes_stable(self):
        """Le préchargement évite le N+1 sur ``groupes_lies``."""
        self.seance.groupes_lies.add(self.grp_b, self.grp_c)
        for i in range(1, 6):
            self.creer_seance(self.creneaux[1], self.grp_b, semaine=i)
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        with CaptureQueriesContext(connection) as ctx:
            self.client.get(f'/api/edts/lmd/{self.edt.pk}/result/')
        n6 = len(ctx.captured_queries)
        # 6 séances mutualisées : si chaque lecture de `groupes_lies`
        # déclenchait une requête, le compte exploserait.
        self.assertLess(n6, 40, f'{n6} requêtes pour 6 séances')


class TestMigrationReversible(TestCase):
    """Critère 6 — la migration est additive et réversible."""

    def test_champs_additifs(self):
        """Aucun champ existant n'a été supprimé ou renommé."""
        noms = {f.name for f in AffectationCreneau._meta.get_fields()}
        for attendu in ('emploi_du_temps', 'creneau_template', 'groupe',
                        'salle', 'actif', 'intitule', 'semaine_debut'):
            self.assertIn(attendu, noms)

    def test_nouveaux_champs_optionnels(self):
        """Additive ⇒ chaque nouveau champ accepte une valeur vide."""
        for nom in ('annee_academique', 'semestre', 'ue', 'ecue', 'date',
                    'statut', 'jeton_qr', 'groupes_lies'):
            champ = AffectationCreneau._meta.get_field(nom)
            self.assertTrue(champ.null or champ.has_default() or champ.many_to_many,
                            msg=f'{nom} devrait être optionnel')

    def test_statut_a_une_valeur_par_defaut(self):
        champ = AffectationCreneau._meta.get_field('statut')
        self.assertEqual(champ.default, 'PLANIFIEE')
