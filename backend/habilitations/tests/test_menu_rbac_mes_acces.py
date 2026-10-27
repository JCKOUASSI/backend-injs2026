"""Navigation RBAC — clé additive ``permissions_effectives`` sur ``mes-acces/``.

La réorganisation de la barre de navigation (menu piloté par les droits) a
besoin, pour un compte **gouverné**, de la liste des codes de permissions qu'il
détient réellement : rôles actifs (matrice) + dérogations OCTROI − RETRAIT.

Cette clé est **strictement additive et descriptive** :

* aucune clé existante de ``GET /api/habilitations/mes-acces/`` n'est modifiée ;
* aucune décision d'accès n'est changée (le moteur et les vues gardent leur
  autorité, l'interface ne fait que masquer/afficher des entrées) ;
* le calcul est **le même service** que celui de l'écran d'administration
  ``GET comptes/<pk>/effective-permissions/`` (réservé aux administrateurs),
  ici en lecture auto-portée.

Règles du chantier respectées : additif uniquement, aucun flush/drop/truncate,
tests de refus inclus (anonyme, compte non gouverné, attribution révoquée).
"""
from datetime import timedelta

from django.core.cache import cache
from django.utils import timezone
from rest_framework.test import APIClient, APITestCase

from habilitations.models import (
    AttributionRole, PermissionAttribuee, PermissionMetier,
)
from habilitations.services.comptes_admin import permissions_effectives
from habilitations.services.moteur import est_autorise
from parametres.flags import invalidate_flags_cache
from parametres.models import Parametre

from .helpers import (
    creer_attribution,
    creer_compte,
    creer_role,
    creer_user,
)

FLAG_CONSOLE = 'flag.curp_ui_admin'
CHEMIN = '/api/habilitations/mes-acces/'


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


