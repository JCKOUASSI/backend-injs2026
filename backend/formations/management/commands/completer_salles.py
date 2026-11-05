"""Complétion experte du référentiel des salles et espaces (INJS Marcory).

**Constat (audit du 04/11/2026 sur la base de démonstration).** Sur 166
salles et espaces actifs : 144 sans capacité, 166 sans aucun équipement,
5 espaces typés SPORT sans type d'espace sportif. Une capacité absente
n'est pas anodine : la contrainte C4 du moteur EDT la traite comme
bloquante dès que l'effectif du groupe est connu — seules 22 salles
étaient donc réellement éligibles à la génération.

**Ce que fait la commande.** Elle propose, pour chaque champ vide, une
valeur de **cadrage fonctionnel** issue de règles métier explicites
(ci-dessous), puis marque les lignes complétées ``fiabilite=CADRAGE``
(« à valider par l'INJS ») : rien n'est présenté comme un relevé terrain.

**Garanties.**
* jamais d'écrasement : un champ déjà renseigné est conservé tel quel ;
* idempotente : un second passage ne modifie rien ;
* sans ``--appliquer`` : rapport seul, aucune écriture (dry-run) ;
* les indisponibilités (``indisponible_du/au``) ne sont jamais inventées :
  vides, elles signifient « disponible », ce qui est l'état par défaut.

**Règles de capacité (places accueillies).** Le nombre inscrit dans le
nom prime (« Amphi 300 places »). Sinon, des valeurs de référence par
famille, calées sur les standards d'un institut de formation sportive et
sur les valeurs déjà attestées du référentiel (salle de cours LMD = 40) :
amphithéâtre 200, cours 40, TD 30, TP 25, informatique 30 postes,
laboratoire 24, conférence selon usage, gymnase 50 pratiquants, espaces
sportifs selon discipline, bureaux et services 6 à 12, etc. Les salles
disciplinaires des blocs ENSEP/ENSEPS (sociologie, psychologie…) sont
des salles d'enseignement : 35 places, sous l'effectif type d'un groupe.

**Équipements.** Dotation standard par famille (projection, tableau,
postes informatiques, paillasses, tatamis, lignes d'eau…), précisée par
mots-clés du nom quand l'espace est spécialisé (ECG, biomécanique,
réalité virtuelle…).

**Types d'espace sportif.** Attribution par mots-clés du nom quand un
type du référentiel correspond. Les espaces extérieurs non sportifs
(parkings, esplanade, place d'armes, jardin) n'en reçoivent aucun : le
rapport les signale au lieu d'inventer une vocation sportive.
"""

from __future__ import annotations

import re
import unicodedata

from django.core.management.base import BaseCommand
from django.db import transaction


def _norm(texte: str) -> str:
    """Minuscules sans accents, pour des mots-clés robustes."""
    texte = unicodedata.normalize('NFKD', texte or '')
    texte = ''.join(c for c in texte if not unicodedata.combining(c))
    return texte.lower()


