"""Tests du LOT 4 — scénario de bout en bout du prompt §35.

Le §35 demande un parcours complet, du provisionnement à l'audit :

    création → rôles → organisation → périmètre → connexion → menu →
    accès autorisé / accès interdit → modification de rôle → recalcul → audit

Ce fichier l'exécute **réellement** : chaque étape passe par l'API livrée
(console CURP U4, organisation LOT 3, authentification LOT 2) avec le moteur
d'autorisation en **mode APPLICATION** sur la base de test (``override_settings``
— le défaut livré OFF n'est jamais modifié, aucune vue métier n'est branchée :
LOT 5 / U8 sur feu vert séparé).

Le scénario complet est un **test unique** (``test_01``) : un parcours de bout
en bout n'a de sens que si l'état se propage d'une étape à l'autre, ce que le
rejeu par savepoint de Django interdirait en tests séparés. Les tests suivants
rejouent des étapes isolées pour verrouiller des propriétés précises (menu,
recalcul, piste d'audit, garde-fous de la console).

Deux constats sont documentés par les tests eux-mêmes (ni masqués, ni corrigés
ici — le LOT 4 est un lot de tests et de documentation) :

* la console ne sait poser qu'un périmètre **secrétariat** sur une attribution
  (``perimetres_secretariats``) : le périmètre DIRECTION du scénario est posé
  par l'ORM, comme le ferait l'admin Django aujourd'hui ;
* une connexion réussie trace ``presences.AuditLog`` (USER_LOGIN) et alimente
  ``last_login`` / ``derniere_connexion``, mais n'émet pas d'événement
  ``CONNEXION`` au journal d'habilitation (type prévu, non émis).
"""
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.test import override_settings
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory, APITestCase, force_authenticate

from administrations.models import Departement, Direction
from habilitations.models import (
    AttributionRole,
    CompteUtilisateur,
    JournalHabilitation,
    Perimetre,
    RoleMetier,
)
from habilitations.permissions import ExigePermission
from habilitations.referentiel.chargement import charger_referentiel
from habilitations.services import observation
from habilitations.services.journalisation import verifier_chaine
from parametres.flags import invalidate_flags_cache
from parametres.models import Parametre
from presences.models import AuditLog
from ressources_humaines.models import Service

User = get_user_model()

APPLICATION = dict(HABILITATIONS_OBSERVATION=True, HABILITATIONS_APPLICATION=True)

FLAG_CONSOLE = 'flag.curp_ui_admin'
MOT_DE_PASSE_ADMIN = 'Admin!2026curp'
MOT_DE_PASSE_CHEF = 'ChefDept!2026x'
MOT_DE_PASSE_AGENT = 'AgentScol!2026x'

CHEF_USERNAME = 'chef.dept.sports'
AGENT_USERNAME = 'agent.scolarite'

#: Droit attendu du chef de département (matrice J2 : scolarite N2).
DROIT_CHEF = 'scolarite.groupe.modifier'
#: Acte hors de sa matrice (aucune colonne « jurys » pour CHEF_DEPARTEMENT).
DROIT_INTERDIT = 'jurys.pv.signer'
#: Lecture conservée après la bascule du rôle en CONSULTATION (scolarite N0).
DROIT_LECTURE = 'scolarite.dossier_etudiant.consulter'


def _drapeau_console(actif=True):
    Parametre.objects.update_or_create(
        cle=FLAG_CONSOLE,
        defaults={
            'libelle': 'Console CURP', 'categorie': 'flags', 'type': 'bool',
            'valeur': 'true' if actif else 'false',
            'valeur_defaut': 'false', 'actif': True,
        },
    )
    invalidate_flags_cache()


def _requete(user):
    brute = APIRequestFactory().get('/api/lot4/sonde/')
    force_authenticate(brute, user=user)
    return Request(brute)


