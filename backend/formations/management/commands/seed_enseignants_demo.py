"""Corps enseignant d'exemple : toutes filières, formations et ECUE couvertes.

Contexte : la base ne comptait que 3 enseignants (héritage formation
continue, spécialités « administration publique », sans grade ni contact)
et **aucune affectation pédagogique** — les 779 ECUE des 40 maquettes
ACTIVE de l'année courante n'avaient aucun enseignant.

Cette commande crée, de façon **étiquetée et réversible** :

- 4 enseignants d'exemple par formation LMD (16 formations, 8 filières),
  avec grade académique (``referentiels.RefGradeEnseignant``), statut,
  fonction éventuelle (chef de département), spécialité cohérente avec la
  filière et contacts fictifs (courriels ``@exemple.injs.ci``) ;
- une affectation pédagogique par ECUE des maquettes ACTIVE de l'année
  courante, répartie en tournante entre les enseignants de la formation.

Le volume horaire des ECUE n'étant pas encore renseigné au référentiel
(0 h partout), le volume d'exemple vaut **5 h par crédit ECTS** : règle de
démonstration documentée, pas une norme officielle.

Idempotente (enseignants reconnus par courriel, affectations d'exemple
régénérées à identique). ``--dry-run`` simule, ``--purger`` retire tout.
"""
import re
import unicodedata
from decimal import Decimal

from django.core.management.base import BaseCommand

from formations.models import Formateur, RefFormation
from referentiels.models import RefGradeEnseignant
from scolarite.models import (
    AffectationPedagogique, AnneeAcademique, ECUE, Groupe, Maquette,
)

MARQUE = '[Exemple]'
DOMAINE = 'exemple.injs.ci'
OBSERVATION_ENSEIGNANT = f'{MARQUE} Enseignant de démonstration (données fictives).'
OBSERVATION_AFFECTATION = (
    f'{MARQUE} Affectation de démonstration '
    '(volume estimé : 5 h par crédit ECTS).'
)
PAR_FORMATION = 4

NOMS = [
    'DIARRASSOUBA', 'Touré', 'Bamba', 'COULIBALY', 'Sangaré', 'DIABATÉ',
    'BAKAYOKO', 'Ouattara', 'YAO', 'KOFFI', "N'Guessan", 'BROU',
    'TOURÉ', 'KONATÉ', 'DIALLO', 'SORO',
]
PRENOMS_F = [
    'Aya', 'Mariam', 'Fanta', 'Aminata', 'Kadidiatou', 'Salimata',
    'Adjoua', 'Akissi', 'Mireille', 'Chantal', 'Larissa', 'Nadège',
    'Estelle', 'Pélagie', 'Rokia', 'Bintou',
]
PRENOMS_H = [
    'Souleymane', 'Mamadou', 'Kouakou', 'Yao', 'Ibrahim', 'Yacouba', 'Adama',
    'Franck', 'Jean-Marc', 'Emmanuel', 'Landry', 'Wilfried', 'Serge',
    'Honoré', 'Didier', 'Séverin',
]

