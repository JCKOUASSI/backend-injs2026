"""U0-CURP — caractérisation du CLOISONNEMENT par secrétariat.

Le filtrage de périmètre est appliqué « à la source » dans
``formations/access.py`` (les vues DRF passent par ces querysets) :
* les rôles à périmètre global (trio admin, DIRECTION, ARCHIVE) voient tous
  les participants ;
* CHEF_SECRETARIAT / SECRETARIAT ne voient que les participants rattachés à
  LEUR secrétariat (directement ou via un module d'inscription) ;
* FINANCE n'a aucun participant dans le queryset opérationnel (son accès se
  limite aux fiches de lecture, voir ``participant_fiche_accessible``) ;
* un visiteur non authentifié ne voit rien.

Ces tests sont la garantie anti-fuite inter-secrétariat pendant toute la
refonte (règle S2).
"""
from django.contrib.auth import get_user_model
from django.test import TestCase

from formations.access import (
    participant_accessible,
    participant_fiche_accessible,
    participants_queryset_for_user,
)
from formations.models import Participant, Secretariat

User = get_user_model()

MOT_DE_PASSE = 'Cloi#2026x'


class CloisonnementSecretariatsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from authentication.role_groups import ensure_role_groups
        ensure_role_groups()

        cls.sec_a = Secretariat.objects.create(numero='SECR-CURP-A', nom='Secrétariat CURP A')
        cls.sec_b = Secretariat.objects.create(numero='SECR-CURP-B', nom='Secrétariat CURP B')
        cls.part_a = Participant.objects.create(
            matricule='CURP-PART-A', nom='PartA', prenom='Temoin', secretariat=cls.sec_a,
        )
        cls.part_b = Participant.objects.create(
            matricule='CURP-PART-B', nom='PartB', prenom='Temoin', secretariat=cls.sec_b,
        )
        cls.part_orpheline = Participant.objects.create(
            matricule='CURP-PART-ORPHELINE', nom='Orpheline', prenom='Temoin',
        )

        def compte(nom, role, secretariat=None):
            utilisateur = User.objects.create_user(
                username=nom, password=MOT_DE_PASSE, role=role,
            )
            if secretariat is not None:
                utilisateur.secretariat = secretariat
                utilisateur.save(update_fields=['secretariat'])
            return utilisateur

        cls.admin = compte('curp-admin', 'ADMIN')
        cls.direction = compte('curp-direction', 'DIRECTION')
        cls.archive = compte('curp-archive', 'ARCHIVE')
        cls.secretaire_a = compte('curp-sec-a', 'SECRETARIAT', cls.sec_a)
        cls.secretaire_b = compte('curp-sec-b', 'SECRETARIAT', cls.sec_b)
        cls.chef_a = compte('curp-chef-a', 'CHEF_SECRETARIAT', cls.sec_a)
        cls.finance = compte('curp-finance', 'FINANCE')
        cls.encadrant_libre = compte('curp-encadrant-libre', 'ENCADRANT')
        cls.secretaire_orphelin = compte('curp-sec-orphelin', 'SECRETARIAT', None)

    def _identifiants(self, utilisateur):
        return set(participants_queryset_for_user(utilisateur).values_list('pk', flat=True))

    # ── Preuve CROISÉE du cloisonnement ───────────────────────────────────
    def test_secretariat_a_autorise_pour_son_participant_uniquement(self):
        visibles = self._identifiants(self.secretaire_a)
        self.assertIn(self.part_a.pk, visibles)
        self.assertNotIn(self.part_b.pk, visibles)

    def test_secretariat_b_refuse_pour_le_participant_du_secretariat_a(self):
        visibles = self._identifiants(self.secretaire_b)
        self.assertIn(self.part_b.pk, visibles)
        self.assertNotIn(self.part_a.pk, visibles)

    def test_chef_secretariat_a_autorise_pour_son_perimetre_unique(self):
        visibles = self._identifiants(self.chef_a)
        self.assertEqual(visibles, {self.part_a.pk})

    # ── Périmètre global ──────────────────────────────────────────────────
    def test_admin_autorise_pour_les_deux_secretariats(self):
        visibles = self._identifiants(self.admin)
        self.assertIn(self.part_a.pk, visibles)
        self.assertIn(self.part_b.pk, visibles)

    def test_direction_autorise_pour_les_deux_secretariats(self):
        visibles = self._identifiants(self.direction)
        self.assertIn(self.part_a.pk, visibles)
        self.assertIn(self.part_b.pk, visibles)

    def test_archive_autorise_pour_les_deux_secretariats(self):
        visibles = self._identifiants(self.archive)
        self.assertIn(self.part_a.pk, visibles)
        self.assertIn(self.part_b.pk, visibles)

    # ── Cas particuliers du queryset de service ───────────────────────────
    def test_finance_refuse_pour_tous_les_participants_operationnels(self):
        visibles = self._identifiants(self.finance)
        self.assertEqual(visibles, set())

    def test_finance_autorise_pour_la_fiche_de_lecture_explicite(self):
        # participant_fiche_accessible est la voie de lecture dérogatoire
        # documentée pour FINANCE (alignée sur la fiche admin).
        self.assertIsNotNone(participant_fiche_accessible(self.finance, self.part_a.pk))

    def test_encadrant_sans_affectation_refuse_pour_tous_les_participants(self):
        # L'ENCADRANT ne voit que les participants des modules dont il est
        # superviseur ; sans affectation, le périmètre est vide.
        visibles = self._identifiants(self.encadrant_libre)
        self.assertEqual(visibles, set())

    def test_secretaire_non_rattache_ne_voit_que_les_participants_orphelins(self):
        visibles = self._identifiants(self.secretaire_orphelin)
        self.assertEqual(visibles, {self.part_orpheline.pk})
        self.assertNotIn(self.part_a.pk, visibles)

    def test_visiteur_anonyme_refuse_pour_tous_les_participants(self):
        from django.contrib.auth.models import AnonymousUser
        self.assertEqual(
            participants_queryset_for_user(AnonymousUser()).count(), 0
        )
        self.assertIsNone(participant_accessible(AnonymousUser(), self.part_a.pk))

    def test_participant_hors_perimetre_non_accessible_par_identifiant(self):
        # Le verrou tient même en devinant l'identifiant (pas d'IDOR).
        self.assertIsNone(participant_accessible(self.secretaire_a, self.part_b.pk))
        self.assertIsNotNone(participant_accessible(self.secretaire_a, self.part_a.pk))

    # ── ÉCART DE DEFENSE EN PROFONDEUR (à instruire en U2) ────────────────
    def test_repli_fonction_service_est_permissif_pour_roles_non_geres(self):
        # COMPORTEMENT ACTUEL CARACTÉRISÉ : participants_queryset_for_user
        # renvoie TOUS les participants pour les rôles qui ne tombent dans
        # aucune branche (SUPERVISEUR) ni dans l'exclusion FINANCE, et pour
        # les rôles mobiles (FORMATEUR/AUDITEUR). La fonction est supposée
        # filtrer « à la source » ; ce repli large est un point dur à
        # instruire en U2 (le moteur est_autorise devra le resserrer).
        formateur = User.objects.create_user(
            username='curp-form-fuite', password=MOT_DE_PASSE, role='FORMATEUR')
        auditeur = User.objects.create_user(
            username='curp-aud-fuite', password=MOT_DE_PASSE, role='AUDITEUR')
        superviseur = User.objects.create_user(
            username='curp-sup-fuite', password=MOT_DE_PASSE, role='SUPERVISEUR')
        for compte in (formateur, auditeur, superviseur):
            with self.subTest(role=compte.role):
                visibles = self._identifiants(compte)
                self.assertIn(self.part_a.pk, visibles)
                self.assertIn(self.part_b.pk, visibles)


