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
        icone='bi-clipboard-check', source='Socle referentiels (lot L0/L7)',
    ),
    'types-decision': entree(
        slug='types-decision', libelle='Types de décision',
        description='Décisions pédagogiques et de jury.',
        categorie=Categorie.PEDAGOGIQUE, modele=RefTypeDecision,
        route_api='/referentiels/types-decision/',
        icone='bi-hammer', source='Socle referentiels (lot L0/L7)',
    ),
    'types-espace-sportif': entree(
        slug='types-espace-sportif', libelle="Types d'espace sportif",
        description='Gymnase, piscine, terrain, dojo…',
        categorie=Categorie.PEDAGOGIQUE, modele=RefTypeEspaceSportif,
        route_api='/referentiels/types-espace-sportif/',
        icone='bi-bounding-box', source='Socle referentiels (lot L0/L7)',
    ),
    'grades-enseignant': entree(
        slug='grades-enseignant', libelle='Grades enseignants',
        description="Grades et statuts des enseignants — à ne pas confondre avec les rôles applicatifs.",
        categorie=Categorie.RESSOURCES_HUMAINES, modele=RefGradeEnseignant,
        route_api='/referentiels/grades-enseignant/',
        icone='bi-award', source='Socle referentiels (lot L0/L7)',
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
        description='L1 à M2 — 60 ECTS par niveau annuel.',
        categorie=Categorie.SYSTEME_LMD, modele='scolarite.Niveau',
        editable=False, route_api='/scolarite/ref/niveaux/',
        route_ui=None, icone='bi-bar-chart-steps',
        source='Architecture LMD (30 ECTS/semestre)',
    ),
    'semestres': entree(
        slug='semestres', libelle='Semestres',
        description='S1 à S10 — 30 ECTS par semestre.',
        categorie=Categorie.SYSTEME_LMD, modele='scolarite.Semestre',
        editable=False, route_api='/scolarite/ref/semestres/',
        route_ui=None, icone='bi-calendar3',
        source='Architecture LMD (30 ECTS/semestre)',
    ),
    'parcours': entree(
        slug='parcours', libelle='Parcours',
        description='Spécialisations internes à un cycle.',
        categorie=Categorie.SYSTEME_LMD, modele='scolarite.Parcours',
        editable=False, route_api='/scolarite/ref/parcours/',
        route_ui=None, icone='bi-signpost-split',
    ),
    'ue-ecue': entree(
        slug='ue-ecue', libelle='UE / ECUE',
        description='Unités d’enseignement et éléments constitutifs des maquettes.',
        categorie=Categorie.SYSTEME_LMD, modele='scolarite.UE',
        editable=False, route_ui=None, icone='bi-layers',
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
