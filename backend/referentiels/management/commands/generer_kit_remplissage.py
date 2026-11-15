"""Génère le kit de fichiers de remplissage (XLSX + CSV) du Hub « Référentiels ».

Le kit est **dérivé du registre** (``referentiels.registre.REGISTRE``) et des
modèles Django réels : aucune colonne n'est inventée, aucune liste de valeurs
n'est recopiée à la main. Régénérer le kit après une évolution des modèles
suffit donc à le maintenir exact.

Colonnes produites : celles de ``colonnes.champs_importables()``, c'est-à-dire
exactement ce que le moteur d'import sait résoudre — y compris les clés
étrangères, qui se renseignent par **clé métier** (code, libellé…) et jamais
par identifiant numérique.

Usage ::

    python manage.py generer_kit_remplissage
    python manage.py generer_kit_remplissage --dossier ./mon_kit --exemples 5
"""

from __future__ import annotations

import csv
import re
from collections import OrderedDict
from pathlib import Path

from django.core.management.base import BaseCommand
from django.db import models

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.workbook.defined_name import DefinedName

from referentiels.moteur.colonnes import champs_importables, libelle_champ
from referentiels.moteur.importations import normaliser_entete
from referentiels.registre import REGISTRE, modele_de

# ═══════════════════════════════════════════════════════════════════════════
# Présentation
# ═══════════════════════════════════════════════════════════════════════════

COULEUR_ENTETE = '1F3864'   # bleu INJS
COULEUR_BANDEAU = '2E5C8A'
COULEUR_OBLIG = 'FCE4E4'    # rose : champ obligatoire
COULEUR_FACULT = 'EAF3EA'   # vert pâle : facultatif
COULEUR_TITRE = 'D9E2F3'

BORDURE = Border(*(Side(style='thin', color='BFBFBF'),) * 4)

FEUILLES = ('Instructions', 'Données', 'Références', 'Exemple', 'Contrôles')

# Catégories du registre -> dossier du kit.
CATEGORIES = OrderedDict([
    ('institutionnel', '01_INSTITUTIONNEL'),
    ('offre-formation', '02_OFFRE_DE_FORMATION'),
    ('pedagogique', '03_PEDAGOGIQUE'),
    ('organisation', '04_ORGANISATION_ET_INFRASTRUCTURES'),
    ('ressources-humaines', '05_RESSOURCES_HUMAINES'),
    ('scolarite', '06_SCOLARITE'),
    ('systeme-lmd', '07_SYSTEME_LMD'),
])
DOSSIER_GUIDE = '00_GUIDE_UTILISATION'
DOSSIER_DEMO = '08_DONNEES_DE_DEMONSTRATION'

# En-têtes lisibles. On n'ajoute que des accents : les lettres restent
# identiques, donc la clé normalisée par le moteur d'import ne bouge pas
# (une vérification automatique le garantit plus bas).
ACCENTS = {
    'abrege': 'Abrégé', 'actif': 'Actif', 'annee_academique': 'Année académique',
    'batiment': 'Bâtiment', 'capacite': 'Capacité', 'caractere': 'Caractère',
    'categorie': 'Catégorie', 'cloturee': 'Clôturée', 'code': 'Code',
    'code_dossier': 'Code dossier', 'courante': 'Courante', 'credits': 'Crédits',
    'credits_requis': 'Crédits requis', 'cycle': 'Cycle',
    'date_cloture': 'Date clôture', 'date_debut': 'Date début',
    'date_fin': 'Date fin', 'description': 'Description', 'domaine': 'Domaine',
    'duree_annees': 'Durée années', 'ecole': 'École',
    'effectif_prevu': 'Effectif prévu', 'effectif_reel': 'Effectif réel',
    'equipements': 'Équipements', 'est_ouvert': 'Est ouvert',
    'est_stage': 'Est stage', 'etat_ventilation': 'État ventilation',
    'famille': 'Famille', 'filiere': 'Filière', 'filiere_code': 'Filière code',
    'formation': 'Formation', 'geofence_latitude': 'Géofence latitude',
    'geofence_longitude': 'Géofence longitude',
    'geofence_rayon_m': 'Géofence rayon m', 'grade': 'Grade',
    'heures_cm': 'Heures CM', 'heures_td': 'Heures TD', 'heures_tp': 'Heures TP',
    'heures_stage': 'Heures stage', 'heures_total': 'Heures total',
    'indisponible_au': 'Indisponible au', 'indisponible_du': 'Indisponible du',
    'intitule': 'Intitulé', 'intitule_module': 'Intitulé module',
    'libelle': 'Libellé', 'maquette': 'Maquette', 'mention': 'Mention',
    'nb_credites': 'Nb crédités', 'nb_semestres': 'Nb semestres',
    'niveau': 'Niveau', 'nom': 'Nom', 'nom_complet': 'Nom complet',
    'numero': 'Numéro', 'ordre': 'Ordre', 'perimetre': 'Périmètre',
    'periode_debut': 'Période début', 'periode_fin': 'Période fin',
    'prix_heure_realisee': 'Prix heure réalisée', 'ref_formation': 'Réf formation',
    'semestre': 'Semestre', 'site': 'Site', 'source': 'Source', 'statut': 'Statut',
    'type_cursus': 'Type cursus', 'type_diplome': 'Type diplôme',
    'type_espace': 'Type espace', 'type_formation': 'Type formation',
    'type_lieu': 'Type lieu',
}

# Noms lisibles des modèles hors Hub, pour les dépendances non couvertes.
LIBELLES_HORS_HUB = {
    'scolarite.famillemodule': 'Famille de module (module Scolarité)',
    'scolarite.maquette': 'Maquette (module Scolarité)',
    'formations.refcategorie': 'Catégorie de formation (module Formations)',
    'formations.refgrade': 'Grade (module Formations)',
}

VALEURS_MAX_LISTE = 200      # valeurs listées par colonne de référence
LIGNES_SAISIE = 200          # lignes ouvertes à la saisie
SEPARATEUR_CSV = ';'
ENCODAGE_CSV = 'utf-8-sig'   # BOM : Excel ouvre les accents correctement


def _nettoyer_nom(valeur):
    """Nom de fichier sûr, sans caractère ambigu."""
    texte = re.sub(r'[^\w\s-]', '', str(valeur), flags=re.UNICODE).strip()
    return re.sub(r'[\s]+', '_', texte)


def entete_lisible(cle):
    """En-tête de colonne : lisible par un humain, mais reconnu par l'import."""
    return ACCENTS.get(cle, libelle_champ(cle))


def nom_fichier(slug):
    """Nom de fichier d'un référentiel, dérivé de son libellé au registre."""
    return _nettoyer_nom(REGISTRE[slug]['libelle'])


# ═══════════════════════════════════════════════════════════════════════════
# Lecture des valeurs
# ═══════════════════════════════════════════════════════════════════════════

def valeur_cellule(obj, cle, colonne):
    """Valeur d'un champ, prête à être écrite dans le tableur.

    Les booléens deviennent « Oui »/« Non » et les dates sont normalisées en
    ISO — les deux seuls formats que le moteur d'import sait relire.
    """
    valeur = getattr(obj, cle, None)
    if valeur is None:
        return ''
    if isinstance(valeur, bool):
        return 'Oui' if valeur else 'Non'
    if hasattr(valeur, 'isoformat') and not isinstance(valeur, str):
        return valeur.isoformat()
    if isinstance(valeur, models.Model):
        # Clé étrangère : la clé métier, jamais l'identifiant.
        return cle_metier_de(valeur, colonne.get('cles_metier') or [])
    return valeur


