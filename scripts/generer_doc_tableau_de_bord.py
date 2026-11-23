#!/usr/bin/env python3
"""Documentation exhaustive du sous-module « Tableau de bord » des référentiels.

Le classeur est **généré depuis le code et la base** : le catalogue des
référentiels, les compteurs et la synthèse sont recalculés au moment de la
génération avec exactement la même logique que l'API
`/referentiels/tableau-de-bord/` (registre backend + comptages par modèle)
— la documentation ne peut donc pas diverger de l'écran qu'elle décrit.
Les chapitres de cadrage (anatomie, API, registre, scénarios) décrivent le
comportement réel des fichiers `TableauDeBordReferentiels.jsx`,
`referentiels/views.py`, `referentiels/registre.py` et
`referentiels/permissions.py`.

Usage (depuis la racine du dépôt) :

    backend/.venv/bin/python scripts/generer_doc_tableau_de_bord.py
    backend/.venv/bin/python scripts/generer_doc_tableau_de_bord.py --sortie /tmp/doc.xlsx

Le .xlsx produit est ignoré par Git (règle « classeurs ») : ce script
versionné est la source durable, le classeur se régénère.
"""

import argparse
import os
import subprocess
import sys
from datetime import date
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
BACKEND = RACINE / 'backend'
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(RACINE))
os.environ.setdefault('USE_SQLITE', '1')
os.environ.setdefault(
    'DJANGO_SETTINGS_MODULE',
    'arena.settings_sandbox' if (RACINE / 'arena' / 'settings_sandbox.py').exists()
    else 'config.settings',
)

import django  # noqa: E402

django.setup()

from referentiels.registre import CATEGORIES, REGISTRE, entrees_par_categorie, modele_de  # noqa: E402

from openpyxl import Workbook  # noqa: E402
from openpyxl.styles import Alignment, Font, PatternFill  # noqa: E402
from openpyxl.utils import get_column_letter  # noqa: E402

BLEU = '1F3864'
GRIS_LIGNE = 'F2F6FC'
ORANGE_RESERVE = 'FFF2CC'
VERT_OK = 'E2EFDA'
ROUGE_ALERTE = 'FCE4EC'

AUJOURD_HUI = date.today().strftime('%d/%m/%Y')


def _a_le_champ(modele, nom):
    return any(f.name == nom for f in modele._meta.concrete_fields)


def instantane():
    """Recalcule l'état du tableau de bord comme l'API (même logique)."""
    categories = []
    total_valeurs = total_a_renseigner = total_sans_source = 0
    total_avec_provenance = 0
    for categorie in entrees_par_categorie():
        lignes = []
        for entree in categorie['entrees']:
            modele = modele_de(entree)
            qs = modele._default_manager.all()
            total = qs.count()
            actifs = qs.filter(actif=True).count() if _a_le_champ(modele, 'actif') else total
            archives = qs.filter(archive=True).count() if _a_le_champ(modele, 'archive') else 0
            a_renseigner = sans_source = None
            if _a_le_champ(modele, 'fiabilite'):
                a_renseigner = qs.filter(fiabilite='A_RENSEIGNER').count()
                total_a_renseigner += a_renseigner
            if _a_le_champ(modele, 'source_document'):
                sans_source = qs.filter(source_document='').count()
                total_sans_source += sans_source
                total_avec_provenance += total
            total_valeurs += total
            lignes.append({
                **entree,
                'modele': f'{modele._meta.app_label}.{modele.__name__}',
                'total': total, 'actifs': actifs, 'archives': archives,
                'a_renseigner': a_renseigner, 'sans_source': sans_source,
                'provenance_suivie': _a_le_champ(modele, 'source_document'),
                'archivage_supporte': _a_le_champ(modele, 'archive'),
                'a_un_code': (
                    _a_le_champ(modele, entree.get('champ_code', 'code'))
                    and entree.get('champ_code', 'code') != entree.get('champ_libelle', 'libelle')
                ),
                'a_une_description': _a_le_champ(modele, 'description'),
                'route_api': entree.get('route_api') or f"/referentiels/{entree['slug']}/",
            })
        categories.append({**categorie, 'entrees': lignes})
    synthese = {
        'nb_referentiels': len(REGISTRE),
        'nb_referentiels_editables': sum(1 for e in REGISTRE.values() if e['editable']),
        'nb_valeurs': total_valeurs,
        'nb_a_renseigner': total_a_renseigner,
        'nb_sans_source': total_sans_source,
        'nb_valeurs_tracees': total_avec_provenance,
        'taux_tracabilite': (
            round((total_avec_provenance - total_sans_source) / total_avec_provenance, 4)
            if total_avec_provenance else None
        ),
    }
    return categories, synthese


def etat_affiche(e):
    """Même table de décision que `etatCompletude` côté frontend."""
    if e['total'] == 0:
        return 'Non renseigné'
    if e['a_renseigner'] is None:
        return 'Provenance non suivie'
    if e['a_renseigner'] == 0:
        return 'Complet'
    return f"{e['a_renseigner']} à renseigner"


def action_affichee(e):
    if e['editable']:
        return (e.get('libelle_bouton') or 'Gérer'), f"/referentiels/gestion/{e['slug']}"
    if e.get('route_ui'):
        return (e.get('libelle_bouton') or 'Consulter'), e['route_ui']
    return 'Sans écran dédié', '—'


# ── Style (même charte que les autres classeurs du dépôt) ───────────────────
def _titre(ws, texte, sous_titre, nb_col):
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=nb_col)
    c = ws.cell(row=1, column=1, value=texte)
    c.font = Font(size=14, bold=True, color=BLEU)
    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=nb_col)
    c = ws.cell(row=2, column=1, value=sous_titre)
    c.font = Font(size=10, italic=True, color='595959')
    c.alignment = Alignment(wrap_text=True, vertical='top')
    ws.row_dimensions[2].height = 34
    ws.sheet_properties.tabColor = BLEU


def _entetes(ws, ligne, colonnes):
    remplissage = PatternFill('solid', fgColor=BLEU)
    for j, nom in enumerate(colonnes, 1):
        c = ws.cell(row=ligne, column=j, value=nom)
        c.font = Font(bold=True, color='FFFFFF', size=10)
        c.fill = remplissage
        c.alignment = Alignment(wrap_text=True, vertical='center')
    ws.row_dimensions[ligne].height = 32


def _table(ws, colonnes, lignes, largeurs, ligne_debut=4, couleurs_etat=None):
    _entetes(ws, ligne_debut, colonnes)
    fond = PatternFill('solid', fgColor=GRIS_LIGNE)
    for i, valeurs in enumerate(lignes):
        for j, valeur in enumerate(valeurs, 1):
            c = ws.cell(row=ligne_debut + 1 + i, column=j, value=valeur)
            c.alignment = Alignment(wrap_text=True, vertical='top')
            c.font = Font(size=10)
            if i % 2 == 1:
                c.fill = fond
            if couleurs_etat and valeur in couleurs_etat:
                c.fill = PatternFill('solid', fgColor=couleurs_etat[valeur])
    for j, largeur in enumerate(largeurs, 1):
        ws.column_dimensions[get_column_letter(j)].width = largeur
    ws.freeze_panes = ws.cell(row=ligne_debut + 1, column=1).coordinate
    ws.auto_filter.ref = (
        f'A{ligne_debut}:{get_column_letter(len(colonnes))}{ligne_debut + len(lignes)}'
    )
    ws.sheet_properties.pageSetUpPr.fitToPage = True


