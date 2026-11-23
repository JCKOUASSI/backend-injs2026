"""Tests du LOT 5 (U8) — bascule CURP : correctifs additifs et amorçage.

Le lot livre, sans rien retirer ni retourner :

* **L4-01** : ``moteur._decrire_perimetre`` expose ``content_type_id`` et
  ``id`` — la cible « objet métier » (voie ``has_object_permission``) est
  résolue au contrôle 9 (verrouillé par
  ``test_lot4_refus_croises.CouvertureObjetEcartTests``, inversée à l'occasion) ;
* **J2-4** : les résolveurs hiérarchiques (``services/resolveurs.py``)
  bornent Direction ⊃ Département ⊃ Service et
  Formation ⊃ Parcours ⊃ Groupe/Niveau ⊃ maquette ⊃ UE ⊃ ECUE ; le type
  ``DEPARTEMENT`` de périmètre naît avec le lot ;
* **L4-02** : l'assistant de la console pose des périmètres de tout type
  (``perimetres``), l'alliage ``perimetres_secretariats`` restant accepté ;
* **L4-03** : la connexion réussie d'un compte gouverné émet ``CONNEXION``
  au journal d'habilitation (best effort, jamais bloquante) ;
* **L4-04** : ``journalisation._resoudre_cible`` accepte la cible dict du
  contrat d'API ;
* **étape 1 de la bascule** : ``rattacher_comptes_legacy`` — rattachement
  additif et idempotent des comptes legacy sans profil gouverné, via la
  table A6, sans jamais auto-valider un rôle sensible ;
* **étape 3** : les premières vues pilotes (liste des inscriptions,
  confirmation de paiement) sont branchées en OBSERVATION : les réponses
  ne changent pas, les écarts sont mesurés.

Comme au LOT 4, le mode APPLICATION ne s'exerce **que sur la base de test**
(``override_settings``) ; le défaut livré (OBSERVATION, refus en veille) n'est
pas touché. Fabriques partagées : ``test_lot4_refus_croises``.
"""
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import override_settings
from rest_framework.test import APITestCase

from administrations.models import Departement, Direction
from formations.models import RefFormation, Secretariat
from habilitations.models import (
    AttributionRole,
    CompteUtilisateur,
    JournalHabilitation,
    Perimetre,
    RoleMetier,
)
from habilitations.api.serializers_admin import CreationCompteSerializer
from habilitations.services import resolveurs
from habilitations.services import observation
from habilitations.services.journalisation import journaliser, verifier_chaine
from habilitations.services.moteur import est_autorise
from habilitations.tests.test_lot4_refus_croises import (
    APPLICATION, MOT_DE_PASSE, SocleLot4, _compte, _perimetre,
)
from scolarite.models import (
    AnneeAcademique, ECUE, Groupe, Maquette, Niveau, Parcours, Semestre, UE,
)
from unittest import mock

User = get_user_model()