def cle_metier_de(cible, cles_metier):
    """Valeur de clé métier d'un objet lié (code prioritairement)."""
    for candidate in cles_metier:
        valeur = getattr(cible, candidate, None)
        if valeur not in (None, ''):
            return valeur
    for attribut in ('code', 'libelle', 'intitule', 'nom'):
        valeur = getattr(cible, attribut, None)
        if valeur not in (None, ''):
            return valeur
    return cible.pk


def valeurs_autorisees(slug, colonne, modele):
    """Valeurs de référence d'une colonne : liste fermée ou clés métier liées."""
    cle = colonne['cle']
    if colonne.get('relation'):
        cible = modele._meta.get_field(cle).related_model
        valeurs = []
        for objet in cible.objects.all()[:VALEURS_MAX_LISTE]:
            valeur = cle_metier_de(objet, colonne.get('cles_metier') or [])
            if valeur not in (None, ''):
                valeurs.append(str(valeur))
        return valeurs
    champ = modele._meta.get_field(cle)
    choix = getattr(champ, 'choices', None)
    if not choix:
        return []
    brut = choix.choices if hasattr(choix, 'choices') else choix
    return [str(v) for v, _l in brut]


def libelles_choix(modele, cle):
    """Paires valeur/libellé d'un champ à choix, pour la feuille Contrôles."""
    champ = modele._meta.get_field(cle)
    choix = getattr(champ, 'choices', None)
    if not choix:
        return []
    brut = choix.choices if hasattr(choix, 'choices') else choix
    return [(str(v), str(l)) for v, l in brut]


# ═══════════════════════════════════════════════════════════════════════════
# Dépendances et ordre de paramétrage
# ═══════════════════════════════════════════════════════════════════════════

def construire_index_modeles():
    """Association modèle -> slug du registre, construite une seule fois."""
    global slug_du_modele_cache
    slug_du_modele_cache = {}
    for slug, entree in REGISTRE.items():
        m = modele_de(entree)
        slug_du_modele_cache[slug] = f'{m._meta.app_label}.{m._meta.model_name}'


slug_du_modele_cache = {}


def dependances_du(slug):
    """Référentiels du Hub à renseigner avant celui-ci (clés étrangères).

    Renvoie ``(dans_le_hub, hors_hub)`` : les dépendances que le kit couvre,
    et celles qui relèvent d'un autre module de l'application.
    """
    modele = modele_de(REGISTRE[slug])
    dans_hub, hors_hub = [], []
    for colonne in champs_importables(modele):
        if not colonne.get('relation'):
            continue
        cible = colonne['modele_lie']
        autre = None
        for s, cle_modele in slug_du_modele_cache.items():
            if cle_modele == cible and s != slug:
                autre = s
                break
        if autre:
            if autre not in dans_hub:
                dans_hub.append(autre)
        elif cible not in hors_hub:
            hors_hub.append(cible)
    return dans_hub, hors_hub


def ordre_de_paramétrage():
    """Niveau de priorité de chaque référentiel (0 = à paramétrer en premier)."""
    niveaux, en_cours = {}, {}

    def niveau(slug):
        if slug in niveaux:
            return niveaux[slug]
        if slug in en_cours:          # cycle : on casse sans planter
            return 0
        en_cours[slug] = True
        prerequis, _ = dependances_du(slug)
        valeur = max([niveau(p) + 1 for p in prerequis], default=0)
        en_cours.pop(slug, None)
        niveaux[slug] = valeur
        return valeur

    for slug in REGISTRE:
        niveau(slug)
    return niveaux


# ═══════════════════════════════════════════════════════════════════════════
# Mise en forme
# ═══════════════════════════════════════════════════════════════════════════

def ecrire_ligne(feuille, numero, valeurs, *, gras=False, couleur=None,
                 alignement=None, format_nombre=None):
    for position, valeur in enumerate(valeurs, start=1):
        cellule = feuille.cell(row=numero, column=position, value=valeur)
        cellule.border = BORDURE
        if gras:
            cellule.font = Font(bold=True)
        if couleur:
            cellule.fill = PatternFill('solid', fgColor=couleur)
        if alignement:
            cellule.alignment = Alignment(**alignement)
        if format_nombre:
            cellule.number_format = format_nombre
    return numero + 1


def bandeau(feuille, titre, sous_titre='', largeur=8):
    """Titre de feuille, sur deux lignes, avec volets figés dessous."""
    largeur = max(largeur, 6)
    feuille.merge_cells(start_row=1, start_column=1, end_row=1, end_column=largeur)
    cellule = feuille.cell(row=1, column=1, value=titre)
    cellule.font = Font(bold=True, size=14, color='FFFFFF')
    cellule.fill = PatternFill('solid', fgColor=COULEUR_ENTETE)
    cellule.alignment = Alignment(vertical='center')
    feuille.row_dimensions[1].height = 26
    if sous_titre:
        feuille.merge_cells(start_row=2, start_column=1, end_row=2, end_column=largeur)
        cellule = feuille.cell(row=2, column=1, value=sous_titre)
        cellule.font = Font(italic=True, size=10, color='FFFFFF')
        cellule.fill = PatternFill('solid', fgColor=COULEUR_BANDEAU)
        feuille.row_dimensions[2].height = 18
        return 4
    return 3


def ajuster_largeurs(feuille, largeurs):
    for position, largeur in enumerate(largeurs, start=1):
        feuille.column_dimensions[get_column_letter(position)].width = largeur


def texte_long(feuille, numero, texte, largeur=8, hauteur=None):
    """Paragraphe fusionné, pour les consignes."""
    feuille.merge_cells(start_row=numero, start_column=1,
                        end_row=numero, end_column=largeur)
    cellule = feuille.cell(row=numero, column=1, value=texte)
    cellule.alignment = Alignment(wrap_text=True, vertical='top')
    if hauteur:
        feuille.row_dimensions[numero].height = hauteur
    return numero + 1


# ═══════════════════════════════════════════════════════════════════════════
# Génération d'un classeur de référentiel
# ═══════════════════════════════════════════════════════════════════════════

