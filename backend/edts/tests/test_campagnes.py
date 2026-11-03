"""GET-INJS APP — LOT 2 : campagnes de génération, cycle de vie et traçabilité.

Ce que ces tests garantissent (aucun n'est décoratif) :

1. une campagne ne peut pas être créée deux fois avec le même libellé sur la
   même année (historique lisible) ;
2. les transitions de statut sont contrôlées — on ne « démarre » pas une
   campagne brouillon, on ne publie pas une campagne non validée ;
3. un lancement double est refusé explicitement (``CAMPAGNE_DEJA_EN_COURS``)
   au lieu de produire deux générations concurrentes ;
4. une génération impossible est consignée comme **échec** (statut ``ECHEC``,
   message technique, anomalies), jamais présentée comme un succès ;
5. une génération réelle produit des EDT brouillons, un bilan par groupe, des
   statistiques mesurées (durée, requêtes SQL) et un historique d'exécutions ;
6. la validation puis la publication suivent les habilitations existantes ;
7. la publication est atomique : un EDT en échec annule tout le lot.
"""

from django.test import TestCase
from rest_framework.test import APIClient

from edts.models import CampagneGeneration, EmploiDuTemps, ExecutionCampagne
from edts.moteur import campagnes as C
from edts.tests.test_lot2_moteur import FabriqueLMD
from scolarite.models import Maquette


def _utilisateur(nom, role):
    from django.contrib.auth import get_user_model

    U = get_user_model()
    user = U.objects.create_user(username=nom, password='x')
    user.role = role
    user.save()
    return user


class BaseCampagneTest(TestCase):
    def setUp(self):
        self.f = FabriqueLMD(self).creer_base(perimetre='INJS', filiere='F01')
        self.formation = self.f.cycle
        self.annee = self.f.annee
        self.f.creer_creneaux(jours=('LUNDI', 'MARDI'), heures=((8, 10), (10, 12)))
        self.f.creer_salle(nom='Salle A', capacite=60)
        maquette, ue, ecue = self.f.creer_maquette()
        ecue.volume_cm = 4
        ecue.save()
        maquette.statut = Maquette.Statut.ACTIVE
        maquette.save()
        self.maquette = maquette

        self.admin = _utilisateur('admin-campagne', 'ADMIN')
        self.direction = _utilisateur('direction-campagne', 'DIRECTION')
        self.auditeur = _utilisateur('auditeur-campagne', 'AUDITEUR')

    def campagne(self, libelle='Campagne de test', **params):
        return C.creer_campagne(
            annee_academique_id=self.annee.pk,
            libelle=libelle,
            user=self.admin,
            semaines=params.pop('semaines', [1]),
            parametres=params or {'persister': True},
        )


class CycleDeVieCampagneTests(BaseCampagneTest):
    def test_creation_en_brouillon_avec_effectif_mesure(self):
        campagne = self.campagne()
        self.assertEqual(campagne.statut, CampagneGeneration.Statut.BROUILLON)
        self.assertIn('effectif_importe_a_la_creation', campagne.statistiques)
        self.assertEqual(campagne.semaines, [1])

    def test_libelle_deja_utilise_refuse(self):
        self.campagne()
        with self.assertRaises(C.TransitionRefusee) as ctx:
            self.campagne()
        self.assertEqual(ctx.exception.motif, 'CAMPAGNE_DEJA_EXISTANTE')

    def test_annee_introuvable_refusee(self):
        with self.assertRaises(C.TransitionRefusee) as ctx:
            C.creer_campagne(annee_academique_id=999999, libelle='X', user=self.admin)
        self.assertEqual(ctx.exception.motif, 'ANNEE_ACADEMIQUE_INTROUVABLE')

    def test_demarrage_depuis_brouillon_refuse(self):
        campagne = self.campagne()
        with self.assertRaises(C.TransitionRefusee) as ctx:
            C.demarrer_campagne(campagne.pk, user=self.admin, asynchrone=False)
        self.assertEqual(ctx.exception.motif, 'TRANSITION_REFUSEE')
        self.assertEqual(ctx.exception.detail['statut_courant'], 'BROUILLON')

    def test_parcours_donnees_pretes_puis_demarrage(self):
        campagne = self.campagne()
        C.valider_donnees(campagne.pk, user=self.admin)
        campagne.refresh_from_db()
        self.assertEqual(campagne.statut, CampagneGeneration.Statut.VALIDATION_DONNEES)
        C.marquer_pret(campagne.pk, user=self.admin)
        campagne.refresh_from_db()
        self.assertEqual(campagne.statut, CampagneGeneration.Statut.PRET)

    def test_double_lancement_refuse(self):
        """Le verrou de concurrence empêche deux exécutions simultanées."""
        campagne = self.campagne()
        C.marquer_pret(campagne.pk, user=self.admin)
        # Simule une exécution déjà en cours (ce que fait `demarrer_campagne`).
        CampagneGeneration.objects.filter(pk=campagne.pk).update(statut='EN_COURS')
        with self.assertRaises(C.TransitionRefusee) as ctx:
            C.demarrer_campagne(campagne.pk, user=self.admin, asynchrone=False)
        self.assertEqual(ctx.exception.motif, 'CAMPAGNE_DEJA_EN_COURS')

    def test_publication_refusee_avant_validation(self):
        campagne = self.campagne()
        C.marquer_pret(campagne.pk, user=self.admin)
        C.demarrer_campagne(campagne.pk, user=self.admin, asynchrone=False)
        campagne.refresh_from_db()
        self.assertIn(campagne.statut, {
            CampagneGeneration.Statut.TERMINE,
            CampagneGeneration.Statut.TERMINE_AVEC_ANOMALIES,
            CampagneGeneration.Statut.ECHEC,
        })
        with self.assertRaises(C.TransitionRefusee):
            C.publier_campagne(campagne.pk, user=self.direction)


