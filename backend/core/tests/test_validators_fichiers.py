"""Contrôles des pièces jointes — correctif d'audit sécurité.

Avant l'audit, aucun champ fichier n'imposait de limite de taille ni de liste
d'extensions : n'importe quel format (page HTML, binaire) et n'importe quel
volume étaient acceptés. Ces tests verrouillent les deux contrôles et
vérifient qu'ils s'appliquent bien là où les fichiers entrent (services), et
pas seulement dans l'admin Django.
"""

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase, TestCase

from core.validators import (
    TAILLE_MAX_PIECE,
    TAILLE_MAX_PREUVE,
    valider_piece_candidature,
    valider_preuve_paiement,
)


class FauxFichier:
    """Objet minimal imitant un fichier téléversé (nom + taille)."""

    def __init__(self, nom, taille=1024):
        self.name = nom
        self.size = taille


class ValidateursUnitaireTests(SimpleTestCase):

    def test_pdf_accepte(self):
        valider_piece_candidature(FauxFichier('diplome.pdf'))  # ne lève pas

    def test_extension_refusee(self):
        for nom in ('script.exe', 'page.html', 'archive.zip', 'sans_extension'):
            with self.assertRaises(ValidationError, msg=nom):
                valider_piece_candidature(FauxFichier(nom))

    def test_extension_insensible_a_la_casse(self):
        valider_piece_candidature(FauxFichier('SCAN.PDF'))
        valider_piece_candidature(FauxFichier('photo.JPG'))

    def test_fichier_trop_volumineux_refuse(self):
        with self.assertRaises(ValidationError):
            valider_piece_candidature(
                FauxFichier('diplome.pdf', taille=TAILLE_MAX_PIECE + 1))

    def test_limite_exacte_acceptee(self):
        valider_piece_candidature(FauxFichier('diplome.pdf', taille=TAILLE_MAX_PIECE))

    def test_preuve_paiement_a_sa_propre_limite(self):
        with self.assertRaises(ValidationError):
            valider_preuve_paiement(
                FauxFichier('recu.pdf', taille=TAILLE_MAX_PREUVE + 1))
        valider_preuve_paiement(FauxFichier('recu.jpg', taille=TAILLE_MAX_PREUVE))

    def test_valeur_vide_ignoree(self):
        """Un champ facultatif non renseigné ne doit pas bloquer."""
        valider_piece_candidature(None)
        valider_piece_candidature('')
        valider_preuve_paiement(None)


class DepotPieceReelTests(TestCase):
    """Le contrôle est appliqué par le service, pas seulement par le modèle."""

    def _piece(self):
        from datetime import date

        from admissions import services as candidature_services
        from admissions.models import (
            Candidat, Candidature, PieceCandidature, TypePiece,
        )
        from formations.models import RefFormation
        from scolarite.models import AnneeAcademique, Niveau

        annee, _ = AnneeAcademique.objects.get_or_create(
            libelle='2026-2027',
            defaults={'date_debut': date(2026, 10, 1),
                      'date_fin': date(2027, 9, 30), 'courante': True},
        )
        formation, _ = RefFormation.objects.get_or_create(intitule='LICENCE STAPS')
        niveau, _ = Niveau.objects.get_or_create(
            code='L1', defaults={'libelle': 'Licence 1', 'ordre': 1})
        candidat = Candidat.objects.create(nom='Test', prenom='Upload')
        type_piece = TypePiece.objects.create(code='DIPLOME', libelle='Diplôme')
        candidature = Candidature.objects.create(
            candidat=candidat, annee_academique=annee,
            ref_formation=formation, niveau=niveau)
        piece = PieceCandidature.objects.create(
            candidature=candidature, type_piece=type_piece)
        return candidature_services, piece

    def test_le_service_refuse_un_executable(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        services, piece = self._piece()
        with self.assertRaises(ValidationError):
            services.deposer_piece(
                piece, fichier=SimpleUploadedFile('virus.exe', b'MZ'))

    def test_le_service_accepte_un_pdf(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        services, piece = self._piece()
        services.deposer_piece(
            piece, fichier=SimpleUploadedFile('diplome.pdf', b'%PDF-1.4'))
        piece.refresh_from_db()
        self.assertTrue(piece.fichier)
