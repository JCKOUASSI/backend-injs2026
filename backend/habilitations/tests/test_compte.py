"""U1 — CompteUtilisateur : profil OneToOne, statuts, canaux, validité."""
from datetime import timedelta

from django.db import IntegrityError
from django.test import TestCase
from django.utils import timezone

from habilitations.models import CanalAcces, CompteUtilisateur

from .helpers import creer_compte, creer_personne, creer_user


class CompteUtilisateurTests(TestCase):
    def test_le_profil_est_un_onetoone_du_user_existant(self):
        user = creer_user('hab-profil')
        compte = creer_compte(user)
        self.assertEqual(user.profil_habilitation, compte)

    def test_un_seul_profil_par_compte(self):
        user = creer_user('hab-profil-2')
        creer_compte(user)
        with self.assertRaises(IntegrityError):
            creer_compte(user)

    def test_un_user_sans_profil_n_a_pas_dacces_force(self):
        # Les comptes existants non migrés n'ont pas de profil CURP.
        user = creer_user('hab-nu')
        self.assertFalse(hasattr(user, 'profil_habilitation'))
        self.assertEqual(CompteUtilisateur.objects.filter(user=user).count(), 0)

    def test_personne_est_optionnelle_comptes_techniques(self):
        compte = creer_compte()
        self.assertIsNone(compte.personne)

    def test_peut_lier_une_personne(self):
        personne = creer_personne(nom='Nomo')
        compte = creer_compte(personne=personne)
        self.assertIn(compte, personne.comptes.all())

    def test_statut_actif_par_defaut(self):
        self.assertTrue(creer_compte().est_actif)

    def test_canal_mobile_refuse_le_web_et_inversement(self):
        mobile = creer_compte(canal=CanalAcces.MOBILE)
        self.assertFalse(mobile.peut_acceder_au_canal(CanalAcces.WEB))
        self.assertTrue(mobile.peut_acceder_au_canal(CanalAcces.MOBILE))
        web = creer_compte(canal=CanalAcces.WEB)
        self.assertTrue(web.peut_acceder_au_canal(CanalAcces.WEB))
        self.assertFalse(web.peut_acceder_au_canal(CanalAcces.MOBILE))

    def test_canal_les_deux_accepte_tout(self):
        compte = creer_compte(canal=CanalAcces.LES_DEUX)
        self.assertTrue(compte.peut_acceder_au_canal(CanalAcces.WEB))
        self.assertTrue(compte.peut_acceder_au_canal(CanalAcces.MOBILE))

    def test_date_expiration_est_respectee(self):
        compte = creer_compte()
        self.assertTrue(compte.est_en_cours_validite())
        compte.date_expiration = timezone.now() - timedelta(days=1)
        self.assertFalse(compte.est_en_cours_validite())

    def test_sans_date_expiration_le_compte_reste_valide(self):
        self.assertTrue(creer_compte().est_en_cours_validite())
