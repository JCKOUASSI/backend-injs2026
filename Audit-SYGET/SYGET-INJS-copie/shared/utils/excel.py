"""
Utilitaires pour la génération et l'export de fichiers Excel.
"""

from io import BytesIO
from typing import Any

import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment


def creer_workbook_excel(
    titre: str,
    entetes: list[str],
    lignes: list[list[Any]],
) -> bytes:
    """
    Génère un fichier Excel en mémoire.

    :param titre: Titre de l'onglet
    :param entetes: Liste des en-têtes de colonnes
    :param lignes: Liste de lignes (listes de valeurs)
    :return: Contenu du fichier XLSX en bytes
    """
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = titre

    header_fill = PatternFill(start_color="003366", end_color="003366", fill_type="solid")
    header_font = Font(color="FFFFFF", bold=True)

    for col_idx, entete in enumerate(entetes, start=1):
        cell = ws.cell(row=1, column=col_idx, value=entete)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center")

    for row_idx, ligne in enumerate(lignes, start=2):
        for col_idx, valeur in enumerate(ligne, start=1):
            ws.cell(row=row_idx, column=col_idx, value=valeur)

    max_cols = max(len(entetes), *(len(row) for row in lignes), 0)
    for col_idx in range(1, max_cols + 1):
        max_length = len(str(entetes[col_idx - 1])) if col_idx <= len(entetes) else 0
        for ligne in lignes:
            if col_idx <= len(ligne):
                max_length = max(max_length, len(str(ligne[col_idx - 1] or "")))
        ws.column_dimensions[openpyxl.utils.get_column_letter(col_idx)].width = min(max_length + 4, 50)

    buffer = BytesIO()
    wb.save(buffer)
    return buffer.getvalue()
