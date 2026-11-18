"""Validateurs de fichiers partagés (pièces jointes métier).

Constat d'audit : aucun champ fichier du projet n'imposait de limite de taille
ni de liste d'extensions autorisées. Un candidat pouvait donc déposer un
exécutable, une page HTML (risque de contenu actif si le fichier venait à être
servi) ou un fichier de plusieurs centaines de mégaoctets, et l'espace disque
comme la bande passante n'étaient bornés par rien.

Les limites ci-dessous sont volontairement généreuses pour un dossier
administratif scanné (10 Mio par pièce) tout en restant strictes sur les
formats : les candidatures acceptent aussi Word OOXML (.docx), mais les
preuves de paiement restent limitées aux PDF et images.
"""

from pathlib import Path
from zipfile import BadZipFile, ZipFile

from django.core.exceptions import ValidationError

# 10 Mio : largement suffisant pour un scan de pièce administrative.
TAILLE_MAX_PIECE = 10 * 1024 * 1024
# 5 Mio : une preuve de paiement (capture ou reçu) reste légère.
TAILLE_MAX_PREUVE = 5 * 1024 * 1024

EXTENSIONS_DOCUMENT = ('.pdf', '.jpg', '.jpeg', '.png')
EXTENSIONS_PIECE_CANDIDATURE = (*EXTENSIONS_DOCUMENT, '.docx')


def _verifier_fichier(valeur, extensions, taille_max, libelle):
    """Contrôle commun : extension autorisée puis taille réelle du fichier."""
    nom = getattr(valeur, 'name', '') or ''
    extension = Path(nom).suffix.lower()
    if extension not in extensions:
        raise ValidationError(
            f'{libelle} : format « {extension or "inconnu"} » refusé. '
            f'Formats acceptés : {", ".join(extensions)}.'
        )
    taille = getattr(valeur, 'size', None)
    if taille is not None and taille > taille_max:
        raise ValidationError(
            f'{libelle} : fichier trop volumineux '
            f'({taille / (1024 * 1024):.1f} Mio, maximum '
            f'{taille_max / (1024 * 1024):.0f} Mio).'
        )


def valider_piece_candidature(valeur):
    """Pièce de candidature : PDF, image ou vrai DOCX, 10 Mio maximum."""
    if not valeur:
        return
    _verifier_fichier(valeur, EXTENSIONS_PIECE_CANDIDATURE, TAILLE_MAX_PIECE, 'Pièce jointe')
    if Path(valeur.name).suffix.lower() == '.docx':
        # Une extension seule ne suffit pas : un .docx est une archive OOXML.
        # On ne décompresse rien (protection contre les archives malveillantes).
        try:
            position = valeur.tell()
            try:
                valeur.seek(0)
                with ZipFile(valeur) as document:
                    noms = set(document.namelist())
                    if not {'[Content_Types].xml', 'word/document.xml'} <= noms:
                        raise ValidationError('Pièce jointe : document Word .docx invalide.')
            finally:
                valeur.seek(position)
        except (BadZipFile, OSError, ValueError, AttributeError, TypeError) as erreur:
            raise ValidationError('Pièce jointe : document Word .docx invalide.') from erreur


def valider_preuve_paiement(valeur):
    """Preuve de paiement : PDF ou image, 5 Mio maximum."""
    if not valeur:
        return
    _verifier_fichier(valeur, EXTENSIONS_DOCUMENT, TAILLE_MAX_PREUVE, 'Preuve de paiement')