@override_settings(**APPLICATION)
class SocleE2E(APITestCase):
    """Référentiel chargé, console ouverte, administrateur habilité."""

    @classmethod
    def setUpTestData(cls):
        charger_referentiel()

    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        observation.remettre_a_zero()
        _drapeau_console(True)
        self.admin = User.objects.create_user(
            username='admin_e2e', password=MOT_DE_PASSE_ADMIN,
            role='ADMIN', is_staff=True, email='admin.e2e@injs.ci')
        self.comme_admin()

    def tearDown(self):
        from django.core.cache import cache
        cache.clear()
        observation.remettre_a_zero()
        super().tearDown()

    # ── Bascules d'identité du client de test ──────────────────────────
    def comme_admin(self):
        self.client.credentials()
        self.client.force_authenticate(self.admin)

    def comme_anonyme(self):
        self.client.credentials()
        self.client.force_authenticate(None)

    def comme_utilisateur(self, user, jeton=None):
        """Authentifie par jeton si fourni, sinon par forçage (console)."""
        self.client.force_authenticate(None)
        if jeton:
            self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {jeton}')
        else:
            self.client.force_authenticate(user)

    # ── Étapes du scénario §35 (réutilisables par les tests ciblés) ─────
    def etape_1_creation(self, username=CHEF_USERNAME, role='CHEF_DEPARTEMENT',
                         niveau='N3', mot_de_passe=MOT_DE_PASSE_CHEF,
                         role_legacy='CHEF_SECRETARIAT', nom='TRAORE',
                         prenoms='Fatou'):
        return self.client.post(
            '/api/habilitations/comptes/',
            {
                'identifiants': {
                    'username': username, 'email': f'{username}@injs.ci',
                    'mot_de_passe': mot_de_passe, 'role_legacy': role_legacy,
                },
                'personne': {'nom': nom, 'prenoms': prenoms},
                'canal': 'WEB',
                'motif': 'Nomination chef de département sports (scénario LOT 4).',
                'roles': [{'role': role, 'niveau': niveau}],
            },
            format='json')

    def etape_3_organisation(self, compte_id, code_direction='DG',
                             code_departement='DEPT-SPORT',
                             nom_service='Service des sports',
                             code_autre='DAE'):
        """Direction → Département → Service + rattachement du compte."""
        direction = self.client.post(
            '/api/habilitations/organisation/directions/',
            {'code': code_direction, 'libelle': 'Direction générale', 'ordre': 1},
            format='json')
        self.assertEqual(direction.status_code, 201, direction.data)
        departement = self.client.post(
            '/api/habilitations/organisation/departements/',
            {'code': code_departement, 'libelle': 'Département sports',
             'direction': direction.data['id'], 'ordre': 1},
            format='json')
        self.assertEqual(departement.status_code, 201, departement.data)
        service = self.client.post(
            '/api/habilitations/organisation/services/',
            {'nom': nom_service, 'departement': departement.data['id']},
            format='json')
        self.assertEqual(service.status_code, 201, service.data)
        rattachement_dept = self.client.post(
            '/api/habilitations/organisation/departements/'
            f"{departement.data['id']}/comptes/",
            {'compte_id': compte_id}, format='json')
        self.assertEqual(rattachement_dept.status_code, 200, rattachement_dept.data)
        rattachement_service = self.client.post(
            '/api/habilitations/organisation/services/'
            f"{service.data['id']}/comptes/",
            {'compte_id': compte_id}, format='json')
        self.assertEqual(rattachement_service.status_code, 200,
                         rattachement_service.data)
        autre = self.client.post(
            '/api/habilitations/organisation/directions/',
            {'code': code_autre, 'libelle': 'Direction des études', 'ordre': 2},
            format='json')
        self.assertEqual(autre.status_code, 201, autre.data)
        return (Direction.objects.get(pk=direction.data['id']),
                Departement.objects.get(pk=departement.data['id']),
                Service.objects.get(pk=service.data['id']),
                Direction.objects.get(pk=autre.data['id']))

    def etape_4_perimetre(self, compte, direction):
        """Pose le périmètre DIRECTION (la console ne pose que SECRETARIAT)."""
        perimetre = Perimetre.objects.create(
            type=Perimetre.Type.DIRECTION,
            content_type=ContentType.objects.get_for_model(Direction),
            object_id=direction.pk,
            reference_lisible=direction.code, libelle=direction.libelle)
        attribution = compte.attributions.get(statut=AttributionRole.Statut.ACTIVE)
        attribution.perimetres.add(perimetre)
        return perimetre

    def etape_5_connexion(self, username=CHEF_USERNAME,
                          mot_de_passe=MOT_DE_PASSE_CHEF):
        self.comme_anonyme()
        # ``format='json'`` (et non ``content_type``) : le client DRF sérialise
        # lui-même le corps, là où le client Django accepte un dict brut.
        return self.client.post(
            '/api/auth/login/',
            {'username': username, 'password': mot_de_passe},
            format='json')

    def _journal(self, **filtres):
        return JournalHabilitation.objects.filter(**filtres).order_by('numero')

    def _types_journal(self, compte=None):
        qs = self._journal()
        if compte is not None:
            qs = qs.filter(compte_concerne=compte)
        return [e.type_evenement for e in qs]

    def _codes_motifs(self, reponse):
        return [motif['code'] for motif in reponse.data['motifs']]


