"""Tests U4 — console web d'administration des comptes (prompt C2).

Le drapeau ``flag.curp_ui_admin`` est éteint par défaut : on l'active par
test (sans jamais toucher au défaut livré). Les vérifications portent sur
le garde drapeau+rôle, la création assistée, le différentiel obligatoire,
les changements de statut, la garde des deux administrateurs, les
dérogations/délégations, la simulation d'import sans écriture et le journal.
"""
from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from habilitations.models import (
    AttributionRole,
    CompteUtilisateur,
    JournalHabilitation,
    Personne,
)
from parametres.flags import invalidate_flags_cache
from parametres.models import Parametre

User = get_user_model()

FLAG_CLE = 'flag.curp_ui_admin'


def _admin_user(username='admin4'):
    return User.objects.create_user(
        username=username, password='Mot#2026x', role='ADMIN',
        is_staff=True,
    )


class ConsoleU4Tests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        # Référentiel U3 en base — chargé UNE FOIS par classe (le standard
        # déjà appliqué par test_lot4_e2e_scenario / test_lot4_refus_croises).
        # Le recharger dans `setUp` le recréait avant chaque test (81 rôles,
        # 1 155 permissions) : c'était la lenteur dominante de la suite.
        from habilitations.referentiel.chargement import charger_referentiel
        charger_referentiel()

    def setUp(self):
        _admin_user()
        self.admin = User.objects.get(username='admin4')
        # Un secrétariat (rôle opérationnel, pas admin habilitations).
        self.secretariat = User.objects.create_user(
            username='secret4', password='Mot#2026x', role='SECRETARIAT',
        )

    def _drapeau(self, actif=True):
        Parametre.objects.update_or_create(
            cle=FLAG_CLE,
            defaults={
                'libelle': 'Console CURP', 'categorie': 'flags',
                'type': 'bool', 'valeur': 'true' if actif else 'false',
                'valeur_defaut': 'false', 'actif': True,
            },
        )
        invalidate_flags_cache()

    def tearDown(self):
        # Le cache de flags est partagé par le processus (LocMem) et n'est
        # pas remis à zéro par le rollback de la transaction : on le purge
        # pour ne pas polluer les tests suivants (contrat de capacités).
        from django.core.cache import cache
        cache.clear()
        super().tearDown()

    def _auth(self, user=None):
        self.client.force_authenticate(user or self.admin)

    def _creer_payload(self, username='curp_x', role='AGENT_INSCRIPTIONS',
                       legacy='SECRETARIAT', **kwargs):
        payload = {
            'identifiants': {
                'username': username, 'email': f'{username}@injs.ci',
                'mot_de_passe': 'Essai#2026', 'role_legacy': legacy,
            },
            'personne': {'nom': 'Test', 'prenoms': 'Compte'},
            'canal': 'WEB',
            'motif': 'Création de test U4.',
            'roles': [{'role': role, 'niveau': kwargs.get('niveau', 'N2')}],
        }
        payload.update(kwargs)
        return payload

    # ── Garde drapeau / capacité ──────────────────────────────────────
    def test_01_drapeau_ferme_les_endpoints_sont_403(self):
        self._drapeau(False)
        self._auth()
        reponse = self.client.get('/api/habilitations/comptes/')
        self.assertEqual(reponse.status_code, 403)

    def test_02_secretariat_refuse_meme_drapeau_ouvert(self):
        self._drapeau(True)
        self._auth(self.secretariat)
        reponse = self.client.get('/api/habilitations/comptes/')
        self.assertEqual(reponse.status_code, 403)

    def test_03_admin_accede_quand_le_drapeau_est_ouvert(self):
        self._drapeau(True)
        self._auth()
        reponse = self.client.get('/api/habilitations/comptes/')
        self.assertEqual(reponse.status_code, 200)
        self.assertEqual(reponse.data['count'], 0)

    def test_04_capacite_habilitations_admin_derivee_du_drapeau(self):
        from authentication.capabilities import compute_capabilities
        self._drapeau(False)
        self.assertEqual(
            compute_capabilities(self.admin)['capacites']['habilitations_admin'], []
        )
        self._drapeau(True)
        self.assertEqual(
            compute_capabilities(self.admin)['capacites']['habilitations_admin'],
            ['gerer'],
        )
        self.assertEqual(
            compute_capabilities(self.secretariat)['capacites']['habilitations_admin'],
            [],
        )

    # ── Création assistée ─────────────────────────────────────────────
    def test_05_creation_compte_complete_et_journalisee(self):
        self._drapeau(True)
        self._auth()
        reponse = self.client.post(
            '/api/habilitations/comptes/',
            self._creer_payload(username='curp_ada', role='AGENT_INSCRIPTIONS'),
            format='json',
        )
        self.assertEqual(reponse.status_code, 201, reponse.data)
        compte = CompteUtilisateur.objects.get(user__username='curp_ada')
        self.assertEqual(compte.statut, CompteUtilisateur.Statut.ACTIF)
        self.assertEqual(compte.user.role, 'SECRETARIAT')
        self.assertTrue(compte.user.is_active)
        self.assertTrue(compte.personne.matricule)
        self.assertEqual(
            compte.attributions.get(statut='ACTIVE').role.code,
            'AGENT_INSCRIPTIONS',
        )
        types = set(JournalHabilitation.objects.values_list('type_evenement', flat=True))
        self.assertIn('COMPTE_CREE', types)
        self.assertIn('ROLE_ATTRIBUE', types)

    def test_06_doublon_identifiant_refuse_409(self):
        self._drapeau(True)
        self._auth()
        self.client.post('/api/habilitations/comptes/',
                         self._creer_payload(username='curp_dbl'), format='json')
        reponse = self.client.post('/api/habilitations/comptes/',
                                   self._creer_payload(username='curp_dbl'),
                                   format='json')
        self.assertEqual(reponse.status_code, 409)

    def test_07_personne_existante_reutilisee_par_matricule(self):
        self._drapeau(True)
        self._auth()
        personne = Personne.objects.create(
            matricule='PERS-EXIST', nom='Existante', prenoms='Awa',
        )
        payload = self._creer_payload(username='curp_exist')
        payload['personne'] = {'matricule': 'PERS-EXIST'}
        reponse = self.client.post('/api/habilitations/comptes/', payload, format='json')
        self.assertEqual(reponse.status_code, 201, reponse.data)
        self.assertEqual(CompteUtilisateur.objects.get(
            user__username='curp_exist').personne_id, personne.pk)
        self.assertEqual(Personne.objects.filter(matricule='PERS-EXIST').count(), 1)

    # ── Différentiel obligatoire (règle d'interface S2) ───────────────
    def _compte_cree(self, username='curp_mod', role='AGENT_INSCRIPTIONS'):
        self._drapeau(True)
        self._auth()
        reponse = self.client.post('/api/habilitations/comptes/',
                                   self._creer_payload(username=username, role=role),
                                   format='json')
        return reponse.data['id']

    def test_08_differential_retourne_gagnes_et_perdus(self):
        self._drapeau(True)
        self._auth()
        pk = self._compte_cree()
        reponse = self.client.post(
            f'/api/habilitations/comptes/{pk}/simuler-modification/',
            {'roles': [{'role': 'SCOLARITE', 'niveau': 'N3'}]}, format='json',
        )
        self.assertEqual(reponse.status_code, 200)
        self.assertIn('SCOLARITE', reponse.data['roles_ajoutes'])
        self.assertIn('AGENT_INSCRIPTIONS', reponse.data['roles_retires'])
        self.assertGreater(len(reponse.data['gagnes']), 0)

    def test_09_modification_sans_acquittement_refusee_409(self):
        self._drapeau(True)
        self._auth()
        pk = self._compte_cree()
        reponse = self.client.patch(
            f'/api/habilitations/comptes/{pk}/modifier/',
            {'roles': [{'role': 'SCOLARITE', 'niveau': 'N3'}],
             'motif': 'Promotion'}, format='json',
        )
        self.assertEqual(reponse.status_code, 409)
        self.assertEqual(reponse.data['code'], 'DIFFERENTIEL_REQUIS')

    def test_10_modification_avec_acquittement_appliquee(self):
        self._drapeau(True)
        self._auth()
        pk = self._compte_cree()
        reponse = self.client.patch(
            f'/api/habilitations/comptes/{pk}/modifier/',
            {'roles': [{'role': 'SCOLARITE', 'niveau': 'N3', 'motif': 'Promotion'}],
             'motif': 'Promotion', 'differential_accepte': True}, format='json',
        )
        self.assertEqual(reponse.status_code, 200, reponse.data)
        codes = [r['role'] for r in reponse.data['roles_actifs']]
        self.assertEqual(codes, ['SCOLARITE'])
        # L'ancienne attribution est révoquée (pas supprimée).
        self.assertTrue(
            AttributionRole.objects.filter(
                compte_id=pk, role__code='AGENT_INSCRIPTIONS',
                statut='REVOQUEE',
            ).exists()
        )
        self.assertIn('ROLE_REVOQUE',
                      set(JournalHabilitation.objects.values_list('type_evenement', flat=True)))

    def test_11_couple_incompatible_signale(self):
        self._drapeau(True)
        self._auth()
        pk = self._compte_cree(role='GESTIONNAIRE_NOTES')
        reponse = self.client.post(
            f'/api/habilitations/comptes/{pk}/simuler-modification/',
            {'roles': [
                {'role': 'GESTIONNAIRE_NOTES'},
                {'role': 'RESPONSABLE_JURY', 'niveau': 'N4'},
            ]}, format='json',
        )
        codes = [a['code'] for a in reponse.data['avertissements']]
        self.assertEqual(codes.count('ROLES_INCOMPATIBLES'), 1)

    # ── Statuts et garde des deux administrateurs ─────────────────────
    def test_12_changement_statut_exige_un_motif(self):
        self._drapeau(True)
        self._auth()
        pk = self._compte_cree(username='curp_st')
        reponse = self.client.post(
            f'/api/habilitations/comptes/{pk}/statut/',
            {'transition': 'suspendre', 'motif': ''}, format='json',
        )
        self.assertEqual(reponse.status_code, 400)

    def test_13_suspension_miroire_sur_le_compte_de_connexion(self):
        self._drapeau(True)
        self._auth()
        pk = self._compte_cree(username='curp_su')
        reponse = self.client.post(
            f'/api/habilitations/comptes/{pk}/statut/',
            {'transition': 'suspendre', 'motif': 'Absence prolongée.'},
            format='json',
        )
        self.assertEqual(reponse.status_code, 200, reponse.data)
        compte = CompteUtilisateur.objects.get(pk=pk)
        self.assertEqual(compte.statut, CompteUtilisateur.Statut.SUSPENDU)
        self.assertFalse(compte.user.is_active)

    def _creer_admin_curp(self, username):
        reponse = self.client.post(
            '/api/habilitations/comptes/',
            self._creer_payload(username=username, role='ADMIN_SYSTEME',
                                legacy='ADMIN', niveau='N4',
                                roles=[{'role': 'ADMIN_SYSTEME', 'niveau': 'N4',
                                        'sensible_valide': True,
                                        'motif': 'Administrateur'}]),
            format='json',
        )
        return reponse.data['id']

    def test_14_garde_deux_administrateurs_refuse_le_dernier_retrait(self):
        from habilitations.services.comptes_admin import administrateurs_actifs
        self._drapeau(True)
        self._auth()
        # Au départ un seul admin (admin4, legacy). On en crée deux autres, on
        # doit pouvoir en neutraliser deux mais pas le dernier des deux restants.
        a = self._creer_admin_curp('curp_a1')
        self._creer_admin_curp('curp_a2')
        self.assertGreaterEqual(administrateurs_actifs(), 3)
        # Neutraliser un des trois : reste 2 → autorisé.
        reponse = self.client.post(
            f'/api/habilitations/comptes/{a}/statut/',
            {'transition': 'desactiver', 'motif': 'Fin de mission.'}, format='json',
        )
        self.assertEqual(reponse.status_code, 200, reponse.data)
        self.assertEqual(administrateurs_actifs(), 2)
        # Tenter de désactiver un autre admin du reste via son compte : il n'en
        # reste que 2 (admin4 + a2), tout nouveau retrait est bloqué.
        a2 = CompteUtilisateur.objects.get(user__username='curp_a2')
        reponse = self.client.post(
            f'/api/habilitations/comptes/{a2.pk}/statut/',
            {'transition': 'desactiver', 'motif': 'Fin de mission.'}, format='json',
        )
        self.assertEqual(reponse.status_code, 409)
        self.assertEqual(reponse.data['code'], 'SEUIL_ADMINISTRATEURS')

    # ── Dérogations / délégations ─────────────────────────────────────
    def test_15_derogation_octroi_non_bornee_refusee(self):
        self._drapeau(True)
        self._auth()
        pk = self._compte_cree(username='curp_der')
        reponse = self.client.post(
            '/api/habilitations/derogations/',
            {'compte': pk, 'permission': 'evaluations.note.saisir',
             'sens': 'OCTROI', 'motif': 'Rattrapage ponctuel.'}, format='json',
        )
        self.assertEqual(reponse.status_code, 400)

    def test_16_derogation_bornee_creee_et_revoquee_avec_motif(self):
        self._drapeau(True)
        self._auth()
        pk = self._compte_cree(username='curp_der2')
        reponse = self.client.post(
            '/api/habilitations/derogations/',
            {'compte': pk, 'permission': 'evaluations.note.saisir',
             'sens': 'OCTROI', 'motif': 'Rattrapage.',
             'date_fin': '2026-12-31'}, format='json',
        )
        self.assertEqual(reponse.status_code, 201, reponse.data)
        derogation_id = reponse.data['id']
        # Révocation sans motif refusée.
        self.assertEqual(
            self.client.post(
                f'/api/habilitations/derogations/{derogation_id}/revoquer/',
                {}, format='json').status_code,
            400,
        )
        reponse = self.client.post(
            f'/api/habilitations/derogations/{derogation_id}/revoquer/',
            {'motif': 'Plus nécessaire.'}, format='json',
        )
        self.assertEqual(reponse.status_code, 200)

    def test_17_delegation_soi_meme_refusee(self):
        self._drapeau(True)
        self._auth()
        pk = self._compte_cree(username='curp_dg1')
        reponse = self.client.post(
            '/api/habilitations/delegations/',
            {'delegant': pk, 'delegataire': pk, 'date_fin': '2026-12-31',
             'motif': 'Test.'}, format='json',
        )
        self.assertEqual(reponse.status_code, 400)

    def test_18_delegation_creee_et_terminee(self):
        self._drapeau(True)
        self._auth()
        d1 = self._compte_cree(username='curp_dla', role='RESPONSABLE_PEDAGOGIQUE')
        d2 = self._compte_cree(username='curp_dlb', role='AGENT_INSCRIPTIONS')
        reponse = self.client.post(
            '/api/habilitations/delegations/',
            {'delegant': d1, 'delegataire': d2,
             'roles': ['RESPONSABLE_PEDAGOGIQUE'],
             'date_fin': '2026-12-31', 'motif': 'Congé.'}, format='json',
        )
        self.assertEqual(reponse.status_code, 201, reponse.data)
        delegation_id = reponse.data['id']
        reponse = self.client.post(
            f'/api/habilitations/delegations/{delegation_id}/terminer/',
            {'motif': 'Retour anticipé.'}, format='json',
        )
        self.assertEqual(reponse.status_code, 200)

    # ── Import (aperçu seul), revue, journal ──────────────────────────
    def test_19_import_apercu_necrit_rien(self):
        self._drapeau(True)
        self._auth()
        avant = CompteUtilisateur.objects.count()
        reponse = self.client.post(
            '/api/habilitations/comptes/import-simuler/',
            {'lignes': [
                {'username': 'curp_imp1', 'nom': 'Ici',
                 'mot_de_passe': 'Essai#2026', 'roles': 'ENSEIGNANT'},
                {'username': '', 'nom': 'SansLogin', 'mot_de_passe': 'x'},
            ]}, format='json',
        )
        self.assertEqual(reponse.status_code, 200)
        self.assertEqual(reponse.data['valides'], 1)
        self.assertEqual(reponse.data['erreurs'], 1)
        self.assertFalse(reponse.data['ecriture'])
        self.assertEqual(CompteUtilisateur.objects.count(), avant)

    def test_20_journal_et_integrite(self):
        self._drapeau(True)
        self._auth()
        self._compte_cree(username='curp_jr')
        reponse = self.client.get('/api/habilitations/journal/integrite/')
        self.assertEqual(reponse.status_code, 200)
        self.assertTrue(reponse.data['integre'])
        reponse = self.client.get('/api/habilitations/journal/?type=COMPTE_CREE')
        self.assertGreaterEqual(reponse.data['count'], 1)

    def test_21_role_detail_et_matrice(self):
        self._drapeau(True)
        self._auth()
        reponse = self.client.get('/api/habilitations/roles/ADMIN_SYSTEME/')
        self.assertEqual(reponse.status_code, 200)
        # 1155 + 2 codes lot A refonte (administrations.organigramme.consulter/gerer).
        self.assertEqual(reponse.data['permissions_count'], 1157)
        reponse = self.client.get('/api/habilitations/matrice/')
        self.assertEqual(reponse.status_code, 200)
        self.assertEqual(len(reponse.data['lignes']), 81)
        self.assertEqual(len(reponse.data['modules']), 20)

    def test_22_revue_est_consultative(self):
        self._drapeau(True)
        self._auth()
        reponse = self.client.get('/api/habilitations/comptes/revue/')
        self.assertEqual(reponse.status_code, 200)
        self.assertTrue(reponse.data['consultation_seule'])

    def test_23_recherche_personne(self):
        self._drapeau(True)
        self._auth()
        Personne.objects.create(matricule='PERS-Z', nom='Zouzoua', prenoms='Kouamé')
        reponse = self.client.get('/api/habilitations/personnes/?q=Zou')
        self.assertEqual(reponse.status_code, 200)
        self.assertEqual(reponse.data['resultats'][0]['matricule'], 'PERS-Z')
