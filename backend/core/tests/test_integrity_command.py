"""Tests de la commande audit_integrity_check : fonctions pures et exécution."""
from io import StringIO
from types import SimpleNamespace

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TransactionTestCase

from core.audit_services import enregistrer_evenement
from core.management.commands.audit_integrity_check import (
    analyser_codes,
    analyser_repliques,
    analyser_sequences,
)
from core.models import CompteurCode, EvenementAudit


def evt(code, source='core', source_entree_id=None):
    return SimpleNamespace(
        code=code, source=source, source_entree_id=source_entree_id)


class AnalyseursPursTests(TransactionTestCase):
    def test_cases_propres(self):
        evenements = [
            evt('AUDIT-20260913-000001'),
            evt('AUDIT-20260913-000002'),
        ]
        compteurs = [SimpleNamespace(cle='AUDIT-20260913', dernier_numero=2)]
        self.assertEqual(analyser_codes(evenements), [])
        self.assertEqual(analyser_sequences(evenements, compteurs), [])
        self.assertEqual(analyser_repliques(evenements), [])

    def test_doublon_et_code_mal_forme(self):
        evenements = [
            evt('AUDIT-20260913-000001'),
            evt('AUDIT-20260913-000001'),
            evt('AUDIT-bidon'),
        ]
        rapports = analyser_codes(evenements)
        self.assertEqual(len(rapports), 2)
        self.assertTrue(any('doublon' in r for r in rapports))
        self.assertTrue(any('mal formé' in r for r in rapports))

    def test_sequence_trouee_et_compteur_incoherent(self):
        evenements = [
            evt('AUDIT-20260913-000001'),
            evt('AUDIT-20260913-000003'),
        ]
        compteurs = [SimpleNamespace(cle='AUDIT-20260913', dernier_numero=9)]
        rapports = analyser_sequences(evenements, compteurs)
        self.assertTrue(any('discontinue' in r for r in rapports))
        self.assertTrue(any('incohérent' in r for r in rapports))

    def test_compteur_sans_evenement(self):
        rapports = analyser_sequences(
            [], [SimpleNamespace(cle='AUDIT-20260913', dernier_numero=5)])
        self.assertTrue(any('sans événement' in r for r in rapports))

    def test_repliques_dupliquees(self):
        evenements = [
            evt('AUDIT-20260913-000001', 'presences', 7),
            evt('AUDIT-20260913-000002', 'presences', 7),
        ]
        rapports = analyser_repliques(evenements)
        self.assertEqual(len(rapports), 1)
        self.assertIn('presences entrée n°7', rapports[0])


class CommandeIntegriteTests(TransactionTestCase):
    def test_base_neuve_conforme(self):
        sortie = StringIO()
        call_command('audit_integrity_check', stdout=sortie)
        self.assertIn('CONFORME', sortie.getvalue())

    def test_apres_evenements_conforme(self):
        for _ in range(3):
            enregistrer_evenement(source=EvenementAudit.Source.CORE, action='X')
        sortie = StringIO()
        call_command('audit_integrity_check', stdout=sortie)
        self.assertIn('3 événement(s)', sortie.getvalue())

    def test_replique_orpheline_denoncee(self):
        # Une réplique dont l'entrée source n'existe pas (ou plus).
        from presences.models import AuditLog
        entree = AuditLog.objects.create(action='USER_LOGIN')
        evenement = enregistrer_evenement(
            source=EvenementAudit.Source.PRESENCES,
            action='USER_LOGIN', source_entree_id=entree.pk)
        entree.delete()  # le journal source est mutable, le core garde la trace
        with self.assertRaises(CommandError):
            call_command('audit_integrity_check', stdout=StringIO(),
                         stderr=StringIO())
        self.assertTrue(
            EvenementAudit.objects.filter(pk=evenement.pk).exists(),
            'La commande doit être strictement en lecture')


class Migration0001Tests(TransactionTestCase):
    def test_migration_initiale_reversible(self):
        from django.core.management import call_command as cc
        from django.db import DatabaseError

        try:
            # Annulation complète de core : les tables disparaissent.
            cc('migrate', 'core', 'zero', verbosity=0, interactive=False)
            with self.assertRaises(DatabaseError):
                list(EvenementAudit.objects.all())
        finally:
            # Réapplication systématique pour ne jamais polluer les tests suivants.
            cc('migrate', 'core', verbosity=0, interactive=False)

        # Les tables sont de nouveau exploitable.
        self.assertEqual(CompteurCode.objects.count(), 0)
        enregistrer_evenement(source=EvenementAudit.Source.CORE, action='X')
        self.assertEqual(EvenementAudit.objects.count(), 1)
