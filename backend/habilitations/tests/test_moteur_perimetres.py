"""U2 — contrôles 9 et 10 : couverture des cibles par les périmètres et
validité des délégations."""
from django.test import TestCase
from django.utils import timezone

from habilitations.models import (
    AttributionRole,
    DelegationHabilitation,
    Perimetre,
)
from habilitations.services.moteur import est_autorise

from .helpers import (
    creer_attribution,
    creer_compte,
    creer_perimetre_secretariat,
    creer_permission,
    creer_role,
    creer_user,
    date_dans,
    date_il_y_a,
    secretariat,
)

CODE = 'form.participant.consulter'


class CouverturePerimetreTests(TestCase):
    def setUp(self):
        self.user = creer_user(username='mp-1', role_existant='ARCHIVE')
        self.compte = creer_compte(user=self.user)
        self.perm = creer_permission(
            code_module='form', ressource='participant', action='consulter',
            portee_maximale='INJS_ENTIER')

    def test_role_global_couvre_toute_cible_nommee(self):
        role = creer_role(
            code='R_GLOBAL', perimetre_defaut=Perimetre.Type.INJS_ENTIER)
        role.permissions.add(self.perm)
        creer_attribution(self.compte, role)
        decision = est_autorise(
            self.user, CODE,
            cible={'type': 'SECRETARIAT', 'object_id': 42})
        self.assertTrue(decision.autorise, decision.motifs)

    def test_role_secretariat_sans_perimetre_refuse(self):
        role = creer_role(
            code='R_SEC_NAK', perimetre_defaut=Perimetre.Type.SECRETARIAT)
        role.permissions.add(self.perm)
        creer_attribution(self.compte, role)
        decision = est_autorise(self.user, CODE)
        self.assertFalse(decision.autorise)
        self.assertIn('PERIMETRE_SECRETARIAT_MANQUANT', decision.motifs)

    def test_cible_dans_le_secretariat_attribue_autorise(self):
        sec = secretariat(numero='SECR-MP-A', nom='MP A')
        per = creer_perimetre_secretariat(sec)
        role = creer_role(
            code='R_SEC_OK', perimetre_defaut=Perimetre.Type.SECRETARIAT)
        role.permissions.add(self.perm)
        attribution = creer_attribution(self.compte, role)
        attribution.perimetres.add(per)
        decision = est_autorise(
            self.user, CODE,
            cible={'type': 'SECRETARIAT', 'object_id': sec.pk})
        self.assertTrue(decision.autorise, decision.motifs)

    def test_cible_autre_secretariat_refusee_pour_tous(self):
        sec_a = secretariat(numero='SECR-MP-B1', nom='B1')
        sec_b = secretariat(numero='SECR-MP-B2', nom='B2')
        per_a = creer_perimetre_secretariat(sec_a)
        role = creer_role(
            code='R_SEC_B', perimetre_defaut=Perimetre.Type.SECRETARIAT)
        role.permissions.add(self.perm)
        attribution = creer_attribution(self.compte, role)
        attribution.perimetres.add(per_a)
        decision = est_autorise(
            self.user, CODE,
            cible={'type': 'SECRETARIAT', 'object_id': sec_b.pk})
        self.assertFalse(decision.autorise)
        self.assertIn('CIBLE_HORS_PERIMETRE', decision.motifs)

    def test_fonction_de_couverture_injectee_est_appelee(self):
        # Un périmètre SERVICE non global : la résolution passe alors par la
        # fonction de couverture fournie par le contexte (résolveur métier
        # branché en U4, ici une sonde).
        per = Perimetre.objects.create(
            type=Perimetre.Type.SERVICE, reference_lisible='SRV-COUV')
        role = creer_role(
            code='R_FCT', perimetre_defaut=Perimetre.Type.SERVICE)
        role.permissions.add(self.perm)
        attribution = creer_attribution(self.compte, role)
        attribution.perimetres.add(per)
        appels = []

        def couverture(perimetre, cible):
            appels.append((perimetre.type, cible.get('code_projet')))
            return cible.get('code_projet') == 'PROJET-7'

        decision = est_autorise(
            self.user, CODE,
            cible={'code_projet': 'PROJET-7'},
            contexte={'couverture': couverture})
        self.assertTrue(decision.autorise, decision.motifs)
        self.assertTrue(appels)
        decision_hors = est_autorise(
            self.user, CODE,
            cible={'code_projet': 'PROJET-99'},
            contexte={'couverture': couverture})
        self.assertFalse(decision_hors.autorise)
        self.assertIn('CIBLE_HORS_PERIMETRE', decision_hors.motifs)