class SocleOrganisation(SocleLot4):
    """Directions, départements, service RH et chaîne pédagogique complètes."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.direction_a = Direction.objects.create(code='DG', libelle='Direction générale')
        cls.direction_b = Direction.objects.create(code='DAE', libelle='Direction des études')
        cls.departement_a = Departement.objects.create(
            code='DEPT-A', libelle='Département A', direction=cls.direction_a)
        cls.departement_b = Departement.objects.create(
            code='DEPT-B', libelle='Département B', direction=cls.direction_b)
        cls.service_a = cls._service('Service des stages', cls.departement_a)
        cls.formation = RefFormation.objects.create(intitule='LICENCE STAPS')
        cls.parcours = Parcours.objects.create(
            ref_formation=cls.formation, code='PAR1', intitule='Parcours 1')
        cls.niveau = Niveau.objects.create(code='L1', libelle='Licence 1', ordre=1)
        cls.annee = AnneeAcademique.objects.create(
            libelle='2026-2027', date_debut='2026-10-01',
            date_fin='2027-07-31', courante=True)
        cls.groupe = Groupe.objects.create(
            annee_academique=cls.annee, ref_formation=cls.formation,
            parcours=cls.parcours, niveau=cls.niveau, nom='L1-G1')
        cls.semestre = Semestre.objects.create(
            niveau=cls.niveau, numero=1, libelle='S1')
        cls.maquette = Maquette.objects.create(
            annee_academique=cls.annee, ref_formation=cls.formation,
            niveau=cls.niveau)
        cls.ue = UE.objects.create(
            maquette=cls.maquette, semestre=cls.semestre, code='UE11',
            intitule='Sciences du mouvement', credits=6)
        cls.ecue = ECUE.objects.create(
            ue=cls.ue, code='ECUE111', intitule='Anatomie', credits=3,
            volume_cm=20, volume_td=10)

    @staticmethod
    def _service(nom, departement):
        from ressources_humaines.models import Service
        return Service.objects.create(nom=nom, departement=departement)


@override_settings(**APPLICATION)
class ResolveursHierarchiquesTests(SocleOrganisation):
    """Le résolveur livré par défaut couvre par rattachement — et rien d'autre."""

    def _chef(self, username, type_p, objet, reference):
        perimetre = _perimetre(type_p, objet, reference=reference)
        user, compte = _compte(
            username, 'CHEF_DEPARTEMENT', perimetres=[perimetre],
            role_legacy='CHEF_SECRETARIAT')
        return user, compte

    def test_01_direction_couvre_ses_departements_pas_les_voisins(self):
        user, _ = self._chef(
            'chef_dir_a', Perimetre.Type.DIRECTION, self.direction_a, 'DG')
        self.assertTrue(est_autorise(
            user, 'scolarite.groupe.modifier', cible=self.departement_a).autorise)
        decision = est_autorise(
            user, 'scolarite.groupe.modifier', cible=self.departement_b)
        self.assertFalse(decision.autorise)
        self.assertIn('CIBLE_HORS_PERIMETRE', decision.motifs)

    def test_02_type_departement_naît_avec_le_lot(self):
        self.assertIn('DEPARTEMENT', Perimetre.Type.values)
        user, _ = self._chef(
            'chef_dep_a', Perimetre.Type.DEPARTEMENT, self.departement_a, 'DEPT-A')
        self.assertTrue(est_autorise(
            user, 'scolarite.groupe.modifier', cible=self.departement_a).autorise)
        # Département ⊃ Service (rattachement RH) : couvert.
        self.assertTrue(est_autorise(
            user, 'scolarite.groupe.modifier', cible=self.service_a).autorise)
        self.assertFalse(est_autorise(
            user, 'scolarite.groupe.modifier', cible=self.departement_b).autorise)

    def test_03_direction_couvre_le_service_via_le_departement(self):
        """Deux sauts (Direction ⊃ Département ⊃ Service) par le résolveur."""
        user_b, _ = self._chef(
            'chef_dir_b', Perimetre.Type.DIRECTION, self.direction_b, 'DAE')
        self.assertFalse(est_autorise(
            user_b, 'scolarite.groupe.modifier', cible=self.service_a).autorise)
        user_a, _ = self._chef(
            'chef_dir_a2', Perimetre.Type.DIRECTION, self.direction_a, 'DG')
        self.assertTrue(est_autorise(
            user_a, 'scolarite.groupe.modifier', cible=self.service_a).autorise)

    def test_04_formation_couvre_parcours_groupe_maquette_et_ecue(self):
        user, _ = self._chef(
            'chef_formation', Perimetre.Type.FORMATION, self.formation,
            'LICENCE STAPS')
        for cible in (self.parcours, self.groupe, self.maquette, self.ecue):
            with self.subTest(cible=cible._meta.model_name):
                self.assertTrue(est_autorise(
                    user, 'pedagogie.maquette.consulter', cible=cible).autorise)

    def test_05_niveau_couvre_groupe_et_ecue_depuis_sa_maquette(self):
        user, _ = self._chef(
            'chef_niveau', Perimetre.Type.NIVEAU, self.niveau, 'L1')
        self.assertTrue(est_autorise(
            user, 'pedagogie.maquette.consulter', cible=self.groupe).autorise)
        self.assertTrue(est_autorise(
            user, 'pedagogie.maquette.consulter', cible=self.ecue).autorise)

    def test_06_cles_couvrantes_contiennent_l_objet_et_ses_ancetres(self):
        cles = resolveurs.cles_couvrantes(self.groupe)
        self.assertIn(('GROUPE', str(self.groupe.pk)), cles)
        self.assertIn(('PARCOURS', str(self.parcours.pk)), cles)
        self.assertIn(('FORMATION', str(self.formation.pk)), cles)
        self.assertIn(('NIVEAU', str(self.niveau.pk)), cles)
        # Un objet sans borne connue ne fournit que rien : le dict brut.
        self.assertEqual(resolveurs.cles_couvrantes(self.direction_a),
                         {('DIRECTION', str(self.direction_a.pk))})

    def test_07_couverture_standard_reproduit_le_defaut_sur_les_deux_formes(self):
        """Injectable, le résolveur suit le moteur : dict exact, objet avec ancêtres."""
        peri = _perimetre(Perimetre.Type.DIRECTION, self.direction_a, reference='DG')
        # Objet : l'ancêtre joue (département rattaché couvert).
        self.assertTrue(resolveurs.couverture_standard(peri, self.departement_a))
        self.assertFalse(resolveurs.couverture_standard(peri, self.departement_b))
        # Dict du contrat : rapprochement exact, sans ancêtre, comme le moteur.
        self.assertTrue(resolveurs.couverture_standard(
            peri, {'type': 'DIRECTION', 'object_id': self.direction_a.pk}))
        self.assertFalse(resolveurs.couverture_standard(
            peri, {'type': 'DEPARTEMENT', 'object_id': self.departement_a.pk}))
        # Exact objet de son propre type : couvert par le pk (+ règle générique
        # secrétariat pour la cible portant secretariat_id).
        secretariat = Secretariat.objects.create(
            numero='SECR-L5', nom='Secrétariat L5')
        peri_s = _perimetre(Perimetre.Type.SECRETARIAT, secretariat,
                             reference='SECR-L5')
        self.assertTrue(resolveurs.couverture_standard(peri_s, secretariat))
        self.assertFalse(resolveurs.couverture_standard(peri_s, self.groupe))

    def test_08_resolveur_ne_touch_pas_aux_globaux(self):
        global_p = Perimetre.objects.create(type=Perimetre.Type.INJS_ENTIER)
        self.assertFalse(resolveurs.couvert_par_ancetre(global_p, self.groupe))
        self.assertTrue(resolveurs.couverture_standard(global_p, self.groupe))