# (motif sur nom normalisé, capacité, équipements) — premier motif gagnant.
REGLES_NOM = [
    (r'(\d+)\s*places', None, None),  # traité à part (nombre du nom)
    (r'parking enseignants', 40, 'Places de stationnement matérialisées, Éclairage extérieur'),
    (r'parking etudiants', 150, 'Places de stationnement matérialisées, Éclairage extérieur'),
    (r'bureau|service |direction des', 8, 'Postes de travail bureautiques, Écran de présentation, Téléphone IP'),
    (r'dortoir', 40, 'Lits superposés, Casiers de rangement, Bloc sanitaire'),
    (r'archives', 6, "Rayonnages d'archives, Fonds documentaire, Bureau de consultation"),
    (r'lecture generale', 80, 'Rayonnages en libre accès, Tables de lecture collectives, Fonds documentaire'),
    (r'lecture numerique', 30, 'Postes de consultation numérique, Tables de lecture, Accès au catalogue en ligne'),
    (r'salle (theses|memoire|revues)', 20, 'Rayonnages spécialisés, Tables de lecture individuelles'),
    (r'audiovisuelle', 25, 'Écran de projection, Sonorisation, Lecteurs multimédias'),
    (r'studio', 12, 'Plateau de tournage, Éclairage studio, Caméras, Régie de production'),
    (r'visioconference', 20, 'Équipement de visioconférence, Écrans muraux, Sonorisation de conférence'),
    (r'ceremonies', 200, 'Estrade, Sonorisation, Vidéoprojecteur, Écran de projection'),
    (r'conseils', 40, 'Grande table de conseil, Écran de présentation, Visioconférence'),
    (r'soutenances', 80, 'Estrade, Sonorisation, Vidéoprojecteur, Écran de projection'),
    (r'conferences', 120, 'Estrade, Sonorisation, Vidéoprojecteur, Écran de projection'),
    (r'piscine olympique', 40, "8 lignes d'eau, Plongeoirs, Chronométrage électronique, Matériel d'apprentissage"),
    (r"bassin d'apprentissage", 20, "Lignes d'apprentissage, Matériel pédagogique aquatique, Planches et frites"),
    (r'piste 400', 60, "Piste d'athlétisme 400 m en tartan, Sautoirs, Aires de lancer, Chronométrage"),
    (r'terrain', 30, "Buts amovibles, Ballons d'entraînement, Cônes et coupelles, Marquages au sol"),
    (r'courts de tennis', 8, 'Filets de tennis, Surface en dur, Éclairage extérieur'),
    (r'(basketball|handball|volleyball) exterieur', 20, 'Panneaux et buts multisports, Marquages au sol, Ballons'),
    (r'(saut|lancers)', 20, 'Sautoirs en longueur et en hauteur, Fosse de réception, Aires de lancer'),
    (r'parcours sportif|aire de fitness', 25, "Agrès extérieurs, Stations d'exercices, Tapis de sol"),
    (r'esplanade|place d.armes', 300, 'Espace extérieur polyvalent, Éclairage extérieur'),
    (r'jardin pedagogique', 30, 'Espace extérieur aménagé, Bancs, Panneaux pédagogiques'),
    (r'gymnase', 50, 'Agrès de gymnastique, Tatamis, Matériel pédagogique EPS, Sono portable'),
    (r'dojo|salle de judo|salle de karate|salle de taekwondo', 30, "Tatamis, Matériel d'arts martiaux, Miroirs muraux"),
    (r'salle de boxe', 20, 'Ring de boxe, Sacs de frappe, Matériel de protection'),
    (r'halterophilie', 15, "Plateformes d'haltérophilie, Barres olympiques, Disques"),
    (r'musculation', 25, 'Appareils de musculation guidée, Charges libres, Bancs de musculation'),
    (r'preparation physique', 20, 'Appareils de préparation physique, Matériel de renforcement, Tapis'),
    (r'cyber', 40, 'Postes informatiques en libre accès, Imprimante en réseau, Accès internet'),
    (r'cybersecurite', 25, 'Postes informatiques en réseau isolé, Environnement virtualisé, Vidéoprojecteur'),
    (r'intelligence artificielle', 25, 'Stations de calcul, Écrans doubles, Vidéoprojecteur'),
    (r'realite virtuelle', 20, 'Casques de réalité virtuelle, Stations graphiques, Espace de capture de mouvement'),
    (r'multimedia', 25, 'Postes de montage audio-vidéo, Équipement de captation, Vidéoprojecteur'),
    (r'moodle|e-learning', 30, 'Postes informatiques en réseau, Vidéoprojecteur, Tableau interactif'),
    (r'informatique', 30, 'Postes informatiques en réseau, Vidéoprojecteur, Tableau interactif'),
    (r'analyse video|analyse tactique', 20, "Postes d'analyse vidéo, Écran grand format, Logiciel d'analyse de la performance"),
    (r'biomecanique', 20, "Plateformes de force, Système d'analyse du mouvement, Caméras rapides"),
    (r'physiologie', 20, 'Ergomètres, Analyseur de gaz, Cardiofréquencemètres'),
    (r'\becg\b', 12, 'Électrocardiographes, Tapis de course, Matériel de surveillance cardiaque'),
    (r'ergometrie', 12, "Ergomètres d'effort, Analyseur de gaz, Matériel de surveillance"),
    (r'anatomie', 20, 'Modèles anatomiques, Tables de dissection, Planches anatomiques'),
    (r'kinesitherapie|reeducation', 12, 'Tables de kinésithérapie, Matériel de rééducation fonctionnelle, Espaliers'),
    (r'massage', 6, 'Tables de massage, Matériel de récupération'),
    (r'cryotherapie', 6, 'Bains froids, Équipement de cryothérapie'),
    (r'recuperation', 10, 'Espace de récupération, Bains contrastés, Matériel de relaxation'),
    (r'urgence sportive', 8, 'Brancard, Matériel de premiers secours, Défibrillateur'),
    (r'nutrition', 15, 'Matériel de mesure anthropométrique, Documentation nutritionnelle'),
    (r'preparation mentale', 12, 'Espace calme, Matériel de relaxation et de concentration'),
    (r'chronometrage', 6, 'Chronométrage électronique, Informatique de compétition'),
    (r'centre de recherche|centre innovation', 10, 'Postes de travail de recherche, Documentation scientifique'),
    (r'chercheurs', 15, 'Postes de travail de recherche, Bibliothèque de travail'),
    (r'doctorants', 12, 'Postes de travail doctoraux, Bibliothèque de travail'),
    (r'publications', 8, 'Postes de rédaction, Documentation scientifique'),
    (r'salle tv', 30, 'Écran collectif, Assises collectives'),
    (r"salle d.etude", 30, 'Tables de travail collectives, Tableau blanc'),
    (r'formation continue', 30, 'Tableau blanc, Vidéoprojecteur, Tables modulables'),
    (r'seminaires', 25, 'Tableau blanc, Vidéoprojecteur, Tables modulables'),
    (r'de langues', 25, 'Laboratoire de langues, Casques audio, Vidéoprojecteur'),
    (r'innovation', 20, 'Tables modulables, Tableau interactif, Matériel de prototypage'),
    (r'leadership', 20, 'Tables modulables, Écran de présentation'),
    (r'protocoles', 15, 'Tables de travail, Documentation protocolaire'),
]

