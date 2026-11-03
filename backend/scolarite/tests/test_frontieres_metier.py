"""Frontières métier du parcours LMD — garde-fous issus de l'audit backend.

Ces tests verrouillent des règles explicitement exigées du backend INJS et
qui n'étaient couvertes par aucun test avant l'audit :

1. la **validation** d'une inscription administrative ne crée jamais, à elle
   seule, une inscription pédagogique (les deux étapes restent distinctes) ;
2. la **génération pédagogique** reste une action explicite et idempotente ;
3. la **conversion d'admission** est idempotente : un rejeu (double clic,
   retentative réseau) ne crée pas une seconde inscription ;
4. une **exclusion (radiation)** n'est jamais déduite d'une anomalie technique :
   elle exige un appel explicite, un acteur, un motif, et laisse une trace.

Aucune donnée réelle n'est touchée : tout est créé en base de test.
"""

from django.test import TestCase

from scolarite.models import (
    EvenementScolarite,
    InscriptionAdministrative,
    InscriptionPedagogique,
    JournalScolarite,
)
from scolarite.tests.test_pedagogie import PedagogieFixture


class FrontieresParcoursTests(PedagogieFixture, TestCase):
    """« Valider », « activer » et « inscrire pédagogiquement » sont distincts."""

    def test_la_validation_ne_cree_aucune_inscription_pedagogique(self):
        """La conversion d'une admission validée est purement administrative."""
        self.assertEqual(self.inscription.statut, 'VALIDEE')
        self.assertEqual(
            InscriptionPedagogique.objects.filter(
                inscription=self.inscription).count(), 0,
            "La validation administrative a créé des lignes pédagogiques : "
            "les deux étapes ne sont plus distinctes.",
        )

    def test_la_generation_pedagogique_reste_une_action_explicite(self):
        """Après validation, seule la génération crée les lignes pédagogiques."""
        from scolarite import pedagogie_services

        self.assertEqual(InscriptionPedagogique.objects.count(), 0)
        pedagogie_services.generer_inscriptions_pedagogiques(
            self.inscription, acteur=self.acteur)
        self.assertGreater(
            InscriptionPedagogique.objects.filter(
                inscription=self.inscription).count(), 0,
            "La génération explicite n'a rien créé : le parcours pédagogique "
            "ne peut pas être constitué.",
        )

    def test_la_generation_pedagogique_est_idempotente(self):
        """Deux générations successives ne dupliquent pas les lignes."""
        from scolarite import pedagogie_services

        pedagogie_services.generer_inscriptions_pedagogiques(
            self.inscription, acteur=self.acteur)
        apres_premiere = InscriptionPedagogique.objects.filter(
            inscription=self.inscription).count()
        pedagogie_services.generer_inscriptions_pedagogiques(
            self.inscription, acteur=self.acteur)
        self.assertEqual(
            InscriptionPedagogique.objects.filter(
                inscription=self.inscription).count(),
            apres_premiere,
            "La seconde génération a dupliqué les inscriptions pédagogiques.",
        )


class IdempotenceConversionTests(PedagogieFixture, TestCase):
    """Un rejeu de la conversion ne doit jamais créer un second dossier."""

    def _admission_supplementaire(self, nom):
        """Rejoue le parcours admission → décision pour un second candidat."""
        from admissions import admission_services, services as candidature_services
        from admissions import workflow
        from admissions.models import Admission, Candidat, Candidature, PieceCandidature

        candidature = candidature_services.creer_candidature(
            Candidat.objects.create(nom=nom, prenom='Audit'),
            annee_academique=self.annee, ref_formation=self.formation,
            niveau=self.niveau,
        )
        for piece in candidature.pieces_obligatoires:
            candidature_services.verifier_piece(
                piece, PieceCandidature.Statut.VALIDEE)
        for statut in (
            Candidature.Statut.SOUMISE,
            Candidature.Statut.EN_ATTENTE_DE_VERIFICATION,
            Candidature.Statut.PIECES_VALIDEES,
            Candidature.Statut.EN_ETUDE,
            Candidature.Statut.ADMISSIBLE,
        ):
            workflow.appliquer_transition(candidature, statut)
        admission = admission_services.creer_admission(candidature)
        admission_services.prononcer_decision(admission, Admission.Decision.ADMIS)
        return admission

    def test_conversion_rejouee_ne_cree_pas_de_seconde_inscription(self):
        from scolarite import inscription_services

        admission = self.inscription.admission
        self.assertEqual(
            InscriptionAdministrative.objects.filter(admission=admission).count(), 1)

        rejouee = inscription_services.convertir_admission_en_inscription(
            admission, acteur=self.acteur, valider=True)

        self.assertEqual(rejouee.pk, self.inscription.pk)
        self.assertEqual(
            InscriptionAdministrative.objects.filter(admission=admission).count(), 1,
            "Le rejeu a créé une seconde inscription pour la même admission.",
        )
        self.assertEqual(rejouee.statut, 'VALIDEE')

    def test_rejeu_sans_validation_ne_cree_pas_de_doublon_silencieux(self):
        """Le cas le plus dangereux : deux brouillons pour une même admission.

        Sans garde-fou, un rejeu sans ``valider`` passait inaperçu (aucune
        contrainte d'unicité) et laissait deux inscriptions BROUILLON.
        """
        from scolarite import inscription_services

        admission = self._admission_supplementaire('Kone')
        premiere = inscription_services.convertir_admission_en_inscription(
            admission, acteur=self.acteur)
        seconde = inscription_services.convertir_admission_en_inscription(
            admission, acteur=self.acteur)

        self.assertEqual(premiere.pk, seconde.pk)
        self.assertEqual(
            InscriptionAdministrative.objects.filter(admission=admission).count(), 1,
            "Un rejeu sans validation a créé une seconde inscription BROUILLON.",
        )

    def test_une_inscription_annulee_permet_une_nouvelle_conversion(self):
        """L'idempotence ne doit pas bloquer une réinscription légitime."""
        from scolarite import inscription_services

        admission = self._admission_supplementaire('Bamba')
        premiere = inscription_services.convertir_admission_en_inscription(
            admission, acteur=self.acteur)
        inscription_services.appliquer_transition(
            premiere, InscriptionAdministrative.Statut.ANNULEE,
            acteur=self.acteur, commentaire='Annulée par erreur de saisie')

        nouvelle = inscription_services.convertir_admission_en_inscription(
            admission, acteur=self.acteur)

        self.assertNotEqual(nouvelle.pk, premiere.pk)
        self.assertEqual(
            InscriptionAdministrative.objects.filter(
                admission=admission).count(), 2)