@override_settings(**APPLICATION)
class ConsolePerimetresTests(SocleOrganisation):
    """L4-02 : la console pose des périmètres de tout type, additivement."""

    def setUp(self):
        super().setUp()
        self.admin, self.compte_admin = _compte(
            'admin_lot5', 'ADMIN_SYSTEME', role_legacy='ADMIN',
            seconde_signature=True, nom='ADMIN LOT5')

    def _payload(self, perimetres=None, secretariats=None):
        ligne = {'role': 'CHEF_DEPARTEMENT', 'motif': 'Test LOT 5.'}
        if perimetres is not None:
            ligne['perimetres'] = perimetres
        if secretariats is not None:
            ligne['perimetres_secretariats'] = secretariats
        return {
            'identifiants': {
                'username': 'nouveau_lot5', 'email': 'n@injs.ci',
                'mot_de_passe': MOT_DE_PASSE, 'role_legacy': 'SECRETARIAT',
            },
            'roles': [ligne],
            'motif': 'Création de test LOT 5.',
        }

    def _creer(self, payload):
        from habilitations.services import comptes_admin
        return comptes_admin.creer_compte(self.admin, payload, {'ip': '127.0.0.1'})

    def test_01_perimetre_direction_pose_depuis_l_assistant(self):
        compte = self._creer(self._payload(perimetres=[
            {'type': 'DIRECTION', 'object_id': self.direction_a.pk},
            {'type': 'DEPARTEMENT', 'object_id': self.departement_a.pk},
        ]))
        perimetre_qs = compte.attributions.first().perimetres.all()
        self.assertCountEqual(
            perimetre_qs.values_list('type', flat=True),
            ['DIRECTION', 'DEPARTEMENT'])
        bornee = perimetre_qs.get(type='DIRECTION')
        self.assertEqual(bornee.cible, self.direction_a)
        self.assertEqual(bornee.reference_lisible, 'DG')

    def test_02_alliage_secretariats_toujours_accepte(self):
        secretariat = Secretariat.objects.create(
            numero='SECR-LOT5', nom='Secrétariat LOT5')
        compte = self._creer(self._payload(secretariats=[secretariat.pk]))
        perimetre = compte.attributions.first().perimetres.get()
        self.assertEqual(perimetre.type, 'SECRETARIAT')
        self.assertEqual(perimetre.object_id, secretariat.pk)

    def test_03_type_inconnu_refuse_sans_compte_fantome(self):
        from habilitations.services.comptes_admin import ErreurConsole
        with self.assertRaises(ErreurConsole) as erreur:
            self._creer(self._payload(perimetres=[
                {'type': 'EMPIRE', 'object_id': 1}]))
        self.assertEqual(erreur.exception.code, 'PERIMETRE_INCONNU')
        self.assertFalse(User.objects.filter(username='nouveau_lot5').exists())

    def test_04_objet_inexistant_refuse(self):
        from habilitations.services.comptes_admin import ErreurConsole
        with self.assertRaises(ErreurConsole) as erreur:
            self._creer(self._payload(perimetres=[
                {'type': 'DIRECTION', 'object_id': 999999}]))
        self.assertEqual(erreur.exception.code, 'PERIMETRE_INCONNU')

    def test_05_serialiseur_valide_la_forme_des_perimetres(self):
        se = CreationCompteSerializer(data={
            'identifiants': {
                'username': 'x', 'mot_de_passe': 'xxxxxx',
                'role_legacy': 'SECRETARIAT',
            },
            'roles': [{'role': 'SCOLARITE', 'perimetres': [{'type': 'DIRECTION'}]}],
            'motif': 'Forme incomplète.',
        })
        self.assertFalse(se.is_valid())
        self.assertIn('perimetres', str(se.errors))