CAPACITES_PAR_TYPE = {
    'AMPHI': 200,
    'COURS': 40,
    'TD': 30,
    'TP': 25,
    'INFORMATIQUE': 30,
    'LABORATOIRE': 24,
    'REUNION': 10,
    'CONFERENCE': 100,
    'GYMNASE': 50,
    'SPORT': 30,
    'SALLE': 30,
}

EQUIPEMENTS_PAR_TYPE = {
    'AMPHI': 'Sièges en gradins, Vidéoprojecteur, Écran de projection, Sonorisation avec micros, Tableau blanc',
    'COURS': 'Tableau blanc, Vidéoprojecteur, Écran de projection',
    'TD': 'Tableau blanc, Vidéoprojecteur',
    'TP': 'Tableau blanc, Paillasses de travaux pratiques, Vidéoprojecteur',
    'INFORMATIQUE': 'Postes informatiques en réseau, Vidéoprojecteur, Tableau interactif',
    'LABORATOIRE': "Paillasses, Matériel d'expérimentation, Point d'eau, Tableau blanc",
    'REUNION': 'Table de réunion, Écran de présentation, Visioconférence',
    'CONFERENCE': 'Estrade, Sonorisation, Vidéoprojecteur, Écran de projection',
    'GYMNASE': 'Agrès de gymnastique, Tatamis, Matériel pédagogique EPS',
    'SPORT': "Matériel d'entraînement sportif, Marquages au sol",
    'SALLE': 'Tableau blanc, Tables et chaises mobiles',
}

# Blocs d'enseignement disciplinaire (ENSEP/ENSEPS, CNMS, CNSHN…) : des
# salles de cours de fait, calibrées sur l'effectif type d'un groupe.
BLOCS_ENSEIGNEMENT = ('Bloc ENSEP', 'Bloc ENSEPS')
CAPACITE_SALLE_ENSEIGNEMENT = 35

# Types d'espace sportif par mots-clés (nom normalisé → code référentiel).
TYPES_ESPACE_PAR_NOM = [
    (r'piscine', 'PISCINE'),
    (r"bassin d'apprentissage", 'BASSIN_APPRENTISSAGE'),
    (r'tennis', 'COURT_TENNIS'),
    (r'piste|athletisme', 'PISTE_ATHLETISME'),
    (r'saut|lancer', 'AIRE_SAUTS_LANCERS'),
    (r'dojo|judo|karate|taekwondo', 'DOJO'),
    (r'boxe', 'SALLE_BOXE'),
    (r'halterophilie', 'SALLE_HALTEROPHILIE'),
    (r'musculation', 'SALLE_MUSCULATION'),
    (r'preparation physique', 'SALLE_PREPARATION_PHYSIQUE'),
    (r'parcours|fitness', 'PARCOURS_SPORTIF'),
    (r'gymnase', 'GYMNASE'),
    (r'stade', 'STADE'),
    (r'sable|beach', 'TERRAIN_SABLE'),
    (r'terrain', 'TERRAIN'),
    (r'basketball|handball|volleyball|plateau', 'PLATEAU_SPORTIF'),
    (r'danse|expression', 'SALLE_EXPRESSION'),
    (r'\bapa\b|reeducation fonctionnelle', 'SALLE_APA'),
]