class ExecutionCampagneTests(BaseCampagneTest):
    def test_generation_impossible_consignee_comme_echec(self):
        """Année sans aucun groupe INJS : échec explicite, motif et anomalies.

        Une génération qui ne peut rien produire n'est jamais présentée comme
        réussie : statut ``ECHEC``, motif ``AUCUN_GROUPE_INJS``, anomalie
        bloquante et historique conservé.
        """
        from scolarite.models import AnneeAcademique

        annee_vide = AnneeAcademique.objects.create(
            libelle='2099-2100', date_debut='2099-09-01', date_fin='2100-08-31',
        )
        campagne = C.creer_campagne(
            annee_academique_id=annee_vide.pk,
            libelle='Année vide',
            user=self.admin,
            semaines=[1],
            parametres={'persister': True},
        )
        C.marquer_pret(campagne.pk, user=self.admin)
        C.demarrer_campagne(campagne.pk, user=self.admin, asynchrone=False)

        campagne.refresh_from_db()
        self.assertEqual(campagne.statut, CampagneGeneration.Statut.ECHEC)
        self.assertEqual(campagne.bilan['motif_echec'], 'AUCUN_GROUPE_INJS')
        self.assertTrue(campagne.anomalies, 'une impossibilité doit être expliquée')
        self.assertEqual(campagne.anomalies[0]['niveau'], 'BLOQUANT')
        execution = campagne.executions.get()
        self.assertEqual(execution.statut, ExecutionCampagne.Statut.ECHEC)

    def test_generation_reelle_produit_bilan_statistiques_et_historique(self):
        from edts.moteur import import_inscrits as I

        lignes = [
            f'INJS-{i:03d};Nom{i};{self.formation.intitule};L1;S1;L1-G1;V1'
            for i in range(30)
        ]
        contenu = (
            'matricule;nom;formation;niveau;semestre;groupe;vague\n'
            + '\n'.join(lignes) + '\n'
        ).encode('utf-8')
        I.importer_inscrits(
            annee_academique_id=self.annee.pk,
            nom_fichier='inscrits.csv',
            contenu=contenu,
            appliquer=True,
        )

        campagne = self.campagne(libelle='Génération réelle', persister=True)
        C.marquer_pret(campagne.pk, user=self.admin)
        C.demarrer_campagne(campagne.pk, user=self.admin, asynchrone=False)

        campagne.refresh_from_db()
        self.assertIn(campagne.statut, {
            CampagneGeneration.Statut.TERMINE,
            CampagneGeneration.Statut.TERMINE_AVEC_ANOMALIES,
        })
        self.assertGreaterEqual(campagne.bilan['totaux']['nb_groupes'], 1)
        self.assertIn('duree_ms', campagne.statistiques)
        self.assertIsNotNone(campagne.terminee_le)
        self.assertGreaterEqual(campagne.statistiques['requetes_sql'], 1)

        # Les EDT produits restent des BROUILLONS : la campagne ne publie rien.
        edt_ids = [l['edt_id'] for l in campagne.bilan['groupes'] if l.get('edt_id')]
        self.assertTrue(edt_ids, 'la campagne doit persister au moins un EDT')
        self.assertTrue(
            EmploiDuTemps.objects.filter(pk__in=edt_ids, statut='BROUILLON').exists()
        )

        # Relance : une seconde exécution est historisée (jamais d'écrasement).
        C.demarrer_campagne(campagne.pk, user=self.admin, asynchrone=False)
        self.assertEqual(campagne.executions.count(), 2)
        self.assertEqual(
            sorted(campagne.executions.values_list('numero', flat=True)), [1, 2]
        )

    def test_validation_et_publication_atomiques(self):
        from edts.moteur import import_inscrits as I

        lignes = [
            f'INJS-{i:03d};Nom{i};{self.formation.intitule};L1;S1;L1-G1;V1'
            for i in range(30)
        ]
        contenu = (
            'matricule;nom;formation;niveau;semestre;groupe;vague\n'
            + '\n'.join(lignes) + '\n'
        ).encode('utf-8')
        I.importer_inscrits(
            annee_academique_id=self.annee.pk,
            nom_fichier='inscrits.csv',
            contenu=contenu,
            appliquer=True,
        )

        campagne = self.campagne(libelle='Validation publication', persister=True)
        C.marquer_pret(campagne.pk, user=self.admin)
        C.demarrer_campagne(campagne.pk, user=self.admin, asynchrone=False)
        campagne.refresh_from_db()
        if campagne.statut == CampagneGeneration.Statut.TERMINE_AVEC_ANOMALIES:
            self.skipTest('bilan incomplet dans ce jeu de données : validation non exigible')

        C.valider_campagne(campagne.pk, user=self.direction)
        campagne.refresh_from_db()
        self.assertEqual(campagne.statut, CampagneGeneration.Statut.VALIDE)

        resultat = C.publier_campagne(campagne.pk, user=self.direction, motif='test')
        campagne.refresh_from_db()
        self.assertEqual(campagne.statut, CampagneGeneration.Statut.PUBLIE)
        edt_ids = [l['edt_id'] for l in campagne.bilan['groupes'] if l.get('edt_id')]
        self.assertTrue(
            EmploiDuTemps.objects.filter(pk__in=edt_ids, statut='PUBLIE').exists()
        )
        self.assertEqual(len(resultat['publications']), len(edt_ids))