# ===========================================================================
# §35 — le scénario complet, d'un seul tenant
# ===========================================================================
@override_settings(**APPLICATION)
class ScenarioE2ETests(SocleE2E):
    def test_01_scenario_complet_du_prompt_35(self):
        # ── Étape 1 — création du compte par la console CURP ───────────
        creation = self.etape_1_creation()
        self.assertEqual(creation.status_code, 201, creation.data)
        compte_id = creation.data['id']
        compte = CompteUtilisateur.objects.get(pk=compte_id)
        self.assertEqual(compte.statut, CompteUtilisateur.Statut.ACTIF)
        self.assertEqual(compte.user.username, CHEF_USERNAME)
        self.assertEqual(compte.user.role, 'CHEF_SECRETARIAT')
        self.assertIn('COMPTE_CREE', self._types_journal(compte))

        # ── Étape 2 — rôles attribués à la création ────────────────────
        fiche = self.client.get(f'/api/habilitations/comptes/{compte_id}/')
        self.assertEqual(fiche.status_code, 200)
        self.assertEqual(fiche.data['nb_roles'], 1)
        self.assertEqual(fiche.data['roles_actifs'][0]['role'], 'CHEF_DEPARTEMENT')
        self.assertEqual(fiche.data['roles_actifs'][0]['niveau'], 'N3')
        self.assertIn('ROLE_ATTRIBUE', self._types_journal(compte))

        # ── Étape 3 — organisation (LOT 1 + LOT 3) ─────────────────────
        direction, departement, service, autre_direction = \
            self.etape_3_organisation(compte_id)
        self.assertEqual(departement.direction_id, direction.pk)
        self.assertEqual(service.departement_id, departement.pk)
        self.assertIn(departement, compte.departements.all())
        self.assertIn(service, compte.services.all())
        self.assertGreaterEqual(
            JournalHabilitation.objects.filter(
                type_evenement='ORGANISATION_MODIFIEE').count(), 6)

        # ── Étape 4 — périmètre posé sur l'attribution ─────────────────
        perimetre = self.etape_4_perimetre(compte, direction)
        self.assertEqual(perimetre.cible, direction)
        effectives = self.client.get(
            f'/api/habilitations/comptes/{compte_id}/effective-permissions/')
        self.assertEqual(effectives.status_code, 200)
        self.assertIn(DROIT_CHEF, effectives.data['codes'])
        self.assertNotIn(DROIT_INTERDIT, effectives.data['codes'])
        total_avant = effectives.data['count']

        # ── Étape 5 — connexion (LOT 2 : JWT + horodatages) ────────────
        connexion = self.etape_5_connexion()
        self.assertEqual(connexion.status_code, 200, connexion.data)
        jeton = connexion.data['access']
        self.assertTrue(jeton)
        self.assertFalse(connexion.data['must_change_password'])
        compte.refresh_from_db()
        compte.user.refresh_from_db()
        self.assertIsNotNone(compte.user.last_login)
        self.assertIsNotNone(compte.derniere_connexion)
        self.assertTrue(AuditLog.objects.filter(
            action=AuditLog.Action.USER_LOGIN,
            cible_numero=CHEF_USERNAME).exists())

        # ── Étape 6 — menu : projection des capacités (lecture seule) ──
        self.comme_utilisateur(compte.user, jeton)
        capacites = self.client.get('/api/auth/capabilities/')
        self.assertEqual(capacites.status_code, 200)
        projection = capacites.data['habilitations']
        self.assertTrue(projection['gouverne'])
        self.assertEqual(projection['mode'], 'APPLICATION')
        self.assertEqual(projection['attributions_actives'], 1)
        self.assertEqual(projection['statut'], 'ACTIF')
        # La projection CURP n'ouvre aucune capacité d'administration : le
        # menu reste piloté par le dispositif legacy tant que le LOT 5 n'est
        # pas passé (règle S3 : le backend est la seule autorité).
        self.assertEqual(
            capacites.data['capacites'].get('habilitations_admin', []), [])
        mes_acces = self.client.get('/api/habilitations/mes-acces/')
        self.assertEqual(mes_acces.status_code, 200)
        self.assertEqual(
            mes_acces.data['attributions'][0]['role'], 'CHEF_DEPARTEMENT')
        self.assertEqual(
            mes_acces.data['attributions'][0]['perimetres'][0]['reference'],
            direction.code)

        # ── Étape 7 — accès autorisé (dans le périmètre) ───────────────
        autorise = self.client.post(
            '/api/habilitations/evaluer/',
            {'permission': DROIT_CHEF,
             'cible': {'type': Perimetre.Type.DIRECTION,
                       'object_id': direction.pk}},
            format='json')
        self.assertEqual(autorise.status_code, 200)
        self.assertTrue(autorise.data['autorise'], autorise.data['motifs'])
        self.assertEqual(autorise.data['mode'], 'APPLICATION')
        self.assertEqual(autorise.data['octrois'][0]['role'], 'CHEF_DEPARTEMENT')

        # ── Étape 8 — accès interdit (autre direction, acte hors matrice)
        interdit = self.client.post(
            '/api/habilitations/evaluer/',
            {'permission': DROIT_CHEF,
             'cible': {'type': Perimetre.Type.DIRECTION,
                       'object_id': autre_direction.pk}},
            format='json')
        self.assertEqual(interdit.status_code, 200)
        self.assertFalse(interdit.data['autorise'])
        self.assertIn('CIBLE_HORS_PERIMETRE', self._codes_motifs(interdit))
        hors_matrice = self.client.post(
            '/api/habilitations/evaluer/', {'permission': DROIT_INTERDIT},
            format='json')
        self.assertFalse(hors_matrice.data['autorise'])
        self.assertIn('AUCUNE_ATTRIBUTION_PERMETTANTE',
                      self._codes_motifs(hors_matrice))

        # Un refus produit par la permission DRF est tracé au journal.
        self.assertFalse(
            ExigePermission(DROIT_INTERDIT).has_permission(
                _requete(compte.user), None))
        refus = JournalHabilitation.objects.filter(
            type_evenement='ACCES_REFUSE', compte_concerne=compte)
        self.assertEqual(refus.count(), 1)
        self.assertEqual(refus.first().nouvelle_valeur['permission'], DROIT_INTERDIT)

        # Un agent de scolarité n'entre pas dans la console des comptes.
        self.comme_admin()
        agent = self.etape_1_creation(
            username=AGENT_USERNAME, role='AGENT_INSCRIPTIONS', niveau='N2',
            mot_de_passe=MOT_DE_PASSE_AGENT, role_legacy='SECRETARIAT',
            nom='CONDE', prenoms='Mariam')
        self.assertEqual(agent.status_code, 201, agent.data)
        agent_user = User.objects.get(username=AGENT_USERNAME)
        self.comme_utilisateur(agent_user)
        self.assertEqual(
            self.client.get('/api/habilitations/comptes/').status_code, 403)
        self.assertEqual(
            self.client.get(
                f'/api/habilitations/comptes/{compte_id}/effective-permissions/'
            ).status_code, 403)

        # ── Étape 9 — modification de rôle (différentiel obligatoire) ──
        self.comme_admin()
        simulation = self.client.post(
            f'/api/habilitations/comptes/{compte_id}/simuler-modification/',
            {'roles': [{'role': 'CONSULTATION'}]}, format='json')
        self.assertEqual(simulation.status_code, 200)
        self.assertIn(DROIT_CHEF, simulation.data['perdus'])
        self.assertIn(DROIT_LECTURE,
                      simulation.data['conserves'] + simulation.data['gagnes'])
        self.assertEqual(simulation.data['roles_retires'], ['CHEF_DEPARTEMENT'])
        self.assertEqual(simulation.data['roles_ajoutes'], ['CONSULTATION'])

        sans_acceptation = self.client.patch(
            f'/api/habilitations/comptes/{compte_id}/modifier/',
            {'roles': [{'role': 'CONSULTATION'}]}, format='json')
        self.assertEqual(sans_acceptation.status_code, 409)
        self.assertEqual(sans_acceptation.data['code'], 'DIFFERENTIEL_REQUIS')

        modification = self.client.patch(
            f'/api/habilitations/comptes/{compte_id}/modifier/',
            {'roles': [{'role': 'CONSULTATION'}], 'differential_accepte': True,
             'motif': 'Fin de mandat : bascule en consultation seule.'},
            format='json')
        self.assertEqual(modification.status_code, 200, modification.data)
        self.assertEqual(
            modification.data['roles_actifs'][0]['role'], 'CONSULTATION')
        self.assertEqual(
            modification.data['roles_inactifs'][0]['role'], 'CHEF_DEPARTEMENT')
        self.assertEqual(
            AttributionRole.objects.get(
                compte=compte, role__code='CHEF_DEPARTEMENT').statut,
            AttributionRole.Statut.REVOQUEE)
        self.assertIn('ROLE_REVOQUE', self._types_journal(compte))

        # ── Étape 10 — recalcul des permissions effectives ─────────────
        apres = self.client.get(
            f'/api/habilitations/comptes/{compte_id}/effective-permissions/')
        self.assertNotIn(DROIT_CHEF, apres.data['codes'])
        self.assertIn(DROIT_LECTURE, apres.data['codes'])
        self.assertLess(apres.data['count'], total_avant)

        # Le compte connecté voit ses droits recalculés sans nouvelle
        # connexion : le même jeton porte la décision mise à jour.
        self.comme_utilisateur(compte.user, jeton)
        recalcul = self.client.post(
            '/api/habilitations/evaluer/', {'permission': DROIT_CHEF},
            format='json')
        self.assertFalse(recalcul.data['autorise'])
        self.assertIn('AUCUNE_ATTRIBUTION_PERMETTANTE',
                      self._codes_motifs(recalcul))
        lecture = self.client.post(
            '/api/habilitations/evaluer/', {'permission': DROIT_LECTURE},
            format='json')
        self.assertTrue(lecture.data['autorise'], lecture.data['motifs'])
        capacites_apres = self.client.get('/api/auth/capabilities/')
        self.assertEqual(
            capacites_apres.data['habilitations']['attributions_actives'], 1)
        mes_acces_apres = self.client.get('/api/habilitations/mes-acces/')
        self.assertEqual(
            mes_acces_apres.data['attributions'][0]['role'], 'CONSULTATION')
        self.assertEqual(
            [a['role'] for a in mes_acces_apres.data['attributions_inactives']],
            ['CHEF_DEPARTEMENT'])

        # ── Étape 11 — audit : chaîne immuable et événements attendus ──
        types = self._types_journal(compte)
        for attendu in ('COMPTE_CREE', 'ROLE_ATTRIBUE', 'ROLE_REVOQUE',
                        'ACCES_REFUSE'):
            self.assertIn(attendu, types)
        self.assertIn('ORGANISATION_MODIFIEE', self._types_journal())
        self.assertEqual(verifier_chaine(), [])
        self.comme_admin()
        integrite = self.client.get('/api/habilitations/journal/integrite/')
        self.assertEqual(integrite.status_code, 200)
        self.assertTrue(integrite.data['integre'], integrite.data['anomalies'])
        self.assertEqual(integrite.data['anomalies'], [])
        self.assertGreaterEqual(integrite.data['total'], len(types))
        self.assertEqual(
            RoleMetier.objects.get(code='CONSULTATION').actif, True)
        # Rien n'est supprimé (règle S5) : les deux attributions demeurent.
        self.assertEqual(AttributionRole.objects.filter(compte=compte).count(), 2)


