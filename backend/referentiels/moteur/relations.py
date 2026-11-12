"""Résolution des relations (clés étrangères) à l'import des référentiels.

Mission « Référentiels » — exigence prioritaire « Résolution des clés
étrangères ».

Un tableur ne connaît pas les identifiants numériques : une colonne « École »
contient « ENSEPS », pas « 3 ». Le moteur doit donc **résoudre** chaque
référence, et le faire sans jamais deviner.

Principes appliqués :

* **identifier** les clés étrangères par introspection du modèle ;
* **résoudre** une référence par son identifiant **ou** par tout champ métier
  pertinent (code, libellé, nom, intitulé, sigle, numéro…) ;
* **détecter les références inexistantes** (aucune correspondance → erreur) ;
* **détecter les références ambiguës** (plusieurs correspondances
  **distinctes** → erreur, jamais un choix arbitraire) ;
* **empêcher les associations incorrectes** : une valeur ambiguë n'est jamais
  rattachée au premier résultat venu ;
* **lever l'ambiguïté** uniquement quand le fichier fournit lui-même de quoi
  le faire (clé composite issue d'un ``unique_together``, ou champ de
  rattachement déclaré au registre — ex. un nom de bâtiment unique *par site*) ;
* **produire un rapport détaillé** : ligne, colonne, valeur, raison ;
* **respecter les contraintes d'unicité** du modèle lié ;
* **garantir l'intégrité transactionnelle** : la résolution a lieu avant
  l'écriture, et l'écriture reste atomique (cf. :mod:`importations`).

Aucune correspondance n'est inventée : en cas de doute, la ligne est
signalée et n'est pas importée.
"""

from django.db import models

# Noms de champs acceptés comme « clé métier » d'un modèle lié, par ordre de
# préférence. Seuls les champs réellement présents sur le modèle sont retenus.
CLES_METIER_CANDIDATES = (
    'code', 'libelle', 'nom', 'intitule', 'sigle', 'abrege',
    'numero', 'annee', 'denomination', 'nom_complet', 'matricule',
)

# Champs techniques jamais utilisés pour retrouver une référence.
CHAMPS_EXCLUS = frozenset({
    'id', 'pk', 'cree_le', 'modifie_le', 'created_at', 'updated_at',
    'description', 'source_document', 'fiabilite',
})


def cles_etrangeres(modele):
    """Clés étrangères directes d'un modèle (hors auto-référence en lecture)."""
    resultat = []
    for field in modele._meta.concrete_fields:
        if not isinstance(field, models.ForeignKey):
            continue
        if field.name in CHAMPS_EXCLUS:
            continue
        resultat.append(field)
    return resultat


def cles_metier(modele_lie):
    """Champs métier utilisables pour retrouver une valeur du modèle lié.

    Sont retenus les champs texte courts présents sur le modèle, en
    commençant par les plus identifiants (code, libellé…).
    """
    noms = {f.name for f in modele_lie._meta.concrete_fields}
    retenus = [n for n in CLES_METIER_CANDIDATES if n in noms]
    if not retenus:
        # Repli : tout champ texte court hors exclusion.
        retenus = [
            f.name for f in modele_lie._meta.concrete_fields
            if isinstance(f, (models.CharField, models.TextField))
            and f.name not in CHAMPS_EXCLUS
            and not f.choices
        ]
    return retenus


def groupes_uniques(modele_lie):
    """Groupes de champs formant une contrainte d'unicité (composite incluse)."""
    groupes = []
    for contrainte in modele_lie._meta.total_unique_constraints:
        champs = tuple(contrainte.fields)
        if champs:
            groupes.append(champs)
    if not groupes:
        # Un champ marqué unique=True forme un groupe d'un seul élément.
        for field in modele_lie._meta.concrete_fields:
            if getattr(field, 'unique', False):
                groupes.append((field.name,))
    return groupes


def normaliser(valeur):
    """Comparaison insensible à la casse, aux accents et aux espaces."""
    texte = ('' if valeur is None else str(valeur)).strip().lower()
    remplacement = {
        'é': 'e', 'è': 'e', 'ê': 'e', 'ë': 'e',
        'à': 'a', 'â': 'a', 'ä': 'a',
        'î': 'i', 'ï': 'i',
        'ô': 'o', 'ö': 'o',
        'ù': 'u', 'û': 'u', 'ü': 'u',
        'ç': 'c',
    }
    texte = ''.join(remplacement.get(c, c) for c in texte)
    return ' '.join(texte.replace('_', ' ').split())


