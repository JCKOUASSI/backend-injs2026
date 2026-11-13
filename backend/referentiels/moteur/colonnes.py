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

# Noms de champs acceptés comme « clé métier » d'un modèle lié, par ordre de
# préférence. Seuls les champs réellement présents sur le modèle sont retenus :
# un tableur écrit « ENSEPS », pas « 3 ».
CLES_METIER_CANDIDATES = (
    'code', 'libelle', 'nom', 'intitule', 'sigle', 'abrege',
    'numero', 'annee', 'denomination', 'nom_complet', 'matricule',
)

# Champs techniques jamais utilisés pour retrouver une référence
# (distinct de CHAMPS_EXCLUS, qui borne les colonnes exportables).
CHAMPS_EXCLUS_RELATION = frozenset({
    'id', 'pk', 'cree_le', 'modifie_le', 'created_at', 'updated_at',
    'description', 'source_document', 'fiabilite',
})

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
    """Un champ importable est un champ que l'utilisateur peut renseigner.

    Les clés étrangères sont importables : elles sont résolues par le moteur
    de relations (identifiant ou clé métier), jamais imposées au format
    numérique de la base.
    """
    if not _est_exportable(field):
        return False
    # Les compteurs et horodatages de cycle de vie sont gérés par l'application.
    if field.name in {'archive', 'cree_le', 'modifie_le', 'date_activation',
                      'date_desactivation', 'source_document', 'fiabilite'}:
        return False
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
    """Liste ordonnée des champs importables.

    Chaque entrée porte ``cle``, ``libelle``, ``type``, ``obligatoire`` et,
    pour une clé étrangère, ``relation=True`` avec le modèle lié et ses clés
    métier — de quoi résoudre la référence sans jamais imposer un
    identifiant numérique à l'utilisateur.
    """
    colonnes = []
    for field in modele._meta.get_fields():
        if not isinstance(field, models.Field) or getattr(field, 'many_to_many', False):
            continue
        if not _est_importable(field):
            continue
        entree = {
            'cle': field.name,
            'libelle': libelle_champ(field.name),
            'type': type(field).__name__,
            'obligatoire': not (field.blank or field.null),
        }
        if isinstance(field, models.ForeignKey):
            lie = field.related_model
            entree.update({
                'relation': True,
                'modele_lie': f'{lie._meta.app_label}.{lie._meta.model_name}',
                'libelle_lie': str(lie._meta.verbose_name),
                'cles_metier': cles_metier_de(lie),
            })
        colonnes.append(entree)
    ordre = {'code': 0, 'libelle': 1}
    colonnes.sort(key=lambda c: (ordre.get(c['cle'], 9), c['libelle']))
    return colonnes


def cles_metier_de(modele_lie):
    """Champs métier permettant de retrouver une valeur du modèle lié."""
    noms = {f.name for f in modele_lie._meta.concrete_fields}
    return [n for n in CLES_METIER_CANDIDATES if n in noms] or [
        f.name for f in modele_lie._meta.concrete_fields
        if isinstance(f, (models.CharField, models.TextField))
        and f.name not in CHAMPS_EXCLUS_RELATION and not f.choices
    ]


def champ_libelle(modele):
    """Nom du champ portant le libellé métier (``libelle``, ``intitule``…).

    Le **registre** est la source de vérité : chaque référentiel y déclare le
    champ qui porte son intitulé, lequel ne s'appelle pas toujours ``libelle``
    (``intitule`` pour une formation, ``intitule_module`` pour un volume
    horaire). Sans cette consultation, un modèle dont le libellé porte un nom
    inattendu était ramené à ``libelle`` par défaut, et l'import échouait sur
    un champ inexistant.
    """
    # Import local : le registre référence les modèles, l'importer au niveau
    # du module refermerait un cycle.
    from ..registre import REGISTRE, modele_de

    for entree in REGISTRE.values():
        try:
            if modele_de(entree) is modele:
                return entree.get('champ_libelle', 'libelle')
        except Exception:
            continue
    noms = {f.name for f in modele._meta.concrete_fields}
    for candidat in ('libelle', 'nom', 'intitule'):
        if candidat in noms:
            return candidat
    return None
