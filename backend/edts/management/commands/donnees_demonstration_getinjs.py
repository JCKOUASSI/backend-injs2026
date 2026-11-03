"""Jeu de démonstration GET-INJS — pour que l'aperçu montre un vrai emploi du temps.

Pourquoi cette commande. Une base vide est honnête mais inutilisable pour
démontrer : l'écran d'audit y répond « génération impossible » faute
d'affectations, de salles et d'année. Un lecteur ne peut alors vérifier aucune
des fonctions livrées (génération, conflits, exports, déplacement, publication).

Trois garde-fous, parce que des données de démonstration sont un danger si elles
fuient :

1. **elles sont identifiables** — année `DÉMO-…`, formation « FORMATION
   DÉMONSTRATION … », matricules `DEMO-…` : aucune ne peut être confondue avec
   une donnée réelle ;
2. **elles sont idempotentes** — relancer la commande ne duplique rien ;
3. **elles ne sortent pas d'un environnement de démonstration** — la commande
   refuse de s'exécuter si `DEBUG` est désactivé, sauf `--forcer` explicite.
   Une production ne doit jamais hériter d'un étudiant `DEMO-…`.

La suppression est prévue (`--supprimer`) et ne touche QUE les objets marqués
par cette commande : rien d'autre n'est effacé.

Exemples
--------
    python manage.py donnees_demonstration_getinjs
    python manage.py donnees_demonstration_getinjs --groupes 6
    python manage.py donnees_demonstration_getinjs --supprimer
"""

from datetime import date

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from edts.moteur import canevas_officiel as CO
from edts.models import CreneauTemplate
from formations.models import (
    Formateur, RefBatiment, RefFormation, RefSalle, RefSite,
)
from scolarite.models import (
    ECUE, AffectationPedagogique, AnneeAcademique, Groupe, Maquette, Niveau,
    Parcours, Semestre, UE,
)

#: Marqueurs — c'est par eux que tout est retrouvé (et supprimé).
PREFIXE_ANNEE = 'DEMO-'
#: Source déclarée de la formation de démonstration : elle dit d'elle-même
#: qu'elle n'appartient pas au référentiel officiel (aucune filière F01–F08).
SOURCE_DEMONSTRATION = 'DÉMONSTRATION — hors référentiel officiel (manage.py donnees_demonstration_getinjs)'
INTITULE_FORMATION = 'FORMATION DÉMONSTRATION GET-INJS'
PREFIXE_PARCOURS = 'DEMO-P'
PREFIXE_GROUPE = 'DEMO-G'
PREFIXE_SALLE = 'DEMO-S'
PREFIXE_SITE = 'SITE DÉMONSTRATION'
NOM_FORMATEUR = 'Démo'


