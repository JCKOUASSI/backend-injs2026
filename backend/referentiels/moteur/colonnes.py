"""Découverte des colonnes exportables et importables d'un référentiel.

Mission « Référentiels » — moteur commun (PHASE 2).

Un référentiel = un modèle Django. Ce module décrit, pour chaque modèle, les
champs qui peuvent être exportés et importés, avec leur libellé francophone.
Il évite de coder en dur une liste de colonnes par référentiel : les 27
entrées du registre sont traitées par le même code, tout en laissant chaque
modèle porter ses propres règles (aiguillages ci-dessous).

Aucune donnée n'est inventée : un champ absent du modèle n'est jamais proposé.
"""

from django.db import models

# Champs techniques jamais présentés à l'utilisateur.
CHAMPS_EXCLUS = frozenset({
    'id', 'pk', 'created_at', 'updated_at', 'slug',
})

# Résolution des clés étrangères : par quel champ naturel les retrouver ?
# (sinon l'import exigerait un identifiant numérique illisible dans un tableur)
CLE_NATURELLE_FK = {
    'annee_academique': ('libelle', 'annee', 'code'),
    'formation': ('libelle', 'code'),
    'filiere': ('libelle', 'code'),
    'site': ('libelle', 'code', 'nom'),
    'batiment': ('libelle', 'code', 'nom'),
}

# En-têtes francophones pour les colonnes communes du socle.
LIBELLES = {
    'code': 'Code',
    'libelle': 'Libellé',
    'description': 'Description',
    'actif': 'Actif',
    'archive': 'Archivé',
    'date_activation': "Date d'activation",
    'date_desactivation': 'Date de désactivation',
    'annee_academique': 'Année académique',
    'source_document': 'Document source',
    'fiabilite': 'Fiabilité',
    'ordre': 'Ordre',
    'cree_le': 'Créé le',
    'modifie_le': 'Modifié le',
}


def libelle_champ(nom):
    """Libellé lisible d'un champ (base de données → français)."""
    if nom in LIBELLES:
        return LIBELLES[nom]
    return nom.replace('_', ' ').capitalize()


def _est_exportable(field):
    if field.name in CHAMPS_EXCLUS or field.primary_key:
        return False
    if isinstance(field, (models.AutoField, models.BigAutoField)):
        return False
    if isinstance(field, models.ManyToManyField):
        return False
    if getattr(field, 'auto_now', False) or getattr(field, 'auto_now_add', False):
        return False
    return True


def _est_importable(field):
    """Un champ importable est un champ que l'utilisateur peut renseigner."""
    if not _est_exportable(field):
        return False
    # Les compteurs et horodatages de cycle de vie sont gérés par l'application.
    if field.name in {'archive', 'cree_le', 'modifie_le', 'date_activation',
                      'date_desactivation', 'source_document', 'fiabilite'}:
        return False
    if isinstance(field, models.ForeignKey):
        return field.name in CLE_NATURELLE_FK
    return True


def champs_exportables(modele):
    """Liste ordonnée des champs exportables : ``[{'cle', 'libelle'}]``."""
    colonnes = []
    for field in modele._meta.get_fields():
        if not isinstance(field, models.Field) or getattr(field, 'many_to_many', False):
            continue
        if not _est_exportable(field):
            continue
        colonnes.append({'cle': field.name, 'libelle': libelle_champ(field.name)})
    # Le code puis le libellé d'abord : c'est l'ordre attendu par les services.
    ordre = {'code': 0, 'libelle': 1}
    colonnes.sort(key=lambda c: (ordre.get(c['cle'], 9), c['libelle']))
    return colonnes


def champs_importables(modele):
    """Liste ordonnée des champs importables : ``[{'cle', 'libelle', 'type'}]``."""
    colonnes = []
    for field in modele._meta.get_fields():
        if not isinstance(field, models.Field) or getattr(field, 'many_to_many', False):
            continue
        if not _est_importable(field):
            continue
        colonnes.append({
            'cle': field.name,
            'libelle': libelle_champ(field.name),
            'type': type(field).__name__,
            'obligatoire': not (field.blank or field.null),
        })
    ordre = {'code': 0, 'libelle': 1}
    colonnes.sort(key=lambda c: (ordre.get(c['cle'], 9), c['libelle']))
    return colonnes


def champ_libelle(modele):
    """Nom du champ portant le libellé métier (``libelle``, ``nom`` ou ``intitule``)."""
    noms = {f.name for f in modele._meta.concrete_fields}
    for candidat in ('libelle', 'nom', 'intitule'):
        if candidat in noms:
            return candidat
    return None