class Command(BaseCommand):
    help = ("Génère le kit de fichiers de remplissage (XLSX + CSV) du Hub "
            "« Référentiels », dérivé du registre et des modèles réels.")

    def add_arguments(self, parser):
        parser.add_argument('--dossier', default=None,
                            help='Dossier de destination (défaut : KIT_REMPLISSAGE_INJS_2026 '
                                 'à la racine du dépôt).')
        parser.add_argument('--exemples', type=int, default=5,
                            help="Nombre de lignes d'exemple par référentiel (défaut : 5).")

    # ── Point d'entrée ─────────────────────────────────────────────────────
    def handle(self, *args, **options):
        construire_index_modeles()
        if options['dossier']:
            racine = Path(options['dossier'])
        else:
            # parents[4] : commands > management > referentiels > backend > dépôt.
            racine = Path(__file__).resolve().parents[4] / 'KIT_REMPLISSAGE_INJS_2026'
        self.racine = racine
        self.nb_exemples = options['exemples']
        self.rapport = []

        self._verifier_entetes()

        if racine.exists():
            for fichier in sorted(racine.rglob('*'), reverse=True):
                if fichier.is_file():
                    fichier.unlink()
                elif fichier.is_dir() and not any(fichier.iterdir()):
                    fichier.rmdir()
        for nom in (DOSSIER_GUIDE, DOSSIER_DEMO, *CATEGORIES.values()):
            (racine / nom).mkdir(parents=True, exist_ok=True)

        self.index = {}
        for slug in REGISTRE:
            self._generer_referentiel(slug)

        self._generer_guide()
        self._generer_index_general()
        self._generer_ordre()
        self._generer_demo()
        self._generer_rapport()
        self._generer_pdf()

        self.stdout.write(self.style.SUCCESS(
            f'Kit généré : {racine} — {len(REGISTRE)} référentiels, '
            f'{len(REGISTRE) * 2} fichiers de données.'))
        for ligne in self.rapport:
            self.stdout.write(f'  · {ligne}')

    # ── Contrôle préalable ─────────────────────────────────────────────────
    def _verifier_entetes(self):
        """Garantit que chaque en-tête produit reste reconnu par l'import."""
        problems = []
        for slug in REGISTRE:
            modele = modele_de(REGISTRE[slug])
            for colonne in champs_importables(modele):
                cle = colonne['cle']
                attendu = normaliser_entete(libelle_champ(cle))
                produit = normaliser_entete(entete_lisible(cle))
                if attendu != produit:
                    problems.append(f'{slug}.{cle}: {attendu!r} != {produit!r}')
        if problems:
            raise SystemExit('En-têtes non reconnus par le moteur d’import :\n  '
                             + '\n  '.join(problems))

    # ── Colonnes ───────────────────────────────────────────────────────────
    def _colonnes_de(self, slug):
        """Colonnes du tableur : identité, puis relations, puis le reste."""
        modele = modele_de(REGISTRE[slug])
        brut = champs_importables(modele)
        identite = REGISTRE[slug].get('champ_libelle') or 'libelle'
        code = REGISTRE[slug].get('champ_code') or 'code'

        def rang(colonne):
            if colonne['cle'] == code:
                return 0
            if colonne['cle'] == identite:
                return 1
            if colonne.get('relation'):
                return 2
            return 3 if colonne['obligatoire'] else 4

        retour = []
        for colonne in sorted(brut, key=lambda c: (rang(c), entete_lisible(c['cle']))):
            copie = dict(colonne)
            copie['entete'] = entete_lisible(colonne['cle'])
            retour.append(copie)
        return retour

    # ── Classeur d'un référentiel ──────────────────────────────────────────
    def _generer_referentiel(self, slug):
        entree = REGISTRE[slug]
        modele = modele_de(entree)
        colonnes = self._colonnes_de(slug)
        dossier = self.racine / CATEGORIES[str(entree['categorie'])]
        base = nom_fichier(slug)

        prerequis, hors_hub = dependances_du(slug)
        valeurs = {c['cle']: valeurs_autorisees(slug, c, modele) for c in colonnes}
        exemples = self._lignes_d_exemple(modele, colonnes)

        classeur = Workbook()
        classeur.remove(classeur.active)
        self._feuille_instructions(classeur, slug, colonnes, prerequis, hors_hub)
        self._feuille_donnees(classeur, slug, colonnes, valeurs)
        ranges = self._feuille_references(classeur, slug, colonnes, valeurs, hors_hub)
        self._feuille_exemple(classeur, slug, colonnes, exemples)
        self._feuille_controles(classeur, slug, colonnes, valeurs)

        if ranges:
            self._feuille_donnees(classeur, slug, colonnes, valeurs, listes=ranges,
                                  reprise=True)

        classeur.save(dossier / f'{base}.xlsx')
        self._ecrire_csv(dossier / f'{base}.csv', colonnes, exemples)

        self.index[slug] = {
            'entree': entree, 'modele': modele, 'colonnes': colonnes,
            'prerequis': prerequis, 'hors_hub': hors_hub, 'fichier': base,
            'dossier': CATEGORIES[str(entree['categorie'])],
            'exemples': exemples,
            'total_base': modele.objects.count(),
        }

    # ── Feuille Instructions ───────────────────────────────────────────────
    def _feuille_instructions(self, classeur, slug, colonnes, prerequis, hors_hub):
        entree = REGISTRE[slug]
        feuille = classeur.create_sheet('Instructions')
        numero = bandeau(feuille, f"{entree['libelle']} — mode d'emploi",
                         f"Référentiel « {slug} » · {self.index_ou_modele(slug)}")

        obligations = [c for c in colonnes if c['obligatoire']]
        relations = [c for c in colonnes if c.get('relation')]

        if not entree.get('editable'):
            numero = texte_long(
                feuille, numero,
                "ATTENTION — référentiel consultable, mais non modifiable depuis le Hub.\n"
                f"Il est maintenu depuis son module d'origine "
                f"({entree.get('route_ui') or 'module dédié'}). Le Hub n'expose donc pas "
                "d'import pour ce référentiel : ce classeur documente le modèle et sert "
                "de référence, il n'est pas destiné à être importé ici.",
                hauteur=48)
            numero += 1

        texte_long(feuille, numero, 'Objet', hauteur=16)
        numero += 1
        numero = texte_long(feuille, numero, str(entree.get('description') or
                                                 'Aucune description déclarée au registre.'),
                            hauteur=30)
        numero += 1

        texte_long(feuille, numero, 'Ordre de saisie', hauteur=16)
        numero += 1
        if prerequis:
            liste = ', '.join(REGISTRE[p]['libelle'] for p in prerequis)
            texte = (f'À renseigner APRÈS : {liste}. Ces référentiels fournissent les '
                     f'valeurs des colonnes de liaison de cette feuille.')
        else:
            texte = ('Aucun préalable dans le Hub : ce référentiel peut être saisi '
                     'en premier.')
        numero = texte_long(feuille, numero, texte, hauteur=30)
        numero += 1
        if hors_hub:
            liste = '; '.join(LIBELLES_HORS_HUB.get(h, h) for h in hors_hub)
            texte = (f'Dépendances hors Hub, à créer depuis leur propre module avant '
                     f'la saisie : {liste}.')
            numero = texte_long(feuille, numero, texte, hauteur=30)
            numero += 1

        texte_long(feuille, numero, 'Comment remplir', hauteur=16)
        numero += 1
        for ligne in [
            "1. Ouvrez la feuille « Données » : c'est la seule à compléter. "
            "Les en-têtes sont figés et les filtres activés.",
            "2. Une colonne sur fond rose est OBLIGATOIRE ; sur fond vert, facultative.",
            "3. Les colonnes à liste déroulante sont fermées : choisissez dans la liste, "
            "toute autre valeur sera refusée à l'import.",
            "4. Pour une colonne de liaison, saisissez la CLÉ MÉTIER de la ligne visée "
            "(son code, ou à défaut son libellé) — jamais un identifiant numérique.",
            "5. Laissez la cellule VIDE (et non 0) pour « non renseigné » sur les "
            "colonnes numériques et les dates.",
            "6. La feuille « Exemple » montre des lignes valides, réellement présentes "
            "dans votre base locale : inspirez-vous-en.",
            f"7. Enregistrez, puis importez le fichier depuis l'écran du Hub "
            f"(« {entree['libelle']} » > Importer), en déclarant la première ligne "
            f"comme en-tête.",
        ]:
            numero = texte_long(feuille, numero, ligne, hauteur=28)
        numero += 1

        texte_long(feuille, numero, 'Formats attendus', hauteur=16)
        numero += 1
        for ligne in [
            '· Dates : AAAA-MM-JJ (ex. 2026-09-15). Le format français JJ/MM/AAAA est '
            'refusé par le moteur d’import.',
            '· Nombres décimaux : point ou virgule (ex. 12.5 ou 12,5).',
            '· Booléens : Oui / Non (ou vrai/faux, 1/0).',
            '· CSV : encodage UTF-8, séparateur point-virgule, une seule ligne '
            "d'en-tête.",
        ]:
            numero = texte_long(feuille, numero, ligne, hauteur=28)
        numero += 1

        texte_long(feuille, numero, 'Récapitulatif', hauteur=16)
        numero += 1
        stats = [
            ('Colonnes au total', str(len(colonnes))),
            ('Colonnes obligatoires', str(len(obligations))),
            ('Colonnes de liaison', str(len(relations))),
            ('Lignes actuellement en base', str(self._total(slug))),
        ]
        for etiquette, valeur in stats:
            feuille.cell(row=numero, column=1, value=etiquette).font = Font(bold=True)
            feuille.cell(row=numero, column=2, value=valeur)
            numero += 1
        ajuster_largeurs(feuille, [46, 18, 14, 14, 14, 14, 14, 14])

    def index_ou_modele(self, slug):
        modele = modele_de(REGISTRE[slug])
        return f'{modele._meta.app_label}.{modele._meta.object_name}'

    def _total(self, slug):
        return modele_de(REGISTRE[slug]).objects.count()

    # ── Feuille Données ────────────────────────────────────────────────────
    def _feuille_donnees(self, classeur, slug, colonnes, valeurs, listes=None,
                         reprise=False):
        if reprise:
            feuille = classeur['Données']
        else:
            feuille = classeur.create_sheet('Données')
        entree = REGISTRE[slug]
        titre = f"{entree['libelle']} — données à renseigner"
        bandeau(feuille, titre, 'Complétez une ligne par valeur. Ne modifiez pas les '
                                "en-têtes : l'import s'en sert pour reconnaître les colonnes.")
        ligne_entete = 4

        for position, colonne in enumerate(colonnes, start=1):
            cellule = feuille.cell(row=ligne_entete, column=position,
                                   value=colonne['entete'])
            cellule.font = Font(bold=True, color='FFFFFF')
            cellule.fill = PatternFill(
                'solid', fgColor=COULEUR_OBLIG if colonne['obligatoire'] else COULEUR_FACULT)
            cellule.alignment = Alignment(wrap_text=True, vertical='center',
                                          horizontal='center')
            cellule.border = BORDURE
            if not colonne['obligatoire']:
                cellule.font = Font(bold=True, color='1F3864')
        feuille.row_dimensions[ligne_entete].height = 30
        feuille.freeze_panes = feuille.cell(row=ligne_entete + 1, column=1)
        feuille.auto_filter.ref = (
            f'A{ligne_entete}:'
            f'{get_column_letter(len(colonnes))}{ligne_entete + LIGNES_SAISIE}')

        for position, colonne in enumerate(colonnes, start=1):
            lettre = get_column_letter(position)
            longueur = max(len(colonne['entete']) + 4, 14)
            feuille.column_dimensions[lettre].width = min(longueur, 42)
            format_nombre = self._format_cellule(colonne)
            for ligne in range(ligne_entete + 1, ligne_entete + 1 + LIGNES_SAISIE):
                feuille.cell(row=ligne, column=position).number_format = format_nombre

        if listes:
            self._poser_listes(feuille, classeur, colonnes, listes, ligne_entete)

    @staticmethod
    def _format_cellule(colonne):
        type_champ = colonne['type']
        if 'DateField' in type_champ:
            return 'YYYY-MM-DD'
        if 'DecimalField' in type_champ:
            return '#,##0.00'
        if 'IntegerField' in type_champ:
            return '0'
        return 'General'

    def _poser_listes(self, feuille, classeur, colonnes, listes, ligne_entete):
        """Listes déroulantes, adossées à des plages nommées."""
        from openpyxl.worksheet.datavalidation import DataValidation

        for position, colonne in enumerate(colonnes, start=1):
            nom = listes.get(colonne['cle'])
            if not nom:
                continue
            lettre = get_column_letter(position)
            plage = (f'{lettre}{ligne_entete + 1}:'
                     f'{lettre}{ligne_entete + LIGNES_SAISIE}')
            validation = DataValidation(type='list', formula1=f'={nom}',
                                        allow_blank=True, showDropDown=False)
            validation.error = ('Valeur non autorisée : choisissez une entrée de la '
                                'liste, sinon la ligne sera rejetée à l’import.')
            validation.errorTitle = 'Valeur hors liste'
            feuille.add_data_validation(validation)
            validation.add(plage)

    # ── Feuille Références ─────────────────────────────────────────────────
    def _feuille_references(self, classeur, slug, colonnes, valeurs, hors_hub):
        feuille = classeur.create_sheet('Références')
        bandeau(feuille, f"{REGISTRE[slug]['libelle']} — valeurs de référence",
                'Valeurs admises. Les listes fermées alimentent les déroulantes de la '
                'feuille « Donnees » ; les liaisons se saisissent par clé métier.')
        entetes = ['Colonne', 'Obligatoire', 'Nature', 'Provenance',
                   'Nb de valeurs', 'Valeurs admises']
        ecrire_ligne(feuille, 4, entetes, gras=True, couleur=COULEUR_TITRE)
        ajuster_largeurs(feuille, [30, 13, 26, 44, 13, 60])

        ligne = 5
        listes = {}
        for colonne in colonnes:
            cle = colonne['cle']
            admises = valeurs.get(cle) or []
            if colonne.get('relation'):
                cible = colonne['modele_lie']
                autre = self._slug_de(cible)
                if autre:
                    nature = f'Liaison → {REGISTRE[autre]["libelle"]}'
                    provenance = (f'Clé métier : {", ".join(colonne["cles_metier"])}. '
                                  f'Valeurs issues du fichier '
                                  f'{nom_fichier(autre)}.xlsx')
                else:
                    nature = f'Liaison → {LIBELLES_HORS_HUB.get(cible, cible)}'
                    provenance = ('Hors Hub : à créer depuis son propre module. '
                                  f'Clé métier : {", ".join(colonne["cles_metier"])}')
            elif 'BooleanField' in colonne['type']:
                admises = ['Oui', 'Non']
                nature = 'Booléen'
                provenance = ('Oui / Non. Acceptés aussi à l’import : oui, vrai, '
                              'true, 1 / non, faux, false, 0.')
            elif admises:
                nature = 'Liste fermée'
                champ = modele_de(REGISTRE[slug])._meta.get_field(cle)
                provenance = f'Valeurs autorisées par le modèle ({type(champ).__name__})'
            else:
                continue

            ecrire_ligne(feuille, ligne, [
                colonne['entete'],
                'Obligatoire' if colonne['obligatoire'] else 'Facultatif',
                nature, provenance,
                len(admises) if colonne.get('relation') or admises else '',
                '',
            ], alignement={'wrap_text': True, 'vertical': 'top'})
            feuille.row_dimensions[ligne].height = 30

            if admises:
                for decalage, valeur in enumerate(admises):
                    feuille.cell(row=ligne, column=6 + decalage, value=valeur)
                debut = get_column_letter(6)
                fin = get_column_letter(6 + len(admises) - 1)
                nom = f'Liste_{_nettoyer_nom(slug)}_{_nettoyer_nom(cle)}'[:255]
                nom = re.sub(r'\W', '_', nom)
                classeur.defined_names.add(DefinedName(
                    nom, attr_text=f"'Références'!${debut}${ligne}:${fin}${ligne}"))
                listes[cle] = nom
            ligne += 1

        if hors_hub:
            ligne += 1
            feuille.cell(row=ligne, column=1, value='Dépendances hors du Hub').font = \
                Font(bold=True)
            ligne += 1
            for cible in hors_hub:
                feuille.cell(row=ligne, column=1,
                             value=LIBELLES_HORS_HUB.get(cible, cible))
                ligne += 1
        return listes

    @staticmethod
    def _slug_de(cible):
        for slug, cle in slug_du_modele_cache.items():
            if cle == cible:
                return slug
        return None

    # ── Feuille Exemple ────────────────────────────────────────────────────
    def _lignes_d_exemple(self, modele, colonnes):
        """Lignes d'exemple : les premières valeurs réellement présentes."""
        ordre = getattr(modele._meta, 'ordering', None) or ['pk']
        lignes = []
        for objet in modele.objects.all().order_by(*ordre)[:self.nb_exemples]:
            lignes.append([valeur_cellule(objet, c['cle'], c) for c in colonnes])
        return lignes

    def _feuille_exemple(self, classeur, slug, colonnes, exemples):
        feuille = classeur.create_sheet('Exemple')
        bandeau(feuille, f"{REGISTRE[slug]['libelle']} — exemples",
                'Lignes réellement extraites de votre base locale : elles montrent le '
                'format exact attendu. Remplacez-les par vos données.')
        ecrire_ligne(feuille, 4, [c['entete'] for c in colonnes], gras=True,
                     couleur=COULEUR_TITRE,
                     alignement={'wrap_text': True, 'horizontal': 'center'})
        feuille.row_dimensions[4].height = 28
        feuille.freeze_panes = 'A5'
        feuille.auto_filter.ref = (
            f'A4:{get_column_letter(len(colonnes))}{4 + max(len(exemples), 1)}')
        ligne = 5
        for rangee in exemples:
            for position, valeur in enumerate(rangee, start=1):
                cellule = feuille.cell(row=ligne, column=position, value=valeur)
                cellule.border = BORDURE
                cellule.number_format = self._format_cellule(colonnes[position - 1])
                cellule.alignment = Alignment(vertical='top')
            ligne += 1
        if not exemples:
            feuille.cell(row=5, column=1, value="(aucune valeur en base pour l'instant)")
        ajuster_largeurs(feuille, [min(max(len(c['entete']) + 4, 14), 42)
                                   for c in colonnes])

    # ── Feuille Contrôles ──────────────────────────────────────────────────
    def _feuille_controles(self, classeur, slug, colonnes, valeurs):
        modele = modele_de(REGISTRE[slug])
        feuille = classeur.create_sheet('Contrôles')
        bandeau(feuille, f"{REGISTRE[slug]['libelle']} — contrôles et règles",
                "Contrôles appliqués à l'import. Une ligne en erreur est signalée sans "
                'rien écrire : corrigez puis relancez.')
        ecrire_ligne(feuille, 4, ['Colonne', 'Règle', 'Détail'],
                     gras=True, couleur=COULEUR_TITRE)
        ajuster_largeurs(feuille, [30, 30, 82])

        ligne = 5
        for colonne in colonnes:
            cle = colonne['cle']
            champ = modele._meta.get_field(cle)
            regles = []
            if colonne['obligatoire']:
                regles.append(('Obligatoire', 'Toute ligne vide sur cette colonne est '
                                              'rejetée.'))
            else:
                defaut = getattr(champ, 'default', None)
                if defaut is not models.NOT_PROVIDED and not callable(defaut):
                    regles.append(('Facultatif', f'Valeur par défaut : {defaut}.'))
                else:
                    regles.append(('Facultatif', 'Peut rester vide.'))
            if colonne.get('relation'):
                cible = colonne['modele_lie']
                regles.append(('Résolution de liaison',
                               f'La valeur doit correspondre à une ligne existante de '
                               f'{cible}, par : {", ".join(colonne["cles_metier"])}. '
                               f'Référence introuvable ou ambiguë = ligne rejetée.'))
            elif valeurs.get(cle):
                paires = libelles_choix(modele, cle)
                detail = ', '.join(f'{v} ({l})' for v, l in paires[:25])
                if len(paires) > 25:
                    detail += f' … et {len(paires) - 25} autre(s)'
                regles.append(('Liste fermée', detail))
            if 'IntegerField' in colonne['type']:
                regles.append(('Nombre entier', 'Aucun séparateur de milliers, pas de '
                                                'décimale.'))
            elif 'DecimalField' in colonne['type']:
                regles.append(('Nombre décimal', 'Point ou virgule comme décimale ; '
                                                 'max_digits=%s, décimales=%s.' % (
                                                     getattr(champ, 'max_digits', '?'),
                                                     getattr(champ, 'decimal_places', '?'))))
            elif 'DateField' in colonne['type']:
                regles.append(('Date ISO', 'Format strict AAAA-MM-JJ (ex. 2026-09-15). '
                                           'JJ/MM/AAAA est refusé.'))
            elif 'BooleanField' in colonne['type']:
                regles.append(('Booléen', 'Oui / Non (oui, vrai, true, 1 acceptés).'))
            if getattr(champ, 'max_length', None):
                regles.append(('Longueur', f'{champ.max_length} caractères au maximum.'))
            if getattr(champ, 'unique', False):
                regles.append(('Unicité', 'Valeur unique dans tout le référentiel.'))

            for regle, detail in regles:
                ecrire_ligne(feuille, ligne, [colonne['entete'], regle, detail],
                             alignement={'wrap_text': True, 'vertical': 'top'})
                feuille.row_dimensions[ligne].height = 28
                ligne += 1

        for contrainte in getattr(modele._meta, 'constraints', []):
            champs = getattr(contrainte, 'fields', None)
            if champs:
                ecrire_ligne(feuille, ligne, [
                    ' + '.join(champs), 'Unicité combinée',
                    'Le couple de valeurs doit être unique : '
                    f'« {" + ".join(champs)} » ne peut pas se répéter.'],
                    alignement={'wrap_text': True, 'vertical': 'top'})
                ligne += 1
        return ligne

    # ── CSV ────────────────────────────────────────────────────────────────
    def _ecrire_csv(self, chemin, colonnes, exemples):
        with open(chemin, 'w', newline='', encoding=ENCODAGE_CSV) as flux:
            writer = csv.writer(flux, delimiter=SEPARATEUR_CSV, quoting=csv.QUOTE_MINIMAL)
            writer.writerow([c['entete'] for c in colonnes])
            for rangee in exemples:
                writer.writerow(['' if v is None else v for v in rangee])

    # ═══════════════════════════════════════════════════════════════════════
    # Fichiers transverses
    # ═══════════════════════════════════════════════════════════════════════

    def _generer_guide(self):
        classeur = Workbook()
        feuille = classeur.active
        feuille.title = 'Guide'
        numero = bandeau(feuille, 'Guide de remplissage — INJS 2026',
                         'Kit de fichiers de remplissage du Hub « Référentiels »')
        ajuster_largeurs(feuille, [34, 100])

        sections = [
            ("Objet du kit",
             "Un classeur et un CSV par référentiel du Hub. Les colonnes sont celles des "
             "modèles Django réels : aucune n'est inventée, et les en-têtes sont reconnus "
             "automatiquement par le moteur d'import de l'application."),
            ("Contenu d'un classeur",
             "· Instructions — objet, préalables, marche à suivre et formats.\n"
             "· Donnees — la seule feuille à compléter (en-têtes figés, filtres, "
             "déroulantes).\n"
             "· References — valeurs admises et clés de liaison, une ligne par colonne.\n"
             "· Exemple — lignes réelles extraites de votre base locale.\n"
             "· Controles — règles appliquées à l'import, colonne par colonne."),
            ("Couleurs",
             "En-tête rose = colonne obligatoire. En-tête vert = colonne facultative."),
            ("Clés étrangères",
             "Elles ne se saisissent JAMAIS avec un identifiant numérique : on indique la "
             "clé métier de la ligne visée (son code, ou à défaut son libellé). La feuille "
             "« References » précise, pour chaque liaison, quel champ utiliser."),
            ("Formats",
             "Dates au format AAAA-MM-JJ (le format français JJ/MM/AAAA est refusé). "
             "Décimaux au point ou à la virgule. Booléens en Oui / Non. "
             "Cellule vide = non renseigné (et non 0)."),
            ("CSV",
             "Encodage UTF-8 avec indicateur d'ordre des octets, séparateur point-virgule, "
             "une seule ligne d'en-tête. Ouvrez-les de préférence depuis l'import de "
             "l'application plutôt qu'en double-cliquant, pour éviter qu'Excel ne "
             "réinterprète les colonnes."),
            ("Ordre de remplissage",
             "Consultez ORDRE_PARAMETRAGE.xlsx : il donne l'ordre issu des dépendances "
             "réelles entre référentiels (clés étrangères). Renseigner un référentiel "
             "avant ceux dont il dépend fait échouer la résolution des liaisons."),
            ("Import dans l'application",
             "Hub « Référentiels » > ouvrir le référentiel > Importer. Déposez le fichier, "
             "cochez « première ligne = en-tête », vérifiez l'analyse (colonnes reconnues, "
             "doublons, erreurs), puis appliquez. L'import est idempotent : les lignes déjà "
             "présentes ne sont pas dupliquées."),
            ("Régénération",
             "Le kit est produit par la commande « python manage.py generer_kit_remplissage ». "
             "Relancez-la après toute évolution des modèles : colonnes, listes et exemples "
             "seront remis à jour."),
        ]
        for titre, texte in sections:
            feuille.cell(row=numero, column=1, value=titre).font = Font(
                bold=True, color=COULEUR_ENTETE)
            cellule = feuille.cell(row=numero, column=2, value=texte)
            cellule.alignment = Alignment(wrap_text=True, vertical='top')
            feuille.row_dimensions[numero].height = max(30, 13 * (texte.count('\n') + 1
                                                                  + len(texte) // 95))
            numero += 1

        classeur.save(self.racine / DOSSIER_GUIDE / 'Guide_remplissage_INJS.xlsx')
        self.rapport.append('Guide_remplissage_INJS.xlsx')

    def _generer_index_general(self):
        classeur = Workbook()
        feuille = classeur.active
        feuille.title = 'Index'
        bandeau(feuille, 'INDEX GENERAL — référentiels du Hub',
                f'{len(REGISTRE)} référentiels · colonnes dérivées des modèles Django réels')
        entetes = ['N°', 'Référentiel', 'Catégorie', 'Modèle Django', 'Dossier',
                   'Fichier', 'Colonnes', 'dont obligatoires', 'Liaisons',
                   'Préalables (Hub)', 'Valeurs en base', 'Importable (Hub)', 'Statut']
        ecrire_ligne(feuille, 4, entetes, gras=True, couleur=COULEUR_TITRE)
        ajuster_largeurs(feuille, [5, 34, 15, 34, 34, 30, 10, 17, 10, 34, 15, 16, 16])
        feuille.freeze_panes = 'A5'

        ligne = 5
        for numero, slug in enumerate(sorted(REGISTRE), start=1):
            donnees = self.index[slug]
            colonnes = donnees['colonnes']
            ecrire_ligne(feuille, ligne, [
                numero,
                REGISTRE[slug]['libelle'],
                str(REGISTRE[slug]['categorie']),
                self.index_ou_modele(slug),
                donnees['dossier'],
                f"{donnees['fichier']}.xlsx",
                len(colonnes),
                sum(1 for c in colonnes if c['obligatoire']),
                sum(1 for c in colonnes if c.get('relation')),
                ', '.join(REGISTRE[p]['libelle'] for p in donnees['prerequis']) or '—',
                donnees['total_base'],
                'Oui' if REGISTRE[slug]['editable'] else 'Non — voir module d’origine',
                'À faire',
            ])
            ligne += 1
        feuille.auto_filter.ref = f'A4:{get_column_letter(len(entetes))}{ligne - 1}'

        from openpyxl.worksheet.datavalidation import DataValidation
        validation = DataValidation(
            type='list', formula1='"À faire,En cours,Terminé,Non concerné"',
            allow_blank=True, showDropDown=False)
        feuille.add_data_validation(validation)
        validation.add(f'M5:M{ligne - 1}')

        classeur.save(self.racine / 'INDEX_GENERAL.xlsx')
        self.rapport.append('INDEX_GENERAL.xlsx')

    def _generer_ordre(self):
        niveaux = ordre_de_paramétrage()
        ordonne = sorted(REGISTRE, key=lambda s: (niveaux[s],
                                                  str(REGISTRE[s]['categorie']), s))
        classeur = Workbook()
        feuille = classeur.active
        feuille.title = 'Ordre de paramétrage'
        bandeau(feuille, 'ORDRE DE PARAMETRAGE',
                'Ordre déduit des dépendances réelles entre référentiels (clés étrangères). '
                'Un niveau regroupe des référentiels indépendants entre eux : ils peuvent '
                'être saisis dans n’importe quel ordre à l’intérieur du niveau.')
        entetes = ['Ordre', 'Niveau', 'Module concerné', 'Référentiels préalables',
                   'Champs obligatoires', 'Dépendances hors Hub', 'Priorité',
                   'Fichier', 'Valeurs en base', 'Importable (Hub)',
                   'Statut de remplissage']
        ecrire_ligne(feuille, 4, entetes, gras=True, couleur=COULEUR_TITRE)
        ajuster_largeurs(feuille, [7, 8, 34, 40, 52, 34, 10, 30, 15, 30, 22])
        feuille.freeze_panes = 'A5'

        ligne = 5
        for rang, slug in enumerate(ordonne, start=1):
            donnees = self.index[slug]
            obligatoires = [c['entete'] for c in donnees['colonnes'] if c['obligatoire']]
            entree = REGISTRE[slug]
            ecrire_ligne(feuille, ligne, [
                rang,
                niveaux[slug],
                entree['libelle'],
                ', '.join(REGISTRE[p]['libelle'] for p in donnees['prerequis']) or '—',
                ', '.join(obligatoires) or '—',
                ', '.join(LIBELLES_HORS_HUB.get(h, h) for h in donnees['hors_hub']) or '—',
                'Haute' if niveaux[slug] == 0 else (
                    'Moyenne' if niveaux[slug] == 1 else 'Basse'),
                f"{donnees['fichier']}.xlsx",
                donnees['total_base'],
                'Oui' if entree['editable'] else 'Non — module d’origine',
                'À faire',
            ], alignement={'wrap_text': True, 'vertical': 'top'})
            feuille.row_dimensions[ligne].height = 30
            ligne += 1
        feuille.auto_filter.ref = f'A4:{get_column_letter(len(entetes))}{ligne - 1}'

        from openpyxl.worksheet.datavalidation import DataValidation
        validation = DataValidation(
            type='list', formula1='"À faire,En cours,Terminé,Non concerné"',
            allow_blank=True, showDropDown=False)
        feuille.add_data_validation(validation)
        validation.add(f'K5:K{ligne - 1}')

        classeur.save(self.racine / 'ORDRE_PARAMETRAGE.xlsx')
        self.rapport.append('ORDRE_PARAMETRAGE.xlsx')
        self.ordre = [(r, s, niveaux[s])
                      for r, s in enumerate(ordonne, start=1)]

    def _generer_demo(self):
        """Classeur consolidé : une feuille d'exemples par référentiel."""
        classeur = Workbook()
        classeur.remove(classeur.active)
        for slug in sorted(REGISTRE):
            donnees = self.index[slug]
            colonnes = donnees['colonnes']
            feuille = classeur.create_sheet(nom_fichier(slug)[:31])
            ecrire_ligne(feuille, 1, [c['entete'] for c in colonnes], gras=True,
                         couleur=COULEUR_TITRE,
                         alignement={'wrap_text': True, 'horizontal': 'center'})
            feuille.freeze_panes = 'A2'
            feuille.auto_filter.ref = (
                f'A1:{get_column_letter(len(colonnes))}'
                f'{1 + max(len(donnees["exemples"]), 1)}')
            for position, colonne in enumerate(colonnes, start=1):
                feuille.column_dimensions[get_column_letter(position)].width = \
                    min(max(len(colonne['entete']) + 4, 14), 42)
            for num, rangee in enumerate(donnees['exemples'], start=2):
                for position, valeur in enumerate(rangee, start=1):
                    cellule = feuille.cell(row=num, column=position, value=valeur)
                    cellule.number_format = self._format_cellule(colonnes[position - 1])
        chemin = self.racine / DOSSIER_DEMO / 'Donnees_demo_consolidees.xlsx'
        classeur.save(chemin)
        self.rapport.append('Donnees_demo_consolidees.xlsx')

    # ── Rapport ─────────────────────────────────────────────────────────────
    def _generer_rapport(self):
        """Rapport de génération : dénombrements et correspondance des modèles."""
        from django.utils import timezone

        lignes = []
        lignes.append('# Rapport de génération — kit de remplissage INJS 2026')
        lignes.append('')
        lignes.append(f'Généré le {timezone.localtime().strftime("%d/%m/%Y à %H:%M")} '
                      'par `python manage.py generer_kit_remplissage`.')
        lignes.append('')
        lignes.append('## Dénombrements')
        lignes.append('')
        lignes.append(f'- Référentiels du Hub (modules) : **{len(REGISTRE)}**')
        lignes.append(f'- Fichiers Excel générés : **{len(REGISTRE) + 4}** '
                      f'({len(REGISTRE)} référentiels + guide, index, ordre, démonstration)')
        lignes.append(f'- Fichiers CSV générés : **{len(REGISTRE)}**')
        lignes.append('- Fichier PDF : **1** (guide)')
        colonnes_total = sum(len(d['colonnes']) for d in self.index.values())
        lignes.append(f'- Colonnes de saisie au total : **{colonnes_total}**')
        lignes.append('')
        lignes.append('## Répartition par catégorie')
        lignes.append('')
        lignes.append('| Catégorie | Dossier | Référentiels | Colonnes |')
        lignes.append('|---|---|---|---|')
        for cle, dossier in CATEGORIES.items():
            slugs = [s for s in REGISTRE if str(REGISTRE[s]['categorie']) == cle]
            colonnes = sum(len(self.index[s]['colonnes']) for s in slugs)
            lignes.append(f'| {cle} | `{dossier}` | {len(slugs)} | {colonnes} |')
        lignes.append('')
        lignes.append('## Correspondance modèle par modèle')
        lignes.append('')
        lignes.append('| Référentiel | Modèle Django | Colonnes | Obligatoires | '
                      'Liaisons | Importable | Fichier |')
        lignes.append('|---|---|---|---|---|---|---|')
        for slug in sorted(REGISTRE, key=lambda s: str(REGISTRE[s]['categorie'])):
            d = self.index[slug]
            c = d['colonnes']
            lignes.append(
                f"| {REGISTRE[slug]['libelle']} | `{self.index_ou_modele(slug)}` | "
                f"{len(c)} | {sum(1 for x in c if x['obligatoire'])} | "
                f"{sum(1 for x in c if x.get('relation'))} | "
                f"{'oui' if REGISTRE[slug]['editable'] else 'non'} | "
                f"`{d['fichier']}.xlsx` |")
        lignes.append('')
        lignes.append('## Source des données')
        lignes.append('')
        lignes.append('- Les colonnes proviennent de `colonnes.champs_importables()` : '
                      "exactement ce que le moteur d'import sait résoudre.")
        lignes.append('- Les listes de valeurs et les exemples sont lus depuis la base '
                      'locale, jamais reconstitués.')
        lignes.append('- Les en-têtes sont vérifiés à la génération : chacun doit rester '
                      "reconnu par le moteur d'import, sinon la commande échoue.")
        lignes.append('')
        chemin = self.racine / 'RAPPORT_GENERATION.md'
        chemin.write_text('\n'.join(lignes), encoding='utf-8')
        self.rapport.append('RAPPORT_GENERATION.md')

    # ── PDF ────────────────────────────────────────────────────────────────
    def _generer_pdf(self):
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_JUSTIFY
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.platypus import (KeepTogether, PageBreak, Paragraph,
                                        SimpleDocTemplate, Spacer, Table, TableStyle)

        chemin = self.racine / DOSSIER_GUIDE / 'GUIDE_REMPLISSAGE_INJS.pdf'
        styles = getSampleStyleSheet()
        titre = ParagraphStyle('titre', parent=styles['Title'], fontSize=20,
                               textColor=colors.HexColor('#1F3864'), spaceAfter=4)
        sous_titre = ParagraphStyle('sous', parent=styles['Normal'], fontSize=10,
                                    textColor=colors.HexColor('#2E5C8A'),
                                    alignment=1, spaceAfter=14)
        h1 = ParagraphStyle('h1', parent=styles['Heading2'], fontSize=13,
                            textColor=colors.HexColor('#1F3864'), spaceBefore=12,
                            spaceAfter=6)
        corps = ParagraphStyle('corps', parent=styles['BodyText'], fontSize=9.5,
                               leading=14, alignment=TA_JUSTIFY, spaceAfter=6)
        puce = ParagraphStyle('puce', parent=corps, leftIndent=12, bulletIndent=3,
                              spaceAfter=3)
        cellule_style = ParagraphStyle('cellule', parent=styles['Normal'], fontSize=7.5,
                                       leading=9.5)

        doc = SimpleDocTemplate(
            str(chemin), pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
            topMargin=16 * mm, bottomMargin=16 * mm,
            title='Guide de remplissage INJS 2026',
            author='INJS-LMD 2026')
        recit = []
        recit.append(Paragraph('Guide de remplissage — INJS 2026', titre))
        recit.append(Paragraph(
            'Kit de fichiers Excel et CSV du Hub « Référentiels »', sous_titre))

        recit.append(Paragraph('1. Objet du kit', h1))
        recit.append(Paragraph(
            f'Ce kit accompagne le paramétrage complet de l\'application en environnement '
            f'local. Il fournit, pour chacun des <b>{len(REGISTRE)} référentiels</b> du Hub, '
            f'un classeur Excel et un fichier CSV. Les colonnes sont celles des modèles '
            f'Django réels : aucune colonne n\'a été ajoutée, et les en-têtes sont reconnus '
            f'automatiquement par le moteur d\'import. Les listes de valeurs et les exemples '
            f'proviennent de votre base locale, ils ne sont pas reconstitués.', corps))

        recit.append(Paragraph('2. Contenu d’un classeur', h1))
        for nom, description in [
            ('Instructions', "objet du référentiel, préalables, marche à suivre, formats."),
            ('Donnees', "la seule feuille à compléter : en-têtes figés, filtres actifs et "
                        "listes déroulantes."),
            ('References', "valeurs admises et clés de liaison, une ligne par colonne."),
            ('Exemple', "lignes réelles extraites de votre base, au format exact attendu."),
            ('Controles', "règles appliquées à l'import, colonne par colonne."),
        ]:
            recit.append(Paragraph(f'<b>{nom}</b> — {description}', puce, bulletText='•'))

        recit.append(Paragraph('3. Règles de saisie', h1))
        for texte in [
            'En-tête <b>rose</b> : colonne obligatoire. En-tête <b>vert</b> : facultative.',
            'Les colonnes à liste déroulante sont fermées : toute autre valeur sera '
            'refusée à l\'import.',
            'Une colonne de liaison se renseigne par la <b>clé métier</b> de la ligne '
            'visée — son code, ou à défaut son libellé. <b>Jamais d\'identifiant '
            'numérique.</b>',
            'Dates au format <b>AAAA-MM-JJ</b> (ex. 2026-09-15). Le format français '
            'JJ/MM/AAAA est rejeté par le moteur d\'import.',
            'Décimaux au point ou à la virgule. Booléens en Oui / Non.',
            'Cellule <b>vide</b> pour « non renseigné », et non 0.',
            'CSV : UTF-8, séparateur point-virgule, une seule ligne d\'en-tête.',
        ]:
            recit.append(Paragraph(texte, puce, bulletText='•'))

        recit.append(Paragraph('4. Procédure d’import', h1))
        recit.append(Paragraph(
            "Hub « Référentiels » → ouvrir le référentiel → <b>Importer</b>. Déposez le "
            "fichier, cochez « première ligne = en-tête », relisez l'analyse (colonnes "
            "reconnues, doublons, erreurs par ligne), puis appliquez. Rien n'est écrit "
            "tant que l'analyse n'est pas validée : une ligne en erreur est signalée sans "
            "être enregistrée. L'import est idempotent — les lignes déjà présentes ne sont "
            "pas dupliquées.", corps))

        recit.append(PageBreak())
        recit.append(Paragraph('5. Ordre de paramétrage', h1))
        recit.append(Paragraph(
            'L\'ordre ci-dessous découle des dépendances réelles entre référentiels : un '
            'référentiel est listé après ceux dont il dépend. Les référentiels d\'un même '
            'niveau sont indépendants entre eux.', corps))

        entetes = ['#', 'Niv.', 'Référentiel', 'Préalables', 'Priorité']
        donnees = [[Paragraph(f'<b>{h}</b>', cellule_style) for h in entetes]]
        for rang, slug, niveau in self.ordre:
            donnees.append([
                Paragraph(str(rang), cellule_style),
                Paragraph(str(niveau), cellule_style),
                Paragraph(str(REGISTRE[slug]['libelle']), cellule_style),
                Paragraph(', '.join(REGISTRE[p]['libelle']
                                    for p in self.index[slug]['prerequis']) or '—',
                          cellule_style),
                Paragraph('Haute' if niveau == 0 else ('Moyenne' if niveau == 1
                                                       else 'Basse'), cellule_style),
            ])
        table = Table(donnees, colWidths=[10 * mm, 11 * mm, 62 * mm, 68 * mm, 21 * mm],
                      repeatRows=1)
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1F3864')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#BFBFBF')),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1),
             [colors.white, colors.HexColor('#F2F5FA')]),
            ('LEFTPADDING', (0, 0), (-1, -1), 4),
            ('RIGHTPADDING', (0, 0), (-1, -1), 4),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ]))
        recit.append(table)

        recit.append(Paragraph('6. Récapitulatif par référentiel', h1))
        donnees = [[Paragraph(f'<b>{h}</b>', cellule_style)
                    for h in ['Référentiel', 'Catégorie', 'Modèle Django',
                              'Colonnes', 'Oblig.', 'En base']]]
        for slug in sorted(REGISTRE, key=lambda s: str(REGISTRE[s]['categorie'])):
            d = self.index[slug]
            donnees.append([
                Paragraph(str(REGISTRE[slug]['libelle']), cellule_style),
                Paragraph(str(REGISTRE[slug]['categorie']), cellule_style),
                Paragraph(self.index_ou_modele(slug), cellule_style),
                Paragraph(str(len(d['colonnes'])), cellule_style),
                Paragraph(str(sum(1 for c in d['colonnes'] if c['obligatoire'])),
                          cellule_style),
                Paragraph(str(d['total_base']), cellule_style),
            ])
        table = Table(donnees, colWidths=[50 * mm, 30 * mm, 48 * mm, 16 * mm, 14 * mm,
                                          16 * mm], repeatRows=1)
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1F3864')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#BFBFBF')),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1),
             [colors.white, colors.HexColor('#F2F5FA')]),
            ('LEFTPADDING', (0, 0), (-1, -1), 4),
            ('RIGHTPADDING', (0, 0), (-1, -1), 4),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ]))
        recit.append(table)

        recit.append(Spacer(1, 8 * mm))
        recit.append(Paragraph(
            '<i>Kit régénérable à tout moment : <b>python manage.py '
            'generer_kit_remplissage</b>. Colonnes, listes de valeurs et exemples sont '
            'relus depuis les modèles et la base : le kit ne peut pas dériver de '
            'l\'application.</i>', corps))

        doc.build(recit)
        self.rapport.append('GUIDE_REMPLISSAGE_INJS.pdf')
