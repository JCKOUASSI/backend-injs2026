"""U1 — Délégations temporaires et politique de sécurité singleton."""
from django.db import IntegrityError, transaction
from django.test import TestCase

from habilitations.models import (
    DelegationHabilitation,
    PolitiqueSecurite,
)
from habilitations.services.journalisation import JournalHabilitation
from habilitations.services.politique import modifier_politique

from .helpers import (
    creer_compte,
    creer_role,
    creer_user,
    date_dans,
    date_il_y_a,
)


class DelegationTests(TestCase):
    def setUp(self):
        self.titulaire = creer_compte(creer_user('hab-del-a'))
        self.remplacant = creer_compte(creer_user('hab-del-b'))

    def test_delegation_active_dans_sa_fenetre(self):
        delegation = DelegationHabilitation.objects.create(
            delegant=self.titulaire, delegataire=self.remplacant,
            date_debut=date_il_y_a(1), date_fin=date_dans(7),
            motif='Congé', statut=DelegationHabilitation.Statut.ACTIVE,
        )
        self.assertTrue(delegation.est_active())

    def test_delegation_hors_fenetre_inactive(self):
        delegation = DelegationHabilitation.objects.create(
            delegant=self.titulaire, delegataire=self.remplacant,
            date_debut=date_il_y_a(10), date_fin=date_il_y_a(1),
            motif='Congé passé', statut=DelegationHabilitation.Statut.ACTIVE,
        )
        self.assertFalse(delegation.est_active())

    def test_delegation_a_soi_meme_refusee_en_base(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            DelegationHabilitation.objects.create(
                delegant=self.titulaire, delegataire=self.titulaire,
                date_fin=date_dans(5), motif='Soi-même',
            )

    def test_periode_incoherente_signalee(self):
        delegation = DelegationHabilitation.objects.create(
            delegant=self.titulaire, delegataire=self.remplacant,
            date_debut=date_dans(5), date_fin=date_il_y_a(1),
            motif='Incohérent',
        )
        self.assertIn('PERIODE_INCOHERENTE', delegation.contraintes())

    def test_les_roles_delegues_sont_enregistres(self):
        delegation = DelegationHabilitation.objects.create(
            delegant=self.titulaire, delegataire=self.remplacant,
            date_fin=date_dans(5), motif='Mission',
        )
        role = creer_role('ROLE_DEL')
        delegation.roles.add(role)
        self.assertEqual(delegation.roles.count(), 1)


class PolitiqueSecuriteTests(TestCase):
    def test_le_singleton_est_unique_et_cree_par_defaut(self):
        self.assertEqual(PolitiqueSecurite.objet().pk, 1)
        self.assertEqual(PolitiqueSecurite.objet().pk, 1)
        self.assertEqual(PolitiqueSecurite.objects.count(), 1)

    def test_les_valeurs_par_defaut_sont_non_derangeantes(self):
        politique = PolitiqueSecurite.objet()
        self.assertEqual(politique.duree_max_derogation_jours, 90)
        self.assertEqual(politique.nombre_echecs_avant_verrouillage, 5)

    def test_la_suppression_est_refusee(self):
        PolitiqueSecurite.objet()
        with self.assertRaises(Exception):
            PolitiqueSecurite.objects.all().delete()

    def test_modification_journalisee(self):
        avant = JournalHabilitation.objects.count()
        modifier_politique(motif='Durcissement test',
                           longueur_min_mot_de_passe=14)
        politique = PolitiqueSecurite.objet()
        self.assertEqual(politique.longueur_min_mot_de_passe, 14)
        self.assertEqual(JournalHabilitation.objects.count(), avant + 1)
        trace = JournalHabilitation.objects.latest('numero')
        self.assertEqual(trace.type_evenement, 'POLITIQUE_MODIFIEE')
        self.assertEqual(trace.nouvelle_valeur['longueur_min_mot_de_passe'], 14)

    def test_un_reglage_inconnu_est_refuse(self):
        with self.assertRaises(ValueError):
            modifier_politique(champ_improbable=True)