# Spécialités (une par rang) et grades selon la base de la formation.
PROFILS = {
    'ÉDUCATION ET MOTRICITÉ': {
        'grades': ['PROFESSEUR_TITULAIRE', 'MAITRE_CONFERENCES', 'MAITRE_ASSISTANT', 'MAITRE_EPS'],
        'specialites': [
            'Didactique de l’EPS', 'Motricité et apprentissages moteurs',
            'Sciences de l’éducation', 'Pratiques physiques et sportives',
        ],
    },
    'ACTIVITÉS PHYSIQUES ADAPTÉES': {
        'grades': ['PROFESSEUR_TITULAIRE', 'MAITRE_CONFERENCES', 'MEDECIN_SPORT', 'MAITRE_ASSISTANT'],
        'specialites': [
            'Activité physique adaptée et santé', 'Réadaptation fonctionnelle',
            'Médecine du sport', 'Handicap et inclusion par le sport',
        ],
    },
    'ENTRAÎNEMENT SPORTIF': {
        'grades': ['PROFESSEUR_TITULAIRE', 'MAITRE_CONFERENCES', 'MAITRE_ASSISTANT', 'PROF_AGREGE_EPS'],
        'specialites': [
            'Physiologie de l’exercice', 'Préparation physique',
            'Biomécanique du geste sportif', 'Entraînement et performance',
        ],
    },
    'MANAGEMENT DU SPORT': {
        'grades': ['PROFESSEUR_TITULAIRE', 'MAITRE_CONFERENCES', 'MAITRE_ASSISTANT', 'ASSISTANT'],
        'specialites': [
            'Management des organisations sportives', 'Marketing du sport',
            'Droit du sport', 'Économie et gestion des équipements sportifs',
        ],
    },
    'ANDRAGOGIE': {
        'grades': ['PROFESSEUR_TITULAIRE', 'MAITRE_CONFERENCES', 'MAITRE_ASSISTANT', 'CONSEILLER_EP'],
        'specialites': [
            'Andragogie et formation des adultes', 'Ingénierie de formation',
            'Éducation permanente', 'Alphabétisation fonctionnelle',
        ],
    },
    'LOISIR': {
        'grades': ['PROFESSEUR_TITULAIRE', 'MAITRE_CONFERENCES', 'MAITRE_ASSISTANT', 'CONSEILLER_EP'],
        'specialites': [
            'Animation socioculturelle', 'Tourisme et loisirs',
            'Gestion des équipements de loisirs', 'Loisirs éducatifs et jeunesse',
        ],
    },
    'ENTREPRENEURIAT JEUNESSE ET CONDUITE DE PROJETS': {
        'grades': ['PROFESSEUR_TITULAIRE', 'MAITRE_CONFERENCES', 'MAITRE_ASSISTANT', 'CONSEILLER_EP'],
        'specialites': [
            'Entrepreneuriat des jeunes', 'Conduite et évaluation de projets',
            'Économie sociale et solidaire', 'Insertion socio-professionnelle',
        ],
    },
    'GÉRONTOLOGIE': {
        'grades': ['PROFESSEUR_TITULAIRE', 'MAITRE_CONFERENCES', 'CADRE_PARAMEDICAL', 'MAITRE_ASSISTANT'],
        'specialites': [
            'Gérontologie sociale', 'Vieillissement et activité physique',
            'Soins et accompagnement des aînés', 'Santé publique et prévention',
        ],
    },
}
PROFIL_DEFAUT = {
    'grades': ['PROFESSEUR_TITULAIRE', 'MAITRE_CONFERENCES', 'MAITRE_ASSISTANT', 'ASSISTANT'],
    'specialites': [
        'Sciences du sport', 'Sciences de l’éducation',
        'Méthodologie de la recherche', 'Pratiques sportives',
    ],
}


def _slug(texte):
    texte = unicodedata.normalize('NFD', texte or '')
    texte = ''.join(c for c in texte if unicodedata.category(c) != 'Mn')
    texte = re.sub(r'[^a-zA-Z0-9]+', '.', texte).strip('.').lower()
    return texte or 'enseignant'


