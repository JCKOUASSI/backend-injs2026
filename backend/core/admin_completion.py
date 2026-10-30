"""Complète l'administration Django pour les modèles métier non inscrits.

Constat d'audit : sur 178 modèles projet, 41 n'étaient pas inscrits dans
l'administration. Certains sont légitimement techniques (historiques,
notifications, synthèses calculées), mais d'autres portent des objets que
l'application gère réellement à l'écran (campagnes d'admission, épreuves,
sessions de jury, affectations pédagogiques, organigramme, demandes d'accès…).
Un administrateur ne pouvait donc pas les corriger depuis l'admin, alors qu'il
le peut depuis le site : deux sources de vérité incohérentes.

Ce module inscrit ces modèles **de façon centralisée et homogène** plutôt que
par 41 classes dispersées :

* les modèles **opérationnels** sont éditables (liste, recherche, filtres,
  `select_related` sur les clés étrangères affichées) ;
* les modèles **techniques** (historiques, notifications, valeurs calculées)
  sont inscrits en **lecture seule** : consultables pour le diagnostic, jamais
  modifiables — une synthèse recalculée ne doit pas être éditée à la main.

Aucun modèle existant n'est modifié ni remplacé : seuls les modèles encore
non inscrits sont pris en charge.
"""

from django.contrib import admin
from django.db import models

# ── Modèles opérationnels : gérables depuis l'administration ─────────────────
OPERATIONNELS = (
    'admissions.CampagneAdmission',
    'admissions.Epreuve',
    'admissions.ConvocationEpreuve',
    'admissions.PieceCandidature',
    'admissions.SurveillanceEpreuve',
    'admissions.NoteConcours',
    'admissions.ClassementConcours',
    'jurys.SessionJury',
    'jurys.MembreJury',
    'jurys.PropositionJury',
    'jurys.DecisionJury',
    'jurys.PVJury',
    'scolarite.AffectationPedagogique',
    'scolarite.IndisponibiliteEnseignant',
    'edts.DisponibiliteHoraire',
    'administrations.Direction',
    'administrations.Departement',
    'habilitations.DemandeAcces',
    'graduation.Reedition',
)

# ── Modèles techniques : consultation seule ─────────────────────────────────
LECTURE_SEULE = (
    'formations.FinanceAjustement',
    'formations.NoteModule',
    'formations.NoteModuleColonne',
    'formations.NoteModuleSynthese',
    'formations.CorrectionNoteModule',
    'formations.NotificationModificationNote',
    'formations.NotificationFinanceAjustement',
    'presences.NotificationAbsence',
    'statistiques.ObservationQualitative',
    'statistiques.SignatureRapport',
    'suiviEvaluation.ChoixQuestion',
    'suiviEvaluation.ReponseQuestion',
    'suiviEvaluation.ParametresEvaluation',
    'suiviEvaluation.MoyenneModule',
    'suiviEvaluation.DecisionPedagogique',
    'evaluations.RegleCalculVersion',
    'evaluations.EpreuveSurveillant',
    'scolarite.RegleValidationLMD',
    'scolarite.MaquetteJournal',
    'admissions.NoteConcoursHistorique',
    'jurys.NotificationJury',
    'habilitations.RoleVersion',
    # Objets produits par le moteur GET-INJS : les campagnes et leurs exécutions
    # sont des traces d'exécution, jamais saisies à la main. Elles doivent être
    # consultables (bilan, anomalies, auteur, durée) mais pas éditables, sans
    # quoi on pourrait réécrire l'historique d'une génération.
    'edts.CampagneGeneration',
    'edts.ExecutionCampagne',
)

# Champs jamais affichés en liste (volumineux ou techniques).
CHAMPS_EXCLUS = {'id', 'created_at', 'updated_at', 'password', 'fichier',
                 'document_pdf', 'pdf_fichier', 'modele_pdf', 'preuve'}