class RadiationExpliciteTests(PedagogieFixture, TestCase):
    """L'exclusion est une décision institutionnelle, jamais une déduction."""

    def test_aucune_radiation_sur_anomalie_technique(self):
        """Une inscription validée sans lignes pédagogiques n'est pas radiée."""
        avant = self.inscription.statut
        for _ in range(3):  # lectures répétées de l'état technique
            self.inscription.refresh_from_db()
            self.assertEqual(
                InscriptionPedagogique.objects.filter(
                    inscription=self.inscription).count(), 0)
        self.assertEqual(self.inscription.statut, avant)
        self.assertEqual(
            EvenementScolarite.objects.filter(
                inscription=self.inscription,
                type_evenement=EvenementScolarite.Type.RADIATION).count(), 0)

    def test_la_radiation_exige_une_action_tracee(self):
        """La radiation passe par le service dédié et laisse une trace complète."""
        from scolarite import inscription_services

        inscription_services.radier_inscription(
            self.inscription, acteur=self.acteur, motif='Décision de la direction')

        self.inscription.refresh_from_db()
        self.assertEqual(self.inscription.statut, 'SUSPENDUE')
        evenement = EvenementScolarite.objects.get(
            inscription=self.inscription,
            type_evenement=EvenementScolarite.Type.RADIATION)
        self.assertEqual(evenement.commentaire, 'Décision de la direction')
        self.assertEqual(evenement.enregistre_par, self.acteur)
        self.assertTrue(
            JournalScolarite.objects.filter(objet_id=self.inscription.pk).exists(),
            "La radiation n'a pas été journalisée.",
        )

    def test_la_radiation_refuse_une_inscription_non_validee(self):
        """Seule une inscription VALIDEE peut être radiée (pas de contournement)."""
        from scolarite import inscription_services

        brouillon = inscription_services.convertir_admission_en_inscription(
            self.inscription.admission, acteur=self.acteur,
            annee_academique=self.annee)
        # La conversion est idempotente : on force un état non validé.
        brouillon.statut = InscriptionAdministrative.Statut.BROUILLON
        brouillon.save(update_fields=['statut'])
        with self.assertRaises(inscription_services.InscriptionImpossible):
            inscription_services.radier_inscription(
                brouillon, acteur=self.acteur, motif='Test')


class IdempotenceViaAPITests(PedagogieFixture, TestCase):
    """Le rejeu d'un appel API ne doit ni créer ni annoncer une création."""

    def setUp(self):
        super().setUp()
        from rest_framework.test import APIClient

        self.client = APIClient()
        self.acteur.is_superuser = True
        self.acteur.is_staff = True
        self.acteur.role = 'ADMIN'
        self.acteur.save(update_fields=['is_superuser', 'is_staff', 'role'])
        self.client.force_authenticate(self.acteur)

    def test_seconde_conversion_renvoie_200_et_une_seule_inscription(self):
        admission = self.inscription.admission
        reponse = self.client.post(
            '/api/scolarite/inscriptions/depuis-admission/',
            {'admission_id': admission.id, 'valider': True}, format='json',
        )
        self.assertEqual(reponse.status_code, 200)
        self.assertEqual(reponse.json()['id'], self.inscription.id)
        self.assertEqual(
            InscriptionAdministrative.objects.filter(admission=admission).count(), 1)