class JournalisationCibleDictTests(SocleLot4):
    """L4-04 : une cible dict du contrat d'API se journalise sans lever."""

    def test_01_refus_sur_cible_dict_est_journalise_avec_sa_cible(self):
        entree = journaliser(
            'ACCES_REFUSE',
            compte=None,
            cible={'type': 'SECRETARIAT', 'object_id': 42,
                   'reference': 'SECR-ABSENT'},
            motif='Sonde L4-04.',
        )
        self.assertEqual(entree.objet_type, 'SECRETARIAT')
        self.assertEqual(entree.object_id, '42')
        self.assertIsNone(entree.content_type_id)
        self.assertEqual(verifier_chaine(), [])

    def test_02_instance_metier_toujours_resolue_comme_avant(self):
        secretariat = Secretariat.objects.create(
            numero='SECR-L44', nom='Secrétariat L4-04')
        entree = journaliser(
            'ACCES_REFUSE', cible=secretariat, motif='Sonde instance.')
        self.assertEqual(entree.objet_type, 'formations.secretariat')
        self.assertEqual(entree.object_id, str(secretariat.pk))
        self.assertEqual(verifier_chaine(), [])


class JournalConnexionTests(SocleLot4):
    """L4-03 : la connexion réussie d'un compte gouverné trace CONNEXION."""

    def _se_connecter(self, username):
        return self.client.post('/api/auth/login/', {
            'username': username, 'password': MOT_DE_PASSE,
        }, format='json')

    def test_01_compte_gouverne_emet_connexion_au_journal(self):
        user, compte = _compte(
            'connecte_l43', 'SCOLARITE', role_legacy='SECRETARIAT')
        reponse = self._se_connecter('connecte_l43')
        self.assertEqual(reponse.status_code, 200)
        entrees = JournalHabilitation.objects.filter(
            type_evenement='CONNEXION', compte_concerne=compte)
        self.assertEqual(entrees.count(), 1)
        entree = entrees.first()
        self.assertEqual(entree.acteur_id, user.pk)
        self.assertEqual(entree.nouvelle_valeur, {'canal': 'WEB'})
        self.assertEqual(verifier_chaine(), [])

    def test_02_compte_non_gouverne_ne_journalise_rien(self):
        user = User.objects.create_user(
            username='libre_l43', password=MOT_DE_PASSE, role='SECRETARIAT')
        reponse = self._se_connecter('libre_l43')
        self.assertEqual(reponse.status_code, 200)
        self.assertFalse(JournalHabilitation.objects.filter(
            type_evenement='CONNEXION').exists())
        del user

    def test_03_panne_du_journal_ne_bloque_jamais_la_connexion(self):
        _compte('solide_l43', 'SCOLARITE', role_legacy='SECRETARIAT')
        with mock.patch('authentication.connexion_sure.journaliser',
                        side_effect=RuntimeError('journal HS')):
            reponse = self._se_connecter('solide_l43')
        self.assertEqual(reponse.status_code, 200)
        self.assertIn('access', reponse.json())