def _champs_affiches(modele, limite=6):
    """Colonnes lisibles : champs simples + clés étrangères."""
    colonnes = []
    for champ in modele._meta.fields:
        if champ.name in CHAMPS_EXCLUS or champ.name.endswith('_id'):
            continue
        if champ.name in ('created_at', 'updated_at'):
            continue
        colonnes.append(champ.name)
        if len(colonnes) >= limite:
            break
    return tuple(colonnes) or ('__str__',)


def _cles_etrangeres(modele, colonnes):
    noms = []
    for nom in colonnes:
        try:
            champ = modele._meta.get_field(nom)
        except Exception:
            continue
        # `is_relation` est vrai aussi pour les relations génériques, qui ne
        # sont pas des colonnes et que `select_related` refuse (FieldError).
        if isinstance(champ, models.ForeignKey) and champ.concrete:
            noms.append(nom)
    return tuple(noms)


def _recherche(modele):
    return tuple(
        champ.name for champ in modele._meta.fields
        if isinstance(champ, (models.CharField, models.TextField))
        and champ.name not in CHAMPS_EXCLUS
        and not champ.name.endswith('_id')
    )[:6]


def _fabriquer(modele, lecture_seule):
    colonnes = _champs_affiches(modele)
    attributs = {
        'list_display': colonnes,
        'list_per_page': 50,
        'search_fields': _recherche(modele),
        'list_filter': _filtres_surs(modele),
        'list_select_related': _relations_etendues(modele, colonnes),
        'show_full_result_count': False,
    }
    for champ in modele._meta.fields:
        if isinstance(champ, (models.DateField, models.DateTimeField)) \
                and champ.name not in CHAMPS_EXCLUS:
            attributs['date_hierarchy'] = champ.name
            break
    if lecture_seule:
        attributs.update({
            'has_add_permission': lambda self, request: False,
            'has_change_permission': lambda self, request: False,
            'has_delete_permission': lambda self, request: False,
        })
        attributs['list_display_links'] = None
    nom = f'{modele.__name__}AdminAuto'
    return type(nom, (admin.ModelAdmin,), attributs)


def _relations_etendues(modele, colonnes, limite=20):
    """Relations à précharger, y compris celles parcourues par `__str__`.

    Une liste d'administration affiche `str(objet)` pour chaque clé étrangère.
    Si ce `__str__` remonte lui-même une relation (`inscription.etudiant`), un
    simple `select_related('inscription')` laisse une requête par ligne : c'est
    ce qui coûtait 190 requêtes à la liste des inscriptions pédagogiques.

    Les clés étrangères **directement affichées** passent en premier ; le budget
    restant sert à descendre d'un niveau, sinon la première relation consomme
    tout et les colonnes suivantes restent en N+1.
    """
    directes = _cles_etrangeres(modele, colonnes)
    relations = list(directes)

    niveau2 = []
    for nom in directes:
        cible = modele._meta.get_field(nom).related_model
        for champ in cible._meta.fields:
            if not (isinstance(champ, models.ForeignKey) and champ.concrete):
                continue
            if champ.remote_field.model is cible:
                continue  # auto-référence : cycle inutile
            niveau2.append(f'{nom}__{champ.name}')

    for chemin in niveau2:
        if len(relations) >= limite:
            break
        relations.append(chemin)

    # Troisième niveau, sous la **première** relation seulement : c'est
    # généralement l'objet parent (`inscription`, `candidature`…) dont le
    # `__str__` remonte encore un niveau (`inscription.etudiant.matricule`).
    if directes:
        premier = modele._meta.get_field(directes[0]).related_model
        for chemin in list(relations):
            if len(relations) >= limite:
                break
            if not chemin.startswith(f'{directes[0]}__'):
                continue
            cible = premier
            for morceau in chemin.split('__')[1:]:
                cible = cible._meta.get_field(morceau).related_model
            for champ in cible._meta.fields:
                if len(relations) >= limite:
                    break
                if not (isinstance(champ, models.ForeignKey) and champ.concrete):
                    continue
                if champ.remote_field.model is cible:
                    continue
                relations.append(f'{chemin}__{champ.name}')
    return tuple(dict.fromkeys(relations))


