"""Registre central du module « Référentiels ».

Ce module est le point d'entrée unique : chaque référentiel y est déclaré une
seule fois, avec sa catégorie métier, son modèle, son API de lecture/écriture
et sa provenance. Le tableau de bord, la navigation et les écrans de gestion
sont générés à partir de ce registre — il n'existe donc aucune liste codée en
dur côté React.

Règles de conception :
* un référentiel = un modèle Django = une source de vérité (aucun doublon) ;
* les référentiels historiques (formations, modules, salles…) restent gérés par
  leurs écrans existants : ils sont déclarés ici en ``editable=False`` avec un
  renvoi vers leur écran, jamais recréés ;
* la provenance (source documentaire + fiabilité) est exposée partout où le
  modèle la porte.
"""

from .models import (
    RefEcole,
    RefFiliere,
    RefGradeEnseignant,
    RefMention,
    RefModePaiement,
    RefModuleOfficiel,
    RefStatutVague,
    RefTypeCursus,
    RefTypeDecision,
    RefTypeDocument,
    RefTypeEnseignement,
    RefTypeEspaceSportif,
    RefTypeEvaluation,
    RefTypeFrais,
    RefTypeNotification,
    RefVolumeHoraireFormation,
)


class Categorie:
    """Catégories fonctionnelles du module (mission §5)."""

    INSTITUTIONNEL = 'institutionnel'
    OFFRE_FORMATION = 'offre-formation'
    SYSTEME_LMD = 'systeme-lmd'
    PEDAGOGIQUE = 'pedagogique'
    RESSOURCES_HUMAINES = 'ressources-humaines'
    ORGANISATION = 'organisation'
    SCOLARITE = 'scolarite'


CATEGORIES = [
    {
        'cle': Categorie.INSTITUTIONNEL,
        'libelle': 'Référentiels institutionnels',
        'description': "Écoles, mentions et structures de rattachement de l'INJS.",
        'icone': 'bi-bank',
    },
    {
        'cle': Categorie.OFFRE_FORMATION,
        'libelle': "Offre de formation",
        'description': 'Filières officielles, natures de cursus et cycles diplômants.',
        'icone': 'bi-mortarboard',
    },
    {
        'cle': Categorie.SYSTEME_LMD,
        'libelle': 'Système LMD',
        'description': 'Niveaux, semestres, parcours, maquettes, UE et ECUE.',
        'icone': 'bi-diagram-3',
    },
    {
        'cle': Categorie.PEDAGOGIQUE,
        'libelle': 'Référentiels pédagogiques',
        'description': "Types d'enseignement, d'évaluation, décisions et espaces sportifs.",
        'icone': 'bi-journal-text',
    },
    {
        'cle': Categorie.RESSOURCES_HUMAINES,
        'libelle': 'Ressources humaines pédagogiques',
        'description': 'Grades et statuts des enseignants (distincts des rôles applicatifs).',
        'icone': 'bi-person-badge',
    },
    {
        'cle': Categorie.ORGANISATION,
        'libelle': 'Organisation pédagogique',
        'description': "Vagues de recrutement, sites, bâtiments et salles de formation.",
        'icone': 'bi-geo-alt',
    },
    {
        'cle': Categorie.SCOLARITE,
        'libelle': 'Administratif & scolarité',
        'description': 'Années académiques, frais, paiements, documents et notifications.',
        'icone': 'bi-folder2-open',
    },
]


def entree(**kwargs):
    """Déclare une entrée de registre avec des valeurs par défaut sûres."""
    kwargs.setdefault('editable', True)
    kwargs.setdefault('selecteurs', [])
    kwargs.setdefault('champs', [])
    kwargs.setdefault('modele', None)
    # Un référentiel éditable est géré par l'écran générique de la refonte ; le
    # défaut pointe donc vers lui. Les référentiels historisés (editable=False)
    # déclarent explicitement leur propre écran — ou `None` quand aucun écran
    # n'existe : le tableau de bord n'affiche alors aucun lien plutôt qu'un lien
    # vers une route qui n'existe pas.
    kwargs.setdefault('route_ui', f"/referentiels/gestion/{kwargs['slug']}")
    kwargs.setdefault('avertissement', '')
    # Adaptateurs pour modèles hors socle (scolarité) : nom réel du champ
    # d'intitulé et du champ de code. ``champ_code`` égal au champ d'intitulé
    # = pas de colonne code distincte (ex. Semestre : « S1 » fait les deux).
    kwargs.setdefault('champ_libelle', 'libelle')
    kwargs.setdefault('champ_code', 'code')
    # Libellé du bouton d'accès sur la carte du tableau de bord (défaut
    # front : « Gérer » si éditable, « Consulter » sinon).
    kwargs.setdefault('libelle_bouton', '')
    return kwargs


