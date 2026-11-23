"""Stages d'exemple : organismes, tuteurs, conventions et évaluations.

Le module Stages était entièrement vide (0 organisme, 0 convention) alors
que ses écrans existaient. Cette commande crée un jeu de démonstration
étiqueté « [Exemple] » et réversible :

- 20 organismes d'accueil génériques du secteur jeunesse/sport/santé
  (contacts ``@exemple.injs.ci``) et leurs tuteurs externes ;
- ~160 conventions pour des étudiants de L3/M1/M2 inscrits en 2026-2027,
  réparties sur tout le workflow (brouillon → validée par jury), avec des
  périodes cohérentes avec chaque statut ;
- les évaluations des stages terminés/soutenus (notes déterministes).

Idempotente : organismes reconnus par nom, conventions d'exemple
régénérées à identique. ``--dry-run`` simule, ``--purger`` retire tout
(organismes reconnus par leur courriel de contact d'exemple).
"""
import random
from datetime import date, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils import timezone

from scolarite.models import (
    AnneeAcademique, InscriptionAdministrative,
)
from stages.models import ConventionStage, EvaluationStage, OrganismeAccueil, TuteurExterne

MARQUE = '[Exemple]'
DOMAINE = 'exemple.injs.ci'
CIBLE_CONVENTIONS = 160

ORGANISMES = [
    ('Complexe Sportif Municipal de Treichville', 'Abidjan', 'Gestion des équipements sportifs'),
    ('Direction Départementale des Sports de Bouaké', 'Bouaké', 'Animation sportive territoriale'),
    ('Centre Médico-Sportif de Cocody', 'Abidjan', 'Médecine et suivi des sportifs'),
    ('Ligue Ivoirienne d’Athlétisme (exemple)', 'Abidjan', 'Organisation de compétitions'),
    ('Académie de Football de Bassam (exemple)', 'Grand-Bassam', 'Formation des jeunes footballeurs'),
    ('Maison des Jeunes de Yopougon', 'Abidjan', 'Animation socio-éducative'),
    ('Centre de Réadaptation Fonctionnelle du Plateau', 'Abidjan', 'Réadaptation et APA'),
    ('Foyer de Jeunes de Korhogo', 'Korhogo', 'Insertion des jeunes'),
    ('Club Omnisports de San Pedro (exemple)', 'San Pedro', 'Pratique sportive encadrée'),
    ('Résidence Les Oliviers — EHPAD (exemple)', 'Abidjan', 'Accompagnement des personnes âgées'),
    ('Centre de Loisirs de Bingerville', 'Bingerville', 'Animation de loisirs éducatifs'),
    ('Direction Régionale de la Jeunesse du Gbêkê', 'Bouaké', 'Politiques jeunesse'),
    ('Institut de Formation Sportive de Yamoussoukro (exemple)', 'Yamoussoukro', 'Formation sportive'),
    ('Association Sport Santé pour Tous (exemple)', 'Abidjan', 'Sport santé et prévention'),
    ('Centre Hospitalier Universitaire — Service de rééducation (exemple)', 'Abidjan', 'Rééducation fonctionnelle'),
    ('Office des Parcs et Loisirs de Daloa (exemple)', 'Daloa', 'Gestion des espaces de loisirs'),
    ('Académie des Sports de Combat d’Abidjan (exemple)', 'Abidjan', 'Arts martiaux et encadrement'),
    ('Centre d’Accueil de l’Enfance de Gagnoa (exemple)', 'Gagnoa', 'Éducation spécialisée'),
    ('Stade Olympique — Cellule événements (exemple)', 'Abidjan', 'Événementiel sportif'),
    ('ONG Jeunesse Active (exemple)', 'Man', 'Entrepreneuriat des jeunes'),
]

SUJETS = [
    'Encadrement d’activités physiques adaptées auprès d’un public senior',
    'Organisation et animation d’un tournoi inter-quartiers',
    'Suivi de la préparation physique d’une équipe de jeunes',
    'Mise en place d’un programme sport-santé en entreprise',
    'Animation d’ateliers de loisirs éducatifs pour adolescents',
    'Accompagnement à la reprise d’activité après blessure',
    'Gestion administrative d’une structure sportive municipale',
    'Conduite d’un projet d’insertion par le sport',
    'Évaluation de la condition physique d’un groupe d’adultes',
    'Coordination des activités périscolaires sportives',
]