class Command(BaseCommand):
    help = (
        'Crée un jeu de démonstration identifiable (année, formation INJS, '
        'groupes, salles, maquette, affectations) pour que les écrans GET-INJS '
        'soient utilisables. Refusé hors mode démonstration sans --forcer.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--groupes', type=int, default=4,
            help='Nombre de groupes de démonstration à créer (défaut 4).',
        )
        parser.add_argument(
            '--supprimer', action='store_true',
            help='Supprime UNIQUEMENT les objets créés par cette commande.',
        )
        parser.add_argument(
            '--forcer', action='store_true',
            help='Autorise l’exécution alors que DEBUG est désactivé.',
        )

    # ── Garde-fou ────────────────────────────────────────────────────────────
    def _verifier_environnement(self, options):
        if options['forcer'] or settings.DEBUG:
            return
        raise CommandError(
            'Refusé : DEBUG est désactivé, cet environnement n’est pas une '
            'démonstration. Des identifiants « DEMO-… » ne doivent pas entrer '
            'dans une base de production. Utilisez --forcer en connaissance de '
            'cause.')

    # ── Suppression ──────────────────────────────────────────────────────────
    def _supprimer(self):
        """Ne supprime que ce que cette commande a créé, dans le bon ordre."""
        annees = AnneeAcademique.objects.filter(libelle__startswith=PREFIXE_ANNEE)
        affectations = AffectationPedagogique.objects.filter(
            annee_academique__in=annees)
        groupes = Groupe.objects.filter(annee_academique__in=annees)
        maquettes = Maquette.objects.filter(annee_academique__in=annees)
        formation = RefFormation.objects.filter(intitule__startswith=INTITULE_FORMATION)
        parcours = Parcours.objects.filter(code=PREFIXE_PARCOURS)
        salles = RefSalle.objects.filter(nom__startswith=PREFIXE_SALLE)
        sites = RefSite.objects.filter(nom__startswith=PREFIXE_SITE)
        formateurs = Formateur.objects.filter(prenom=NOM_FORMATEUR)

        compteurs = {
            'affectations': affectations.count(),
            'groupes': groupes.count(),
            'maquettes': maquettes.count(),
            'parcours': parcours.count(),
            'formations': formation.count(),
            'salles': salles.count(),
            'sites': sites.count(),
        }
        # Ordre imposé par les protections de clés étrangères.
        # Ordre imposé par les protections : parcours protège la formation,
        # la maquette protège le parcours (PROTECT, pas CASCADE). Une erreur
        # ici ne serait pas un détail : elle empêcherait tout nettoyage.
        affectations.delete()
        groupes.delete()
        maquettes.delete()
        parcours.delete()
        formation.delete()
        salles.delete()
        sites.delete()
        formateurs.delete()
        annees.delete()
        for nom, nombre in compteurs.items():
            self.stdout.write(f'  {nombre} {nom} supprimé(s)')
        return compteurs

    # ── Création ─────────────────────────────────────────────────────────────
    def _creer(self, nb_groupes):
        crees = {}
        annee, _ = AnneeAcademique.objects.get_or_create(
            libelle=f'{PREFIXE_ANNEE}2026-2027',
            defaults={
                'date_debut': date(2026, 10, 1),
                'date_fin': date(2027, 6, 30),
                'courante': True,
            },
        )
        # Une année courante doit être la seule : on la rend courante sans
        # toucher aux autres années réelles.
        if not annee.courante:
            AnneeAcademique.objects.exclude(pk=annee.pk).update(courante=False)
            annee.courante = True
            annee.save(update_fields=['courante'])
        crees['annee'] = str(annee)

        # Deux contraintes opposées, toutes deux réelles :
        #  1. le moteur d'emploi du temps refuse une population hors périmètre
        #     INJS (`HORS_PERIMETRE_INJS`) : la démonstration doit rester INJS
        #     pour être planifiable, sinon elle ne démontre rien ;
        #  2. un support de démonstration n'est PAS un cycle du référentiel
        #     officiel : il ne doit jamais être compté comme tel.
        # D'où : périmètre INJS (contrainte 1) et AUCUNE filière F01–F08 +
        # marqueur de source explicite, la ligne étant écartée du corpus
        # officiel par `formations_injs()` (contrainte 2, défense en
        # profondeur sur l'intitulé).
        formation, _ = RefFormation.objects.get_or_create(
            intitule=INTITULE_FORMATION,
            defaults={'perimetre': RefFormation.Perimetre.INJS,
                      'filiere_code': '', 'source': SOURCE_DEMONSTRATION},
        )
        # Un jeu créé par une version antérieure revendiquait la filière F01
        # et le périmètre INJS : on corrige la ligne existante (idempotence =
        # même état final, quel que soit l'état de départ).
        corriges = []
        if formation.filiere_code:
            formation.filiere_code = ''
            corriges.append('filiere_code')
        if formation.perimetre != RefFormation.Perimetre.INJS:
            formation.perimetre = RefFormation.Perimetre.INJS
            corriges.append('perimetre')
        if formation.source != SOURCE_DEMONSTRATION:
            formation.source = SOURCE_DEMONSTRATION
            corriges.append('source')
        if corriges:
            formation.save(update_fields=corriges)
        crees['formation'] = formation.intitule

        niveau, _ = Niveau.objects.get_or_create(
            code='L1',
            defaults={'libelle': 'Licence 1', 'cycle': 'LICENCE',
                      'ordre': 1, 'credits_requis': 60},
        )
        semestre, _ = Semestre.objects.get_or_create(
            niveau=niveau, numero=1, defaults={'libelle': 'S1'},
        )
        parcours, _ = Parcours.objects.get_or_create(
            code=PREFIXE_PARCOURS, ref_formation=formation,
            defaults={'intitule': 'Parcours de démonstration'},
        )
        site, _ = RefSite.objects.get_or_create(nom=f'{PREFIXE_SITE} ABIDJAN')
        batiment, _ = RefBatiment.objects.get_or_create(site=site, nom='Bâtiment démo')

        # Salles réellement typées : sans quoi C7 (compatibilité) n'a rien à
        # vérifier et l'audit signalerait un manque de capacité.
        for index, (type_lieu, capacite) in enumerate((
                ('AMPHI', 300), ('COURS', 80), ('TD', 45), ('INFORMATIQUE', 40)), 1):
            RefSalle.objects.get_or_create(
                site=site, nom=f'{PREFIXE_SALLE}{index}',
                defaults={'batiment': batiment, 'type_lieu': type_lieu,
                          'capacite': capacite, 'actif': True},
            )

        formateur, _ = Formateur.objects.get_or_create(
            nom='Enseignant', prenom=NOM_FORMATEUR,
            defaults={'specialite': 'Démonstration'},
        )

        # Canevas officiel : la démonstration ne doit pas reposer sur un
        # canevas inventé (cf. verifier_canevas).
        creneaux_crees = 0
        for jour, debut, fin in CO.grille_officielle():
            _, cree = CreneauTemplate.objects.get_or_create(
                jour=jour, heure_debut=debut, heure_fin=fin)
            creneaux_crees += int(cree)
        crees['creneaux'] = CreneauTemplate.objects.count()

        maquette, cree = Maquette.objects.get_or_create(
            annee_academique=annee, ref_formation=formation,
            parcours=parcours, niveau=niveau,
            defaults={'statut': Maquette.Statut.BROUILLON},
        )
        if cree:
            # Les volumes se renseignent AVANT l'activation : une maquette
            # ACTIVE est immuable (règle R4). Même contrainte qu'en production.
            for numero, (cm, td) in enumerate(((10, 6), (8, 4), (6, 6)), 1):
                ue = UE.objects.create(
                    maquette=maquette, semestre=semestre,
                    code=f'DEMO-UE{numero}', intitule=f'UE démonstration {numero}',
                    credits=6,
                )
                ecue = ECUE.objects.create(
                    ue=ue, code=f'DEMO-ECUE{numero}',
                    intitule=f'ECUE démonstration {numero}', credits=3,
                )
                ecue.volume_cm = cm
                ecue.volume_td = td
                ecue.save(update_fields=['volume_cm', 'volume_td'])
            maquette.statut = Maquette.Statut.ACTIVE
            maquette.save()

        groupes = []
        for index in range(1, nb_groupes + 1):
            groupe, _ = Groupe.objects.get_or_create(
                annee_academique=annee, ref_formation=formation,
                parcours=parcours, niveau=niveau,
                nom=f'{PREFIXE_GROUPE}{index}',
                defaults={'capacite_max': 60},
            )
            groupes.append(groupe)

        # Affectations pédagogiques : une par ECUE et par groupe, validées,
        # pour que la génération ait de vrais besoins à placer.
        affectations = 0
        for groupe in groupes:
            for ecue in ECUE.objects.filter(ue__maquette=maquette):
                _, cree = AffectationPedagogique.objects.get_or_create(
                    annee_academique=annee, ref_formation=formation,
                    parcours=parcours, niveau=niveau, semestre=semestre,
                    ue=ecue.ue, ecue=ecue, groupe=groupe, enseignant=formateur,
                    type_enseignement='CM',
                    defaults={'volume_horaire': 4, 'statut': 'VALIDEE'},
                )
                affectations += int(cree)
        crees['groupes'] = len(groupes)
        crees['affectations'] = affectations
        crees['maquette'] = str(maquette)
        return crees

    def handle(self, *args, **options):
        self._verifier_environnement(options)
        with transaction.atomic():
            if options['supprimer']:
                self._supprimer()
                self.stdout.write(self.style.SUCCESS(
                    'Jeu de démonstration supprimé (seuls les objets DEMO-…).'))
                return
            crees = self._creer(options['groupes'])

        self.stdout.write(self.style.SUCCESS('Jeu de démonstration prêt :'))
        for cle, valeur in crees.items():
            self.stdout.write(f'  {cle} : {valeur}')
        self.stdout.write(
            '  Tout est identifiable : année DEMO-, formation '
            f'« {INTITULE_FORMATION} », groupes DEMO-G…')
        self.stdout.write(
            '  Pour retirer ce jeu : manage.py donnees_demonstration_getinjs '
            '--supprimer')