class DelegationTests(TestCase):
    def _preparer(self, criticite='NORMALE'):
        self.admin = creer_user(username='mp-adm', role_existant='ADMIN')
        self.titulaire_user = creer_user(username='mp-tit', role_existant='ARCHIVE')
        self.titulaire = creer_compte(user=self.titulaire_user)
        self.remplacant_user = creer_user(username='mp-rem', role_existant='ARCHIVE')
        self.remplacant = creer_compte(user=self.remplacant_user)
        self.perm = creer_permission(
            code_module='sco', ressource='jury', action='valider',
            criticite=criticite)
        self.role = creer_role(code='R_JURY_DEL')
        self.role.permissions.add(self.perm)
        creer_attribution(self.titulaire, self.role)

    def _creer_delegation(self, **kwargs):
        valeurs = {
            'delegant': self.titulaire,
            'delegataire': self.remplacant,
            'date_debut': timezone.localdate(),
            'date_fin': date_dans(15),
            'motif': 'Absence du titulaire.',
            'statut': DelegationHabilitation.Statut.ACTIVE,
            'valide_par': self.admin,
        }
        valeurs.update(kwargs)
        delegation = DelegationHabilitation.objects.create(**valeurs)
        delegation.roles.add(self.role)
        return delegation

    def test_delegation_active_autorise_pour_delegataire(self):
        self._preparer()
        self._creer_delegation()
        decision = est_autorise(self.remplacant_user, 'sco.jury.valider')
        self.assertTrue(decision.autorise, decision.motifs)
        self.assertEqual(decision.octrois[0].source, 'DELEGATION')

    def test_delegation_hors_periode_ne_donne_rien(self):
        self._preparer()
        self._creer_delegation(
            date_debut=date_il_y_a(30), date_fin=date_il_y_a(15))
        decision = est_autorise(self.remplacant_user, 'sco.jury.valider')
        self.assertFalse(decision.autorise)
        self.assertIn('AUCUNE_ATTRIBUTION_PERMETTANTE', decision.motifs)

    def test_delegation_critique_non_signee_refusee_pour_delegataire(self):
        self._preparer(criticite='CRITIQUE')
        self._creer_delegation(valide_par=None)
        decision = est_autorise(self.remplacant_user, 'sco.jury.valider')
        self.assertFalse(decision.autorise)
        self.assertIn('DELEGATION_NON_SIGNEE', decision.motifs)

    def test_delegation_sans_titulaire_valide_refusee(self):
        self._preparer()
        # Le titulaire perd son attribution (révoquée) : la délégation devient
        # sans fondement.
        self.titulaire.attributions.all().update(
            statut=AttributionRole.Statut.REVOQUEE)
        self._creer_delegation()
        decision = est_autorise(self.remplacant_user, 'sco.jury.valider')
        self.assertFalse(decision.autorise)
        self.assertIn('DELEGATION_SANS_TITULAIRE_VALIDE', decision.motifs)

    def test_pas_de_re_delegation_en_chaine(self):
        self._preparer()
        self._creer_delegation()
        # Un troisième compte ne reçoit qu'une délégation depuis le
        # remplaçant, qui ne détient rien en direct : elle doit être invalide.
        troisieme_user = creer_user(username='mp-trois', role_existant='ARCHIVE')
        troisieme = creer_compte(user=troisieme_user)
        delegation2 = DelegationHabilitation.objects.create(
            delegant=self.remplacant, delegataire=troisieme,
            date_debut=timezone.localdate(), date_fin=date_dans(10),
            motif='Re-délégation interdite.',
            statut=DelegationHabilitation.Statut.ACTIVE,
            valide_par=self.admin)
        delegation2.roles.add(self.role)
        decision = est_autorise(troisieme_user, 'sco.jury.valider')
        self.assertFalse(decision.autorise)
        self.assertIn('DELEGATION_SANS_TITULAIRE_VALIDE', decision.motifs)

    def test_delegation_avec_pour_perimetre_ceux_du_titulaire(self):
        sec = secretariat(numero='SECR-DEL', nom='Délégation')
        per = creer_perimetre_secretariat(sec)
        self._preparer()
        self.role.perimetre_defaut = Perimetre.Type.SECRETARIAT
        self.role.save()
        attribution = self.titulaire.attributions.first()
        attribution.perimetres.add(per)
        # Le titulaire a maintenant besoin aussi de la seconde signature (le
        # rôle n'est pas sensible ici) ; la délégation reprend le périmètre.
        self._creer_delegation()
        decision = est_autorise(
            self.remplacant_user, 'sco.jury.valider',
            cible={'type': 'SECRETARIAT', 'object_id': sec.pk})
        self.assertTrue(decision.autorise, decision.motifs)