NOMS_TUTEURS = [
    ('TRAORÉ', 'Issa'), ('Konan', 'Jean-Baptiste'), ('N’DRI', 'Clarisse'),
    ('Bakayoko', 'Fatou'), ('Touré', 'Mohamed'), ('DIALLO', 'Rama'),
    ('Sangaré', 'Olivier'), ('KOFFI', 'Estelle'), ('BAMBA', 'Cheick'),
    ('Diabaté', 'Aïcha'), ('Ouattara', 'Brice'), ('BROU', 'Nathalie'),
    ('COULIBALY', 'Yaya'), ('FOFANA', 'Mariam'), ('YAO', 'Stéphane'),
    ('CAMARA', 'Laciné'), ('GNAHORÉ', 'Judicaël'), ('BALLÉ', 'Prisca'),
    ('TOURÉ', 'Naminata'), ('SORO', 'Wilfried'), ('KONE', 'Alphonsine'),
    ('DIABY', 'Moussa'), ('AKÉ', 'Sandrine'), ('LOUKOU', 'Armand'),
    ('KPAN', 'Ghislaine'), ('ZADI', 'Hermann'), ('N’GORAN', 'Raïssa'),
    ('BLEU', 'Constant'), ('DJÈ', 'Marina'), ('SILUÉ', 'Ténin'),
]

REPARTITION_STATUTS = [
    ('BROUILLON', 4), ('SOUMISE', 8), ('VALIDEE', 10), ('SIGNEE', 18),
    ('EN_COURS', 62), ('TERMINEE', 24), ('SOUTENUE', 20), ('VALIDEE_JURY', 12),
    ('REFUSEE', 2),
]


def _mention(note):
    if note >= 16:
        return EvaluationStage.Mention.TRES_BIEN
    if note >= 14:
        return EvaluationStage.Mention.BIEN
    if note >= 12:
        return EvaluationStage.Mention.ASSEZ_BIEN
    if note >= 10:
        return EvaluationStage.Mention.PASSABLE
    return EvaluationStage.Mention.INSUFFISANT


