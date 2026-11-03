"""Finalise les maquettes LMD : exemples pour les filières sans référentiel,
ventilation des crédits ECUE, validation puis activation.

Contexte
--------
``configurer_referentiel_injs`` importe les maquettes **officielles** des
filières F01–F04 en BROUILLON, ECUE à 0 crédit (le référentiel publie
l'ECTS au niveau UE uniquement) : aucune n'est validable en l'état, et les
filières F05–F08 (Andragogie, Loisir, EJCP, Gérontologie) n'ont aucune
maquette — leur référentiel n'est pas publié.

Cette commande — décision institutionnelle explicite, jamais lancée par un
import de données — rend l'écran « Maquettes pédagogiques LMD » pleinement
démontrable :

1. crée des maquettes **d'exemple** (libellé ``[Exemple] …``) pour F05–F08,
   Licence (L1–L3) et Master (M1–M2), 60 ECTS par niveau, UE/ECUE
   cohérents dès la création ;
2. ventile les crédits officiels des UE vers leurs ECUE à parts égales
   (``Maquette.repartir_credits_ecue``, UE dont toutes les ECUE sont à 0) ;
3. valide (BROUILLON → VALIDEE) chaque maquette cohérente de l'année ;
4. active (VALIDEE → ACTIVE), sauf ``--sans-activation``.

Chaque transition est journalisée (``MaquetteJournal``) avec son origine.
Idempotente : les maquettes déjà abouties sont ignorées, rien n'est
réécrit. ``--purger-exemples`` retire les seules maquettes ``[Exemple]``
que rien ne référence encore.

Exemples
--------
    python manage.py finaliser_maquettes_injs --dry-run
    python manage.py finaliser_maquettes_injs --utilisateur admin
    python manage.py finaliser_maquettes_injs --purger-exemples
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models.deletion import ProtectedError
from django.utils import timezone

from formations.models import RefFormation
from scolarite.models import (
    ECUE, AnneeAcademique, Maquette, MaquetteJournal, Niveau, Semestre, UE,
)

#: Marqueur des maquettes de démonstration (libellé + purge ciblée).
MARQUE_EXEMPLE = '[Exemple]'

NIVEAUX_PAR_CYCLE = {
    'LICENCE': ['L1', 'L2', 'L3'],
    'MASTER': ['M1', 'M2'],
}

# ── Tronc commun INJS (exemple) : par semestre, (UE, crédits, [ECUE…]) ─────
TRONC = {
    1: [
        ('Sciences de la vie et de la santé', 6,
         ['Anatomie fonctionnelle du corps humain', "Physiologie de l'effort"]),
        ('Sciences humaines et sociales', 4,
         ['Psychologie générale', 'Sociologie générale']),
        ('Techniques de communication écrite et orale', 4,
         ['Français : expression écrite', 'Anglais général']),
    ],
    2: [
        ('Sciences de la vie et de la santé II', 5,
         ['Physiologie des grandes fonctions', 'Hygiène, santé et activités physiques']),
        ('Sciences humaines et sociales II', 4,
         ['Psychologie du développement', 'Sociologie des organisations']),
        ('Initiation aux technologies de l’information', 3,
         ['Bureautique et outils numériques']),
        ('Communication orale', 2, ['Prise de parole en public']),
    ],
    3: [
        ('Méthodologie de la recherche', 4,
         ['Épistémologie et démarche scientifique', 'Techniques de collecte de données']),
        ('Statistiques appliquées', 4,
         ['Statistique descriptive', 'Statistique inférentielle']),
        ('Anglais professionnel', 2, ['Communication professionnelle en anglais']),
    ],
    4: [
        ('Droit et institutions', 4,
         ['Organisation institutionnelle du sport, des loisirs et de la jeunesse',
          'Cadre juridique des activités']),
        ('Méthodologie de la recherche II', 4,
         ['Analyse qualitative', 'Rédaction scientifique']),
        ('Communication professionnelle', 2, ['Documents et présentations professionnels']),
    ],
    5: [
        ('Éthique et déontologie professionnelles', 3,
         ['Éthique et déontologie professionnelles']),
        ('Gestion de projet', 5, ['Planification de projet', 'Suivi-évaluation de projet']),
    ],
    6: [
        ('Stage de professionnalisation', 10, ['Stage en milieu professionnel']),
        ('Projet tutoré', 4, ['Conduite et soutenance du projet tutoré']),
    ],
    7: [
        ('Méthodologie avancée de la recherche', 6,
         ['Protocoles de recherche', 'Analyse de données quantitatives']),
        ('Anglais scientifique', 4,
         ["Lecture d'articles scientifiques", 'Communication scientifique']),
    ],
    8: [
        ('Management des organisations', 6, ["Pilotage d'équipe", 'Gestion des ressources']),
        ('Séminaires thématiques', 6, ['Séminaire thématique 1', 'Séminaire thématique 2']),
    ],
    9: [
        ('Préparation du mémoire', 8, ['Problématique et protocole', 'Collecte des données']),
    ],
    10: [
        ('Stage professionnel et mémoire', 20,
         ['Stage de longue durée', 'Rédaction du mémoire']),
        ('Soutenance et insertion professionnelle', 10,
         ['Soutenance du mémoire', 'Projet professionnel']),
    ],
}

# ── UE spécifiques d'exemple : par sigle de filière puis semestre ──────────
# (intitulé UE, crédits) — les ECUE sont dérivées (cadres / pratiques).
SPECIFIQUES = {
    'AND': {  # F05 — Andragogie
        1: [("Introduction à l'andragogie", 6), ("Psychologie de l'adulte apprenant", 5),
            ("Histoire et politiques de l'éducation des adultes", 5)],
        2: [("Théories de l'apprentissage adulte", 6),
            ('Éducation populaire et développement communautaire', 5),
            ('Alphabétisation fonctionnelle', 5)],
        3: [('Ingénierie de la formation', 7),
            ("Animation de groupe en formation d'adultes", 7), ('Didactique des adultes', 6)],
        4: [('Conception de programmes de formation', 7),
            ('Évaluation des apprentissages des adultes', 7),
            ('Formation en milieu de travail', 6)],
        5: [('Ingénierie pédagogique et dispositifs hybrides', 8),
            ('Accompagnement et tutorat des adultes', 7),
            ("Validation des acquis de l'expérience", 7)],
        6: [('Pratiques de formation en contexte réel', 6),
            ('Éducation non formelle et insertion', 5),
            ('Communication et médiation éducative', 5)],
        7: [("Recherche en éducation des adultes", 8),
            ("Politiques d'éducation tout au long de la vie", 6),
            ('Formation des formateurs', 6)],
        8: [('Conseil en ingénierie de formation', 7),
            ('Qualité et évaluation des dispositifs de formation', 6),
            ('Numérique éducatif pour adultes', 5)],
        9: [('Expertise en ingénierie de formation des adultes', 12),
            ('Études avancées en andragogie', 10)],
    },
    'LOI': {  # F06 — Loisir
        1: [('Introduction aux sciences du loisir', 6), ('Sociologie du temps libre', 5),
            ('Animation socioculturelle : fondamentaux', 5)],
        2: [('Typologie des pratiques de loisir', 6), ('Animation sportive et culturelle', 5),
            ('Jeunesse, loisir et société', 5)],
        3: [('Gestion des équipements de loisirs', 7),
            ("Programmation d'activités de loisir", 7), ('Loisir et santé', 6)],
        4: [('Tourisme et loisirs', 7), ('Événementiel et animation événementielle', 7),
            ('Sécurité et réglementation des accueils de loisirs', 6)],
        5: [('Marketing des loisirs', 8), ('Loisir éducatif et périscolaire', 7),
            ('Animation en milieu touristique', 7)],
        6: [("Pratiques d'animation en structures de loisirs", 6),
            ('Loisirs adaptés et inclusion', 5), ('Développement durable et écotourisme', 5)],
        7: [('Recherche en sciences du loisir', 8), ('Politiques publiques des loisirs', 6),
            ('Management des destinations de loisir', 6)],
        8: [('Innovation et industries créatives', 7),
            ('Évaluation des programmes de loisir', 6),
            ('Loisir numérique et pratiques émergentes', 5)],
        9: [('Expertise en ingénierie des loisirs', 12),
            ('Études avancées en management du loisir', 10)],
    },
    'EJCP': {  # F07 — Entrepreneuriat Jeunesse et Conduite de Projets
        1: [("Introduction à l'entrepreneuriat", 6), ('Économie générale', 5),
            ('Jeunesse et insertion socio-professionnelle', 5)],
        2: [("Création d'entreprise", 6), ('Comptabilité générale', 5),
            ('Conduite de projet : fondamentaux', 5)],
        3: [('Étude de marché et marketing', 7), ('Gestion financière', 7),
            ("Idéation et modèle d'affaires", 6)],
        4: [("Plan d'affaires", 7), ('Droit des affaires', 7),
            ('Suivi-évaluation de projets jeunesse', 6)],
        5: [('Entrepreneuriat social et solidaire', 8),
            ("Leadership et management d'équipe", 7), ('Recherche de financement', 7)],
        6: [('Incubation et accompagnement de porteurs de projets', 6),
            ('Gestion des risques projet', 5), ('Communication entrepreneuriale', 5)],
        7: [('Recherche en entrepreneuriat', 8),
            ("Politiques publiques de jeunesse et d'emploi", 6), ("Stratégie d'entreprise", 6)],
        8: [('Innovation et transformation numérique des PME', 7),
            ("Évaluation d'impact des projets", 6),
            ('Gouvernance des organisations de jeunesse', 5)],
        9: [('Expertise en conduite de projets et entrepreneuriat', 12),
            ('Études avancées en management de projets', 10)],
    },
    'GER': {  # F08 — Gérontologie
        1: [('Introduction à la gérontologie', 6), ('Vieillissement physiologique', 5),
            ('Psychologie du vieillissement', 5)],
        2: [('Sociologie du vieillissement', 6), ('Pathologies liées au vieillissement', 5),
            ('Nutrition de la personne âgée', 5)],
        3: [('Activités physiques adaptées aux seniors', 7),
            ('Prévention des chutes et autonomie', 7), ('Évaluation gérontologique', 6)],
        4: [('Accompagnement de la personne âgée', 7), ('Maladies neurodégénératives', 7),
            ('Aidants et soutien familial', 6)],
        5: [('Animation et vie sociale des seniors', 8),
            ('Gérontologie sociale et territoires', 7), ('Éthique en gérontologie', 7)],
        6: [('Pratiques en établissements et services seniors', 6),
            ('Promotion de la santé des aînés', 5), ("Technologies d'aide à l'autonomie", 5)],
        7: [('Recherche en gérontologie', 8), ('Politiques du vieillissement', 6),
            ('Vieillissement actif et en santé', 6)],
        8: [('Management des services aux personnes âgées', 7),
            ('Évaluation des programmes gérontologiques', 6),
            ('Fin de vie et accompagnement', 5)],
        9: [('Expertise en intervention gérontologique', 12),
            ('Études avancées en gérontologie', 10)],
    },
}

#: Code de filière (référentiel) → sigle technique des codes UE/ECUE.
SIGLE_PAR_FILIERE = {'F05': 'AND', 'F06': 'LOI', 'F07': 'EJCP', 'F08': 'GER'}


def _ecues_pour(intitule_ue, credits, intitules=None):
    """[(intitulé ECUE, crédits)…] sommant exactement aux crédits de l'UE."""
    if intitules:
        base, reste = divmod(credits, len(intitules))
        return [
            (titre, base + (1 if rang < reste else 0))
            for rang, titre in enumerate(intitules)
        ]
    if credits >= 4:
        moitie = credits // 2
        return [
            (f'{intitule_ue} : cadres et concepts', credits - moitie),
            (f'{intitule_ue} : pratiques et études de cas', moitie),
        ]
    return [(f'{intitule_ue} : fondements', credits)]


