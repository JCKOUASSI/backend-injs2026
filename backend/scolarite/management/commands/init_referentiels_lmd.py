"""Initialise les référentiels LMD de l'INJS.

Commande idempotente : elle n'écrase jamais une donnée existante et peut être
relancée sans risque. Les parcours INJS sont optionnels car ils dépendent de
l'offre de formation réellement ouverte, qui doit être confirmée par la
scolarité.

    python manage.py init_referentiels_lmd --annee 2026-2027
    python manage.py init_referentiels_lmd --avec-parcours-injs
"""

from datetime import date

from django.core.management.base import BaseCommand
from django.db import transaction

from formations.models import RefFormation
from scolarite.models import (
    AnneeAcademique,
    Niveau,
    Parcours,
    RegimeEtudes,
    Semestre,
    StatutEtudiant,
    TypeFormation,
)

TYPES_FORMATION = [
    ('LICENCE', 'Licence'),
    ('MASTER', 'Master'),
    ('FORMATION_CONTINUE', 'Formation continue'),
    ('FORMATION_INITIALE', 'Formation initiale'),
]

# (code, libellé, cycle, ordre, semestres) — semestres numérotés globalement (S1 → S10).
NIVEAUX = [
    ('L1', 'Licence 1', Niveau.Cycle.LICENCE, 1, (1, 2)),
    ('L2', 'Licence 2', Niveau.Cycle.LICENCE, 2, (3, 4)),
    ('L3', 'Licence 3', Niveau.Cycle.LICENCE, 3, (5, 6)),
    ('M1', 'Master 1', Niveau.Cycle.MASTER, 4, (7, 8)),
    ('M2', 'Master 2', Niveau.Cycle.MASTER, 5, (9, 10)),
]

REGIMES = [
    ('INITIAL', 'Formation initiale'),
    ('CONTINU', 'Formation continue'),
    ('ALTERNANCE', 'Alternance'),
    ('PROFESSIONNEL', 'Formation professionnelle'),
]

# bloque_inscription : empêche toute nouvelle inscription tant que le statut est actif.
STATUTS_ETUDIANT = [
    ('ACTIF', 'Actif', False),
    ('SUSPENDU', 'Suspendu', True),
    ('ABANDON', 'Abandon', True),
    ('EXCLU', 'Exclu', True),
    ('DIPLOME', 'Diplômé', False),
    ('TRANSFERE', 'Transféré', True),
]

# Filières historiques de l'INJS. Créées uniquement sur demande explicite,
# et rattachées au cycle de formation portant le même intitulé s'il existe.
PARCOURS_INJS = [
    ('EM', 'Éducation et Motricité'),
    ('ES', 'Entraînement Sportif'),
    ('MS', 'Management du Sport'),
    ('APAS', 'Activité Physique Adaptée et Santé'),
    ('ASE', 'Animation Socio-Éducative'),
    ('MJ', 'Métiers de la Jeunesse'),
]