class Command(BaseCommand):
    help = 'Crée organismes, tuteurs, conventions et évaluations de stage d’exemple.'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true')
        parser.add_argument('--purger', action='store_true')

    def handle(self, *args, **options):
        if options['purger']:
            nb_conv, _ = ConventionStage.objects.filter(
                commentaires__startswith=MARQUE,
            ).delete()
            organismes = OrganismeAccueil.objects.filter(
                contact_email__endswith=f'@{DOMAINE}',
            )
            nb_tut = TuteurExterne.objects.filter(organisme__in=organismes).count()
            nb_org = organismes.count()
            organismes.delete()
            self.stdout.write(self.style.SUCCESS(
                f'Purge : {nb_conv} convention(s), {nb_tut} tuteur(s) et '
                f'{nb_org} organisme(s) d’exemple retirés.',
            ))
            return

        dry_run = options['dry_run']
		# Graine fixe : génération reproductible (notes, périodes).
        alea = random.Random(20261103)
        annee = AnneeAcademique.objects.filter(courante=True).first()
        if annee is None:
            self.stdout.write(self.style.WARNING('Aucune année courante : abandon.'))
            return

        # ── Organismes + tuteurs ───────────────────────────────────────────
        organismes = []
        for idx, (nom, ville, activite) in enumerate(ORGANISMES):
            organisme, _ = OrganismeAccueil.objects.get_or_create(
                nom=nom,
                defaults={
                    'ville': ville, 'raison_sociale': activite,
                    'contact_nom': 'Service des stages',
                    'contact_telephone': f'+225 27 21 {40 + idx:02d} {10 + idx:02d} {20 + idx:02d}',
                    'contact_email': f'stages{idx + 1:02d}@{DOMAINE}',
                },
            ) if not dry_run else (OrganismeAccueil(nom=nom), True)
            organismes.append(organisme)
            if not dry_run:
                for j in range(2 if idx % 3 else 1):
                    tnom, tprenom = NOMS_TUTEURS[(idx * 2 + j) % len(NOMS_TUTEURS)]
                    TuteurExterne.objects.get_or_create(
                        organisme=organisme, nom=tnom, prenom=tprenom,
                        defaults={
                            'fonction': 'Tuteur de stage',
                            'email': f'tuteur{idx + 1:02d}{j}@{DOMAINE}',
                        },
                    )

        # ── Étudiants éligibles (L3, M1, M2 inscrits validés) ─────────────
        inscriptions = list(
            InscriptionAdministrative.objects.filter(
                annee_academique=annee,
                statut=InscriptionAdministrative.Statut.VALIDEE,
                niveau__code__in=['L3', 'M1', 'M2'],
            ).select_related('etudiant', 'ref_formation').order_by('id'),
        )
        pas = max(1, len(inscriptions) // CIBLE_CONVENTIONS)
        selection = inscriptions[::pas][:CIBLE_CONVENTIONS]

        # ── Conventions (régénérées à identique) ──────────────────────────
        if not dry_run:
            ConventionStage.objects.filter(
                annee_academique=annee, commentaires__startswith=MARQUE,
            ).delete()

        tuteurs_par_org = {}
        if not dry_run:
            for tuteur in TuteurExterne.objects.filter(organisme__in=organismes):
                tuteurs_par_org.setdefault(tuteur.organisme_id, []).append(tuteur)

        statuts = []
        for code, nombre in REPARTITION_STATUTS:
            statuts.extend([code] * nombre)
        alea.shuffle(statuts)

        conventions = []
        evaluations = []
        maintenant = timezone.now()
        for i, inscription in enumerate(selection):
            statut = statuts[i % len(statuts)]
            organisme = organismes[i % len(organismes)]
            sujet = SUJETS[i % len(SUJETS)]
            if statut in ('TERMINEE', 'SOUTENUE', 'VALIDEE_JURY'):
                debut = date(2026, 10, 5) + timedelta(days=(i % 4) * 7)
                fin = debut + timedelta(weeks=8)
            elif statut == 'EN_COURS':
                debut = date(2026, 10, 19) + timedelta(days=(i % 3) * 7)
                fin = debut + timedelta(weeks=12)
            else:
                debut = date(2027, 2, 1) + timedelta(days=(i % 5) * 7)
                fin = debut + timedelta(weeks=10)
            convention = ConventionStage(
                etudiant=inscription.etudiant, annee_academique=annee,
                ref_formation=inscription.ref_formation, organisme=organisme,
                intitule=f'Stage — {sujet[:60]}…',
                sujet=sujet, objectifs='Objectifs pédagogiques définis avec le tuteur.',
                date_debut=debut, date_fin=fin,
                lieu=organisme.ville or 'Abidjan',
                statut=statut,
                commentaires=f'{MARQUE} Convention de démonstration.',
                date_soumission=maintenant if statut != 'BROUILLON' else None,
                motif_refus='Dossier incomplet (exemple).' if statut == 'REFUSEE' else '',
                date_debut_effectif=debut if statut in ('EN_COURS', 'TERMINEE', 'SOUTENUE', 'VALIDEE_JURY') else None,
                date_fin_effective=fin if statut in ('TERMINEE', 'SOUTENUE', 'VALIDEE_JURY') else None,
            )
            tuteurs = tuteurs_par_org.get(organisme.pk) or []
            if tuteurs:
                convention.tuteur_externe = tuteurs[i % len(tuteurs)]
            if statut in ('SOUTENUE', 'VALIDEE_JURY'):
                convention.note_rapport = Decimal(alea.randint(100, 180)) / 10
                convention.note_soutenance = Decimal(alea.randint(100, 185)) / 10
                convention.mention = str(_mention(float(convention.note_rapport)))
                convention.date_soutenance = maintenant
            conventions.append(convention)
            if statut in ('TERMINEE', 'SOUTENUE', 'VALIDEE_JURY'):
                notes = [Decimal(alea.randint(95, 185)) / 10 for _ in range(5)]
                finale = sum(notes) / len(notes)
                evaluations.append((convention, notes, finale))

        if not dry_run:
            ConventionStage.objects.bulk_create(conventions, batch_size=200)
            EvaluationStage.objects.bulk_create([
                EvaluationStage(
                    convention=convention,
                    note_aptitude=notes[0], note_integration=notes[1],
                    note_autonomie=notes[2], note_production=notes[3],
                    note_rapport=notes[4],
                    appreciation_libre='Travail sérieux et bonne intégration (exemple).',
                    note_finale=finale.quantize(Decimal('0.01')),
                    mention=_mention(float(finale)),
                    date_validation=maintenant,
                )
                for convention, notes, finale in evaluations
            ], batch_size=200)

        verbe = 'seraient créées' if dry_run else 'créées'
        self.stdout.write(self.style.SUCCESS(
            f'Stages d’exemple : {len(organismes)} organisme(s), '
            f'{len(conventions)} convention(s) {verbe} et '
            f'{len(evaluations)} évaluation(s) ({annee.libelle}).',
        ))