class Command(BaseCommand):
    help = 'Crée le corps enseignant d’exemple et couvre toutes les ECUE actives.'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true',
                            help='Simule sans écrire.')
        parser.add_argument('--purger', action='store_true',
                            help='Retire enseignants et affectations d’exemple.')

    # ── Enseignants ────────────────────────────────────────────────────────
    def _candidats(self):
        """64 couples (nom, prénom) uniques, déterministes."""
        candidats = []
        for i, nom in enumerate(NOMS):
            for j in range(4):
                prenoms = PRENOMS_F if (i + j) % 2 == 0 else PRENOMS_H
                candidats.append((nom, prenoms[(i * 4 + j) % len(prenoms)]))
        return candidats

    def _enseignants_par_formation(self, formations, grades, dry_run):
        """Retourne {formation_id: [Formateur, …]} (créés ou existants)."""
        existants = {
            f.email: f for f in Formateur.objects.filter(
                email__endswith=f'@{DOMAINE}',
            )
        }
        suffixes = [
            int(m.group(1))
            for badge in Formateur.objects.values_list('numerobadge', flat=True)
            if (m := re.fullmatch(r'F(\d+)', badge or ''))
        ]
        compteur = (max(suffixes) + 1) if suffixes else 1
        candidats = iter(self._candidats())
        resultat = {}
        crees = presents = 0

        for formation in formations:
            base = formation.intitule.split('—')[0].strip()
            profil = PROFILS.get(base, PROFIL_DEFAUT)
            equipe = []
            for rang in range(PAR_FORMATION):
                nom, prenom = next(candidats)
                email = f'{_slug(prenom)}.{_slug(nom)}@{DOMAINE}'
                if email in existants:
                    equipe.append(existants[email])
                    presents += 1
                    continue
                grade = grades.get(profil['grades'][rang])
                enseignant = Formateur(
                    numerobadge=f'F{compteur:03d}',
                    nom=nom, prenom=prenom, email=email,
                    telephone=f'+225 07 07 {10 + compteur % 80:02d} '
                              f'{20 + compteur % 70:02d} {30 + compteur % 60:02d}',
                    specialite=profil['specialites'][rang],
                    organisation='INJS',
                    grade_ref=grade,
                    fonction=(
                        'Chef de département'
                        if rang == 0 and 'LICENCE' in formation.intitule else ''
                    ),
                    statut_enseignant='Vacataire' if rang == 3 else 'Titulaire',
                    observations=OBSERVATION_ENSEIGNANT,
                )
                compteur += 1
                if not dry_run:
                    enseignant.save()
                    existants[email] = enseignant
                equipe.append(enseignant)
                crees += 1
            resultat[formation.pk] = equipe

        return resultat, crees, presents

    # ── Affectations ───────────────────────────────────────────────────────
    def _affectations(self, annee, equipes, dry_run):
        maquettes = (
            Maquette.objects.filter(statut=Maquette.Statut.ACTIVE, annee_academique=annee)
            .select_related('ref_formation', 'niveau').order_by('ref_formation_id', 'niveau__ordre')
        )
        # Affectations d'exemple déjà présentes, indexées par ECUE : la
        # régénération est NON destructive. L'ancien « tout supprimer puis
        # recréer » est devenu impossible dès que des évaluations référencent
        # ces affectations (FK PROTECT) — on met donc à jour en place
        # (rattachement au groupe) et on ne crée que les manquantes.
        existantes = {
            ap.ecue_id: ap
            for ap in AffectationPedagogique.objects.filter(
                annee_academique=annee,
                observations__startswith=MARQUE,
            )
        }

        # Groupes pédagogiques actifs par (formation, niveau) : chaque
        # affectation est rattachée à un groupe réel de son périmètre
        # (rotation déterministe). Sans ce rattachement, le tableau de bord
        # signalait à tort « 130 groupes sans affectation pédagogique »
        # alors que 779 affectations existaient, simplement non reliées.
        groupes_par_cle = {}
        for g in (Groupe.objects.filter(annee_academique=annee, actif=True)
                  .order_by('nom', 'id')):
            groupes_par_cle.setdefault(
                (g.ref_formation_id, g.niveau_id), []).append(g)

        a_creer = []
        ecue_total = 0
        for maquette in maquettes:
            equipe = equipes.get(maquette.ref_formation_id) or []
            if not equipe:
                continue
            ecues = (
                ECUE.objects.filter(ue__maquette=maquette)
                .select_related('ue__semestre', 'ue')
                .order_by('ue__semestre_id', 'ue__ordre', 'ordre')
            )
            groupes = groupes_par_cle.get(
                (maquette.ref_formation_id, maquette.niveau_id)) or []
            for index, ecue in enumerate(ecues):
                ecue_total += 1
                a_creer.append(AffectationPedagogique(
                    annee_academique=annee,
                    ref_formation=maquette.ref_formation,
                    niveau=maquette.niveau,
                    groupe=groupes[index % len(groupes)] if groupes else None,
                    semestre=ecue.ue.semestre,
                    ue=ecue.ue,
                    ecue=ecue,
                    enseignant=equipe[index % len(equipe)],
                    type_enseignement=AffectationPedagogique.TypeEnseignement.CM,
                    volume_horaire=Decimal(ecue.credits * 5),
                    statut=AffectationPedagogique.Statut.VALIDEE,
                    observations=OBSERVATION_AFFECTATION,
                ))

        if dry_run:
            return len(a_creer), ecue_total

        nouvellement_creees = []
        a_mettre_a_jour = []
        ecues_vues = set()
        for souhaitee in a_creer:
            ecues_vues.add(souhaitee.ecue_id)
            actuelle = existantes.get(souhaitee.ecue_id)
            if actuelle is None:
                nouvellement_creees.append(souhaitee)
            elif (actuelle.groupe_id != souhaitee.groupe_id
                  or actuelle.enseignant_id != souhaitee.enseignant_id):
                actuelle.groupe = souhaitee.groupe
                actuelle.enseignant = souhaitee.enseignant
                a_mettre_a_jour.append(actuelle)
        AffectationPedagogique.objects.bulk_create(
            nouvellement_creees, batch_size=500)
        if a_mettre_a_jour:
            AffectationPedagogique.objects.bulk_update(
                a_mettre_a_jour, ['groupe', 'enseignant'], batch_size=500)

        # Obsolètes (ECUE hors maquettes actives) : suppression limitée à
        # celles qu'aucune évaluation ne référence (PROTECT).
        obsoletes = [ap for eid, ap in existantes.items()
                     if eid not in ecues_vues]
        if obsoletes:
            from evaluations.models import Evaluation as _Eval
            referencees = set(_Eval.objects.filter(
                affectation_pedagogique__in=obsoletes,
            ).values_list('affectation_pedagogique_id', flat=True))
            AffectationPedagogique.objects.filter(
                pk__in=[ap.pk for ap in obsoletes if ap.pk not in referencees],
            ).delete()
        return len(nouvellement_creees) + len(a_mettre_a_jour), ecue_total

    # ── Point d'entrée ─────────────────────────────────────────────────────
    def handle(self, *args, **options):
        if options['purger']:
            nb_aff, _ = AffectationPedagogique.objects.filter(
                observations__startswith=MARQUE,
            ).delete()
            # Signature du seed (pas le seul domaine de courriel) : un compte
            # @exemple.injs.ci créé à la main ne doit jamais être purgé.
            enseignants = Formateur.objects.filter(
                observations__startswith=MARQUE,
            )
            nb_ens = enseignants.count()
            enseignants.delete()
            self.stdout.write(self.style.SUCCESS(
                f'Purge : {nb_aff} affectation(s) et {nb_ens} enseignant(s) '
                'd’exemple retirés.',
            ))
            return

        dry_run = options['dry_run']
        annee = AnneeAcademique.objects.filter(courante=True).first()
        if annee is None:
            self.stdout.write(self.style.WARNING('Aucune année courante : abandon.'))
            return
        grades = {g.code: g for g in RefGradeEnseignant.objects.filter(actif=True)}
        formations = list(
            RefFormation.objects.filter(actif=True).order_by('intitule', 'id'),
        )

        equipes, crees, presents = self._enseignants_par_formation(
            formations, grades, dry_run,
        )
        nb_aff, ecue_total = self._affectations(annee, equipes, dry_run)

        verbe = 'seraient créés' if dry_run else 'créés'
        self.stdout.write(self.style.SUCCESS(
            f'Corps enseignant d’exemple : {crees} enseignant(s) {verbe} '
            f'({presents} déjà présents) sur {len(formations)} formation(s) ; '
            f'{nb_aff} affectation(s) couvrant {ecue_total} ECUE '
            f'({annee.libelle}).',
        ))
