"""U2 — contrôle 7 et 8 du moteur : octrois par rôle, dérogations OCTROI,
priorité du RETRAIT."""
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from habilitations.models import (
    AttributionRole,
    PermissionAttribuee,
    PermissionMetier,
)
from habilitations.services.moteur import est_autorise
from habilitations.services.validations import declarer_incompatibilite

from .helpers import (
    creer_attribution,
    creer_compte,
    creer_derogation,
    creer_permission,
    creer_role,
    creer_user,
    date_dans,
    date_il_y_a,
)


class OctroiRoleTests(TestCase):
    def setUp(self):
        self.user = creer_user(username='mo-1', role_existant='ARCHIVE')
        self.compte = creer_compte(user=self.user)
        self.perm = creer_permission(
            code_module='scol', ressource='inscription', action='creer')
        self.role = creer_role(code='R_OCTROI')
        self.role.permissions.add(self.perm)

    def test_role_actif_autorise_pour_titulaire(self):
        creer_attribution(self.compte, self.role)
        decision = est_autorise(self.user, 'scol.inscription.creer')
        self.assertTrue(decision.autorise)
        self.assertEqual(decision.octrois[0].source, 'ROLE')

    def test_attribution_proposee_ne_donne_rien(self):
        creer_attribution(
            self.compte, self.role, statut=AttributionRole.Statut.PROPOSEE)
        decision = est_autorise(self.user, 'scol.inscription.creer')
        self.assertFalse(decision.autorise)
        self.assertIn('AUCUNE_ATTRIBUTION_PERMETTANTE', decision.motifs)

    def test_attribution_expiree_ne_donne_rien(self):
        creer_attribution(
            self.compte, self.role,
            statut=AttributionRole.Statut.ACTIVE, date_fin=date_il_y_a(2))
        self.assertFalse(
            est_autorise(self.user, 'scol.inscription.creer').autorise)

    def test_attribution_future_ne_donne_rien(self):
        creer_attribution(
            self.compte, self.role, date_debut=date_dans(5))
        self.assertFalse(
            est_autorise(self.user, 'scol.inscription.creer').autorise)

    def test_role_inactif_ne_donne_rien(self):
        self.role.actif = False
        self.role.save()
        creer_attribution(self.compte, self.role)
        self.assertFalse(
            est_autorise(self.user, 'scol.inscription.creer').autorise)

    def test_module_requis_absent_bloque_l_octroi(self):
        self.role.module_requis = 'application_inexistante_xyz'
        self.role.save()
        creer_attribution(self.compte, self.role)
        decision = est_autorise(self.user, 'scol.inscription.creer')
        self.assertFalse(decision.autorise)
        self.assertIn('MODULE_REQUIS_ABSENT', decision.motifs)

    def test_roles_incompatibles_bloquent_les_deux_octrois(self):
        perm_b = creer_permission(
            code_module='rh', ressource='paie', action='valider')
        role_b = creer_role(code='R_INC_B')
        role_b.permissions.add(perm_b)
        declarer_incompatibilite(self.role, role_b)
        creer_attribution(self.compte, self.role)
        creer_attribution(self.compte, role_b)
        decision_a = est_autorise(self.user, 'scol.inscription.creer')
        decision_b = est_autorise(self.user, 'rh.paie.valider')
        self.assertFalse(decision_a.autorise)
        self.assertFalse(decision_b.autorise)
        self.assertIn('ROLES_INCOMPATIBLES', decision_a.motifs)

    def test_niveau_insuffisant_refuse_selon_contexte(self):
        self.role.niveau_defaut = 'N1'
        self.role.save()
        creer_attribution(self.compte, self.role, niveau='N1')
        decision = est_autorise(
            self.user, 'scol.inscription.creer',
            contexte={'niveau_minimum': 'N3'})
        self.assertFalse(decision.autorise)
        self.assertIn('NIVEAU_INSUFFISANT', decision.motifs)

    def test_permission_inconnue_refusee(self):
        creer_attribution(self.compte, self.role)
        self.assertEqual(
            est_autorise(self.user, 'inexistant.rien.faire').motifs,
            ['PERMISSION_INCONNUE'],
        )