class Command(BaseCommand):
    help = "Initialise les référentiels LMD (niveaux, semestres, régimes, statuts, année académique)."

    def add_arguments(self, parser):
        parser.add_argument(
            '--annee',
            help="Année académique à créer, au format 2026-2027. Omettre pour ne pas en créer.",
        )
        parser.add_argument(
            '--courante',
            action='store_true',
            help="Marque l'année créée comme année courante.",
        )
        parser.add_argument(
            '--avec-parcours-injs',
            action='store_true',
            help="Crée aussi les parcours INJS, rattachés au premier cycle de formation actif.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        self._creer_types_formation()
        self._creer_niveaux_et_semestres()
        self._creer_simples(RegimeEtudes, REGIMES, "Régimes d'études")
        self._creer_statuts()

        if options['annee']:
            self._creer_annee(options['annee'], courante=options['courante'])
        if options['avec_parcours_injs']:
            self._creer_parcours_injs()

        self.stdout.write(self.style.SUCCESS('Référentiels LMD initialisés.'))

    def _creer_types_formation(self):
        crees = 0
        for code, libelle in TYPES_FORMATION:
            _, cree = TypeFormation.objects.get_or_create(code=code, defaults={'libelle': libelle})
            crees += int(cree)
        self.stdout.write(f'Types de formation : {crees} créé(s), {len(TYPES_FORMATION) - crees} déjà présent(s).')

    def _creer_niveaux_et_semestres(self):
        niveaux_crees = semestres_crees = 0
        for code, libelle, cycle, ordre, numeros in NIVEAUX:
            niveau, cree = Niveau.objects.get_or_create(
                code=code,
                defaults={'libelle': libelle, 'cycle': cycle, 'ordre': ordre},
            )
            niveaux_crees += int(cree)
            for numero in numeros:
                _, cree_sem = Semestre.objects.get_or_create(
                    niveau=niveau,
                    numero=numero,
                    defaults={'libelle': f'S{numero}'},
                )
                semestres_crees += int(cree_sem)
        self.stdout.write(f'Niveaux : {niveaux_crees} créé(s). Semestres : {semestres_crees} créé(s).')

    def _creer_simples(self, model, entrees, label):
        crees = 0
        for code, libelle in entrees:
            _, cree = model.objects.get_or_create(code=code, defaults={'libelle': libelle})
            crees += int(cree)
        self.stdout.write(f'{label} : {crees} créé(s), {len(entrees) - crees} déjà présent(s).')

    def _creer_statuts(self):
        crees = 0
        for code, libelle, bloque in STATUTS_ETUDIANT:
            _, cree = StatutEtudiant.objects.get_or_create(
                code=code,
                defaults={'libelle': libelle, 'bloque_inscription': bloque},
            )
            crees += int(cree)
        self.stdout.write(f'Statuts étudiant : {crees} créé(s), {len(STATUTS_ETUDIANT) - crees} déjà présent(s).')

    def _creer_annee(self, libelle, courante):
        try:
            debut_annee = int(libelle.split('-')[0])
        except (ValueError, IndexError):
            self.stderr.write(self.style.ERROR(f"Format d'année invalide : {libelle}. Attendu : 2026-2027."))
            return
        # Marquer une nouvelle année courante impose de libérer la précédente,
        # la contrainte d'unicité partielle n'autorisant qu'une seule année courante.
        if courante:
            AnneeAcademique.objects.filter(courante=True).exclude(libelle=libelle).update(courante=False)
        annee, cree = AnneeAcademique.objects.get_or_create(
            libelle=libelle,
            defaults={
                'date_debut': date(debut_annee, 10, 1),
                'date_fin': date(debut_annee + 1, 9, 30),
                'courante': courante,
            },
        )
        if not cree and courante and not annee.courante:
            annee.courante = True
            annee.save(update_fields=['courante'])
        self.stdout.write(f"Année académique {libelle} : {'créée' if cree else 'déjà présente'}.")

    def _creer_parcours_injs(self):
        formation = RefFormation.objects.filter(actif=True).order_by('intitule').first()
        if formation is None:
            self.stderr.write(self.style.WARNING(
                "Aucun cycle de formation actif : parcours INJS non créés. "
                "Créez d'abord un RefFormation, puis relancez avec --avec-parcours-injs."
            ))
            return
        type_licence = TypeFormation.objects.filter(code='LICENCE').first()
        crees = 0
        for code, intitule in PARCOURS_INJS:
            _, cree = Parcours.objects.get_or_create(
                ref_formation=formation,
                code=code,
                defaults={'intitule': intitule, 'type_formation': type_licence},
            )
            crees += int(cree)
        self.stdout.write(
            f'Parcours INJS : {crees} créé(s) sur le cycle « {formation.intitule} ». '
            'Vérifiez leur rattachement avec la scolarité.'
        )