class Command(BaseCommand):
    help = (
        'Maquettes LMD : exemples F05–F08, ventilation des crédits ECUE, '
        'validation puis activation (journalisé, idempotent).'
    )

    def add_arguments(self, parser):
        parser.add_argument('--annee', help="Libellé d'année (défaut : année courante).")
        parser.add_argument('--utilisateur', help="Nom d'utilisateur signataire des transitions.")
        parser.add_argument('--sans-exemples', action='store_true',
                            help='Ne pas créer les maquettes d’exemple F05–F08.')
        parser.add_argument('--sans-activation', action='store_true',
                            help='S’arrêter au statut VALIDEE.')
        parser.add_argument('--purger-exemples', action='store_true',
                            help='Supprimer les maquettes [Exemple] non référencées, puis quitter.')
        parser.add_argument('--dry-run', action='store_true', help='Simuler sans écrire.')

    # ── Référentiels ─────────────────────────────────────────────────────
    def _annee(self, libelle):
        if libelle:
            annee = AnneeAcademique.objects.filter(libelle=libelle).first()
        else:
            annee = (
                AnneeAcademique.objects.filter(courante=True).first()
                or AnneeAcademique.objects.order_by('-libelle').first()
            )
        if annee is None:
            raise CommandError('Aucune année académique disponible.')
        return annee

    def _utilisateur(self, nom):
        User = get_user_model()
        if nom:
            user = User.objects.filter(username=nom).first()
            if user is None:
                raise CommandError(f'Utilisateur introuvable : {nom}')
            return user
        return User.objects.filter(is_superuser=True, is_active=True).order_by('id').first()

    # ── Maquettes d'exemple ──────────────────────────────────────────────
    def _creer_exemples(self, annee, dry_run):
        crees = 0
        formations = RefFormation.objects.filter(
            filiere_code__in=SIGLE_PAR_FILIERE, actif=True,
        ).order_by('filiere_code', 'intitule')
        for formation in formations:
            sigle = SIGLE_PAR_FILIERE[formation.filiere_code]
            cycle = (formation.type_diplome or '').upper()
            if cycle not in NIVEAUX_PAR_CYCLE:
                cycle = 'MASTER' if 'MASTER' in formation.intitule.upper() else 'LICENCE'
            for code_niveau in NIVEAUX_PAR_CYCLE[cycle]:
                niveau = Niveau.objects.filter(code=code_niveau).first()
                if niveau is None:
                    continue
                existe = Maquette.objects.filter(
                    annee_academique=annee, ref_formation=formation,
                    niveau=niveau, parcours__isnull=True,
                ).exists()
                if existe:
                    continue
                crees += 1
                if dry_run:
                    continue
                with transaction.atomic():
                    maquette = Maquette.objects.create(
                        annee_academique=annee, ref_formation=formation, niveau=niveau,
                        libelle=(
                            f'{MARQUE_EXEMPLE} {formation.intitule} – {niveau.code} : '
                            'maquette de démonstration (en attente du référentiel officiel)'
                        ),
                    )
                    self._remplir(maquette, sigle, niveau)
        return crees

    def _remplir(self, maquette, sigle, niveau):
        semestres = list(Semestre.objects.filter(niveau=niveau).order_by('numero'))
        for semestre in semestres:
            lignes = (
                SPECIFIQUES[sigle].get(semestre.numero, [])
                + TRONC.get(semestre.numero, [])
            )
            for ordre, ligne in enumerate(lignes, start=1):
                intitule, credits = ligne[0], ligne[1]
                intitules_ecue = ligne[2] if len(ligne) > 2 else None
                code_ue = f'{sigle}-S{semestre.numero}-UE{ordre:02d}'
                ue = UE.objects.create(
                    maquette=maquette, semestre=semestre, code=code_ue,
                    intitule=intitule, credits=credits, ordre=ordre,
                )
                for rang, (titre_ecue, credits_ecue) in enumerate(
                    _ecues_pour(intitule, credits, intitules_ecue), start=1,
                ):
                    ECUE.objects.create(
                        ue=ue, code=f'{code_ue}-EC{rang:02d}',
                        intitule=titre_ecue[:255], credits=credits_ecue, ordre=rang,
                    )

    # ── Transitions ──────────────────────────────────────────────────────
    def _journaliser(self, maquette, action, utilisateur, **detail):
        MaquetteJournal.objects.create(
            maquette=maquette, action=action, utilisateur=utilisateur,
            detail={'origine': 'finaliser_maquettes_injs', **detail},
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        annee = self._annee(options.get('annee'))
        utilisateur = self._utilisateur(options.get('utilisateur'))
        self.stdout.write(f"Année cible : {annee.libelle}{' (simulation)' if dry_run else ''}")

        if options['purger_exemples']:
            exemples = Maquette.objects.filter(libelle__startswith=MARQUE_EXEMPLE)
            supprimes = conserves = 0
            for maquette in exemples:
                if dry_run:
                    supprimes += 1
                    continue
                try:
                    with transaction.atomic():
                        maquette.delete()
                    supprimes += 1
                except ProtectedError:
                    conserves += 1
            self.stdout.write(
                f"Exemples supprimés : {supprimes} ; conservés (référencés) : {conserves}.",
            )
            return

        exemples_crees = 0
        if not options['sans_exemples']:
            exemples_crees = self._creer_exemples(annee, dry_run)

        validees = actives = echecs = 0
        maquettes = Maquette.objects.filter(
            annee_academique=annee, statut__in=['BROUILLON', 'VALIDEE'],
        ).order_by('ref_formation__intitule', 'niveau__ordre')
        for maquette in maquettes:
            if maquette.statut == 'BROUILLON' and dry_run:
                validees += 1
                maquette.statut = Maquette.Statut.VALIDEE  # mémoire : pour le comptage
            elif maquette.statut == 'BROUILLON':
                with transaction.atomic():
                    ventilees = maquette.repartir_credits_ecue()
                    if maquette.verifier_coherence():
                        echecs += 1
                        continue  # laissée en brouillon, ventilation conservée
                    est_exemple = maquette.libelle.startswith(MARQUE_EXEMPLE)
                    maquette.statut = Maquette.Statut.VALIDEE
                    maquette.validee_par = utilisateur
                    maquette.validee_le = timezone.now()
                    maquette.commentaire_validation = (
                        "Maquette d'exemple validée pour démonstration — "
                        'en attente du référentiel officiel.'
                        if est_exemple else
                        'Validation en lot (finalisation) — crédits ECUE ventilés '
                        'à parts égales depuis les crédits officiels des UE.'
                    )
                    maquette.save()
                    self._journaliser(
                        maquette, MaquetteJournal.Action.VALIDATION, utilisateur,
                        ecue_ventilees=ventilees, exemple=est_exemple,
                    )
                validees += 1
            if not options['sans_activation'] and maquette.statut == 'VALIDEE':
                if dry_run:
                    actives += 1
                    continue
                if maquette.verifier_coherence():
                    echecs += 1
                    continue
                maquette.statut = Maquette.Statut.ACTIVE
                maquette.activee_par = utilisateur
                maquette.activee_le = timezone.now()
                maquette.save()
                self._journaliser(maquette, MaquetteJournal.Action.ACTIVATION, utilisateur)
                actives += 1

        self.stdout.write(
            f'Exemples créés : {exemples_crees} ; validées : {validees} ; '
            f'activées : {actives} ; échecs de cohérence : {echecs}.',
        )