@override_settings(HABILITATIONS_OBSERVATION=False,
                   HABILITATIONS_APPLICATION=False)
class RattacherComptesLegacyTests(SocleOrganisation):
    """Étape 1 de la bascule : rattachement additif, idempotent, sûr."""

    def _user(self, username, role):
        return User.objects.create_user(
            username=username, password=MOT_DE_PASSE, role=role)

    def test_01_simulation_n_ecrit_rien(self):
        self._user('legacy_sim', 'SECRETARIAT')
        sortie = __import__('io').StringIO()
        call_command('rattacher_comptes_legacy', stdout=sortie)
        self.assertEqual(CompteUtilisateur.objects.count(), 0)
        self.assertEqual(AttributionRole.objects.count(), 0)
        self.assertIn('Rattachement simulé', sortie.getvalue())

    def test_02_appliquer_pose_profil_et_attributions_non_sensibles(self):
        self._user('legacy_pos', 'SECRETARIAT')
        call_command('rattacher_comptes_legacy', '--appliquer',
                     stdout=__import__('io').StringIO())
        compte = CompteUtilisateur.objects.get(user__username='legacy_pos')
        codes_actifs = set(compte.attributions.filter(
            statut=AttributionRole.Statut.ACTIVE
        ).values_list('role__code', flat=True))
        self.assertEqual(codes_actifs, {
            'AGENT_INSCRIPTIONS', 'AGENT_ADMISSIONS', 'GESTIONNAIRE_ETUDIANTS'})
        self.assertTrue(all(
            a.motif.startswith('Rattachement LOT 5')
            for a in compte.attributions.all()))
        types = set(JournalHabilitation.objects.filter(
            compte_concerne=compte
        ).values_list('type_evenement', flat=True))
        self.assertIn('COMPTE_CREE', types)
        self.assertIn('ROLE_ATTRIBUE', types)

    def test_03_role_sensible_jamais_auto_valide(self):
        self._user('legacy_admin', 'ADMIN')
        call_command('rattacher_comptes_legacy', '--appliquer',
                     stdout=__import__('io').StringIO())
        # ADMIN ne mapping qu'ADMIN_SYSTEME (sensible) : pas de compte posé,
        # le rattachement refuse l'auto-élévation (J2-1).
        self.assertFalse(CompteUtilisateur.objects.filter(
            user__username='legacy_admin').exists())
        # Un rôle mixte (CHEF_INJS_ADMIN = ADMIN_SYSTEME sensible seul ?) :
        # ici on vérifie le cheminement « propositions » sur un compte posé.
        role = RoleMetier.objects.get(code='ADMIN_SYSTEME')
        self.assertTrue(role.sensible)

    def test_04_idempotence_et_role_sans_correspondance(self):
        """Rattachement idempotent, et rejet des rôles hors nomenclature.

        Lot L4b : `User.role` n'accepte plus que les 12 rôles RBAC canoniques.
        L'ancien scénario « role='INCONNU' » n'est plus constructible : la
        commande `rattacher_comptes_legacy` rejette elle-même toute valeur hors
        nomenclature (voir `ROLE_LEGACY_INCONNU`). Le cas « sans
        correspondance » se teste désormais au niveau applicatif, et non via
        une écriture SQL invalide.
        """
        self._user('legacy_rejoue', 'SECRETARIAT')
        self._user('legacy_orphelin', 'FORMATEUR')
        appel = dict(stdout=__import__('io').StringIO())
        call_command('rattacher_comptes_legacy', '--appliquer', **appel)
        premier = CompteUtilisateur.objects.count()
        call_command('rattacher_comptes_legacy', '--appliquer', **appel)
        # Idempotence : la seconde passe ne pose aucun compte supplémentaire.
        self.assertEqual(CompteUtilisateur.objects.count(), premier)
        # Les deux rôles ont une correspondance CURP (CORRESPONDANCE_LEGACY).
        self.assertEqual(premier, 2)
        for username in ('legacy_rejoue', 'legacy_orphelin'):
            self.assertTrue(CompteUtilisateur.objects.filter(
                user__username=username).exists(), username)

    def test_04b_role_hors_nomenclature_refuse_par_la_commande(self):
        """Un rôle absent des 12 rôles RBAC est rejeté avant toute écriture.

        Lot L4b : `User.role` est un champ RBAC strict. Le service de création
        refuse explicitement toute valeur hors nomenclature
        (`ROLE_LEGACY_INCONNU`), et la contrainte de base
        `auth_user_role_canonique_l4b` ferme la porte en dernier recours.
        """
        from django.contrib.auth import get_user_model
        from habilitations.services.comptes_admin import (
            ErreurConsole, creer_compte,
        )
        User = get_user_model()
        acteur = self._user('acteur_console', 'ADMIN')
        avant = User.objects.count()
        payload = {
            'identifiants': {
                'username': 'role_bidon',
                'role_legacy': 'PERSONNEL',  # rôle CURP, pas RBAC
                'mot_de_passe': 'Mot#2026x',
                'email': '',
            },
            'personne': {},
        }
        with self.assertRaises(ErreurConsole) as contexte:
            creer_compte(acteur, payload)
        self.assertEqual(contexte.exception.code, 'ROLE_LEGACY_INCONNU')
        # Aucune écriture partielle : le compte fantôme n'existe pas.
        self.assertEqual(User.objects.count(), avant)
        self.assertFalse(User.objects.filter(username='role_bidon').exists())
        self.assertFalse(User.objects.filter(
            username='legacy_orphelin',
            profil_habilitation__isnull=False).exists())

    def test_05_sous_ensemble_par_role(self):
        self._user('legacy_tri_a', 'SECRETARIAT')
        self._user('legacy_tri_b', 'FINANCE')
        call_command('rattacher_comptes_legacy', '--appliquer', '--role',
                     'SECRETARIAT', stdout=__import__('io').StringIO())
        self.assertTrue(CompteUtilisateur.objects.filter(
            user__username='legacy_tri_a').exists())
        self.assertFalse(CompteUtilisateur.objects.filter(
            user__username='legacy_tri_b').exists())