class DerogationOctroiTests(TestCase):
    def setUp(self):
        self.user = creer_user(username='mo-2', role_existant='ARCHIVE')
        self.compte = creer_compte(user=self.user)
        self.perm = creer_permission(
            code_module='rh', ressource='agent', action='modifier')

    def test_octroi_derogatoire_borne_autorise(self):
        creer_derogation(
            self.compte, self.perm, statut=PermissionAttribuee.Statut.ACTIVE,
            date_debut=date_il_y_a(1), date_fin=date_dans(30))
        decision = est_autorise(self.user, 'rh.agent.modifier')
        self.assertTrue(decision.autorise)
        self.assertEqual(decision.octrois[0].source, 'DEROGATION_OCTROI')

    def test_octroi_sans_date_fin_refuse(self):
        creer_derogation(
            self.compte, self.perm, statut=PermissionAttribuee.Statut.ACTIVE,
            date_debut=date_il_y_a(1), date_fin=None)
        self.assertIn(
            'DEROGATION_SANS_DATE_FIN',
            est_autorise(self.user, 'rh.agent.modifier').motifs,
        )

    def test_octroi_trop_long_refuse(self):
        creer_derogation(
            self.compte, self.perm, statut=PermissionAttribuee.Statut.ACTIVE,
            date_debut=timezone.localdate(), date_fin=date_dans(365))
        self.assertIn(
            'DEROGATION_TROP_LONGUE',
            est_autorise(self.user, 'rh.agent.modifier').motifs,
        )

    def test_octroi_periode_incoherente_ne_donne_rien(self):
        # Une période incohérente (fin avant début) ne peut jamais contenir
        # aujourd'hui : la dérogation n'est pas active et n'octroie rien. Le
        # contrôle pur de cohérence est testé par ailleurs (U1).
        creer_derogation(
            self.compte, self.perm, statut=PermissionAttribuee.Statut.ACTIVE,
            date_debut=date_dans(10), date_fin=date_dans(5))
        decision = est_autorise(self.user, 'rh.agent.modifier')
        self.assertFalse(decision.autorise)
        self.assertEqual(decision.octrois, [])

    def test_octroi_critique_sans_seconde_signature_refuse(self):
        perm = PermissionMetier.objects.get(code='rh.agent.modifier')
        perm.necessite_double_validation = True
        perm.save()
        creer_derogation(
            self.compte, perm, statut=PermissionAttribuee.Statut.ACTIVE,
            date_debut=date_il_y_a(1), date_fin=date_dans(10))
        self.assertIn(
            'DEROGATION_SANS_SECONDE_SIGNATURE',
            est_autorise(self.user, 'rh.agent.modifier').motifs,
        )

    def test_octroi_depassant_la_portee_maximale_refuse(self):
        from .helpers import creer_perimetre_secretariat, secretariat
        sec = secretariat(numero='SECR-PORT', nom='Portée')
        per_global = creer_perimetre_secretariat(sec)
        perm = creer_permission(
            code_module='form', ressource='fiche', action='consulter',
            portee_maximale='GROUPE')
        creer_derogation(
            self.compte, perm, statut=PermissionAttribuee.Statut.ACTIVE,
            date_debut=date_il_y_a(1), date_fin=date_dans(10),
            perimetre=per_global)
        self.assertIn(
            'DEROGATION_HORS_PORTEE_MAXIMALE',
            est_autorise(self.user, 'form.fiche.consulter').motifs,
        )


class RetraitTests(TestCase):
    def setUp(self):
        self.admin = creer_user(username='mo-admin', role_existant='ADMIN')
        self.user = creer_user(username='mo-3', role_existant='ARCHIVE')
        self.compte = creer_compte(user=self.user)
        self.perm = creer_permission(
            code_module='scol', ressource='fiche', action='consulter')
        self.role = creer_role(code='R_RETRAIT')
        self.role.permissions.add(self.perm)
        creer_attribution(self.compte, self.role)

    def test_retrait_global_refuse_meme_avec_role(self):
        creer_derogation(
            self.compte, self.perm, sens=PermissionAttribuee.Sens.RETRAIT,
            statut=PermissionAttribuee.Statut.ACTIVE,
            date_debut=date_il_y_a(1), date_fin=None)
        decision = est_autorise(self.user, 'scol.fiche.consulter')
        self.assertFalse(decision.autorise)
        self.assertIn('PERMISSION_RETIREE', decision.motifs)

    def test_retrait_permanent_est_autorise_pour_le_sens_retrait(self):
        retrait = creer_derogation(
            self.compte, self.perm, sens=PermissionAttribuee.Sens.RETRAIT,
            statut=PermissionAttribuee.Statut.ACTIVE,
            date_debut=date_il_y_a(1), date_fin=None)
        self.assertTrue(retrait.est_active())
        self.assertFalse(
            est_autorise(self.user, 'scol.fiche.consulter').autorise)

    def test_retrait_cible_hors_zone_sans_effet(self):
        from .helpers import creer_perimetre_secretariat, secretariat
        sec_a = secretariat(numero='SECR-A-RT', nom='A')
        sec_b = secretariat(numero='SECR-B-RT', nom='B')
        per_a = creer_perimetre_secretariat(sec_a)
        creer_derogation(
            self.compte, self.perm, sens=PermissionAttribuee.Sens.RETRAIT,
            statut=PermissionAttribuee.Statut.ACTIVE,
            date_debut=date_il_y_a(1), date_fin=None, perimetre=per_a)
        # La cible est dans le secrétariat B : non couverte par le retrait.
        decision = est_autorise(
            self.user, 'scol.fiche.consulter',
            cible={'type': 'SECRETARIAT', 'object_id': sec_b.pk})
        # Le rôle n'a pas de périmètre attaché : rien ne couvre B non plus,
        # mais ce n'est pas un RETRAIT.
        self.assertNotIn('PERMISSION_RETIREE', decision.motifs)

    def test_octroi_posterieur_signe_leve_un_retrait_global(self):
        retrait = creer_derogation(
            self.compte, self.perm, sens=PermissionAttribuee.Sens.RETRAIT,
            statut=PermissionAttribuee.Statut.ACTIVE,
            date_debut=date_il_y_a(30), date_fin=None)
        # Un OCTROI postérieur, doublement signé, lève le retrait.
        octroi = creer_derogation(
            self.compte, self.perm, sens=PermissionAttribuee.Sens.OCTROI,
            statut=PermissionAttribuee.Statut.ACTIVE,
            date_debut=timezone.localdate(), date_fin=date_dans(10),
            valide_par=self.admin)
        octroi.date_creation = retrait.date_creation + timedelta(days=1)
        octroi.save()
        self.assertTrue(
            est_autorise(self.user, 'scol.fiche.consulter').autorise)