class SocleMesAcces(APITestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()

    def tearDown(self):
        cache.clear()

    # -- fabrication ------------------------------------------------------
    def _role_avec(self, *codes):
        """Rôle portant les permissions ``module.ressource.action`` données."""
        self._sequence = getattr(self, '_sequence', 0) + 1
        role = creer_role(code=f'R_MENU_{self._sequence:03d}')
        for code in codes:
            role.permissions.add(self._permission(code))
        return role

    def _permission(self, code):
        """Permission partagée : le code est unique, on ne la recrée pas."""
        module, ressource, action = code.split('.')
        permission, _ = PermissionMetier.objects.get_or_create(
            code=code,
            defaults={
                'module': module, 'ressource': ressource, 'action': action,
                'libelle': code,
            },
        )
        return permission

    def _compte_gouverne(self, username='menu.user', role_legacy='SECRETARIAT'):
        user = creer_user(username=username, role_existant=role_legacy)
        return user, creer_compte(user=user)

    def _derogation(self, compte, code, sens, **kwargs):
        valeurs = {
            'compte': compte, 'permission': self._permission(code),
            'sens': sens,
            'motif': 'Dérogation de test (navigation RBAC).',
            'statut': PermissionAttribuee.Statut.ACTIVE,
            'date_debut': timezone.localdate() - timedelta(days=1),
            'date_fin': timezone.localdate() + timedelta(days=30),
        }
        valeurs.update(kwargs)
        return PermissionAttribuee.objects.create(**valeurs)

    def _mes_acces(self, user):
        self.client.force_authenticate(user)
        reponse = self.client.get(CHEMIN)
        self.assertEqual(reponse.status_code, 200)
        return reponse.json()


class RefusEtAbstentionTests(SocleMesAcces):
    """Garde-fous : personne n'obtient de liste de droits indue."""

    def test_01_anonyme_obtient_401(self):
        self.assertEqual(self.client.get(CHEMIN).status_code, 401)

    def test_02_compte_non_gouverne_ne_porte_pas_la_cle(self):
        """Sans profil CURP, le moteur s'abstient : aucune liste CURP exposée."""
        user = creer_user(username='menu.non.gouverne', role_existant='SECRETARIAT')
        corps = self._mes_acces(user)
        self.assertFalse(corps['gouverne'])
        self.assertNotIn('permissions_effectives', corps)

    def test_03_attribution_revoquee_ne_donne_rien(self):
        user, compte = self._compte_gouverne('menu.revoque')
        role = self._role_avec('scolarite.inscription.consulter')
        creer_attribution(
            compte, role, statut=AttributionRole.Statut.REVOQUEE)
        self.assertEqual(self._mes_acces(user)['permissions_effectives'], [])

    def test_04_attribution_expiree_ne_donne_rien(self):
        user, compte = self._compte_gouverne('menu.expire')
        role = self._role_avec('scolarite.inscription.consulter')
        creer_attribution(
            compte, role,
            date_debut=timezone.localdate() - timedelta(days=30),
            date_fin=timezone.localdate() - timedelta(days=1),
        )
        self.assertEqual(self._mes_acces(user)['permissions_effectives'], [])

    def test_05_derogation_proposee_non_signee_ne_donne_rien(self):
        user, compte = self._compte_gouverne('menu.proposee')
        self._derogation(
            compte, 'jurys.pv.signer', PermissionAttribuee.Sens.OCTROI,
            statut=PermissionAttribuee.Statut.PROPOSEE,
        )
        self.assertEqual(self._mes_acces(user)['permissions_effectives'], [])


class PermissionsEffectivesTests(SocleMesAcces):
    """Contenu de la clé additive."""

    def test_06_codes_des_roles_actifs_exposes(self):
        user, compte = self._compte_gouverne('menu.chef')
        role = self._role_avec(
            'scolarite.groupe.modifier', 'scolarite.dossier_etudiant.consulter')
        creer_attribution(compte, role)
        codes = self._mes_acces(user)['permissions_effectives']
        self.assertEqual(
            sorted(codes),
            ['scolarite.dossier_etudiant.consulter', 'scolarite.groupe.modifier'],
        )

    def test_07_liste_triee_sans_doublon(self):
        user, compte = self._compte_gouverne('menu.doublon')
        premier = self._role_avec('scolarite.groupe.modifier')
        second = self._role_avec('scolarite.groupe.modifier', 'jurys.pv.signer')
        creer_attribution(compte, premier)
        creer_attribution(compte, second)
        codes = self._mes_acces(user)['permissions_effectives']
        self.assertEqual(codes, sorted(codes))
        self.assertEqual(len(codes), len(set(codes)))
        self.assertEqual(
            codes, ['jurys.pv.signer', 'scolarite.groupe.modifier'])

    def test_08_derogation_octroi_ajoute_un_code(self):
        user, compte = self._compte_gouverne('menu.octroi')
        creer_attribution(compte, self._role_avec('scolarite.groupe.modifier'))
        self._derogation(
            compte, 'finances_etud.paiement.valider',
            PermissionAttribuee.Sens.OCTROI,
        )
        codes = self._mes_acces(user)['permissions_effectives']
        self.assertIn('finances_etud.paiement.valider', codes)
        self.assertIn('scolarite.groupe.modifier', codes)

    def test_09_derogation_retrait_a_la_priorite(self):
        """Un RETRAIT retire le code même s'il vient d'un rôle (règle S4)."""
        user, compte = self._compte_gouverne('menu.retrait')
        creer_attribution(compte, self._role_avec(
            'scolarite.groupe.modifier', 'jurys.pv.signer'))
        self._derogation(
            compte, 'jurys.pv.signer', PermissionAttribuee.Sens.RETRAIT)
        codes = self._mes_acces(user)['permissions_effectives']
        self.assertNotIn('jurys.pv.signer', codes)
        self.assertIn('scolarite.groupe.modifier', codes)

    def test_10_projection_plus_stricte_que_le_moteur_sur_un_retrait_leve(self):
        """Écart **caractérisé** (et fail-closed) entre projection et moteur.

        Le moteur applique la règle S4 : un RETRAIT global est levé par un OCTROI
        dérogatoire **postérieur** (contrôle 8). La projection
        ``permissions_effectives`` applique un RETRAIT prioritaire sans effet de
        date : le code reste absent de la liste exposée à l'interface.

        Pour la navigation, l'écart va dans le sens de la prudence : une entrée
        peut être masquée alors que le backend l'autoriserait — jamais l'inverse.
        Le backend reste la seule autorité (règle S3) ; rien n'est « corrigé »
        ici, l'état livré est simplement figé et documenté (voir
        ``docs/audit/permissions.md``, écart L4-07).
        """
        user, compte = self._compte_gouverne('menu.releve')
        creer_attribution(compte, self._role_avec('jurys.pv.signer'))
        self._derogation(
            compte, 'jurys.pv.signer', PermissionAttribuee.Sens.RETRAIT)
        self._derogation(
            compte, 'jurys.pv.signer', PermissionAttribuee.Sens.OCTROI)

        # Projection (navigation) : le retrait l'emporte, liste vide.
        self.assertEqual(self._mes_acces(user)['permissions_effectives'], [])

        # Moteur (autorité) : l'OCTROI postérieur lève le RETRAIT.
        decision = est_autorise(user, 'jurys.pv.signer')
        self.assertTrue(decision.autorise, decision.motifs)


class AdditiviteEtCoherenceTests(SocleMesAcces):
    """La clé n'a rien cassé et dit exactement ce que dit le service."""

    def test_11_cles_existantes_inchangees(self):
        user, compte = self._compte_gouverne('menu.additif')
        creer_attribution(compte, self._role_avec('scolarite.groupe.modifier'))
        corps = self._mes_acces(user)
        for cle in (
            'gouverne', 'mode', 'compte', 'attributions',
            'attributions_inactives', 'derogations_actives',
            'delegations_recues', 'delegations_donnees',
        ):
            self.assertIn(cle, corps)
        self.assertTrue(corps['gouverne'])
        self.assertIn('statut', corps['compte'])
        self.assertEqual(len(corps['attributions']), 1)

    def test_12_identique_au_service_permissions_effectives(self):
        user, compte = self._compte_gouverne('menu.service')
        creer_attribution(compte, self._role_avec(
            'scolarite.groupe.modifier', 'jurys.pv.signer'))
        self._derogation(
            compte, 'jurys.pv.signer', PermissionAttribuee.Sens.RETRAIT)
        self.assertEqual(
            self._mes_acces(user)['permissions_effectives'],
            sorted(permissions_effectives(compte)),
        )

    def test_13_identique_a_l_ecran_admin_effective_permissions(self):
        """Même vérité que l'endpoint administrateur (une seule source)."""
        user, compte = self._compte_gouverne('menu.cible', role_legacy='SECRETARIAT')
        creer_attribution(compte, self._role_avec('scolarite.groupe.modifier'))

        # La console reste gardée par le trio d'administration legacy + le
        # drapeau ``flag.curp_ui_admin`` : le profil CURP de l'administrateur
        # n'intervient pas dans cette garde (constat LOT 4).
        admin = creer_user(
            username='menu.admin', role_existant='ADMIN', is_staff=True)
        _drapeau_console(True)
        self.client.force_authenticate(admin)
        reponse = self.client.get(
            f'/api/habilitations/comptes/{compte.pk}/effective-permissions/')
        self.assertEqual(reponse.status_code, 200)
        self.assertEqual(
            reponse.json()['codes'],
            self._mes_acces(user)['permissions_effectives'],
        )

    def test_14_compte_sans_aucun_role_expose_une_liste_vide(self):
        user, _compte = self._compte_gouverne('menu.vide')
        self.assertEqual(self._mes_acces(user)['permissions_effectives'], [])