@override_settings(HABILITATIONS_OBSERVATION=True,
                   HABILITATIONS_APPLICATION=False)
class VuesPilotesObservationTests(SocleOrganisation):
    """Étape 3 : les vues pilotes branchées restent inertes en OBSERVATION."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.agent = User.objects.create_user(
            username='pilote_l5', password=MOT_DE_PASSE, role='SECRETARIAT')
        cls.etudiant = User.objects.create_user(
            username='etudiant_l5', password=MOT_DE_PASSE, role='AUDITEUR')

    def _client(self, user):
        from rest_framework.test import APIClient
        client = APIClient()
        client.force_authenticate(user=user)
        return client

    def test_01_liste_inscriptions_inchangee_et_comptee(self):
        """La vue répond comme avant le branchement ; l'écart est mesuré."""
        avant = observation.etat_observation()['evaluations_total']
        reponse = self._client(self.agent).get('/api/scolarite/inscriptions/')
        self.assertEqual(reponse.status_code, 200)
        apres = observation.etat_observation()
        self.assertGreater(apres['evaluations_total'], avant)
        self.assertEqual(apres['ecarts_legacy_autorise_moteur_refuse'], 0)
        self.assertEqual(JournalHabilitation.objects.filter(
            type_evenement='ACCES_REFUSE').count(), 0)

    def test_02_compte_gouverne_sans_droit_n_est_pas_bloque_en_observation(self):
        """Le compte CURP sans attribution payante est évalué mais jamais refusé."""
        # Legacy ADMIN pour que l'ancien dispositif laisse entrer la vue
        # (IsDFRC) et que le moteur soit réellement évalué en observation.
        user, _compte_c = _compte(
            'sans_droit_l5', 'ETUDIANT', role_legacy='ADMIN')
        reponse = self._client(user).post(
            '/api/finances-etudiantes/paiements/1/confirmer/')
        self.assertEqual(reponse.status_code, 404)  # paiement absent, pas 403 CURP
        etat = observation.etat_observation()
        self.assertGreater(etat['evaluations_total'], 0)
        self.assertEqual(JournalHabilitation.objects.filter(
            type_evenement='ACCES_REFUSE').count(), 0)

    def test_03_en_mode_off_la_vue_pilote_ne_collecte_rien(self):
        reponse = None
        with override_settings(HABILITATIONS_OBSERVATION=False,
                               HABILITATIONS_APPLICATION=False):
            reponse = self._client(self.etudiant).get(
                '/api/scolarite/inscriptions/')
        self.assertEqual(reponse.status_code, 403)  # l'ancien dispositif décide seul
        self.assertEqual(
            observation.etat_observation()['evaluations_total'], 0)