def capacite_proposee(salle):
    """Capacité de cadrage pour une salle, ou ``None`` si déjà renseignée."""
    if salle.capacite is not None:
        return None
    nom = _norm(salle.nom)
    match = re.search(r'(\d+)\s*places', nom)
    if match:
        return int(match.group(1))
    for motif, capacite, _equipements in REGLES_NOM[1:]:
        if capacite is not None and re.search(motif, nom):
            return capacite
    if (
        salle.type_lieu == 'SALLE'
        and salle.batiment_id
        and salle.batiment.nom in BLOCS_ENSEIGNEMENT
        and nom.startswith('salle')
    ):
        return CAPACITE_SALLE_ENSEIGNEMENT
    return CAPACITES_PAR_TYPE.get(salle.type_lieu, 30)


def equipements_proposes(salle):
    """Équipements de cadrage, ou ``None`` si déjà renseignés."""
    if (salle.equipements or '').strip():
        return None
    nom = _norm(salle.nom)
    for motif, _capacite, equipements in REGLES_NOM[1:]:
        if equipements and re.search(motif, nom):
            return equipements
    return EQUIPEMENTS_PAR_TYPE.get(salle.type_lieu, 'Tableau blanc')


def type_espace_propose(salle, types_par_code):
    """Type d'espace sportif déduit du nom, ou ``None`` (non sportif)."""
    if salle.type_espace_id or salle.type_lieu not in ('SPORT', 'GYMNASE'):
        return None
    nom = _norm(salle.nom)
    for motif, code in TYPES_ESPACE_PAR_NOM:
        if re.search(motif, nom) and code in types_par_code:
            return types_par_code[code]
    return None


class Command(BaseCommand):
    help = (
        'Complète (cadrage à valider) les capacités, équipements et types '
        "d'espace sportif manquants des salles. Dry-run sans --appliquer."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--appliquer', action='store_true',
            help='Écrit les propositions en base (défaut : rapport seul).',
        )

    def handle(self, *args, **options):
        from formations.models import RefSalle
        from referentiels.models import RefTypeEspaceSportif

        appliquer = options['appliquer']
        types_par_code = {t.code: t for t in RefTypeEspaceSportif.objects.all()}
        compteurs = {'capacite': 0, 'equipements': 0, 'type_espace': 0, 'fiabilite': 0}
        sans_type = []

        salles = list(
            RefSalle.objects.select_related('batiment', 'type_espace').order_by('nom')
        )
        with transaction.atomic():
            for salle in salles:
                modifiee = False
                capacite = capacite_proposee(salle)
                if capacite is not None:
                    salle.capacite = capacite
                    compteurs['capacite'] += 1
                    modifiee = True
                equipements = equipements_proposes(salle)
                if equipements is not None:
                    salle.equipements = equipements[:255]
                    compteurs['equipements'] += 1
                    modifiee = True
                type_espace = type_espace_propose(salle, types_par_code)
                if type_espace is not None:
                    salle.type_espace = type_espace
                    compteurs['type_espace'] += 1
                    modifiee = True
                if (
                    salle.type_lieu in ('SPORT', 'GYMNASE')
                    and not salle.type_espace_id
                ):
                    sans_type.append(f'{salle.code} {salle.nom}')
                if modifiee:
                    if salle.fiabilite != 'CADRAGE':
                        salle.fiabilite = 'CADRAGE'
                        compteurs['fiabilite'] += 1
                    if appliquer:
                        salle.save(update_fields=[
                            'capacite', 'equipements', 'type_espace', 'fiabilite',
                        ])
            if not appliquer:
                transaction.set_rollback(True)

        mode = 'APPLIQUÉ' if appliquer else 'SIMULATION (dry-run, aucun --appliquer)'
        self.stdout.write(f'--- Complétion des salles : {mode} ---')
        self.stdout.write(f"Salles examinées : {len(salles)}")
        self.stdout.write(f"Capacités complétées : {compteurs['capacite']}")
        self.stdout.write(f"Équipements complétés : {compteurs['equipements']}")
        self.stdout.write(f"Types d'espace sportif attribués : {compteurs['type_espace']}")
        self.stdout.write(f"Fiabilités passées en CADRAGE : {compteurs['fiabilite']}")
        if sans_type:
            self.stdout.write(
                'Espaces SPORT/GYMNASE sans type sportif (non sportifs, '
                'à requalifier par l’INJS si besoin) :'
            )
            for ligne in sans_type:
                self.stdout.write(f'  - {ligne}')