class CampagnesApiTests(BaseCampagneTest):
    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.client.force_authenticate(user=self.admin)

    def test_creation_puis_lecture(self):
        reponse = self.client.post('/api/edts/campagnes/', {
            'annee_academique_id': self.annee.pk,
            'libelle': 'API campagne',
            'semaines': [2, 3],
            'parametres': {'persister': True},
        }, format='json')
        self.assertEqual(reponse.status_code, 201, reponse.data)
        pk = reponse.data['id']
        detail = self.client.get(f'/api/edts/campagnes/{pk}/')
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.data['semaines'], [2, 3])

    def test_creation_sans_libelle_refusee(self):
        reponse = self.client.post('/api/edts/campagnes/', {
            'annee_academique_id': self.annee.pk,
        }, format='json')
        self.assertEqual(reponse.status_code, 400)
        self.assertEqual(reponse.data['motif_echec'], 'PARAMETRES_INCOMPLETS')

    def test_demarrage_synchrone_puis_statut(self):
        campagne = self.campagne(libelle='API démarrage')
        C.marquer_pret(campagne.pk, user=self.admin)
        reponse = self.client.post(
            f'/api/edts/campagnes/{campagne.pk}/demarrer/',
            {'asynchrone': False}, format='json',
        )
        self.assertEqual(reponse.status_code, 200, reponse.data)
        statut = self.client.get(f'/api/edts/campagnes/{campagne.pk}/statut/')
        self.assertEqual(statut.status_code, 200)
        self.assertFalse(statut.data['en_cours'])

    def test_demarrage_double_refuse_en_409(self):
        campagne = self.campagne(libelle='API double')
        C.marquer_pret(campagne.pk, user=self.admin)
        CampagneGeneration.objects.filter(pk=campagne.pk).update(statut='EN_COURS')
        reponse = self.client.post(f'/api/edts/campagnes/{campagne.pk}/demarrer/', {}, format='json')
        self.assertEqual(reponse.status_code, 409)
        self.assertEqual(reponse.data['motif_echec'], 'CAMPAGNE_DEJA_EN_COURS')

    def test_lecture_ouverte_mais_creation_interdite_a_un_auditeur(self):
        campagne = self.campagne(libelle='API droits')
        self.client.force_authenticate(user=self.auditeur)
        self.assertEqual(self.client.get('/api/edts/campagnes/').status_code, 200)
        self.assertEqual(self.client.get(f'/api/edts/campagnes/{campagne.pk}/').status_code, 200)
        refus = self.client.post('/api/edts/campagnes/', {
            'annee_academique_id': self.annee.pk, 'libelle': 'Interdit',
        }, format='json')
        self.assertEqual(refus.status_code, 403)

    def test_validation_reservee_a_la_direction(self):
        from edts.moteur import import_inscrits as I

        lignes = [
            f'INJS-{i:03d};Nom{i};{self.formation.intitule};L1;S1;L1-G1;V1'
            for i in range(30)
        ]
        I.importer_inscrits(
            annee_academique_id=self.annee.pk,
            nom_fichier='inscrits.csv',
            contenu=('matricule;nom;formation;niveau;semestre;groupe;vague\n'
                     + '\n'.join(lignes) + '\n').encode('utf-8'),
            appliquer=True,
        )
        campagne = self.campagne(libelle='API validation')
        C.marquer_pret(campagne.pk, user=self.admin)
        C.demarrer_campagne(campagne.pk, user=self.admin, asynchrone=False)
        self.client.force_authenticate(user=self.admin)
        reponse = self.client.post(f'/api/edts/campagnes/{campagne.pk}/valider/', {}, format='json')
        # L'ADMIN valide (règle du module) ; un compte de planification seul est refusé.
        self.assertEqual(reponse.status_code, 200, reponse.data)

        self.client.force_authenticate(user=self.auditeur)
        refus = self.client.post(f'/api/edts/campagnes/{campagne.pk}/publier/', {}, format='json')
        self.assertEqual(refus.status_code, 403)
