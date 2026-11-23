"""U1 — Périmètres, attributions de rôles et dérogations de permissions."""
from django.db import IntegrityError
from django.test import TestCase

from habilitations.models import (
    PermissionAttribuee,
    Perimetre,
    PolitiqueSecurite,
)
from habilitations.services.validations import (
    controle_duree_derogation,
    declarer_incompatibilite,
)

from .helpers import (
    creer_attribution,
    creer_compte,
    creer_derogation,
    creer_perimetre_secretariat,
    creer_permission,
    creer_role,
    date_dans,
    secretariat,
)


class PerimetreTests(TestCase):
    def test_perimetre_global_sans_objet(self):
        perimetre = Perimetre.obtenir_ou_creer_global(Perimetre.Type.INJS_ENTIER)
        self.assertTrue(perimetre.est_global)
        self.assertIsNone(perimetre.content_type)
        self.assertIn('tout entière', str(perimetre))

    def test_le_perimetre_global_est_reutilise(self):
        a = Perimetre.obtenir_ou_creer_global(Perimetre.Type.INJS_ENTIER)
        b = Perimetre.obtenir_ou_creer_global(Perimetre.Type.INJS_ENTIER)
        self.assertEqual(a.pk, b.pk)

    def test_perimetre_secretariat_pointe_vers_l_objet(self):
        sec = secretariat()
        perimetre = creer_perimetre_secretariat(sec)
        self.assertEqual(perimetre.type, Perimetre.Type.SECRETARIAT)
        self.assertEqual(perimetre.cible, sec)
        self.assertEqual(perimetre.reference_lisible, sec.numero)


class AttributionRoleTests(TestCase):
    def setUp(self):
        self.compte = creer_compte()
        self.role = creer_role(perimetre_defaut=Perimetre.Type.INJS_ENTIER)

    def test_attribution_active_par_defaut_apres_creation_explicite(self):
        attribution = creer_attribution(self.compte, self.role)
        self.assertTrue(attribution.est_active())

    def test_une_seule_attribution_active_par_compte_et_role(self):
        creer_attribution(self.compte, self.role)
        with self.assertRaises(IntegrityError):
            creer_attribution(self.compte, self.role)

    def test_attribution_expiree_n_est_pas_active(self):
        attribution = creer_attribution(self.compte, self.role,
                                        date_fin=date_dans(-1))
        self.assertFalse(attribution.est_active())

    def test_perimetre_secretariat_exige_quand_le_role_en_releve(self):
        role_sec = creer_role(
            'ROLE_SEC', perimetre_defaut=Perimetre.Type.SECRETARIAT)
        attribution = creer_attribution(self.compte, role_sec)
        self.assertIn('PERIMETRE_SECRETARIAT_MANQUANT',
                      attribution.contraintes())
        perimetre = creer_perimetre_secretariat(secretariat(numero='SECR-X'))
        attribution.perimetres.add(perimetre)
        self.assertNotIn('PERIMETRE_SECRETARIAT_MANQUANT',
                         attribution.contraintes())

    def test_role_sans_module_signale(self):
        role = creer_role('ROLE_ABS', module_requis='application_absente')
        attribution = creer_attribution(self.compte, role)
        self.assertIn('MODULE_REQUIS_ABSENT', attribution.contraintes())

    def test_role_sensible_exige_une_seconde_signature(self):
        role = creer_role('ROLE_SENS', sensible=True)
        attribution = creer_attribution(self.compte, role)
        self.assertIn('ROLE_SENSIBLE_SANS_SECONDE_SIGNATURE',
                      attribution.contraintes())

    def test_incompatibilite_de_roles_signalee_pas_bloquee(self):
        a = creer_role('ROLE_A')
        b = creer_role('ROLE_B')
        declarer_incompatibilite(a, b)
        creer_attribution(self.compte, a)
        conflit = creer_attribution(self.compte, b)
        self.assertIn('ROLES_INCOMPATIBLES', conflit.contraintes())


class DerogationTests(TestCase):
    def setUp(self):
        self.compte = creer_compte()
        self.permission = creer_permission()

    def test_octroi_sans_date_fin_est_signale(self):
        derogation = creer_derogation(self.compte, self.permission,
                                      date_fin=None)
        self.assertEqual(derogation.sens, PermissionAttribuee.Sens.OCTROI)
        controle = controle_duree_derogation(
            derogation.date_debut, derogation.date_fin)
        self.assertEqual(controle, 'DEROGATION_SANS_DATE_FIN')

    def test_octroi_au_dela_de_90_jours_refuse_par_le_controle(self):
        controle = controle_duree_derogation(date_dans(0), date_dans(91))
        self.assertEqual(controle, 'DEROGATION_TROP_LONGUE')

    def test_octroi_dans_les_90_jours_conforme(self):
        controle = controle_duree_derogation(date_dans(0), date_dans(60))
        self.assertIsNone(controle)

    def test_duree_max_lue_dans_la_politique(self):
        politique = PolitiqueSecurite.objet()
        politique.duree_max_derogation_jours = 30
        politique.save()
        controle = controle_duree_derogation(date_dans(0), date_dans(60),
                                             politique=politique)
        self.assertEqual(controle, 'DEROGATION_TROP_LONGUE')

    def test_derogation_retrait_est_active_sans_date_fin(self):
        derogation = creer_derogation(
            self.compte, self.permission,
            sens=PermissionAttribuee.Sens.RETRAIT,
            statut=PermissionAttribuee.Statut.ACTIVE, date_fin=None)
        self.assertTrue(derogation.est_active())
