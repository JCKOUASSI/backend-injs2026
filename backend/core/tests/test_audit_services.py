"""Tests du service d'audit core : codes atomiques, immutabilité, connecteurs."""
from datetime import date, timedelta
from unittest import skipIf

from django.contrib.contenttypes.models import ContentType
from django.core.cache import cache
from django.db import connection
from django.test import TransactionTestCase

from core.audit_services import (
    FLAG_LOT1,
    enregistrer_evenement,
    formater_code,
    repliquer_depuis_presences,
    repliquer_depuis_referentiels,
    repliquer_depuis_scolarite,
)
from core.models import (
    CompteurCode,
    EvenementAudit,
    JournalImmuableError,
)
from parametres.flags import FLAGS_CACHE_KEY
from parametres.models import Parametre
from presences.models import AuditLog
from referentiels.models import ReferentielJournal
from scolarite.models import JournalScolarite


DEFAUTS_FLAG = dict(
    libelle=FLAG_LOT1, categorie='flags', type='bool',
    valeur_defaut='false', modifiable=True,
    modifiable_par_roles='["ADMIN", "CHEF_INJS_ADMIN", "INJS_ADMIN"]',
    lecturable_par_roles='["ADMIN", "CHEF_INJS_ADMIN", "INJS_ADMIN"]',
    actif=True,
)


def _positionner_flag(valeur):
    # get/update_or_create car les TransactionTestCase vident les tables entre
    # deux tests (le seed de migration n'existe plus forcément).
    Parametre.objects.update_or_create(
        cle=FLAG_LOT1, defaults={**DEFAUTS_FLAG, 'valeur': valeur})
    cache.delete(FLAGS_CACHE_KEY)


def activer_flag_lot1():
    _positionner_flag('true')


def desactiver_flag_lot1():
    _positionner_flag('false')


class FormatCodeTests(TransactionTestCase):
    def test_format_du_code(self):
        self.assertEqual(
            formater_code(date(2026, 9, 13), 1),
            'AUDIT-20260913-000001',
        )
        self.assertEqual(
            formater_code(date(2026, 9, 13), 1234),
            'AUDIT-20260913-001234',
        )


class SequenceCodesTests(TransactionTestCase):
    reset_sequences = True

    def test_sequence_continue_pour_une_journee(self):
        e1 = enregistrer_evenement(source=EvenementAudit.Source.CORE, action='A')
        e2 = enregistrer_evenement(source=EvenementAudit.Source.CORE, action='B')
        self.assertTrue(e1.code.endswith('-000001'))
        self.assertTrue(e2.code.endswith('-000002'))
        self.assertEqual(CompteurCode.objects.get().dernier_numero, 2)

    def test_sequence_remise_a_zero_chaque_jour(self):
        hier = date.today() - timedelta(days=1)
        e_hier = enregistrer_evenement(
            source=EvenementAudit.Source.CORE, action='A', le_jour=hier)
        e_auj = enregistrer_evenement(
            source=EvenementAudit.Source.CORE, action='B')
        self.assertIn(hier.strftime('%Y%m%d'), e_hier.code)
        self.assertTrue(e_hier.code.endswith('-000001'))
        self.assertTrue(e_auj.code.endswith('-000001'))
        self.assertEqual(CompteurCode.objects.count(), 2)

    def test_reprise_sur_collision_de_code(self):
        """Un code déjà présent fait avancer la séquence (pas de doublon)."""
        e1 = enregistrer_evenement(source=EvenementAudit.Source.CORE, action='A')
        # On recule artificiellement le compteur : la prochaine valeur proposée
        # entre en collision avec e1, le service doit réessayer.
        CompteurCode.objects.update(dernier_numero=0)
        e2 = enregistrer_evenement(source=EvenementAudit.Source.CORE, action='B')
        self.assertNotEqual(e1.code, e2.code)
        self.assertTrue(e2.code.endswith('-000002'))
        self.assertEqual(EvenementAudit.objects.count(), 2)


class ImmutabiliteTests(TransactionTestCase):
    def setUp(self):
        self.evenement = enregistrer_evenement(
            source=EvenementAudit.Source.CORE, action='TEST')

    def test_modification_interdite(self):
        self.evenement.action = 'AUTRE'
        with self.assertRaises(JournalImmuableError):
            self.evenement.save()

    def test_suppression_unitaire_interdite(self):
        with self.assertRaises(JournalImmuableError):
            self.evenement.delete()

    def test_mise_a_jour_en_masse_interdite(self):
        with self.assertRaises(JournalImmuableError):
            EvenementAudit.objects.update(action='X')

    def test_suppression_en_masse_interdite(self):
        with self.assertRaises(JournalImmuableError):
            EvenementAudit.objects.all().delete()

    def test_seule_la_permission_view_est_declaree(self):
        # default_permissions = ('view',) : pas de permission d'écriture.
        self.assertEqual(EvenementAudit._meta.default_permissions, ('view',))


