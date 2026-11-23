"""U2 — contrôles 1 à 6 du moteur : session, gouvernance, statut, validité,
canal et MFA."""
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from habilitations.models import (
    CompteUtilisateur,
    PolitiqueSecurite,
)
from habilitations.services.moteur import est_autorise

from .helpers import (
    creer_attribution,
    creer_compte,
    creer_permission,
    creer_role,
    creer_user,
)

CODE_PERM = 'scol.inscription.creer'


def mettre_en_place(compte_statut=CompteUtilisateur.Statut.ACTIF, **kwargs_role):
    user = creer_user(username=f"mc-{CompteUtilisateur.objects.count() + 1}",
                      role_existant='ARCHIVE')
    compte = creer_compte(user=user, statut=compte_statut)
    permission = creer_permission(
        code_module='scol', ressource='inscription', action='creer')
    role = creer_role(code=f"R{CompteUtilisateur.objects.count()}", **kwargs_role)
    role.permissions.add(permission)
    creer_attribution(compte, role)
    return user, compte, role, permission


class ControlesCompteTests(TestCase):
    def test_non_authentifie_refuse_pour_anonyme(self):
        decision = est_autorise(None, CODE_PERM)
        self.assertFalse(decision.autorise)
        self.assertFalse(decision.gouverne)
        self.assertEqual(decision.motifs, ['NON_AUTHENTIFIE'])

    def test_compte_sans_profil_est_abstention_pas_refus(self):
        user = creer_user(username='mc-sans-profil', role_existant='SECRETARIAT')
        decision = est_autorise(user, CODE_PERM)
        self.assertFalse(decision.gouverne)
        self.assertFalse(decision.autorise)
        self.assertEqual(decision.motifs, [])

    def test_compte_invite_refuse(self):
        user, _, _, _ = mettre_en_place(compte_statut=CompteUtilisateur.Statut.INVITE)
        self.assertEqual(est_autorise(user, CODE_PERM).motifs, ['COMPTE_INVITE'])

    def test_compte_suspendu_refuse_pour_tous(self):
        user, _, _, _ = mettre_en_place(compte_statut=CompteUtilisateur.Statut.SUSPENDU)
        decision = est_autorise(user, CODE_PERM)
        self.assertFalse(decision.autorise)
        self.assertIn('COMPTE_SUSPENDU', decision.motifs)

    def test_compte_desactive_refuse_pour_tous(self):
        user, _, _, _ = mettre_en_place(compte_statut=CompteUtilisateur.Statut.DESACTIVE)
        self.assertIn('COMPTE_DESACTIVE', est_autorise(user, CODE_PERM).motifs)

    def test_compte_verrouille_refuse_pour_tous(self):
        user, _, _, _ = mettre_en_place(compte_statut=CompteUtilisateur.Statut.VERROUILLE)
        self.assertIn('COMPTE_VERROUILLE', est_autorise(user, CODE_PERM).motifs)

    def test_compte_statut_expire_refuse_pour_tous(self):
        user, _, _, _ = mettre_en_place(compte_statut=CompteUtilisateur.Statut.EXPIRE)
        self.assertIn('COMPTE_EXPIRE', est_autorise(user, CODE_PERM).motifs)

    def test_date_expiration_atteinte_refuse_meme_actif(self):
        user, compte, _, _ = mettre_en_place()
        compte.date_expiration = timezone.now() - timedelta(days=1)
        compte.save()
        decision = est_autorise(user, CODE_PERM)
        self.assertFalse(decision.autorise)
        self.assertIn('COMPTE_EXPIRATION_ATTEINTE', decision.motifs)

    def test_date_expiration_future_laisse_passer(self):
        user, compte, _, _ = mettre_en_place()
        compte.date_expiration = timezone.now() + timedelta(days=10)
        compte.save()
        self.assertTrue(est_autorise(user, CODE_PERM).autorise)

    def test_canal_mobile_refuse_sur_le_web(self):
        user = creer_user(username='mc-can', role_existant='ARCHIVE')
        compte = creer_compte(user=user, canal='MOBILE')
        permission = creer_permission(
            code_module='scol', ressource='inscription', action='consulter')
        role = creer_role(code='R_CAN_MOB')
        role.permissions.add(permission)
        creer_attribution(compte, role)
        decision_web = est_autorise(user, 'scol.inscription.consulter', canal='WEB')
        self.assertIn('CANAL_NON_AUTORISE', decision_web.motifs)
        decision_mob = est_autorise(user, 'scol.inscription.consulter', canal='MOBILE')
        self.assertTrue(decision_mob.autorise)

    def test_canal_impose_par_role_refuse_le_mauvais_canal(self):
        user = creer_user(username='mc-imp', role_existant='ARCHIVE')
        compte = creer_compte(user=user, canal='LES_DEUX')
        permission = creer_permission(
            code_module='badg', ressource='badge', action='consulter')
        role = creer_role(code='R_CAN_IMP', canal_impose='MOBILE')
        role.permissions.add(permission)
        creer_attribution(compte, role)
        decision = est_autorise(user, 'badg.badge.consulter', canal='WEB')
        self.assertFalse(decision.autorise)
        self.assertIn('CANAL_IMPOSE_PAR_ROLE', decision.motifs)

    def test_mfa_exige_par_role_sensible_refuse_sans_mfa(self):
        admin = creer_user(username='mc-mfa-admin', role_existant='ADMIN')
        user = creer_user(username='mc-mfa', role_existant='ARCHIVE')
        compte = creer_compte(user=user, mfa_actif=False)
        permission = creer_permission(
            code_module='rh', ressource='compte', action='administrer')
        role = creer_role(code='R_SENS', sensible=True)
        role.permissions.add(permission)
        creer_attribution(compte, role, valide_par=admin)
        decision = est_autorise(user, 'rh.compte.administrer')
        self.assertFalse(decision.autorise)
        self.assertIn('MFA_REQUIS_NON_ACTIF', decision.motifs)

    def test_mfa_actif_sur_role_sensible_signe_autorise(self):
        admin = creer_user(username='mc-mfa-ok-admin', role_existant='ADMIN')
        user = creer_user(username='mc-mfa-ok', role_existant='ARCHIVE')
        compte = creer_compte(user=user, mfa_actif=True)
        permission = creer_permission(
            code_module='rh', ressource='compte', action='consulter')
        role = creer_role(code='R_SENS_OK', sensible=True)
        role.permissions.add(permission)
        creer_attribution(compte, role, valide_par=admin)
        self.assertTrue(est_autorise(user, 'rh.compte.consulter').autorise)

    def test_mfa_exige_par_politique_refuse_sans_mfa(self):
        politique = PolitiqueSecurite.objet()
        politique.roles_mfa_obligatoire = ['R_POL_MFA']
        politique.save()
        user = creer_user(username='mc-pol', role_existant='ARCHIVE')
        compte = creer_compte(user=user, mfa_actif=False)
        permission = creer_permission(
            code_module='rh', ressource='agent', action='valider')
        role = creer_role(code='R_POL_MFA')
        role.permissions.add(permission)
        creer_attribution(compte, role)
        self.assertIn(
            'MFA_REQUIS_NON_ACTIF',
            est_autorise(user, 'rh.agent.valider').motifs,
        )
        compte.mfa_actif = True
        compte.save()
        self.assertTrue(est_autorise(user, 'rh.agent.valider').autorise)

    def test_role_sensible_sans_seconde_signature_refuse(self):
        user = creer_user(username='mc-ss', role_existant='ARCHIVE')
        compte = creer_compte(user=user, mfa_actif=True)
        permission = creer_permission(
            code_module='rh', ressource='recrut', action='valider')
        role = creer_role(code='R_SENS2', sensible=True)
        role.permissions.add(permission)
        creer_attribution(compte, role)  # pas de valide_par
        decision = est_autorise(user, 'rh.recrut.valider')
        self.assertFalse(decision.autorise)
        self.assertIn('ROLE_SENSIBLE_SANS_SECONDE_SIGNATURE', decision.motifs)