class Resolution:
    """Résultat de la résolution d'une valeur vers une référence liée."""

    __slots__ = ('valeur', 'objet', 'erreur', 'candidats')

    def __init__(self, valeur, objet=None, erreur=None, candidats=()):
        self.valeur = valeur
        self.objet = objet
        self.erreur = erreur
        self.candidats = list(candidats)

    @property
    def ok(self):
        return self.objet is not None and self.erreur is None

    def __repr__(self):  # pragma: no cover — aide au débogage
        return f'<Resolution {self.valeur!r} -> {self.objet or self.erreur!r}>'


class ResolveurRelations:
    """Résout les clés étrangères d'un modèle à partir de valeurs de tableur.

    Les correspondances sont mises en cache par (champ, valeur normalisée) :
    un fichier de 5 000 lignes ne déclenche pas 5 000 requêtes.
    """

    def __init__(self, modele, queryset_lie=None, rattachement=None):
        """
        :param modele: modèle cible de l'import.
        :param queryset_lie: queryset de travail (restreint aux permissions).
        :param rattachement: ``{champ_fk: champ_de_rattachement}`` issu du
            registre (``unicite_par``) pour lever une ambiguïté légitime.
        """
        self.modele = modele
        self.queryset_lie = queryset_lie
        self.rattachement = rattachement or {}
        self._cache = {}
        self._index = {}
        self._cles_par_champ = {
            field.name: cles_metier(field.related_model)
            for field in cles_etrangeres(modele)
            if field.related_model is not None
        }
        self._groupes_uniques = {
            field.name: groupes_uniques(field.related_model)
            for field in cles_etrangeres(modele)
            if field.related_model is not None
        }

    def champs_lies(self):
        """Noms des champs de clé étrangère résolvable."""
        return sorted(self._cles_par_champ)

    def relations_attendues(self):
        """Clés étrangères du référentiel et la façon de les retrouver.

        Exposé à l'interface pour qu'elle indique à l'utilisateur quelles
        colonnes de rattachement sont attendues (identifiant **ou** libellé),
        au lieu de le laisser deviner. Une seule source de vérité : le
        validateur et l'interface lisent la même description.
        """
        champs = {f.name: f for f in cles_etrangeres(self.modele)}
        return [
            {
                'cle': nom,
                'libelle': str(champs[nom].verbose_name).capitalize(),
                'modele_lie': '{}.{}'.format(
                    champs[nom].related_model._meta.app_label,
                    champs[nom].related_model._meta.model_name,
                ),
                'libelle_lie': str(champs[nom].related_model._meta.verbose_name),
                'cles_metier': self._cles_par_champ.get(nom, []),
                'obligatoire': not (champs[nom].null or champs[nom].blank),
            }
            for nom in self.champs_lies()
        ]

    def _queryset(self, field):
        modele_lie = field.related_model
        qs = self.queryset_lie if self.queryset_lie is not None else None
        if qs is not None and qs.model is modele_lie:
            return qs
        if qs is not None and qs.model is self.modele:
            return None
        return modele_lie._default_manager.all()

    def _construire_index(self, field):
        """Indexe une fois le modèle lié par identifiant et par clés métier."""
        if field.name in self._index:
            return self._index[field.name]

        qs = self._queryset(field)
        if qs is None:
            # Repli : gestionnaire par défaut du modèle lié.
            qs = field.related_model._default_manager.all()

        index = {}
        for objet in qs.iterator() if hasattr(qs, 'iterator') else qs:
            valeurs = {normaliser(objet.pk): objet}
            for cle in self._cles_par_champ.get(field.name, ()):
                valeur = getattr(objet, cle, None)
                if valeur in (None, ''):
                    continue
                valeurs.setdefault(normaliser(valeur), objet)
            for norme, objet_trouve in valeurs.items():
                # Détection d'ambiguïté : deux objets distincts, même clé.
                if norme in index and index[norme] is not objet_trouve:
                    index[norme] = AMBIGU
                else:
                    index.setdefault(norme, objet_trouve)
        self._index[field.name] = index
        return index

    def resoudre(self, nom_champ, valeur_brute, contexte=None):
        """Résout ``valeur_brute`` pour le champ ``nom_champ``.

        :returns: une :class:`Resolution`. En cas d'ambiguïté, ``erreur``
            mentionne les candidats : aucune association n'est proposée.
        """
        if valeur_brute is None or str(valeur_brute).strip() == '':
            return Resolution(valeur_brute, objet=None, erreur=None)

        # La clé de cache intègre le contexte : deux lignes du même fichier
        # peuvent viser deux valeurs homonymes départagées par leur
        # rattachement (un « Bâtiment A » par site, par exemple).
        cle_cache = (nom_champ, normaliser(valeur_brute), self._signature_contexte(contexte))
        if cle_cache in self._cache:
            return self._cache[cle_cache]

        field = self._champ(nom_champ)
        if field is None:
            resultat = Resolution(valeur_brute, erreur='Champ inconnu.')
            self._cache[cle_cache] = resultat
            return resultat

        index = self._construire_index(field)
        norme = normaliser(valeur_brute)
        trouve = index.get(norme)

        if trouve is AMBIGU:
            # Le fichier fournit-il de quoi lever l'ambiguïté ?
            leve = self._lever_ambiguite(field, valeur_brute, contexte)
            if leve is not None:
                resultat = Resolution(valeur_brute, objet=leve)
            else:
                resultat = Resolution(
                    valeur_brute,
                    erreur=(
                        f'Référence ambiguë : « {valeur_brute} » correspond à '
                        f'plusieurs valeurs de {field.related_model._meta.verbose_name}. '
                        'Précisez la référence (identifiant ou combinaison de colonnes).'
                    ),
                )
        elif trouve is None:
            resultat = Resolution(
                valeur_brute,
                erreur=(
                    f'Référence inexistante : aucune valeur de '
                    f'{field.related_model._meta.verbose_name} ne correspond à '
                    f'« {valeur_brute} ». Créez-la avant d’importer.'
                ),
            )
        else:
            resultat = Resolution(valeur_brute, objet=trouve)

        self._cache[cle_cache] = resultat
        return resultat

    def _signature_contexte(self, contexte):
        """Empreinte du contexte servant à lever une ambiguïté (chaîne stable)."""
        if not contexte:
            return ''
        champs = sorted(set(self.rattachement.values()))
        if not champs:
            return ''
        return '|'.join(
            f'{nom}={normaliser(contexte.get(nom))}' for nom in champs if nom in contexte
        )

    def _champ(self, nom_champ):
        for field in cles_etrangeres(self.modele):
            if field.name == nom_champ:
                return field
        return None

    def _lever_ambiguite(self, field, valeur_brute, contexte):
        """Lève une ambiguïté **uniquement** si le fichier en donne les moyens.

        Deux moyens acceptés :
        * une clé composite déclarée unique sur le modèle lié, dont le fichier
          fournit toutes les colonnes ;
        * un champ de rattachement (``unicite_par``) fourni dans le contexte.
        """
        if not contexte:
            return None

        # 1. Clé composite (unique_together) entièrement renseignée.
        for groupe in self._groupes_uniques.get(field.name, ()):
            if len(groupe) < 2:
                continue
            valeurs = [contexte.get(nom) for nom in groupe]
            if any(v in (None, '') for v in valeurs):
                continue
            filtres = {nom: valeur for nom, valeur in zip(groupe, valeurs)}
            qs = self._queryset(field) or field.related_model._default_manager.all()
            candidats = list(qs.filter(**filtres)[:2])
            if len(candidats) == 1:
                return candidats[0]

        # 2. Rattachement déclaré au registre (unicité « par » un parent).
        rattache = self.rattachement.get(field.name)
        if rattache and contexte.get(rattache) not in (None, ''):
            qs = self._queryset(field) or field.related_model._default_manager.all()
            filtres = {rattache: contexte[rattache]}
            for cle in self._cles_par_champ.get(field.name, ()):
                candidats = list(qs.filter(**{**filtres, cle: valeur_brute})[:2])
                if len(candidats) == 1:
                    return candidats[0]
        return None


class _Ambigu:
    """Marqueur interne : plusieurs objets distincts partagent la même clé."""

    def __repr__(self):  # pragma: no cover
        return '<AMBIGU>'


AMBIGU = _Ambigu()