def _prose(ws, blocs, largeur=118):
    """Blocs (rubrique, texte) présentés en deux colonnes lisibles."""
    _entetes(ws, 4, ['Rubrique', 'Contenu'])
    fond = PatternFill('solid', fgColor=GRIS_LIGNE)
    for i, (rubrique, texte) in enumerate(blocs):
        ligne = 5 + i
        c = ws.cell(row=ligne, column=1, value=rubrique)
        c.font = Font(size=10, bold=True, color=BLEU)
        c.alignment = Alignment(wrap_text=True, vertical='top')
        c = ws.cell(row=ligne, column=2, value=texte)
        c.font = Font(size=10)
        c.alignment = Alignment(wrap_text=True, vertical='top')
        if i % 2 == 1:
            ws.cell(row=ligne, column=1).fill = fond
            ws.cell(row=ligne, column=2).fill = fond
        ws.row_dimensions[ligne].height = max(30, 14 * (1 + len(texte) // 95))
    ws.column_dimensions['A'].width = 34
    ws.column_dimensions['B'].width = largeur
    ws.freeze_panes = 'A5'


# ── Feuilles ────────────────────────────────────────────────────────────────
def feuille_couverture(wb, synthese, commit):
    ws = wb.active
    ws.title = 'Couverture & sommaire'
    _titre(
        ws,
        'Module Référentiels — Sous-module « Tableau de bord »',
        "Documentation exhaustive de l'écran de cartographie des référentiels de "
        "l'application INJS-LMD (Institut National de la Jeunesse et des Sports, "
        f"Abidjan-Marcory). Généré le {AUJOURD_HUI} depuis le code et la base "
        f"(commit {commit}) : les compteurs de ce document sont ceux de l'écran au "
        "jour de génération.",
        3,
    )
    meta = [
        ('Application', 'INJS-LMD (GET-INJS) — gestion académique LMD de l’INJS d’Abidjan'),
        ('Module', 'Référentiels (source unique de vérité des données de référence)'),
        ('Sous-module documenté', 'Tableau de bord — route /referentiels, API GET /api/referentiels/tableau-de-bord/'),
        ('État au jour de génération',
         f"{synthese['nb_referentiels']} référentiels ({synthese['nb_referentiels_editables']} éditables), "
         f"{synthese['nb_valeurs']} valeurs, {synthese['nb_a_renseigner']} à renseigner, "
         f"{synthese['nb_sans_source']} sans source, taux de traçabilité "
         f"{(round(synthese['taux_tracabilite'] * 100) if synthese['taux_tracabilite'] is not None else '—')} %"),
        ('Fichiers de référence',
         'frontend/src/pages/referentiels/TableauDeBordReferentiels.jsx · '
         'backend/referentiels/views.py (TableauDeBordReferentielsView) · '
         'backend/referentiels/registre.py · backend/referentiels/permissions.py'),
        ('Régénération', 'backend/.venv/bin/python scripts/generer_doc_tableau_de_bord.py'),
    ]
    _table(ws, ['Repère', 'Valeur', ''], meta, [30, 110, 2])
    sommaire = [
        ('1. Présentation', 'Rôle du tableau de bord, place dans l’application, principes directeurs, publics.'),
        ('2. Accès & habilitations', 'Routes, authentification, permission ReferentielPermission et rôles d’édition.'),
        ("3. Anatomie de l'écran", 'Chaque zone de la page, ses comportements et ses états (chargement, erreur, vide).'),
        ('4. Indicateurs de synthèse', 'Les 7 compteurs globaux : définition, formule exacte, affichage, valeur du jour.'),
        ('5. La carte référentiel', 'Anatomie d’une plaquette, table de décision des badges d’état et des boutons d’action.'),
        ('6. Catalogue des 27 référentiels', 'Inventaire complet et chiffré des 27 plaquettes au jour de génération.'),
        ('7. Catégories', 'Les 7 familles du catalogue et leur rôle métier.'),
        ('8. Provenance & fiabilité', 'Les 4 degrés de fiabilité, la source documentaire et le taux de traçabilité.'),
        ('9. API tableau de bord', 'Contrat complet de l’endpoint : structure et dictionnaire des 31 clés d’une entrée.'),
        ('10. Registre (moteur)', 'Comment le registre pilote l’écran ; ajouter un référentiel pas à pas.'),
        ('11. Données & import', 'D’où viennent les valeurs : importeur idempotent, documents sources, contrôles.'),
        ("12. Scénarios d'usage", 'Parcours pas à pas des utilisateurs (consultation, gestion, audit, préparation d’année).'),
        ('13. Points ouverts & glossaire', 'Décisions en attente, réserves connues et définitions des termes.'),
    ]
    ligne = 6 + len(meta)
    ws.cell(row=ligne, column=1, value='Sommaire').font = Font(size=12, bold=True, color=BLEU)
    _table(ws, ['Feuille', 'Contenu', ''], sommaire, [30, 110, 2], ligne_debut=ligne + 1)


def feuille_presentation(wb):
    ws = wb.create_sheet('1. Présentation')
    _titre(ws, '1. Présentation du sous-module',
           "Ce qu'est le tableau de bord, à quoi il sert et sur quels principes il repose.", 2)
    _prose(ws, [
        ('Définition',
         "Le tableau de bord est l'écran d'accueil du module Référentiels. Il présente, "
         "sous forme de cartes regroupées en catégories, la cartographie complète des "
         "données de référence de l'INJS : un référentiel = une plaquette, avec son "
         "volume (nombre de valeurs), son état de complétude et le chemin vers son écran "
         "de gestion. C'est le point d'entrée unique pour consulter et administrer les "
         "nomenclatures qui alimentent tous les autres modules (scolarité, finances, "
         "présences, emplois du temps, diplômation…)."),
        ('« Source unique de vérité »',
         "La mention affichée en en-tête rappelle la règle fondatrice : une valeur "
         "(une filière, un type de frais, une année académique…) n'existe qu'à un seul "
         "endroit, dans le référentiel qui la porte. Les autres modules la référencent, "
         "ils ne la recopient jamais. Le tableau de bord est la vitrine de cette règle : "
         "si une donnée de référence doit changer, c'est ici que l'on vérifie où elle vit."),
        ('Piloté par le registre (aucune liste codée en dur)',
         "Ni l'écran (React) ni l'API ne contiennent la liste des référentiels : tout est "
         "généré depuis le registre backend (`referentiels/registre.py`), qui déclare pour "
         "chaque référentiel son modèle, sa catégorie, ses capacités et ses routes. Ajouter "
         "un référentiel côté serveur le fait apparaître immédiatement sur le tableau de "
         "bord, avec ses compteurs, sans toucher au frontend."),
        ('Complétude et provenance d’abord',
         "L'écran ne se contente pas de compter les valeurs : il dit si elles sont "
         "traçables (source documentaire + degré de fiabilité). Une carte peut donc être "
         "« Complète » en volume mais signaler des valeurs « à renseigner » : c'est la "
         "différence entre une donnée présente et une donnée opposable. Le taux de "
         "traçabilité global est l'indicateur de pilotage de cette exigence."),
        ('Jamais de suppression',
         "Conformément au processus de l'Institut, une valeur de référentiel ne se supprime "
         "pas : elle se désactive ou s'archive, pour que les dossiers qui l'utilisent "
         "(inscriptions, paiements, diplômes passés) restent interprétables. Le tableau de "
         "bord affiche le nombre de valeurs archivées sur chaque carte concernée."),
        ('Publics',
         "• Direction et pilotage : lecture de l'état de complétude et de la traçabilité.\n"
         "• Administration (scolarité, secrétariat, DAF, DFRC, DIEM) : accès aux écrans de "
         "gestion via le bouton « Gérer ».\n"
         "• Audit : consultation en lecture seule, contrôle des provenances et des journaux.\n"
         "• Tous les utilisateurs authentifiés peuvent consulter les référentiels, qui "
         "alimentent les écrans web et mobile (listes déroulantes, sélecteurs)."),
        ('Périmètre exact de ce sous-module',
         "Le tableau de bord est un écran de **cartographie et de navigation** : il ne modifie "
         "aucune donnée. Les modifications ont lieu dans les écrans de gestion "
         "(/referentiels/gestion/{slug}, écran générique) ou dans les écrans métier dédiés "
         "(maquettes, formations). Cette documentation décrit le tableau de bord et tout ce "
         "qu'il affiche ; les écrans de gestion sont évoqués comme destinations des cartes."),
    ])


def feuille_acces(wb):
    ws = wb.create_sheet('2. Accès & habilitations')
    _titre(ws, '2. Accès, navigation et habilitations',
           "Routes de l'écran et de ses destinations, authentification et règles de permission.", 2)
    _prose(ws, [
        ('Route de l’écran', '/referentiels — composant TableauDeBordReferentiels (menu « Référentiels »).'),
        ('Destination « Gérer »', '/referentiels/gestion/{slug} — écran générique de gestion du référentiel (création, modification, activation, archivage selon capacités du modèle, journal).'),
        ('Écran historique par onglets', '/referentiels/edition — édition des référentiels du module Formations (cycles, catégories, sites, bâtiments, salles, vagues…), conservé pour ses usages existants.'),
        ('Destination Maquettes', '/scolarite/maquettes — la carte UE/ECUE y renvoie (les UE/ECUE se gèrent dans leurs maquettes, pas comme une nomenclature plate).'),
        ('API du tableau de bord', 'GET /api/referentiels/tableau-de-bord/ — réponse JSON {categories, catalogue, synthese} (détail feuille 9).'),
        ('Authentification', 'JWT (Bearer). Sans jeton valide : 401. L’écran affiche alors le message d’erreur et le bouton « Réessayer ».'),
        ('Permission lecture', 'ReferentielPermission : tout utilisateur authentifié peut LIRE le tableau de bord et les référentiels (ils alimentent les écrans web et mobile).'),
        ('Permission écriture (destinations)',
         "Les écritures via l'écran générique exigent un rôle de gestion : ADMIN, DIRECTION, "
         "CHEF_INJS_ADMIN, INJS_ADMIN, CHEF_SECRETARIAT, SECRETARIAT (ensemble "
         "ROLES_EDITION_REFERENTIEL, évalué via get_user_roles). Les autres rôles "
         "(FINANCE, ENCADRANT, SUPERVISEUR, FORMATEUR, ARCHIVE, AUDITEUR…) restent en "
         "lecture : toute tentative d'écriture reçoit 403, et l'écran générique se met en "
         "lecture seule pour un référentiel non éditable."),
        ('Exception héritée (Formations)',
         "L'ancienne API /formations/ref/* (écran par onglets) réserve toujours ses écritures "
         "au rôle DFRC (IsDFRC). L'écran générique, lui, applique ReferentielPermission : "
         "pour les lieux et les vagues, le périmètre d'écriture est donc celui des rôles de "
         "gestion ci-dessus — point à confirmer par la gouvernance si un resserrement DFRC "
         "est souhaité."),
        ('Suppression', 'Aucune route DELETE n’existe sur les référentiels génériques (405). On désactive (actif=false) ou on archive (réversible), jamais on ne supprime.'),
        ('Comptes de démonstration', 'admin / admin123 (ADMIN), jckouassi (commanditaire), secretariat / sec123 — environnements de démonstration uniquement.'),
    ])


def feuille_anatomie(wb):
    ws = wb.create_sheet("3. Anatomie de l'écran")
    _titre(ws, "3. Anatomie de l'écran, zone par zone",
           "De haut en bas : en-tête, indicateurs, exploration, sections de catégories, cartes, note de fiabilité.", 4)
    _table(ws, ['Zone', 'Contenu affiché', 'Comportements', 'Données utilisées (API)'], [
        ('En-tête (héro)',
         'Icône sliders, badge « Source unique de vérité », titre « Référentiels de l’INJS », sous-titre.',
         'Statique.',
         '—'),
        ('Pastilles de l’en-tête',
         '« N référentiels » (bleu) et « N valeurs » (neutre).',
         'Rappel synthétique toujours visible.',
         'synthese.nb_referentiels, synthese.nb_valeurs'),
        ('Rangée d’indicateurs (4 KPI)',
         'Référentiels (bleu, bi-collection) · Valeurs référencées (vert, bi-list-ol) · À renseigner (ambre, bi-exclamation-circle) · Taux de traçabilité (ardoise, bi-patch-check, en %).',
         'Le taux affiche « — » si aucune valeur n’est à provenance suivie (division impossible).',
         'synthese.* (détail feuille 4)'),
        ('Panneau « Explorer le catalogue »',
         'Champ de recherche + puces de catégories (« Toutes » + 7 catégories avec icônes) + compteur « N référentiel(s) ».',
         'Filtrage 100 % côté client, instantané, sans nouvel appel API. La recherche compare en minuscules sur libellé, description et slug. Les catégories sans résultat disparaissent ; le compteur reflète le filtrage.',
         'categories[].entrees, catalogue[]'),
        ('État « aucun résultat »',
         'Panneau « Aucun référentiel trouvé » citant le texte recherché.',
         'Affiché uniquement si le filtrage ne laisse aucune carte.',
         '—'),
        ('Sections de catégories',
         'En-tête (icône, titre, description) puis grille responsive de cartes.',
         'Ordre = ordre de déclaration du registre backend.',
         'categories[] (cle, libelle, description, icone)'),
        ('Carte référentiel',
         'En-tête (icône, titre, description), mesures (valeurs, à renseigner, archivées), pied (badge d’état + action).',
         'Détail complet feuille 5.',
         'entrees[] (31 clés, feuille 9)'),
        ('Note de bas de page',
         'Explication des 4 degrés de fiabilité avec leurs pastilles colorées (Officiel, Modélisé, Cadrage, À renseigner).',
         'Statique, toujours visible : c’est la légende de la provenance.',
         '—'),
        ('État de chargement',
         'Panneau avec spinner « Chargement des référentiels… ».',
         'Au premier appel API (aria-live pour l’accessibilité).',
         '—'),
        ('État d’erreur',
         'Alerte rouge avec le message renvoyé par l’API (detail) ou un message générique + bouton « Réessayer ».',
         '« Réessayer » relance l’appel sans recharger la page.',
         '—'),
    ], [24, 52, 52, 34])


def feuille_indicateurs(wb, synthese):
    ws = wb.create_sheet('4. Indicateurs de synthèse')
    _titre(ws, '4. Les indicateurs de synthèse',
           'Les 7 champs calculés par l’API à chaque affichage : définition, formule exacte, où ils paraissent.', 5)
    taux = synthese['taux_tracabilite']
    _table(ws, ['Indicateur (clé API)', 'Définition', 'Formule exacte (backend)', 'Affichage à l’écran', f"Valeur au {AUJOURD_HUI}"], [
        ('nb_referentiels', 'Nombre de plaquettes du catalogue.',
         'len(REGISTRE) — nombre d’entrées déclarées dans le registre.',
         'Pastille bleue de l’en-tête + KPI « Référentiels ».', synthese['nb_referentiels']),
        ('nb_referentiels_editables', 'Plaquettes gérables par l’écran générique (bouton « Gérer »).',
         'Entrées du registre avec editable=True.',
         'Non affiché en KPI ; visible indirectement (boutons des cartes).', synthese['nb_referentiels_editables']),
        ('nb_valeurs', 'Total des lignes de tous les référentiels (actives, inactives et archivées confondues).',
         'Somme des count() de chaque modèle déclaré au registre.',
         'Pastille neutre de l’en-tête + KPI « Valeurs référencées ».', synthese['nb_valeurs']),
        ('nb_a_renseigner', 'Valeurs dont la fiabilité vaut A_RENSEIGNER (aucune source ne les atteste encore).',
         'Somme, sur les modèles ayant un champ fiabilite, des lignes fiabilite = A_RENSEIGNER. Les modèles sans fiabilité suivie ne contribuent ni au numérateur ni ailleurs.',
         'KPI ambre « À renseigner ».', synthese['nb_a_renseigner']),
        ('nb_sans_source', 'Valeurs à provenance suivie dont le document source est vide.',
         'Somme, sur les modèles ayant source_document, des lignes source_document = ».',
         'Non affiché en KPI ; alimente le taux de traçabilité et le contrôle de cohérence.', synthese['nb_sans_source']),
        ('nb_valeurs_tracees', 'Périmètre de la traçabilité : total des valeurs des modèles qui suivent la provenance (champ source_document présent).',
         'Somme des total des modèles ayant source_document.',
         'Non affiché ; dénominateur du taux.', synthese['nb_valeurs_tracees']),
        ('taux_tracabilite', 'Part des valeurs traçables ayant effectivement une source renseignée.',
         'arrondi((nb_valeurs_tracees − nb_sans_source) / nb_valeurs_tracees, 4) ; null si le périmètre est vide.',
         'KPI « Taux de traçabilité » en pourcentage arrondi (« — » si null).',
         f"{round(taux * 100)} %" if taux is not None else '—'),
    ], [26, 44, 52, 38, 16])
    _prose_bas(ws, 13, [
        ('Lecture pilotage',
         "Le couple (nb_a_renseigner, taux_tracabilite) est l'indicateur de gouvernance : "
         "il mesure la part du référentiel qui est opposable (rattachée à un document). "
         "Un nb_valeurs élevé avec un taux faible signale un remplissage sans preuve ; "
         "l'état actuel (0 à renseigner, 100 %) est la cible."),
        ('Fraîcheur',
         "Les indicateurs sont recalculés à chaque chargement de l'écran (comptages SQL "
         "par modèle, aucun cache) : une valeur créée dans un écran de gestion est "
         "comptée au prochain affichage du tableau de bord."),
    ])


def _prose_bas(ws, ligne, blocs):
    for rubrique, texte in blocs:
        ws.cell(row=ligne, column=1, value=rubrique).font = Font(size=10, bold=True, color=BLEU)
        ws.merge_cells(start_row=ligne, start_column=2, end_row=ligne, end_column=5)
        c = ws.cell(row=ligne, column=2, value=texte)
        c.font = Font(size=10)
        c.alignment = Alignment(wrap_text=True, vertical='top')
        ws.row_dimensions[ligne].height = max(28, 13 * (1 + len(texte) // 110))
        ligne += 1


def feuille_carte(wb):
    ws = wb.create_sheet('5. La carte référentiel')
    _titre(ws, '5. La carte (plaquette) d’un référentiel',
           'Anatomie, table de décision du badge d’état et règles du bouton d’action.', 4)
    _table(ws, ['Élément de la carte', 'Ce qui s’affiche', 'Règle', 'Clés API'], [
        ('Icône', 'Pictogramme Bootstrap Icons dans un médaillon.', 'Déclarée au registre par référentiel.', 'icone'),
        ('Titre', 'Libellé du référentiel (ex. « Salles et espaces »).', 'Registre.', 'libelle'),
        ('Description', 'Phrase courte de périmètre (ex. « Salles, amphithéâtres, gymnases et espaces sportifs. »).', 'Registre ; utilisée aussi par la recherche.', 'description'),
        ('Mesure « valeurs »', '« N valeur(s) » en gras.', 'Toujours affichée ; total des lignes du modèle (actives + inactives + archivées).', 'total'),
        ('Mesure « à renseigner »', '« N à renseigner » en alerte ambre.', 'Affichée seulement si a_renseigner n’est pas null et > 0.', 'a_renseigner'),
        ('Mesure « archivées »', '« N archivée(s) » en douce.', 'Affichée seulement si archives > 0 (modèles avec champ archive).', 'archives'),
        ('Badge d’état', 'Pastille colorée + icône en pied de carte.', 'Table de décision ci-dessous (fonction etatCompletude).', 'total, a_renseigner'),
        ('Action', 'Lien fléché à droite du pied de carte, ou mention « Sans écran dédié ».', 'Règles ci-dessous.', 'editable, route_ui, libelle_bouton'),
    ], [24, 48, 52, 26])
    ligne = 15
    ws.cell(row=ligne, column=1, value='Table de décision — badge d’état (etatCompletude)').font = Font(size=12, bold=True, color=BLEU)
    _table(ws, ['Priorité', 'Condition', 'Badge affiché', 'Signification métier'], [
        (1, 'total = 0', 'Non renseigné (rouge, bi-exclamation-circle)',
         'Le référentiel est vide : aucune valeur. C’est l’état des plaquettes avant remplissage (ex. Administratif & scolarité avant nov. 2026).'),
        (2, 'a_renseigner = null (modèle sans champ fiabilite)', 'Provenance non suivie (ambre, bi-dash-circle)',
         'Le modèle ne trace pas la provenance : on ne peut ni affirmer ni mesurer la traçabilité (ex. Niveaux, Formations, UE/ECUE).'),
        (3, 'a_renseigner = 0', 'Complet (vert, bi-check-circle)',
         'Toutes les valeurs ont une fiabilité arrêtée (Officiel/Modélisé/Cadrage).'),
        (4, 'a_renseigner > 0', '« N à renseigner » (ambre, bi-exclamation-circle)',
         'N valeurs restent sans attestation : travail de sourcing à terminer.'),
    ], [10, 46, 44, 62], ligne_debut=ligne + 1,
        couleurs_etat={'Complet (vert, bi-check-circle)': VERT_OK,
                       'Non renseigné (rouge, bi-exclamation-circle)': ROUGE_ALERTE})
    ligne2 = ligne + 8
    ws.cell(row=ligne2, column=1, value='Table de décision — bouton d’action').font = Font(size=12, bold=True, color=BLEU)
    _table(ws, ['Priorité', 'Condition (registre)', 'Bouton', 'Destination'], [
        (1, 'editable = true', '« Gérer » (ou libelle_bouton personnalisé)',
         '/referentiels/gestion/{slug} — écran générique (CRUD selon capacités). 23 plaquettes aujourd’hui.'),
        (2, 'editable = false et route_ui renseignée', '« Consulter » (ou libelle_bouton, ex. UE/ECUE : « Gérer »)',
         'route_ui déclarée : /formations (cycles), /scolarite/maquettes (UE/ECUE), ou l’écran générique en lecture seule (modules officiels, volumes horaires).'),
        (3, 'editable = false et route_ui = null', 'Mention « Sans écran dédié » (non cliquable)',
         'Aucun écran ne gère ce référentiel : plutôt qu’un lien mort, l’absence est annoncée. Plus aucun cas aujourd’hui (les Années académiques, dernier cas, sont gérables depuis la migration scolarite 0019).'),
    ], [10, 40, 44, 68], ligne_debut=ligne2 + 1)


def feuille_catalogue(wb, categories):
    ws = wb.create_sheet('6. Catalogue des 27')
    _titre(ws, '6. Catalogue complet des référentiels',
           f"Les 27 plaquettes et leurs compteurs réels au {AUJOURD_HUI}, recalculés en base "
           'avec la même logique que l’API. État et action = ce que l’utilisateur voit.', 18)
    lignes = []
    numero = 0
    for categorie in categories:
        for e in categorie['entrees']:
            numero += 1
            bouton, destination = action_affichee(e)
            lignes.append((
                numero, categorie['libelle'], e['libelle'], e['slug'], e['description'],
                e['total'], e['actifs'], e['archives'],
                '—' if e['a_renseigner'] is None else e['a_renseigner'],
                '—' if e['sans_source'] is None else e['sans_source'],
                etat_affiche(e),
                'Oui' if e['editable'] else 'Non', bouton,
                'Oui' if e['provenance_suivie'] else 'Non',
                'Oui' if e['archivage_supporte'] else 'Non',
                'Oui' if e['a_un_code'] else 'Non (= libellé/nom)',
                destination, e['route_api'], e['modele'],
                e.get('source') or '', e.get('avertissement') or '',
            ))
    _table(ws, ['N°', 'Catégorie', 'Référentiel', 'Slug', 'Description', 'Valeurs',
                'Actives', 'Archiv.', 'À renseigner', 'Sans source', 'État affiché',
                'Éditable', 'Action', 'Provenance suivie', 'Archivage', 'Code distinct',
                'Écran (route UI)', 'Route API', 'Modèle Django', 'Source (registre)',
                'Avertissement (registre)'],
           lignes, [5, 24, 26, 20, 40, 9, 9, 9, 11, 10, 18, 9, 12, 12, 10, 14, 30, 30, 28, 36, 60],
           couleurs_etat={'Complet': VERT_OK, 'Non renseigné': ROUGE_ALERTE,
                          'Provenance non suivie': ORANGE_RESERVE})


def feuille_categories(wb, categories):
    ws = wb.create_sheet('7. Catégories')
    _titre(ws, '7. Les sept catégories du catalogue',
           'Familles d’affichage et de filtrage, dans l’ordre de l’écran (= ordre du registre).', 7)
    lignes = []
    for c in categories:
        lignes.append((
            c['cle'], c['libelle'], c['description'], c['icone'],
            len(c['entrees']),
            sum(e['total'] for e in c['entrees']),
            ', '.join(e['libelle'] for e in c['entrees']),
        ))
    _table(ws, ['Clé', 'Catégorie', 'Description', 'Icône', 'Référentiels', 'Valeurs',
                'Plaquettes (dans l’ordre d’affichage)'],
           lignes, [20, 30, 52, 16, 12, 10, 70])
    _prose_bas(ws, 13, [
        ('Rôle des catégories',
         "Elles structurent la lecture (sections de l'écran) et le filtrage (puces du panneau "
         "« Explorer le catalogue »). L'API les expose deux fois : `catalogue` (liste légère "
         "pour les puces) et `categories` (avec leurs entrées chiffrées). Une catégorie sans "
         "résultat après filtrage disparaît de l'écran."),
        ('Ordre d’affichage',
         'Institutionnels → Offre de formation → Système LMD → Pédagogiques → Ressources '
         'humaines pédagogiques → Organisation pédagogique → Administratif & scolarité : du '
         'cadre de l’Institut vers son fonctionnement quotidien.'),
    ])


def feuille_provenance(wb, synthese):
    ws = wb.create_sheet('8. Provenance & fiabilité')
    _titre(ws, '8. Provenance et degrés de fiabilité',
           'Chaque valeur à provenance suivie conserve le document qui l’atteste et son degré de fiabilité.', 4)
    _table(ws, ['Degré (code)', 'Signification', 'Quand il s’applique', 'Exemples réels en base'], [
        ('OFFICIEL — Officiel',
         'La source affirme la valeur : document officiel, nomenclature du socle technique, décision en vigueur.',
         'Valeur reprise mot pour mot d’un document d’autorité ou du code métier en production.',
         '5 natures de frais et 6 modes de paiement (socle finances) ; 4 décisions de jury ; 28 grades enseignants ; années écoulées/courante ; 8 filières.'),
        ('MODELISE — Modélisé',
         'La source elle-même présente la valeur comme une proposition ou un inventaire modélisé.',
         'Inventaires et répartitions proposés par le document source, non encore arrêtés.',
         '166 salles et 16 bâtiments (inventaire des lieux) ; volumes horaires par module ; types d’espace sportif issus de l’inventaire.'),
        ('CADRAGE — Cadrage',
         'Catégorie de travail fonctionnelle, cohérente mais à arrêter par l’autorité compétente.',
         'Typologies « pratique INJS » des documents, en attente de validation du service propriétaire.',
         '20 types d’évaluation ; 56 types de document et 47 types de notification (à arrêter DAF/Scolarité/Direction des études) ; années planifiées 2027-2028 et 2028-2029.'),
        ('A_RENSEIGNER — À renseigner',
         'Aucune source ne fournit (encore) la valeur ou sa provenance.',
         'État transitoire à résorber : il alimente le KPI ambre et le badge « N à renseigner ».',
         f"Aujourd'hui : {synthese['nb_a_renseigner']} valeur(s) — cible atteinte et surveillée par les tests."),
    ], [24, 48, 48, 58])
    _prose_bas(ws, 10, [
        ('source_document',
         "Champ texte porté par chaque valeur à provenance suivie : il nomme le document exact "
         "(et souvent le paragraphe) qui atteste la valeur — ex. « ADMINISTRATIF & SCOLARITÉ "
         "(PDF, 1er novembre 2026) — §4.1 ». Une valeur sans source (source_document vide) est "
         "comptée dans nb_sans_source et fait baisser le taux de traçabilité."),
        ('Quels modèles suivent la provenance ?',
         "Ceux qui possèdent les champs source_document/fiabilite : tous les référentiels du "
         "socle (RefSocle), les modèles Formations remplis par l'importeur (sites, bâtiments, "
         "salles, vagues) et, depuis la migration 0019, les années académiques. Les modèles de "
         "scolarité (niveaux, semestres, parcours) et les cycles/UE-ECUE ne la suivent pas : "
         "leurs cartes affichent « Provenance non suivie », honnêtement, plutôt qu'un faux taux."),
        ('Taux de traçabilité',
         "(valeurs du périmètre suivi − sans source) / valeurs du périmètre suivi. Il ne dit "
         "rien des référentiels hors périmètre : c'est un taux de complétude documentaire, "
         "pas un taux de vérité métier."),
        ('Journal d’audit',
         "Toute écriture via l'écran générique est journalisée (ReferentielJournal : qui, quoi, "
         "quand, avant/après). La provenance saisie manuellement (source + fiabilité) est donc "
         "elle-même traçable dans le temps."),
    ])


def feuille_api(wb, categories):
    ws = wb.create_sheet('9. API tableau de bord')
    _titre(ws, '9. API du tableau de bord',
           'GET /api/referentiels/tableau-de-bord/ — contrat complet de la réponse consommée par l’écran.', 4)
    _prose(ws, [
        ('Endpoint', 'GET /api/referentiels/tableau-de-bord/ (APIView TableauDeBordReferentielsView, nom de route ref-tableau-de-bord).'),
        ('Authentification / permission', 'JWT Bearer ; ReferentielPermission (lecture pour tout utilisateur authentifié). 401 sans jeton.'),
        ('Paramètres', 'Aucun. La réponse est complète et recalculée à chaque appel (pas de cache, pas de pagination).'),
        ('Structure de la réponse',
         '{\n  "categories": [ {cle, libelle, description, icone, entrees: [entrée, …]}, … ],\n'
         '  "catalogue": [ {cle, libelle, description, icone}, … ],   // catégories légères pour les puces\n'
         '  "synthese": {nb_referentiels, nb_referentiels_editables, nb_valeurs, '
         'nb_a_renseigner, nb_sans_source, nb_valeurs_tracees, taux_tracabilite}\n}'),
        ('Construction', 'Pour chaque catégorie (registre), pour chaque entrée : résolution du modèle (modele_de), comptages (total, actifs si champ actif, archivées si champ archive, a_renseigner si champ fiabilite, sans_source si champ source_document), capacités du modèle, métadonnées de formulaire (champs_choix/numeriques/dates), routes des sélecteurs. La synthèse agrège ces compteurs (feuille 4).'),
        ('Consommation', "L'écran générique de gestion relit la même API (chargerCatalogue) pour connaître, par slug, les capacités du référentiel avant d'afficher son formulaire : le tableau de bord est aussi le contrat de configuration des écrans de gestion."),
    ])
    cles = [
        ('slug', 'chaîne', 'Identifiant d’URL du référentiel (clé du registre).', 'salles'),
        ('libelle', 'chaîne', 'Titre affiché sur la carte.', 'Salles et espaces'),
        ('description', 'chaîne', 'Phrase de périmètre sous le titre ; indexée par la recherche.', 'Salles, amphithéâtres…'),
        ('categorie', 'chaîne', 'Clé de la catégorie de rattachement.', 'organisation'),
        ('icone', 'chaîne', 'Classe Bootstrap Icons de la carte.', 'bi-door-open'),
        ('modele', 'chaîne', 'Modèle Django résolu (app.modele) — ajouté par l’API.', 'formations.refsalle'),
        ('editable', 'booléen', 'Gérable par l’écran générique (bouton Gérer).', 'true'),
        ('route_ui', 'chaîne|null', 'Écran de destination pour un référentiel non éditable.', '/scolarite/maquettes'),
        ('route_api', 'chaîne', 'Route de lecture des valeurs (défaut /referentiels/{slug}/).', '/referentiels/salles/'),
        ('libelle_bouton', 'chaîne', 'Texte du bouton si différent de Gérer/Consulter.', 'Gérer (UE/ECUE)'),
        ('source', 'chaîne', 'Source documentaire de référence affichée dans le registre (métadonnée de carte).', 'Organisation pédagogique (PDF) — §5-8'),
        ('avertissement', 'chaîne', 'Réserve métier affichée dans l’écran de gestion (données à confirmer, périmètres).', 'Capacités = inventaire DIEM…'),
        ('total', 'entier', 'Nombre de lignes du modèle.', '166'),
        ('actifs', 'entier', 'Lignes actif=true (ou total si le modèle n’a pas de champ actif).', '166'),
        ('archives', 'entier', 'Lignes archive=true (0 si le modèle n’archive pas).', '0'),
        ('a_renseigner', 'entier|null', 'Lignes fiabilite=A_RENSEIGNER ; null si le modèle n’a pas de champ fiabilite (→ « Provenance non suivie »).', '0 / null'),
        ('sans_source', 'entier|null', 'Lignes source_document vide ; null si le champ n’existe pas.', '0 / null'),
        ('provenance_suivie', 'booléen', 'Le modèle possède source_document (affiche fiabilité/source dans le formulaire).', 'true'),
        ('archivage_supporte', 'booléen', 'Le modèle possède archive (action Archiver/Réactiver proposée).', 'false (salles)'),
        ('a_un_code', 'booléen', 'Le modèle a une colonne code distincte de l’intitulé (sinon le libellé/nom tient lieu de code).', 'true (AMP-001)'),
        ('a_une_description', 'booléen', 'Le modèle possède une description éditable (sinon pas de champ mort dans le formulaire).', 'false (salles)'),
        ('champs', 'liste', 'Champs métier éditables déclarés au registre (ordre du formulaire).', "['type_lieu','capacite',…]"),
        ('champs_choix', 'objet', 'Pour chaque champ à choices : liste {value, label} lue sur le modèle.', "type_lieu: 11 choix"),
        ('champs_numeriques', 'liste', 'Champs entiers/décimaux (saisie number, conversion en nombre).', "['capacite']"),
        ('champs_dates', 'liste', 'Champs DateField (saisie date, chaîne vide convertie en null).', "['indisponible_du', …]"),
        ('selecteurs', 'liste', 'Clés étrangères éditables en listes déroulantes.', "['site','batiment','type_espace']"),
        ('selecteurs_routes', 'objet', 'Par sélecteur : route API des options (+ slug/éditable de la cible).', 'batiment → /referentiels/batiments/'),
        ('champ_libelle', 'chaîne', 'Nom réel du champ d’intitulé sur le modèle (libelle, nom, intitule…).', 'nom (salles)'),
        ('champ_code', 'chaîne', 'Nom réel du champ de code ; égal à champ_libelle = pas de code distinct.', 'code / libelle'),
        ('unicite_par', 'chaîne', 'Rattachement bornant l’anti-doublon de libellé (vide = global).', 'site (salles, bâtiments)'),
        ('bascule_unique', 'chaîne', 'Drapeau booléen « un seul vrai » basculé automatiquement à l’écriture.', 'courante (années)'),
    ]
    ligne = 13
    ws.cell(row=ligne, column=1, value='Dictionnaire des clés d’une entrée (31 clés)').font = Font(size=12, bold=True, color=BLEU)
    _table(ws, ['Clé', 'Type', 'Signification', 'Exemple'], cles, [22, 14, 84, 34], ligne_debut=ligne + 1)


def feuille_registre(wb):
    ws = wb.create_sheet('10. Registre (moteur)')
    _titre(ws, '10. Le registre : le moteur du tableau de bord',
           'backend/referentiels/registre.py — déclaration des catégories et des 27 entrées, et leurs effets.', 4)
    _table(ws, ['Élément du registre', 'Rôle', 'Défaut (fonction entree)', 'Effet sur le tableau de bord / l’écran générique'], [
        ('CATEGORIES', 'Les 7 familles (cle, libelle, description, icone), dans l’ordre d’affichage.', '—', 'Sections de l’écran + puces de filtrage + clé catalogue.'),
        ('REGISTRE', 'Dictionnaire ordonné slug → entrée (27 entrées).', '—', 'Une entrée = une carte. nb_referentiels = len(REGISTRE).'),
        ('slug', 'Identifiant d’URL et clé du registre.', 'obligatoire', 'Route /referentiels/gestion/{slug} et API /referentiels/{slug}/.'),
        ('modele', 'Modèle Django (classe ou « app.Modele ») résolu par modele_de().', 'None', 'Source des comptages et du CRUD générique.'),
        ('editable', 'Gérable par l’écran générique.', 'True', 'true → bouton « Gérer » ; false → Consulter ou « Sans écran dédié » selon route_ui.'),
        ('route_ui', 'Écran de destination si non éditable.', '/referentiels/gestion/{slug}', 'Lien de la carte (Consulter) ; None → mention non cliquable.'),
        ('route_api', 'Route de lecture historique si différente du générique.', '/referentiels/{slug}/', 'Utilisée par l’écran générique en lecture seule pour les référentiels historisés.'),
        ('champs', 'Champs métier éditables supplémentaires (hors socle).', '[]', 'Colonnes du tableau + champs du formulaire, dans l’ordre déclaré.'),
        ('selecteurs', 'Clés étrangères présentées en listes déroulantes.', '[]', 'Colonnes « …_libelle » + selects (options lues sur selecteurs_routes).'),
        ('champ_libelle / champ_code', 'Adaptateurs pour modèles hors socle (nom, intitule…).', 'libelle / code', 'Contrat unifié code/libellé de l’API ; code = libellé → pas de champ code demandé.'),
        ('unicite_par', 'Borne l’anti-doublon de libellé à un rattachement.', "'' (global)", 'Ex. nom de salle unique PAR SITE (contrôle aligné sur la contrainte métier).'),
        ('bascule_unique', 'Drapeau « un seul vrai » (année courante).', "''", 'Passer le drapeau à vrai bascule les autres lignes à faux avant écriture (processus), la contrainte DB restant le garde-fou.'),
        ('libelle_bouton', 'Texte du bouton de la carte.', "'' (Gérer/Consulter)", 'Ex. UE/ECUE affiche « Gérer » vers le module Maquettes bien que non éditable ici.'),
        ('source / avertissement', 'Métadonnées documentaires de la carte.', "''", 'Source de référence ; avertissement = réserve affichée dans l’écran de gestion.'),
        ('entrees_par_categorie()', 'Regroupe les entrées par catégorie dans l’ordre déclaré.', '—', 'Alimente categories de l’API, donc les sections de l’écran.'),
    ], [26, 48, 26, 64])
    _prose_bas(ws, 21, [
        ('Ajouter un référentiel (procédure)',
         "1) Modèle : créer le modèle (idéalement RefSocle : code, libelle, description, "
         "actif, archive, source_document, fiabilite) + migration. 2) Registre : ajouter "
         "l'entrée entree(slug=…, modele=…, categorie=…, champs/selecteurs si besoin). "
         "3) Données : bloc JSON dans referentiels/data + import idempotent dans "
         "importer_referentiels_injs (ou saisie via l'écran). 4) Rien d'autre : la carte "
         "apparaît sur le tableau de bord, l'écran de gestion, les compteurs et les routes "
         "sont générés. 5) Tester : CRUD, doublons, permissions (patrons existants dans "
         "referentiels/tests)."),
        ('Capacités calculées, jamais déclarées',
         "provenance_suivie, archivage_supporte, a_un_code, a_une_description et les "
         "métadonnées de champs (choix, numériques, dates) sont déduites du modèle réel "
         "par l'API : impossible d'annoncer une capacité que le modèle n'a pas."),
    ])


def feuille_donnees(wb):
    ws = wb.create_sheet('11. Données & import')
    _titre(ws, '11. D’où viennent les valeurs : import, sources, contrôles',
           'Le remplissage initial et sa reproductibilité (commande importer_referentiels_injs).', 4)
    _table(ws, ['Bloc d’import', 'Fichier de données', 'Contenu', 'Clé métier / idempotence'], [
        ('1. Institutions (+ vagues)', 'institutions.json',
         'Écoles, mentions, natures de cursus, 8 filières codées F01→F08, 5 statuts de vague, 3 vagues codées, types d’enseignement ; rattachement des cycles aux filières.',
         'code (libellé pour les vagues) ; upsert, 0 doublon à la ré-exécution.'),
        ('2. Cycles LMD documentés', '(dans le code de la commande)',
         'Création des cycles Licence/Master des filières F01→F04 si absents — socle des modules et volumes (désactivable --sans-cycles).',
         'couple filiere_code × diplôme.'),
        ('3. Modules officiels', 'modules_officiels.json',
         '227 intitulés de modules des maquettes ENSEPS, semestre uniquement quand la source le documente.',
         'formation × semestre × libellé.'),
        ('4. Lieux', 'lieux.json',
         'Site INJS Marcory (géorepérage validé), 16 bâtiments, 166 salles codées (AMP-001…), capacité quand l’inventaire la donne, rattachement sportif de 25 espaces.',
         'site × bâtiment × nom ; codes par type et par bâtiment.'),
        ('5. Volumes horaires', 'volumes_horaires.json',
         '51 répartitions CM/TD/TP/stage (proposition de cadrage, fiabilité MODELISE), cursus INJS uniquement.',
         'formation × intitulé de module.'),
        ('6. Nomenclatures pédagogiques', 'nomenclatures_pedagogiques.json',
         '20 types d’évaluation (CADRAGE), 4 décisions de jury (OFFICIEL), 18 types d’espace sportif (MODELISE + 4 CADRAGE), 28 grades enseignants (OFFICIEL).',
         'code ; provenance par bloc, surchargeable par valeur.'),
        ('7. Administratif & scolarité', 'nomenclatures_administratif.json',
         '14 modes de paiement, 28 types de frais, 56 types de document, 47 types de notification, 8 années académiques.',
         'code ; années par libellé (statut → drapeaux courante/actif/clôturée).'),
        ('Chaîne LMD (hors référentiels)', 'Commandes scolarite init → configurer → completer',
         'Niveaux, semestres, parcours, cycles, 20 maquettes (BROUILLON), 331 UE / 407 ECUE / 1 200 crédits.',
         'Commandes idempotentes enchaînées par reconstruire.sh / start_dev.sh.'),
    ], [28, 34, 66, 44])
    _prose_bas(ws, 14, [
        ('Documents sources (dossier_trvx/)',
         "RÉFÉRENTIEL COMPLET DU SYSTÈME LMD (PDF) · GRADES ET STATUTS DES ENSEIGNANTS-INJS "
         "(PDF) · Organisation pédagogique (PDF) · ADMINISTRATIF & SCOLARITÉ (PDF) · "
         "Formations et Modules INJS · Liste des bâtiments, salles et espaces · Vagues INJS "
         "2026 · Modéliser les volumes horaires · Refonte du Module Évaluations. Chaque valeur "
         "importée cite son document dans source_document."),
        ('Règles d’or du remplissage',
         "Jamais de donnée inventée : ce que la source ne dit pas reste vide ou CADRAGE avec "
         "réserve tracée (ex. maquette MS-S8 reconstituée « à confirmer DENSEPS » ; capacités "
         "de salles et montants de frais jamais déduits — inventaire DIEM et arrêté de "
         "tarification). Les arbitrages sont écrits dans le bloc _meta de chaque fichier JSON."),
        ('Reproductibilité',
         "./arena/reconstruire.sh reconstruit tout (venv, migrations, import, chaîne LMD, "
         "contrôle) ; ./arena/sauvegarder-donnees.sh / restaurer-donnees.sh gèrent les "
         "instantanés de la base de l'aperçu (non versionnés, dépôt public). Le vérificateur "
         "verifier_coherence_referentiels termine la chaîne (« référentiels cohérents »)."),
    ])


def feuille_scenarios(wb):
    ws = wb.create_sheet("12. Scénarios d'usage")
    _titre(ws, "12. Scénarios d'usage pas à pas",
           'Ce que fait chaque profil, depuis le tableau de bord.', 3)
    _table(ws, ['Scénario', 'Qui', 'Pas à pas et résultat'], [
        ('Vérifier la santé du référentiel',
         'Direction, pilotage',
         "Ouvrir /referentiels → lire les 4 KPI (référentiels, valeurs, à renseigner, taux de "
         "traçabilité) → parcourir les badges : vert = Complet. Objectif permanent : 0 à "
         "renseigner et 100 % de traçabilité."),
        ('Retrouver un référentiel',
         'Tous',
         "Saisir un mot dans « Rechercher un référentiel » (libellé, description ou slug, "
         "insensible à la casse) ou cliquer une puce de catégorie. Le compteur « N "
         "référentiel(s) » suit le filtrage ; vider la recherche réaffiche tout."),
        ('Gérer les valeurs d’une plaquette',
         'Rôles de gestion (ADMIN, DIRECTION, CHEF/INJS_ADMIN, CHEF/SECRETARIAT)',
         "Carte → « Gérer » → écran générique : Ajouter (code exigé si la plaquette en a un, "
         "formats validés, doublon refusé avec message), Modifier (code non modifiable), "
         "activer/désactiver, archiver si supporté. Chaque écriture est journalisée."),
        ('Traiter un badge « N à renseigner »',
         'Service propriétaire de la nomenclature',
         "Ouvrir la plaquette → filtrer les valeurs À RENSEIGNER → pour chacune, retrouver le "
         "document qui l'atteste → renseigner source_document et fiabilite réelles (jamais "
         "OFFICIEL sans preuve). Le badge repasse à « Complet » à 0."),
        ('Comprendre « Provenance non suivie »',
         'Audit, direction',
         "Le modèle ne porte ni source ni fiabilité (niveaux, parcours, formations, UE/ECUE) : "
         "ce n'est pas un manque de données mais une limite de traçabilité du modèle. La "
         "provenance de ces référentiels est portée par leurs documents de chargement "
         "(maquettes officielles, PDF LMD) et par l'historique Git des jeux de données."),
        ('Ouvrir une nouvelle année académique',
         'Direction des études / Scolarité',
         "Carte Années académiques → Gérer → Ajouter (libellé AAAA-AAAA, 1er octobre → 31 "
         "juillet, fiabilité Cadrage tant que planifiée). Le moment venu, cocher « Année "
         "courante » : l'ancienne bascule automatiquement. La clôture de l'ancienne année "
         "reste faite par le workflow Scolarité (jurys, diplômation)."),
        ('Rattacher les vagues d’une campagne',
         'DFRC / Scolarité',
         "Carte Vagues → Gérer → sur chaque vague, renseigner formation, site, statut, "
         "période et effectifs de LA campagne concernée (jamais déduits par avance)."),
        ('Auditer une modification',
         'Auditeur (lecture seule)',
         "Le tableau de bord donne l'état ; le journal des référentiels (ReferentielJournal, "
         "API en lecture) donne l'historique : auteur, action (création, modification, "
         "activation, archivage…), avant/après, horodatage."),
        ('Diagnostiquer un écran vide ou en erreur',
         'Support',
         "Spinner prolongé ou alerte : vérifier le jeton (401 → se reconnecter), cliquer "
         "« Réessayer », contrôler l'API GET /api/referentiels/tableau-de-bord/. Un compteur "
         "à 0 sur une carte signale un modèle vide (import non joué) : relancer "
         "importer_referentiels_injs puis verifier_coherence_referentiels."),
    ], [34, 34, 104])


def feuille_points_glossaire(wb):
    ws = wb.create_sheet('13. Points ouverts & gloss.')
    _titre(ws, '13. Points ouverts, réserves et glossaire',
           'Décisions en attente des autorités de l’Institut et définitions des termes employés.', 3)
    _table(ws, ['Point ouvert', 'État dans l’application', 'Décision / action attendue'], [
        ('Montants des frais (barèmes)',
         'Types de frais chargés sans aucun prix ; Tarification du module Finances prête par formation/parcours/niveau/année/nature.',
         'Arrêté annuel de tarification (Direction/DAF) puis saisie des barèmes 2026-2027.'),
        ('Typologies « pratique INJS » (CADRAGE)',
         'Modes de paiement hors socle, types de frais hors natures, documents, notifications : chargés en fiabilité CADRAGE.',
         'Validation DAF / Scolarité / Direction des études (§9.1 du PDF) → passer en OFFICIEL.'),
        ('Rattachements des vagues',
         'VAGUE_1/2/3 codées, sans formation/site/statut/période (aucune invention).',
         'À renseigner campagne par campagne (DFRC/Scolarité), via la carte Vagues → Gérer.'),
        ('Capacités et équipements des salles',
         'Capacité connue pour 22/166 salles ; équipements vides (indéductibles).',
         'Inventaire DIEM pièce par pièce.'),
        ('Écritures Lieux/Vagues : DFRC ou rôles de gestion ?',
         'Ancienne API : DFRC seule ; écran générique : ReferentielPermission (6 rôles de gestion).',
         'Arbitrage de gouvernance ; resserrement possible si souhaité.'),
        ('Code ELEPHANT_MONEY',
         'Code historique du socle finances conservé à l’identique (alignement référentiel ↔ paiements).',
         'Renommage en ORANGE_MONEY seulement via migration des paiements existants.'),
        ('Maquettes STASE et semestre MS-S8',
         'Maquettes ENSEP/STASE non publiées (absentes, non inventées) ; MS-S8 reconstitué du PDF « à confirmer DENSEPS ».',
         'Publication/confirmation DENSEPS ; les maquettes restent BROUILLON, parcours non rattachés.'),
        ('Grades PDF vs politique de rôles',
         '21 écarts documentés entre la matrice du PDF grades et ROLE_POLICY du code.',
         'Arbitrage DRH/Direction : aligner le code ou le document (grades ≠ rôles, acquis).'),
        ('Années planifiées 2027-2029',
         'Présentes en CADRAGE (prévisions du PDF §6).',
         'Confirmation du calendrier par la Direction des études avant ouverture des campagnes.'),
    ], [34, 62, 62])
    ligne = 15
    ws.cell(row=ligne, column=1, value='Glossaire').font = Font(size=12, bold=True, color=BLEU)
    _table(ws, ['Terme', 'Définition', 'Où le voir'], [
        ('Référentiel', 'Table de valeurs de référence partagée par toute l’application (nomenclature).', 'Une plaquette du tableau de bord.'),
        ('Valeur', 'Une ligne d’un référentiel (ex. la salle AMP-001).', 'Écrans de gestion.'),
        ('Plaquette / carte', 'Vignette d’un référentiel sur le tableau de bord.', 'Grille par catégorie.'),
        ('Registre', 'Déclaration backend des 27 référentiels et de leurs capacités (registre.py).', 'backend/referentiels/'),
        ('Slug', 'Identifiant d’URL d’un référentiel (ex. salles, annees).', 'Routes /referentiels/gestion/{slug}.'),
        ('Provenance', 'Couple (source_document, fiabilite) porté par une valeur.', 'Formulaire de gestion, colonne Fiabilité.'),
        ('Fiabilité', 'Degré d’attestation : OFFICIEL, MODELISE, CADRAGE, A_RENSEIGNER.', 'Badges colorés ; feuille 8.'),
        ('Traçabilité (taux)', 'Part des valeurs suivies ayant une source renseignée.', 'KPI du tableau de bord.'),
        ('Socle (RefSocle)', 'Modèle abstrait commun : code, libellé, description, actif, archive, source, fiabilité.', 'backend/referentiels/models.py'),
        ('Écran générique', 'Écran de gestion unique piloté par les capacités que l’API annonce par référentiel.', '/referentiels/gestion/{slug}'),
        ('Archivage', 'Sortie d’usage réversible d’une valeur (jamais de suppression).', 'Action Archiver/Réactiver.'),
        ('Bascule (année courante)', 'Désigner une année courante retire automatiquement ce statut à la précédente.', 'Carte Années académiques.'),
        ('Importeur', 'Commande idempotente importer_referentiels_injs (7 blocs JSON sourcés).', 'backend/referentiels/data/'),
        ('DFRC / DAF / DIEM / DENSEPS',
         'Directions de l’INJS : Formation & Recherche (DFRC), Administrative & Financière (DAF), Infrastructures & Équipements (DIEM), École normale supérieure EPS (DENSEPS).',
         'Propriétaires métier des décisions ci-dessus.'),
    ], [26, 84, 48], ligne_debut=ligne + 1)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--sortie',
        default=str(RACINE / 'Documentation_Tableau_de_bord_Referentiels_INJS.xlsx'))
    args = parser.parse_args()

    try:
        commit = subprocess.run(
            ['git', 'rev-parse', '--short', 'HEAD'], cwd=RACINE,
            capture_output=True, text=True, timeout=10).stdout.strip() or '—'
    except Exception:
        commit = '—'

    categories, synthese = instantane()
    wb = Workbook()
    feuille_couverture(wb, synthese, commit)
    feuille_presentation(wb)
    feuille_acces(wb)
    feuille_anatomie(wb)
    feuille_indicateurs(wb, synthese)
    feuille_carte(wb)
    feuille_catalogue(wb, categories)
    feuille_categories(wb, categories)
    feuille_provenance(wb, synthese)
    feuille_api(wb, categories)
    feuille_registre(wb)
    feuille_donnees(wb)
    feuille_scenarios(wb)
    feuille_points_glossaire(wb)

    wb.save(args.sortie)
    print(f"Classeur écrit : {args.sortie}")
    print(f"Feuilles : {len(wb.sheetnames)} — {', '.join(wb.sheetnames)}")
    print(f"Synthèse : {synthese}")


if __name__ == '__main__':
    main()
