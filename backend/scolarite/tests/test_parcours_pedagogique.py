"""Chaîne métier : admission → inscription administrative → parcours pédagogique.

Le dépôt porte une règle de frontière explicite (voir
``scolarite/tests/test_frontieres_metier.py``) : la validation administrative ne
crée par défaut AUCUNE inscription pédagogique, la génération restant une action
explicite du service de scolarité.

Ce module vérifie les deux régimes, sans jamais affaiblir la règle par défaut :

* régime par défaut (``INJS_AUTO_INSCRIPTION_PEDAGOGIQUE = False``) : la
  validation reste purement administrative ;
* régime activé : la validation déclenche la génération depuis la maquette
  ACTIVE, de façon idempotente ; sans maquette active, elle est DIFFÉRÉE et
  journalisée, et ne fait jamais échouer la validation.
"""

from datetime import date

from django.test import TestCase, override_settings

from scolarite import inscription_services
from scolarite.models import (
    ECUE,
    InscriptionAdministrative,
    InscriptionPedagogique,
    JournalScolarite,
    Maquette,
    Niveau,
    UE,
)
from scolarite.pedagogie_services import generer_inscriptions_pedagogiques
from scolarite.tests.test_inscriptions import ConversionFixture


class ParcoursPedagogiqueApresValidationTests(ConversionFixture, TestCase):
    """Le parcours académique s'ouvre à la validation administrative."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        # Maquette officielle du niveau L1, en brouillon au départ.
        cls.maquette = Maquette.objects.create(
            annee_academique=cls.annee, ref_formation=cls.formation,
            niveau=cls.niveau, version=1,
            libelle='Maquette L1 de recette',
        )
        from scolarite.models import Semestre

        cls.semestre, _ = Semestre.objects.get_or_create(
            niveau=cls.niveau, numero=1, defaults={'libelle': 'Semestre 1'},
        )
        ue = UE.objects.create(
            maquette=cls.maquette, semestre=cls.semestre,
            code='REC-S1-UE01', intitule='UE de recette', credits=10,
        )
        ECUE.objects.create(ue=ue, code='REC-S1-UE01-EC01', intitule='ECUE 1')
        ECUE.objects.create(ue=ue, code='REC-S1-UE01-EC02', intitule='ECUE 2')

    def _valider(self, inscription, acteur=None):
        from scolarite.models import InscriptionAdministrative as I

        for etape in (I.Statut.EN_ATTENTE, I.Statut.A_VALIDER, I.Statut.VALIDEE):
            inscription = inscription_services.appliquer_transition(
                inscription, etape, acteur=acteur or self.acteur,
            )
        return inscription

    def _inscription(self, valider=False):
        admission = self.admettre()
        return inscription_services.convertir_admission_en_inscription(
            admission, acteur=self.acteur, valider=valider,
        )

    # ── Régime par défaut : frontière métier préservée ─────────────────────
    def test_inscription_creee_avant_validation_ne_genere_rien(self):
        inscription = self._inscription()
        self.assertEqual(inscription.statut, InscriptionAdministrative.Statut.BROUILLON)
        self.assertEqual(inscription.inscriptions_pedagogiques.count(), 0)

    def test_par_defaut_la_validation_ne_genere_rien_meme_avec_maquette(self):
        """La règle de frontière reste intacte : aucune génération implicite."""
        self.maquette.statut = Maquette.Statut.ACTIVE
        self.maquette.save(update_fields=['statut'])
        inscription = self._valider(self._inscription())
        self.assertEqual(inscription.statut, InscriptionAdministrative.Statut.VALIDEE)
        self.assertEqual(inscription.inscriptions_pedagogiques.count(), 0)
        self.assertFalse(
            JournalScolarite.objects.filter(
                action=JournalScolarite.Action.INSCRIPTION_PEDAGOGIQUE_GENEREE,
            ).exists(),
        )

    # ── Régime activé : enchaînement automatique ───────────────────────────
    @override_settings(INJS_AUTO_INSCRIPTION_PEDAGOGIQUE=True)
    def test_validation_sans_maquette_active_differe_sans_echouer(self):
        inscription = self._valider(self._inscription())
        self.assertEqual(inscription.statut, InscriptionAdministrative.Statut.VALIDEE)
        self.assertEqual(inscription.inscriptions_pedagogiques.count(), 0)
        self.assertTrue(
            JournalScolarite.objects.filter(
                action=JournalScolarite.Action.INSCRIPTION_PEDAGOGIQUE_DIFFEREE,
            ).exists(),
            'La génération différée doit être journalisée, pas silencieuse.',
        )

    @override_settings(INJS_AUTO_INSCRIPTION_PEDAGOGIQUE=True)
    def test_validation_avec_maquette_active_genere_le_parcours(self):
        self.maquette.statut = Maquette.Statut.ACTIVE
        self.maquette.save(update_fields=['statut'])
        inscription = self._valider(self._inscription())
        lignes = inscription.inscriptions_pedagogiques.all()
        self.assertEqual(lignes.count(), 2)
        self.assertEqual(
            {ligne.origine for ligne in lignes},
            {InscriptionPedagogique.Origine.AUTOMATIQUE},
        )
        self.assertTrue(
            JournalScolarite.objects.filter(
                action=JournalScolarite.Action.INSCRIPTION_PEDAGOGIQUE_GENEREE,
            ).exists(),
        )

    @override_settings(INJS_AUTO_INSCRIPTION_PEDAGOGIQUE=True)
    def test_conversion_avec_validation_genere_le_parcours(self):
        """Le chemin direct (conversion + validation) enchaîne aussi."""
        self.maquette.statut = Maquette.Statut.ACTIVE
        self.maquette.save(update_fields=['statut'])
        inscription = self._inscription(valider=True)
        self.assertEqual(inscription.statut, InscriptionAdministrative.Statut.VALIDEE)
        self.assertEqual(inscription.inscriptions_pedagogiques.count(), 2)

    # ── Idempotence ────────────────────────────────────────────────────────
    @override_settings(INJS_AUTO_INSCRIPTION_PEDAGOGIQUE=True)
    def test_revalidation_ne_duplique_pas(self):
        self.maquette.statut = Maquette.Statut.ACTIVE
        self.maquette.save(update_fields=['statut'])
        inscription = self._valider(self._inscription())
        avant = inscription.inscriptions_pedagogiques.count()
        # Une seconde génération explicite ne doit rien ajouter.
        generer_inscriptions_pedagogiques(inscription, acteur=self.acteur)
        self.assertEqual(inscription.inscriptions_pedagogiques.count(), avant)

    @override_settings(INJS_AUTO_INSCRIPTION_PEDAGOGIQUE=True)
    def test_generation_apres_activation_complete_sans_doublon(self):
        """Parcours réel : validation avant activation, puis reprise."""
        inscription = self._valider(self._inscription())
        self.assertEqual(inscription.inscriptions_pedagogiques.count(), 0)
        self.maquette.statut = Maquette.Statut.ACTIVE
        self.maquette.save(update_fields=['statut'])
        creees = generer_inscriptions_pedagogiques(inscription, acteur=self.acteur)
        self.assertEqual(len(creees), 2)
        self.assertEqual(inscription.inscriptions_pedagogiques.count(), 2)
        # Relance : aucune création supplémentaire.
        creees = generer_inscriptions_pedagogiques(inscription, acteur=self.acteur)
        self.assertEqual(len(creees), 0)
        self.assertEqual(inscription.inscriptions_pedagogiques.count(), 2)

    # ── Séparation des décisions ───────────────────────────────────────────
    @override_settings(INJS_AUTO_INSCRIPTION_PEDAGOGIQUE=True)
    def test_aucune_exclusion_automatique(self):
        """Une inscription validée reste validée : pas de décision déduite."""
        self.maquette.statut = Maquette.Statut.ACTIVE
        self.maquette.save(update_fields=['statut'])
        inscription = self._valider(self._inscription())
        inscription.refresh_from_db()
        self.assertEqual(inscription.statut, InscriptionAdministrative.Statut.VALIDEE)
        self.assertIsNotNone(inscription.date_validation)
        self.assertEqual(
            JournalScolarite.objects.filter(
                action=JournalScolarite.Action.INSCRIPTION_TRANSITION,
                commentaire__icontains='exclu',
            ).count(),
            0,
        )
