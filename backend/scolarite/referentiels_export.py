"""Export des référentiels (niveaux, semestres, filières…) — 4 formats.

Ce module ne connaît ni les droits ni les filtres de l'écran : il reçoit un
``queryset`` déjà filtré et la description des champs servie par
``REFERENTIEL_FIELDS``. Les quatre sorties partagent donc exactement les mêmes
colonnes, les mêmes libellés et les mêmes règles de sécurité.

Sécurité : chaque valeur texte passe par :func:`maquettes_export.neutraliser`
(préfixe apostrophe devant ``=``, ``+``, ``-``, ``@``, tabulation, retour
chariot) pour empêcher l'exécution d'une formule à l'ouverture du fichier dans
Excel ou LibreOffice.

Lecture humaine : les clés étrangères (``niveau_id``, ``parcours_id``…)
sortent sous forme de code ou de libellé lisible, pas d'identifiant technique.
L'import sait relire les deux formes (voir :mod:`scolarite.referentiels_import`).
"""

from __future__ import annotations

from datetime import date

from . import tableaux_export
from .maquettes_export import CONTENT_TYPES, EXTENSIONS, FORMATS, neutraliser

# ── Libellés de colonnes ────────────────────────────────────────────────────
LIBELLES = {
    'id': 'ID',
    'code': 'CODE',
    'libelle': 'LIBELLE',
    'intitule': 'INTITULE',
    'nom': 'NOM',
    'actif': 'ACTIF',
    'cycle': 'CYCLE',
    'ordre': 'ORDRE',
    'credits_requis': 'CREDITS_REQUIS',
    'niveau_id': 'NIVEAU',
    'numero': 'NUMERO',
    'date_debut': 'DATE_DEBUT',
    'date_fin': 'DATE_FIN',
    'courante': 'COURANTE',
    'bloque_inscription': 'BLOQUE_INSCRIPTION',
    'ref_formation_id': 'FORMATION',
    'type_formation_id': 'TYPE_FORMATION',
    'annee_academique_id': 'ANNEE_ACADEMIQUE',
    'parcours_id': 'PARCOURS',
    'vague_id': 'VAGUE',
    'site_id': 'SITE',
    'capacite_max': 'CAPACITE_MAX',
    'capacite': 'CAPACITE',
    'type_diplome': 'TYPE_DIPLOME',
    'domaine': 'DOMAINE',
    'mention': 'MENTION',
    'type_lieu': 'TYPE_LIEU',
}


def libelle_champ(champ):
    """En-tête humain stable d'un champ (``niveau_id`` → ``NIVEAU``).

    Une clé étrangère non répertoriée garde son nom métier sans le suffixe
    technique ``_id`` : l'en-tête reste lisible et l'import sait le relire.
    """
    if champ in LIBELLES:
        return LIBELLES[champ]
    if champ.endswith('_id'):
        return champ[:-3].upper()
    return champ.upper()


def entetes(fields):
    """Liste ``(champ, en-tête)`` dans l'ordre servi par l'API."""
    return [(champ, libelle_champ(champ)) for champ in fields]


def _valeur_lisible(obj, champ):
    """Valeur d'affichage : choix traduits, booléens OUI/NON, clés lisibles."""
    valeur = getattr(obj, champ, None)
    if champ.endswith('_id'):
        try:
            lie = getattr(obj, champ[:-3])
        except Exception:  # pragma: no cover - relation absente
            lie = None
        if lie is None:
            return ''
        for attribut in ('code', 'libelle', 'nom', 'intitule'):
            texte = getattr(lie, attribut, None)
            if texte:
                return str(texte)
        return str(lie)
    if isinstance(valeur, bool):
        return 'OUI' if valeur else 'NON'
    if valeur is None:
        return ''
    affichage = getattr(obj, f'get_{champ}_display', None)
    if callable(affichage):
        try:
            return str(affichage())
        except Exception:  # pragma: no cover - choix non standard
            pass
    return str(valeur)


def lignes(queryset, fields):
    """Une ligne ``{EN_TETE: valeur}`` par objet du queryset."""
    colonnes = [libelle_champ(champ) for champ in fields]
    resultat = []
    for obj in queryset:
        resultat.append({
            colonne: neutraliser(_valeur_lisible(obj, champ))
            for colonne, champ in zip(colonnes, fields)
        })
    return resultat


def _titre(ressource, modele):
    return f'Référentiel — {modele._meta.verbose_name_plural}'.capitalize()


# ── Sérialisation ───────────────────────────────────────────────────────────
def colonnes(fields):
    """Libellés humains des colonnes, dans l'ordre de l'API."""
    return [libelle_champ(champ) for champ in fields]


def construire_csv(queryset, fields):
    """CSV UTF-8 avec BOM, séparateur ``;`` (ouverture directe dans Excel)."""
    return tableaux_export.construire_csv(colonnes(fields), lignes(queryset, fields))


def construire_xlsx(queryset, fields, ressource=''):
    """Classeur Excel : feuille de données + feuille d'informations."""
    return tableaux_export.construire_xlsx(
        colonnes(fields), lignes(queryset, fields),
        feuille='Référentiel', titre=f'Référentiel — {ressource}',
        sous_titre=f'{len(lignes(queryset, fields))} ligne(s)',
    )


def construire_docx(queryset, fields, ressource='', modele=None, filtres=None):
    """Document Word paginé, tableau à en-tête répété."""
    titre = ('Référentiel — ' + modele._meta.verbose_name_plural) if modele else 'Référentiel'
    return tableaux_export.construire_docx(
        colonnes(fields), lignes(queryset, fields), titre=titre,
        sous_titre=filtres or ressource,
    )


def construire_pdf(queryset, fields, ressource='', modele=None, filtres=None):
    """PDF A4 paysage, en-tête répété et pied de page paginé."""
    titre = ('Référentiel — ' + modele._meta.verbose_name_plural) if modele else 'Référentiel'
    return tableaux_export.construire_pdf(
        colonnes(fields), lignes(queryset, fields), titre=titre,
        sous_titre=filtres or ressource,
    )


# ── Réponse HTTP ────────────────────────────────────────────────────────────
def nom_fichier(ressource, fmt):
    """Nom stable, sans accent ni espace, daté."""
    return f'referentiel-{ressource}_{date.today().isoformat()}.{EXTENSIONS[fmt]}'


def reponse_export(queryset, fields, fmt, ressource, modele=None, filtres=None):
    """Construit la réponse de téléchargement dans le format demandé."""
    lignes_tableau = lignes(queryset, fields)
    titre = ('Référentiel — ' + modele._meta.verbose_name_plural) if modele else 'Référentiel'
    return tableaux_export.reponse(
        colonnes(fields), lignes_tableau, fmt, nom_fichier(ressource, fmt),
        feuille='Référentiel',
        titre=titre,
        sous_titre=filtres or ressource,
    )


__all__ = [
    'FORMATS', 'LIBELLES', 'colonnes', 'construire_csv', 'construire_docx',
    'construire_pdf', 'construire_xlsx', 'entetes', 'libelle_champ', 'lignes',
    'reponse_export',
]
