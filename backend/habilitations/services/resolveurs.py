"""Résolveurs hiérarchiques de couverture des périmètres (LOT 5 / U8, écart J2-4).

Le moteur compare la cible aux périmètres des octrois au **contrôle 9**. En
dessous du rapprochement exact (type+pk) et de la règle générique
``SECRETARIAT``, la couverture s'étend ici **par rattachement hiérarchique** :

* administratif : ``DIRECTION`` ⊃ ``DEPARTEMENT`` ⊃ ``SERVICE`` ;
* pédagogique : ``FORMATION`` ⊃ ``PARCOURS`` ⊃ ``GROUPE`` (et ``NIVEAU``,
  ``SITE`` en coupes transverses) ⊃ maquette ⊃ UE ⊃ ECUE ;
* dossier : ``ETUDIANT`` couvre les inscriptions de ce dossier.

Le module ne dépend d'aucun modèle métier importé en dur : les chaînes sont
décrites par étiquettes ``app_label.model`` et chemins d'attributs, parcourus
tardivement. Il reste ainsi neutre vis-à-vis des applications métier (décision
U1 : pas de couplage dur de l'application transverse).

Deux usages :

* :func:`couvert_par_ancetre`, branché par défaut dans
  ``moteur._cible_couverte`` (voie « objet métier » de DRF,
  ``has_object_permission``) — additif : seule une paire auparavant refusée
  peut basculer vers « couvert » ;
* :func:`couverture_standard`, injectable comme résolveur explicite
  (``contexte={'couverture': couverture_standard}``) pour les vues ou les
  appels qui veulent la chaîne complète, dict et objet confondus.

Règle S5 respectée : ces résolveurs ne retirent jamais un accès ; ils
précisent uniquement la couverture d'un périmètre déjà accordé.
"""
from django.contrib.contenttypes.models import ContentType

#: Type de périmètre → objet métier qu'il peut borner (labels ContentType).
#: Sert à la validation de la console (``comptes_admin``) comme aux résolveurs.
TYPES_OBJETS = {
    'SECRETARIAT': ('formations', 'secretariat'),
    'SITE': ('formations', 'refsite'),
    'DIRECTION': ('administrations', 'direction'),
    'DEPARTEMENT': ('administrations', 'departement'),
    'SERVICE': ('ressources_humaines', 'service'),
    'FORMATION': ('formations', 'refformation'),
    'PARCOURS': ('scolarite', 'parcours'),
    'NIVEAU': ('scolarite', 'niveau'),
    'GROUPE': ('scolarite', 'groupe'),
    'MODULE_ECUE': ('scolarite', 'ecue'),
    'ETUDIANT': ('scolarite', 'dossieretudiant'),
}

#: Étiquette « app_label.model » → type de périmètre qui sait la borner.
_TYPE_PAR_LABEL = {
    f'{app}.{model}': type_p
    for type_p, (app, model) in TYPES_OBJETS.items()
}
# Un module du vieux catalogue (formations.Module) est bornable comme ECUE.
_TYPE_PAR_LABEL['formations.module'] = 'MODULE_ECUE'
_TYPE_PAR_LABEL['scolarite.maquette'] = 'FORMATION'

#: Étiquette modèle → chemins d'attributs vers les porteurs de périmètre,
#: sous la forme ``(type_de_périmètre, 'champ__…__fk_id')``. Les chemins sont
#: parcourus tardivement ; un maillon manquant (None) est simplement ignoré.
ANCESTRES = {
    'administrations.departement': [
        ('DIRECTION', 'direction_id'),
    ],
    'ressources_humaines.service': [
        ('DEPARTEMENT', 'departement_id'),
        ('DIRECTION', 'departement__direction_id'),
    ],
    'scolarite.parcours': [
        ('FORMATION', 'ref_formation_id'),
    ],
    'scolarite.groupe': [
        ('PARCOURS', 'parcours_id'),
        ('FORMATION', 'ref_formation_id'),
        ('NIVEAU', 'niveau_id'),
        ('SITE', 'site_id'),
    ],
    'scolarite.maquette': [
        ('FORMATION', 'ref_formation_id'),
        ('PARCOURS', 'parcours_id'),
        ('NIVEAU', 'niveau_id'),
    ],
    'scolarite.semestre': [
        ('NIVEAU', 'niveau_id'),
    ],
    'scolarite.ecue': [
        ('FORMATION', 'ue__maquette__ref_formation_id'),
        ('PARCOURS', 'ue__maquette__parcours_id'),
        ('NIVEAU', 'ue__maquette__niveau_id'),
    ],
    'formations.module': [
        ('FORMATION', 'formation_id'),
        ('SECRETARIAT', 'secretariat_id'),
        ('SITE', 'site_id'),
    ],
    'scolarite.inscriptionadministrative': [
        ('ETUDIANT', 'etudiant_id'),
        ('FORMATION', 'ref_formation_id'),
        ('PARCOURS', 'parcours_id'),
        ('NIVEAU', 'niveau_id'),
    ],
    'scolarite.inscriptionpedagogique': [
        ('ETUDIANT', 'inscription__etudiant_id'),
        ('GROUPE', 'groupe_id'),
    ],
}