def _recherche_enrichie(modele):
    """Colonnes de recherche, y compris via une relation si le modèle en manque.

    Un modèle sans aucune colonne texte (ex. `NoteConcours`) reste trouvable :
    on cherche dans le premier champ texte de la relation affichée.
    """
    colonnes = _recherche(modele)
    if colonnes:
        return colonnes
    for champ in modele._meta.fields:
        if isinstance(champ, models.ForeignKey) and champ.concrete:
            cibles = _recherche(champ.related_model)
            if cibles:
                return (f'{champ.name}__{cibles[0]}',)
    return ()


def _filtres_surs(modele):
    """Filtres à cardinalité bornée seulement.

    Un filtre sur une clé étrangère non bornée oblige l'administration à
    charger toute la table liée : acceptable sur nos modèles ajoutés
    automatiquement (volumes connus), pas sur une liste préexistante dont on
    ignore le volume. On se limite donc aux choix énumérés et aux booléens.
    """
    noms = []
    for champ in modele._meta.fields:
        if champ.name in CHAMPS_EXCLUS:
            continue
        if isinstance(champ, models.BooleanField) or champ.choices:
            noms.append(champ.name)
    return tuple(noms[:5])


def enrichir_listes():
    """Donne recherche et filtres aux listes qui n'en ont pas.

    Constat d'audit : 53 listes sans `search_fields` (impossible de retrouver un
    enregistrement, il faut paginer) et 19 sans `list_filter`. Aucun champ
    existant n'est retiré : on ne complète que les listes vides.
    """
    completees = 0
    for modele, classe in list(admin.site._registry.items()):
        modifie = False
        if not classe.search_fields:
            champs = _recherche_enrichie(modele)
            if champs:
                classe.search_fields = champs
                modifie = True
        if not classe.list_filter:
            filtres = _filtres_surs(modele)
            if filtres:
                classe.list_filter = filtres
                modifie = True
        completees += modifie
    return completees


def optimiser_listes():
    """Précharge les clés étrangères affichées dans les listes existantes.

    Constat d'audit : 50 listes d'administration exposaient une clé étrangère
    (`étudiant`, `candidat`, `annee_academique`…) sans `select_related`. Django
    exécute alors **une requête par ligne** pour l'afficher : sur une liste de
    100 lignes, 101 requêtes au lieu de 1. Le correctif est appliqué ici, une
    seule fois, plutôt que dans 50 classes dispersées.

    On ne précharge que les relations réellement affichées : un `select_related`
    sans argument suivrait toute la chaîne et alourdirait la requête.
    """
    optimisees = 0
    for modele, classe in list(admin.site._registry.items()):
        if classe.list_select_related:
            continue  # choix explicite de l'auteur : ne pas écraser
        try:
            colonnes = tuple(classe.list_display or ())
        except Exception:
            continue
        relations = _relations_etendues(modele, colonnes)
        if not relations:
            continue
        classe.list_select_related = relations
        optimisees += 1
    return optimisees


def completer_administration():
    """Inscrit les modèles métier encore absents de l'administration."""
    from django.apps import apps

    inscrits = 0
    for reference, lecture_seule in (
        *((r, False) for r in OPERATIONNELS),
        *((r, True) for r in LECTURE_SEULE),
    ):
        try:
            modele = apps.get_model(reference)
        except LookupError:
            continue  # modèle retiré : rien à faire
        if modele is None or admin.site.is_registered(modele):
            continue
        admin.site.register(modele, _fabriquer(modele, lecture_seule))
        inscrits += 1
    return inscrits