# ===========================================================================
# Propriétés vérifiées étape par étape (rejeu isolé)
# ===========================================================================
@override_settings(**APPLICATION)
class EtapesIsoleesE2ETests(SocleE2E):
    def _compte_chef(self, avec_perimetre=True):
        creation = self.etape_1_creation()
        self.assertEqual(creation.status_code, 201, creation.data)
        compte = CompteUtilisateur.objects.get(pk=creation.data['id'])
        if avec_perimetre:
            direction = Direction.objects.create(
                code='DG', libelle='Direction générale')
            self.etape_4_perimetre(compte, direction)
        return compte

    def test_02_menu_et_projections_pour_le_compte_connecte(self):
        compte = self._compte_chef()
        self.comme_utilisateur(compte.user)
        capacites = self.client.get('/api/auth/capabilities/')
        self.assertEqual(capacites.status_code, 200)
        self.assertTrue(capacites.data['habilitations']['gouverne'])
        self.assertEqual(capacites.data['habilitations']['mode'], 'APPLICATION')
        self.assertEqual(capacites.data['habilitations']['statut'], 'ACTIF')
        self.assertEqual(capacites.data['habilitations']['mfa_actif'], False)
        mes_acces = self.client.get('/api/habilitations/mes-acces/')
        self.assertEqual(mes_acces.status_code, 200)
        self.assertEqual(mes_acces.data['compte']['canal'], 'WEB')
        self.assertEqual(
            mes_acces.data['attributions'][0]['perimetres'][0]['type'], 'DIRECTION')

    def test_03_recalcul_apres_revocation_du_role(self):
        compte = self._compte_chef()
        avant = self.client.get(
            f'/api/habilitations/comptes/{compte.pk}/effective-permissions/')
        self.assertIn(DROIT_CHEF, avant.data['codes'])
        modification = self.client.patch(
            f'/api/habilitations/comptes/{compte.pk}/modifier/',
            {'roles': [{'role': 'CONSULTATION'}], 'differential_accepte': True,
             'motif': 'Bascule en consultation seule (test LOT 4).'},
            format='json')
        self.assertEqual(modification.status_code, 200, modification.data)
        apres = self.client.get(
            f'/api/habilitations/comptes/{compte.pk}/effective-permissions/')
        self.assertNotIn(DROIT_CHEF, apres.data['codes'])
        self.assertIn(DROIT_LECTURE, apres.data['codes'])
        # La révocation ne supprime rien (règle S5) : l'attribution demeure.
        self.assertEqual(AttributionRole.objects.filter(compte=compte).count(), 2)

    def test_04_piste_d_audit_complete_et_integre(self):
        compte = self._compte_chef(avec_perimetre=False)
        direction, _departement, _service, _autre = \
            self.etape_3_organisation(compte.pk)
        self.etape_4_perimetre(compte, direction)
        connexion = self.etape_5_connexion()
        self.assertEqual(connexion.status_code, 200, connexion.data)
        self.assertFalse(
            ExigePermission(DROIT_INTERDIT).has_permission(
                _requete(compte.user), None))
        types = self._types_journal(compte)
        self.assertIn('COMPTE_CREE', types)
        self.assertIn('ROLE_ATTRIBUE', types)
        self.assertIn('ACCES_REFUSE', types)
        self.assertIn('ORGANISATION_MODIFIEE', self._types_journal())
        self.assertEqual(verifier_chaine(), [])
        # Chaque geste sensible porte un motif non vide (exigence d'audit).
        for entree in self._journal(compte_concerne=compte):
            self.assertTrue(entree.motif.strip(), f'entrée {entree.numero} sans motif')
        self.assertTrue(AuditLog.objects.filter(
            action=AuditLog.Action.USER_LOGIN,
            cible_numero=CHEF_USERNAME).exists())

    def test_05_journal_filtrable_par_compte_et_par_type(self):
        compte = self._compte_chef()
        self.comme_admin()
        par_compte = self.client.get(
            f'/api/habilitations/journal/?compte={compte.pk}')
        self.assertEqual(par_compte.status_code, 200)
        self.assertTrue(par_compte.data['results'])
        self.assertTrue(all(
            ligne['compte'] == compte.pk for ligne in par_compte.data['results']))
        par_type = self.client.get(
            '/api/habilitations/journal/?type=ACCES_REFUSE')
        self.assertEqual(par_type.status_code, 200)
        self.assertEqual(par_type.data['results'], [])

    def test_06_console_fermee_par_drapeau_meme_pour_l_admin(self):
        _drapeau_console(False)
        self.assertEqual(
            self.client.get('/api/habilitations/comptes/').status_code, 403)
        self.assertEqual(
            self.client.get(
                '/api/habilitations/organisation/directions/').status_code, 403)

    def test_07_creation_refusee_sans_motif_ou_avec_role_inconnu(self):
        sans_motif = self.client.post(
            '/api/habilitations/comptes/',
            {'identifiants': {'username': 'x1', 'mot_de_passe': 'Essai!2026x',
                              'role_legacy': 'SECRETARIAT'},
             'personne': {'nom': 'X', 'prenoms': 'Y'}},
            format='json')
        self.assertEqual(sans_motif.status_code, 400)
        role_inconnu = self.client.post(
            '/api/habilitations/comptes/',
            {'identifiants': {'username': 'x2', 'mot_de_passe': 'Essai!2026x',
                              'role_legacy': 'SECRETARIAT'},
             'personne': {'nom': 'X', 'prenoms': 'Y'},
             'motif': 'Test de rôle inconnu.',
             'roles': [{'role': 'ROLE_INEXISTANT'}]},
            format='json')
        self.assertEqual(role_inconnu.status_code, 400)
        self.assertEqual(role_inconnu.data['code'], 'ROLE_INCONNU')
        # La création est atomique : aucun compte fantôme ne subsiste.
        self.assertFalse(User.objects.filter(username__in=['x1', 'x2']).exists())

    def test_08_doublon_d_identifiant_refuse(self):
        premiere = self.etape_1_creation()
        self.assertEqual(premiere.status_code, 201)
        seconde = self.etape_1_creation()
        self.assertEqual(seconde.status_code, 409)
        self.assertEqual(seconde.data['code'], 'IDENTIFIANT_EXISTANT')
        self.assertEqual(
            CompteUtilisateur.objects.filter(
                user__username=CHEF_USERNAME).count(), 1)

    def test_09_suspension_du_compte_coupe_les_acces(self):
        """Machine à états A5 : un compte suspendu n'a plus aucun droit."""
        compte = self._compte_chef()
        suspension = self.client.post(
            f'/api/habilitations/comptes/{compte.pk}/statut/',
            {'transition': 'suspendre',
             'motif': 'Suspension de test (scénario LOT 4).'},
            format='json')
        self.assertEqual(suspension.status_code, 200, suspension.data)
        self.assertEqual(suspension.data['statut'], 'SUSPENDU')
        self.comme_utilisateur(compte.user)
        decision = self.client.post(
            '/api/habilitations/evaluer/', {'permission': DROIT_CHEF},
            format='json')
        self.assertFalse(decision.data['autorise'])
        self.assertIn('COMPTE_SUSPENDU', self._codes_motifs(decision))
        self.assertIn('COMPTE_SUSPENDU', self._types_journal(compte))