#: Types de périmètres sans objet borné (couverture triviale côté moteur).
_GLOBAUX = frozenset({'INJS_ENTIER', 'PROPRE_COMPTE'})


def etiquette(objet):
    """Étiquette ContentType ``app_label.model`` d'une instance modèle."""
    return f'{objet._meta.app_label}.{objet._meta.model_name}'


def _valeur_chemin(objet, chemin):
    """Suit un chemin ``a__b__c`` ; remplace la dernière partie si elle finit
    par ``_id`` ; renvoie ``None`` au premier maillon manquant."""
    valeur = objet
    for maillon in chemin.split('__'):
        if valeur is None:
            return None
        try:
            valeur = getattr(valeur, maillon)
        except Exception:  # objet intermédiaire incohérent → pas d'ancêtre
            return None
    return valeur


def cles_couvrantes(objet):
    """Ensemble ``{(type_de_périmètre, pk_en_str)}`` couvrant l'objet : sa
    propre borne exacte (si le modèle est bornable) puis ses ancêtres."""
    label = etiquette(objet)
    cles = set()
    type_p = _TYPE_PAR_LABEL.get(label)
    if type_p is not None:
        cles.add((type_p, str(objet.pk)))
    for anc_type, chemin in ANCESTRES.get(label, ()):
        valeur = _valeur_chemin(objet, chemin)
        if valeur is not None:
            cles.add((anc_type, str(valeur)))
    return cles


def couvert_par_ancetre(perimetre, cible):
    """Le périmètre couvre-t-il la cible (objet modèle) par rattachement ?

    Ne couvre jamais un périmètre global (traité en amont par le moteur) ni
    une cible sans ancêtre connu ; renvoie ``False`` dans ces cas — le
    comportement est strictement additif par rapport au rapprochement exact.
    """
    type_p = getattr(perimetre, 'type', None)
    if type_p is None or type_p in _GLOBAUX:
        return False
    borne = str(getattr(perimetre, 'object_id', '') or '')
    if not borne:
        return False
    return (type_p, borne) in cles_couvrantes(cible)


def _content_type_valide(perimetre, cible):
    ct = ContentType.objects.get_for_model(cible.__class__)
    return perimetre.content_type_id is not None \
        and perimetre.content_type_id == ct.pk


def couverture_standard(perimetre, cible):
    """Résolveur complet injectable via ``contexte={'couverture': …}``.

    Ordre : global → cible dict (contrat d'API, rapprochement exact) →
    objet modèle : rapprochement exact ``content_type``+pk, règle générique
    ``SECRETARIAT`` (la cible porte ``secretariat_id``), puis ancêtres.
    """
    if getattr(perimetre, 'type', None) in _GLOBAUX:
        return True
    if isinstance(cible, dict):
        return (
            perimetre.type == cible.get('type')
            and str(perimetre.object_id or '') == str(cible.get('object_id', ''))
        )
    try:
        if _content_type_valide(perimetre, cible) and \
                str(perimetre.object_id or '') == str(cible.pk):
            return True
    except Exception:
        pass
    if perimetre.type == 'SECRETARIAT':
        sid = getattr(cible, 'secretariat_id', None)
        if sid is not None and str(sid) == str(perimetre.object_id or ''):
            return True
    return couvert_par_ancetre(perimetre, cible)