class BarriereApiParticipantsTests(TestCase):
    """La permission DRF est la vraie barrière quand la fonction de service
    est permise : ces tests HTTP prouvent que les rôles non listés ne peuvent
    pas atteindre la liste des participants, même avec un jeton valide."""

    _compteur = 0

    @classmethod
    def setUpTestData(cls):
        from authentication.role_groups import ensure_role_groups
        ensure_role_groups()
        cls.sec = Secretariat.objects.create(numero='SECR-BAR-1', nom='Secrétariat barrière')
        Participant.objects.create(
            matricule='BAR-P1', nom='Bar', prenom='P1', secretariat=cls.sec)

    def _reponse(self, role, route):
        from rest_framework.test import APIClient
        numero = BarriereApiParticipantsTests._compteur
        BarriereApiParticipantsTests._compteur += 1
        compte = User.objects.create_user(
            username=f'curp-bar-{numero}-{role.lower()}',
            password=MOT_DE_PASSE, role=role,
        )
        if role in ('SECRETARIAT', 'CHEF_SECRETARIAT'):
            compte.secretariat = self.sec
            compte.save(update_fields=['secretariat'])
        client = APIClient()
        client.force_authenticate(compte)
        return client.get(route)

    def test_route_classique_refuse_aux_roles_non_dfrc(self):
        # ParticipantListCreateView : trio admin + DIRECTION/ARCHIVE (lecture)
        # + ENCADRANT ; les secrétariats passent par la route de recherche.
        for role in ('SUPERVISEUR', 'FINANCE', 'FORMATEUR', 'AUDITEUR',
                     'SECRETARIAT', 'CHEF_SECRETARIAT'):
            with self.subTest(role=role):
                self.assertEqual(
                    self._reponse(role, '/api/formations/participants/').status_code, 403)

    def test_route_classique_autorise_aux_roles_dfrc_et_encadrant(self):
        for role in ('ADMIN', 'DIRECTION', 'ARCHIVE', 'ENCADRANT'):
            with self.subTest(role=role):
                self.assertEqual(
                    self._reponse(role, '/api/formations/participants/').status_code, 200)

    def test_route_recherche_refuse_aux_roles_exclus(self):
        # CanListParticipants : exclus FINANCE, FORMATEUR, AUDITEUR,
        # SUPERVISEUR ; c'est elle qui ferme la porte au repli permissif.
        for role in ('SUPERVISEUR', 'FINANCE', 'FORMATEUR', 'AUDITEUR'):
            with self.subTest(role=role):
                self.assertEqual(
                    self._reponse(role, '/api/formations/participants/list/').status_code, 403)

    def test_route_recherche_autorise_aux_roles_listes(self):
        for role in ('ADMIN', 'DIRECTION', 'ARCHIVE', 'ENCADRANT',
                     'SECRETARIAT', 'CHEF_SECRETARIAT'):
            with self.subTest(role=role):
                self.assertEqual(
                    self._reponse(role, '/api/formations/participants/list/').status_code, 200)

    def test_deux_routes_exigent_un_jeton(self):
        from rest_framework.test import APIClient
        for route in ('/api/formations/participants/',
                      '/api/formations/participants/list/'):
            with self.subTest(route=route):
                self.assertEqual(APIClient().get(route).status_code, 401)