class ConnecteursTests(TransactionTestCase):
    def setUp(self):
        desactiver_flag_lot1()
        cache.clear()

    def tearDown(self):
        desactiver_flag_lot1()
        cache.clear()

    def test_flag_off_aucune_replique(self):
        AuditLog.objects.create(action='USER_LOGIN', acteur_label='Dupont')
        JournalScolarite.objects.create(
            action='CANDIDATURE_CREEE', objet_libelle='Candidature')
        self.assertFalse(EvenementAudit.objects.exists())

    def test_replique_presences_quand_flag_actif(self):
        activer_flag_lot1()
        entree = AuditLog.objects.create(action='USER_LOGIN', acteur_label='Dupont')
        replique = EvenementAudit.objects.get(source='presences')
        self.assertEqual(replique.action, 'USER_LOGIN')
        self.assertEqual(replique.acteur_label, 'Dupont')
        self.assertEqual(replique.source_entree_id, entree.pk)
        self.assertTrue(replique.code.endswith('-000001'))
        # Idempotence du connecteur appelé deux fois.
        repliquer_depuis_presences(entree)
        self.assertEqual(
            EvenementAudit.objects.filter(source='presences').count(), 1)

    def test_replique_scolarite_quand_flag_actif(self):
        activer_flag_lot1()
        entree = JournalScolarite.objects.create(
            action='JURY_DECISION', objet_libelle='Jury L1',
            ancienne_valeur='DELIBERATION', nouvelle_valeur='VERROUILLE',
        )
        replique = EvenementAudit.objects.get(source='scolarite')
        self.assertEqual(replique.action, 'JURY_DECISION')
        self.assertEqual(replique.detail['nouvelle_valeur'], 'VERROUILLE')
        self.assertEqual(replique.source_entree_id, entree.pk)
        repliquer_depuis_scolarite(entree)
        self.assertEqual(
            EvenementAudit.objects.filter(source='scolarite').count(), 1)

    def test_replique_referentiels_quand_flag_actif(self):
        from authentication.models import User
        activer_flag_lot1()
        utilisateur = User.objects.create_user(username='ref_agent', password='x')
        cible = User.objects.create_user(username='cible', password='x')
        ct = ContentType.objects.get_for_model(cible)
        entree = ReferentielJournal.objects.create(
            content_type=ct, object_id=cible.pk,
            action=ReferentielJournal.Action.MODIFICATION,
            utilisateur=utilisateur, detail={'champ': 'libelle'},
        )
        replique = EvenementAudit.objects.get(source='referentiels')
        self.assertEqual(replique.action, 'MODIFICATION')
        self.assertEqual(replique.acteur_id, utilisateur.pk)
        self.assertEqual(replique.object_id, cible.pk)
        self.assertEqual(replique.detail['champ'], 'libelle')
        repliquer_depuis_referentiels(entree)
        self.assertEqual(
            EvenementAudit.objects.filter(source='referentiels').count(), 1)

    def test_echec_de_replique_ne_casse_pas_le_journal_source(self):
        activer_flag_lot1()
        # Un connecteur qui échoue ne doit pas propager lors de la création
        # (l'exception est capturée par le récepteur de signal).
        import core.signals as core_signals
        original = core_signals.audit_services.repliquer_depuis_presences

        def cassante(_entree):
            raise RuntimeError('panne réplication')

        core_signals.audit_services.repliquer_depuis_presences = cassante
        try:
            entree = AuditLog.objects.create(
                action='USER_LOGIN', acteur_label='X')
        finally:
            core_signals.audit_services.repliquer_depuis_presences = original
        # L'entrée source existe bien, la réplique non, sans exception propagée.
        self.assertTrue(AuditLog.objects.filter(pk=entree.pk).exists())
        self.assertFalse(EvenementAudit.objects.filter(source='presences').exists())


@skipIf(connection.vendor == 'sqlite',
        'La concurrence par verrous de ligne se vérifie sur PostgreSQL (CI).')
class ConcurrencePostgreSQLTests(TransactionTestCase):
    def test_codes_distincts_en_verrouillage_concurrent(self):
        import threading

        nombre = 5
        barriere = threading.Barrier(nombre)
        resultats = []
        erreurs = []

        def travailleur():
            # Pas de connection.close() ici : `connection` est le proxy
            # thread-local de Django, et le fermer depuis un thread de test
            # scalpait aussi la connexion du thread principal du worker, ce qui
            # faisait échouer en cascade les tests suivants avec
            # InterfaceError('connection already closed') sous --parallel.
            # Django ferme et gère lui-même les connexions des threads de test.
            try:
                barriere.wait(timeout=10)
                evenement = enregistrer_evenement(
                    source=EvenementAudit.Source.CORE, action='CONCURRENT')
                resultats.append(evenement.code)
            except Exception as exc:  # noqa: BLE001
                erreurs.append(exc)

        fils = [threading.Thread(target=travailleur) for _ in range(nombre)]
        for fil in fils:
            fil.start()
        for fil in fils:
            fil.join(timeout=30)

        self.assertFalse(erreurs, erreurs)
        self.assertEqual(len(resultats), nombre)
        self.assertEqual(len(set(resultats)), nombre)
        self.assertEqual(CompteurCode.objects.get().dernier_numero, nombre)