REGISTRE = {
    # ── Référentiels métier créés par la refonte (CRUD générique) ──────────
    'ecoles': entree(
        slug='ecoles',
        libelle='Écoles',
        description="Écoles supérieures de l'INJS : ENSEPS et ENSEP.",
        categorie=Categorie.INSTITUTIONNEL,
        modele=RefEcole,
        champs=['nom_complet'],
        icone='bi-bank',
        source='Formations et Modules INJS — §1',
    ),
    'mentions': entree(
        slug='mentions',
        libelle='Mentions',
        description='Mentions de rattachement : STAPS (ENSEPS) et STASE (ENSEP).',
        categorie=Categorie.INSTITUTIONNEL,
        modele=RefMention,
        champs=['nom_complet'],
        selecteurs=['ecole'],
        icone='bi-tag',
        source='Formations et Modules INJS — §1',
    ),
    'types-cursus': entree(
        slug='types-cursus',
        libelle='Natures de cursus',
        description=(
            'Sépare le cursus LMD des formations professionnelles, continues, '
            'à la carte et des préparations aux concours.'
        ),
        categorie=Categorie.OFFRE_FORMATION,
        modele=RefTypeCursus,
        icone='bi-signpost-split',
        source='Cadrage mission §5.B',
        avertissement=(
            'Le référentiel hérité scolarite.TypeFormation (LICENCE, MASTER, '
            'FORMATION_INITIALE, FORMATION_CONTINUE) mélange niveau de diplôme et '
            'modalité : il reste en place pour la compatibilité des API existantes '
            'et sa fusion est planifiée (anomalie A-53-01).'
        ),
    ),
    'filieres': entree(
        slug='filieres',
        libelle='Filières',
        description='Les huit filières officielles (4 ENSEPS, 4 ENSEP).',
        categorie=Categorie.OFFRE_FORMATION,
        modele=RefFiliere,
        champs=['code_dossier', 'ordre'],
        selecteurs=['ecole', 'mention', 'type_cursus'],
        icone='bi-collection',
        source='Formations et Modules INJS — §1',
    ),
    'types-enseignement': entree(
        slug='types-enseignement',
        libelle="Types d'enseignement",
        description='Nature des heures enseignées : CM, TD, TP et stage.',
        categorie=Categorie.PEDAGOGIQUE,
        modele=RefTypeEnseignement,
        champs=['abrege', 'est_stage'],
        icone='bi-easel',
        source='Modéliser les volumes horaires — §1',
    ),
    'statuts-vague': entree(
        slug='statuts-vague',
        libelle='Statuts de vague',
        description='Cycle de vie d’une vague de recrutement ou de formation.',
        categorie=Categorie.ORGANISATION,
        modele=RefStatutVague,
        champs=['est_ouvert'],
        icone='bi-signpost',
        source='Vagues INJS 2026',
    ),
    # ── Référentiels du socle déjà existants (API dédiée, CRUD générique) ──
    'types-evaluation': entree(
        slug='types-evaluation', libelle="Types d'évaluation",
        description='Examen, contrôle continu, rattrapage…',
        categorie=Categorie.PEDAGOGIQUE, modele=RefTypeEvaluation,
        route_api='/referentiels/types-evaluation/',
        icone='bi-clipboard-check',
        source='Refonte du Module Évaluations — nomenclature des types d’évaluation',
        avertissement=(
            'Nomenclature issue du cadrage du module Évaluations : les '
            'pondérations (contrôle continu / examen) restent paramétrées '
            'par ECUE et ne sont pas figées par ce référentiel.'
        ),
    ),
    'types-decision': entree(
        slug='types-decision', libelle='Types de décision',
        description='Décisions pédagogiques et de jury.',
        categorie=Categorie.PEDAGOGIQUE, modele=RefTypeDecision,
        route_api='/referentiels/types-decision/',
        icone='bi-hammer',
        source='Jurys de délibération INJS — décisions officielles (module Jurys)',
    ),
    'types-espace-sportif': entree(
        slug='types-espace-sportif', libelle="Types d'espace sportif",
        description='Gymnase, piscine, terrain, dojo…',
        categorie=Categorie.PEDAGOGIQUE, modele=RefTypeEspaceSportif,
        route_api='/referentiels/types-espace-sportif/',
        icone='bi-bounding-box',
        source="Liste des Bâtiments, salles et espaces de formation de l'INJS",
        avertissement=(
            'Catégories issues de l’inventaire des installations (source '
            'déclarée modélisée) : le rattachement de chaque salle à son '
            'type reste à opérer dans l’écran des salles, sans reclassement '
            'automatique.'
        ),
    ),
    'grades-enseignant': entree(
        slug='grades-enseignant', libelle='Grades enseignants',
        description="Grades et statuts des enseignants — à ne pas confondre avec les rôles applicatifs.",
        categorie=Categorie.RESSOURCES_HUMAINES, modele=RefGradeEnseignant,
        route_api='/referentiels/grades-enseignant/',
        icone='bi-award',
        source='GRADES ET STATUTS DES ENSEIGNANTS-INJS (PDF, 1er nov. 2026) — §2 et §3',
        avertissement=(
            'Un grade est une décision officielle (listes d’aptitude CAMES, '
            'arrêté de nomination dans un corps) : il ne se crée ni ne '
            's’attribue dans l’application, et ne doit jamais être confondu '
            'avec un rôle applicatif INJS-LMD, un statut d’exercice ou une '
            'fonction de direction. Échelons, indices et statuts particuliers '
            'restent à confirmer par la DRH de l’INJS.'
        ),
    ),
    'types-document': entree(
        slug='types-document', libelle='Types de document',
        description='Documents officiels et justificatifs.',
        categorie=Categorie.SCOLARITE, modele=RefTypeDocument,
        route_api='/referentiels/types-document/',
        icone='bi-file-earmark-text', source='Socle referentiels (lot L0/L7)',
    ),
    'types-frais': entree(
        slug='types-frais', libelle='Types de frais',
        description='Inscription, scolarité, examen, réinscription…',
        categorie=Categorie.SCOLARITE, modele=RefTypeFrais,
        route_api='/referentiels/types-frais/',
        icone='bi-cash-coin', source='Socle referentiels (lot L0/L7)',
    ),
    'modes-paiement': entree(
        slug='modes-paiement', libelle='Modes de paiement',
        description='Espèces, virement, mobile money…',
        categorie=Categorie.SCOLARITE, modele=RefModePaiement,
        route_api='/referentiels/modes-paiement/',
        icone='bi-credit-card', source='Socle referentiels (lot L0/L7)',
    ),
    'types-notification': entree(
        slug='types-notification', libelle='Types de notification',
        description='Alertes, rappels et validations du système.',
        categorie=Categorie.SCOLARITE, modele=RefTypeNotification,
        route_api='/referentiels/types-notification/',
        icone='bi-bell', source='Socle referentiels (lot L0/L7)',
    ),
    # ── Référentiels historiques : lecture seule ici, écran existant ───────
    'formations': entree(
        slug='formations', libelle='Formations (cycles)',
        description='Cycles diplômants du référentiel — Licence et Master.',
        categorie=Categorie.OFFRE_FORMATION,
        modele='formations.RefFormation',
        editable=False, route_api='/formations/ref/formations/',
        route_ui='/formations', icone='bi-mortarboard-fill',
        source='Formations et Modules INJS — §1',
    ),
    'niveaux': entree(
        slug='niveaux', libelle='Niveaux',
        description='L1 à D3 — 60 ECTS par niveau annuel (Licence, Master, Doctorat).',
        categorie=Categorie.SYSTEME_LMD, modele='scolarite.Niveau',
        champs=['cycle', 'ordre', 'credits_requis'],
        icone='bi-bar-chart-steps',
        source='Architecture LMD (30 ECTS/semestre)',
        avertissement=(
            'Structure LMD : chaque niveau porte 60 crédits ECTS et deux '
            'semestres. Modifier un niveau ouvert impacte les semestres et '
            'les maquettes qui s’appuient dessus.'
        ),
    ),
    'semestres': entree(
        slug='semestres', libelle='Semestres',
        description='S1 à S16 — 30 ECTS par semestre (S11–S16 : doctorat).',
        categorie=Categorie.SYSTEME_LMD, modele='scolarite.Semestre',
        champ_code='libelle',
        champs=['numero'],
        selecteurs=['niveau'],
        icone='bi-calendar3',
        source='Architecture LMD (30 ECTS/semestre)',
        avertissement=(
            'Le libellé du semestre (S1, S2…) fait aussi office de code. '
            'Le numéro global suit l’ordre du cursus (S1 = 1, S2 = 2…).'
        ),
    ),
    'parcours': entree(
        slug='parcours', libelle='Parcours',
        description='Spécialisations internes à un cycle (8 filières × Licence/Master).',
        categorie=Categorie.SYSTEME_LMD, modele='scolarite.Parcours',
        champ_libelle='intitule',
        selecteurs=['ref_formation', 'type_formation'],
        icone='bi-signpost-split',
        source='RÉFÉRENTIEL COMPLET DU SYSTÈME LMD (PDF) — §6',
    ),
    'types-formation': entree(
        slug='types-formation', libelle='Types de formation',
        description=(
            'Nature du cycle rattaché aux parcours (Licence, Master…). '
            'Référentiel hérité de la scolarité, distinct des natures de cursus.'
        ),
        categorie=Categorie.SYSTEME_LMD, modele='scolarite.TypeFormation',
        icone='bi-diagram-2',
        source='Scolarité (init_referentiels_lmd)',
    ),
    'ue-ecue': entree(
        slug='ue-ecue', libelle='UE / ECUE',
        description=(
            'Unités d’enseignement et éléments constitutifs des maquettes — '
            'gérés dans le module Maquettes LMD (cycle de vie par maquette).'
        ),
        categorie=Categorie.SYSTEME_LMD, modele='scolarite.UE',
        editable=False, route_ui='/scolarite/maquettes', icone='bi-layers',
        libelle_bouton='Gérer',
        source='Maquettes officielles INJS',
    ),
    'annees': entree(
        slug='annees', libelle='Années académiques',
        description='Périodes de référence de la scolarité.',
        categorie=Categorie.SCOLARITE, modele='scolarite.AnneeAcademique',
        editable=False, route_api='/scolarite/ref/annees/',
        route_ui=None, icone='bi-calendar-range',
    ),
    'sites': entree(
        slug='sites', libelle='Sites',
        description='Sites et centres de formation.',
        categorie=Categorie.ORGANISATION, modele='formations.RefSite',
        editable=False, route_api='/formations/ref/sites/',
        route_ui='/referentiels/edition', icone='bi-geo-alt-fill',
        source='Liste des bâtiments, salles et espaces',
    ),
    'batiments': entree(
        slug='batiments', libelle='Bâtiments',
        description='Bâtiments rattachés aux sites.',
        categorie=Categorie.ORGANISATION, modele='formations.RefBatiment',
        editable=False, route_api='/formations/ref/batiments/',
        route_ui='/referentiels/edition', icone='bi-building',
        source='Liste des bâtiments, salles et espaces',
    ),
    'salles': entree(
        slug='salles', libelle='Salles et espaces',
        description='Salles, amphithéâtres, gymnases et espaces sportifs.',
        categorie=Categorie.ORGANISATION, modele='formations.RefSalle',
        editable=False, route_api='/formations/ref/salles/',
        route_ui='/referentiels/edition', icone='bi-door-open',
        source='Liste des bâtiments, salles et espaces',
    ),
    'vagues': entree(
        slug='vagues', libelle='Vagues',
        description='Vagues de recrutement et de formation.',
        categorie=Categorie.ORGANISATION, modele='formations.RefVague',
        editable=False, route_api='/formations/ref/vagues/',
        route_ui='/referentiels/edition', icone='bi-layers-half',
        source='Vagues INJS 2026',
    ),
    'modules-officiels': entree(
        slug='modules-officiels', libelle='Modules officiels',
        description=(
            'Modules des maquettes INJS tels qu’ils figurent dans le document '
            'de formation, par filière et par semestre.'
        ),
        categorie=Categorie.OFFRE_FORMATION, modele=RefModuleOfficiel,
        editable=False, route_api='/referentiels/modules-officiels/',
        route_ui='/referentiels/gestion/modules-officiels', icone='bi-journal-text',
        source='Formations et Modules INJS',
    ),
    'volumes-modules': entree(
        slug='volumes-modules', libelle='Volumes horaires (modélisation)',
        description=(
            'Répartition CM/TD/TP/stage issue du document de cadrage. '
            'Valeurs de modélisation, jamais réglementaires.'
        ),
        categorie=Categorie.OFFRE_FORMATION, modele=RefVolumeHoraireFormation,
        editable=False, route_api='/referentiels/volumes-horaires/',
        route_ui='/referentiels/gestion/volumes-modules', icone='bi-clock-history',
        source='Modéliser les volumes horaires — avertissement de la source',
    ),
}


def entrees_par_categorie():
    """Retourne les catégories avec leurs entrées, dans l'ordre déclaré."""
    par_categorie = {c['cle']: [] for c in CATEGORIES}
    for slug, item in REGISTRE.items():
        par_categorie[item['categorie']].append(item)
    resultat = []
    for categorie in CATEGORIES:
        entrees = sorted(
            par_categorie[categorie['cle']], key=lambda e: (not e['editable'], e['libelle']),
        )
        resultat.append({**categorie, 'entrees': entrees})
    return resultat


def modele_de(entree_registre):
    """Résout le modèle Django d'une entrée (« app.Model » ou classe)."""
    modele = entree_registre['modele']
    if not isinstance(modele, str):
        return modele
    from django.apps import apps

    app_label, model_name = modele.split('.')
    return apps.get_model(app_label, model_name)
