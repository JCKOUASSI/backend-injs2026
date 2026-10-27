"""U1 — Journal append-only chaîné : écriture, immuabilité, intégrité."""
from django.contrib import admin as django_admin
from django.db import connection
from django.test import TestCase

from habilitations.admin import JournalHabilitationAdmin
from habilitations.models import (
    JournalHabilitation,
    JournalImmuableError,
)
from habilitations.services.journalisation import (
    GENESE,
    journaliser,
    verifier_chaine,
)

from .helpers import creer_compte


def _trois_evenements():
    e1 = journaliser('COMPTE_CREE', nouvelle_valeur={'n': 1})
    e2 = journaliser('CONNEXION', nouvelle_valeur={'n': 2})
    e3 = journaliser('ROLE_ATTRIBUE', nouvelle_valeur={'n': 3})
    return e1, e2, e3


class ChainageTests(TestCase):
    def test_numeros_et_empreintes_sont_chaines(self):
        e1, e2, e3 = _trois_evenements()
        self.assertEqual([e1.numero, e2.numero, e3.numero], [1, 2, 3])
        self.assertEqual(e1.empreinte_precedente, GENESE)
        self.assertEqual(e2.empreinte_precedente, e1.empreinte)
        self.assertEqual(e3.empreinte_precedente, e2.empreinte)

    def test_les_empreintes_sont_uniques_et_remplies(self):
        e1, e2, _ = _trois_evenements()
        self.assertEqual(len(e1.empreinte), 64)
        self.assertNotEqual(e1.empreinte, e2.empreinte)

    def test_chaine_saine_ne_signale_aucune_anomalie(self):
        _trois_evenements()
        self.assertEqual(verifier_chaine(), [])

    def test_une_meme_empreinte_pour_un_meme_contenu(self):
        # Déterminisme : recalcul à l'identique.
        from habilitations.services.journalisation import calculer_empreinte
        e = journaliser('AUTRE')
        self.assertEqual(calculer_empreinte(e), e.empreinte)

    def test_le_compte_concerne_est_trace(self):
        compte = creer_compte()
        entree = journaliser('COMPTE_ACTIVE', compte=compte, motif='test')
        self.assertEqual(entree.compte_concerne, compte)
        self.assertEqual(entree.motif, 'test')


class ImmuabiliteORMDansTests(TestCase):
    def setUp(self):
        self.entree = journaliser('CONNEXION')

    def test_la_mise_a_jour_d_une_ligne_est_refusee(self):
        self.entree.motif = 'modifié'
        with self.assertRaises(JournalImmuableError):
            self.entree.save()

    def test_la_suppression_d_une_ligne_est_refusee(self):
        with self.assertRaises(JournalImmuableError):
            self.entree.delete()

    def test_la_mise_a_jour_en_masse_est_refusee(self):
        with self.assertRaises(JournalImmuableError):
            JournalHabilitation.objects.all().update(motif='x')

    def test_la_suppression_en_masse_est_refusee(self):
        with self.assertRaises(JournalImmuableError):
            JournalHabilitation.objects.all().delete()


class AdministrationLectureSeuleTests(TestCase):
    def test_l_admin_du_journal_est_consultative(self):
        classe_admin = JournalHabilitationAdmin
        instance = classe_admin(JournalHabilitation, django_admin.site)
        requete = None
        self.assertFalse(instance.has_add_permission(requete))
        self.assertFalse(instance.has_change_permission(requete))
        self.assertFalse(instance.has_delete_permission(requete))


class DetectionAlterationTests(TestCase):
    """Sur SQLite (développement), l'ORM protège ; on vérifie ici qu'une
    altération directe en base est bien DÉTECTÉE par le contrôle de chaîne.
    Sur PostgreSQL, c'est le déclencheur base qui empêche l'altération
    (test dédié ``test_declencheurs_postgres``)."""

    def test_une_altération_sql_sqlite_est_detectee(self):
        if connection.vendor != 'sqlite':
            self.skipTest("L'altération SQL est bloquée par le trigger PostgreSQL.")
        journaliser('CONNEXION', motif='original')
        journaliser('CONNEXION')
        with connection.cursor() as curseur:
            curseur.execute(
                "UPDATE habilitations_journalhabilitation "
                "SET motif = 'altéré' WHERE numero = 1"
            )
        anomalies = verifier_chaine()
        self.assertTrue(
            any('Empreinte altérée' in a or 'altérée' in a for a in anomalies))
