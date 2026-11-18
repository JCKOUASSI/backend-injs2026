"""Validateurs de fichiers partagés (pièces jointes métier).

Constat d'audit : aucun champ fichier du projet n'imposait de limite de taille
ni de liste d'extensions autorisées. Un candidat pouvait donc déposer un
exécutable, une page HTML (risque de contenu actif si le fichier venait à être
servi) ou un fichier de plusieurs centaines de mégaoctets, et l'espace disque
comme la bande passante n'étaient bornés par rien.

Les limites ci-dessous sont volontairement généreuses pour un dossier
administratif scanné (10 Mio par pièce) tout en restant strictes sur les
formats : les candidatures acceptent les documents bureautiques et images
courants (pas d'exécutables, HTML ni archives génériques). Les preuves de
paiement restent limitées aux PDF et images.
"""

from pathlib import Path
from zipfile import BadZipFile, ZipFile

from django.core.exceptions import ValidationError

# 10 Mio : largement suffisant pour un scan de pièce administrative.
TAILLE_MAX_PIECE = 10 * 1024 * 1024
# 5 Mio : une preuve de paiement (capture ou reçu) reste légère.
TAILLE_MAX_PREUVE = 5 * 1024 * 1024

EXTENSIONS_DOCUMENT = ('.pdf', '.jpg', '.jpeg', '.png')
EXTENSIONS_PIECE_CANDIDATURE = (
    *EXTENSIONS_DOCUMENT, '.gif', '.webp', '.bmp', '.tif', '.tiff', '.heic', '.heif',
    '.doc', '.docx', '.odt', '.rtf', '.txt', '.csv',
    '.xls', '.xlsx', '.ods', '.ppt', '.pptx', '.odp',
)
# OOXML et OpenDocument sont des archives structurées, PAS des ZIP libres.
OOXML_FICHIERS = {
    '.docx': 'word/document.xml',
    '.xlsx': 'xl/workbook.xml',
    '.pptx': 'ppt/presentation.xml',
}
ODF_TYPES = {
    '.odt': 'application/vnd.oasis.opendocument.text',
    '.ods': 'application/vnd.oasis.opendocument.spreadsheet',
    '.odp': 'application/vnd.oasis.opendocument.presentation',
}
SIGNATURE_OFFICE_ANCIEN = b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1'


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


def _verifier_bureautique(valeur, extension):
    """Refuse les fichiers renommés en Office/ODF sans archive ou signature attendue."""
    try:
        position = valeur.tell()
        try:
            valeur.seek(0)
            if extension in OOXML_FICHIERS or extension in ODF_TYPES:
                with ZipFile(valeur) as document:
                    noms = set(document.namelist())
                    if extension in OOXML_FICHIERS:
                        valide = {'[Content_Types].xml', OOXML_FICHIERS[extension]} <= noms
                    else:
                        # La chaîne mimetype ODF doit rester courte : ne jamais
                        # décompresser un membre arbitraire de l'archive.
                        info = document.getinfo('mimetype')
                        valide = 'content.xml' in noms and info.file_size <= 128
                        if valide:
                            valide = document.read('mimetype').decode('ascii') == ODF_TYPES[extension]
                    if not valide:
                        raise ValidationError(f'Pièce jointe : fichier {extension} invalide.')
            elif extension in ('.doc', '.xls', '.ppt'):
                if valeur.read(8) != SIGNATURE_OFFICE_ANCIEN:
                    raise ValidationError(f'Pièce jointe : fichier {extension} invalide.')
            elif extension == '.rtf' and not valeur.read(5).startswith(b'{\\rtf'):
                raise ValidationError('Pièce jointe : fichier .rtf invalide.')
        finally:
            valeur.seek(position)
    except (BadZipFile, KeyError, OSError, ValueError, AttributeError, TypeError, UnicodeError) as erreur:
        raise ValidationError(f'Pièce jointe : fichier {extension} invalide.') from erreur


def valider_piece_candidature(valeur):
    """Documents usuels (sans exécutables ni archives libres), 10 Mio maximum."""
    if not valeur:
        return
    _verifier_fichier(valeur, EXTENSIONS_PIECE_CANDIDATURE, TAILLE_MAX_PIECE, 'Pièce jointe')
    extension = Path(valeur.name).suffix.lower()
    if extension in OOXML_FICHIERS or extension in ODF_TYPES or extension in ('.doc', '.xls', '.ppt', '.rtf'):
        _verifier_bureautique(valeur, extension)


def valider_preuve_paiement(valeur):
    """Preuve de paiement : PDF ou image, 5 Mio maximum."""
    if not valeur:
        return
    _verifier_fichier(valeur, EXTENSIONS_DOCUMENT, TAILLE_MAX_PREUVE, 'Preuve de paiement')
