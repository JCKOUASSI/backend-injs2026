"""L1 — Non-régression du versionnement des relevés de notes.

Cible l'erreur d'agrégation Django `['maximum__max']` : l'alias déclaré est
`maximum`, la clé de lecture doit l'être aussi. Ce test échouait avec
`KeyError('maximum__max')` avant correction.
"""
import tempfile

from django.test import TestCase, override_settings

from evaluations.services.releves import enregistrer_releve

MEDIA = tempfile.mkdtemp(prefix='l_releve_version_')


@override_settings(MEDIA_ROOT=MEDIA)
class ReleveVersionnementTests(TestCase):
    """Le numéro de version suit bien le maximum réel en base."""

    def _jeu(self):
        """Inscription + session minimales (aucune donnée fictive injectée)."""
        from datetime import date

        from django.contrib.auth import get_user_model

        from evaluations.models import SessionEvaluation
        from formations.models import Participant, RefFormation
        from scolarite.models import (
            AnneeAcademique, DossierEtudiant, InscriptionAdministrative,
            Maquette, Niveau, Semestre,
        )

        User = get_user_model()
        User.objects.create_user(username='releve_admin', password='x')
        annee = AnneeAcademique.objects.create(
            libelle='2025-2026',
            date_debut=date(2025, 9, 1), date_fin=date(2026, 7, 31),
        )
        niveau = Niveau.objects.create(
            code='L1', libelle='Licence 1', ordre=1, credits_requis=60,
        )
        Semestre.objects.create(niveau=niveau, numero=1, libelle='S1')
        ref_formation = RefFormation.objects.create(intitule='Formation 1')
        maquette = Maquette.objects.create(
            annee_academique=annee, ref_formation=ref_formation,
            niveau=niveau, version=1,
        )
        participant = Participant.objects.create(
            matricule='RELEVE-TEST-1', nom='Nom', prenom='Prenom',
        )
        dossier = DossierEtudiant.objects.create(participant=participant)
        inscription = InscriptionAdministrative.objects.create(
            etudiant=dossier, annee_academique=annee,
            ref_formation=ref_formation, niveau=niveau, statut='BROUILLON',
        )
        session = SessionEvaluation.objects.create(
            annee_academique=annee, ref_formation=ref_formation,
            niveau=niveau, maquette=maquette, libelle='Session de test',
            type_session='NORMALE', statut='CLOTUREE',
        )
        return inscription, session

    def test_01_premiere_generation_version_1(self):
        inscription, session = self._jeu()
        releve, contenu = enregistrer_releve(inscription, session)
        # L'agrégation doit rester lisible : aucune KeyError sur l'alias.
        self.assertEqual(releve.version, 1)
        self.assertEqual(len(releve.sha256), 64)
        # L'empreinte archivée est bien celle du contenu canonique.
        from evaluations.services.empreinte import empreinte

        self.assertEqual(releve.sha256, empreinte(contenu))

    def test_02_agregation_maximum_lit_le_vrai_maximum(self):
        inscription, session = self._jeu()
        from evaluations.models import ReleveNotes
        from django.db.models import Max

        for version in (1, 2, 5):
            ReleveNotes.objects.create(
                inscription=inscription, session=session, version=version,
                fichier=f'releves/v{version}.pdf', sha256='a' * 64,
            )
        maximum = (
            ReleveNotes.objects
            .filter(inscription=inscription, session=session)
            .aggregate(maximum=Max('version'))['maximum']
        )
        self.assertEqual(maximum, 5)
        # Le service propose bien la version suivante.
        releve, _contenu = enregistrer_releve(inscription, session)
        self.assertEqual(releve.version, 6)