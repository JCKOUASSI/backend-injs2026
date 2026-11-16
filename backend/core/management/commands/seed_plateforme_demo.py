"""Orchestration explicite de la démonstration complète (jamais au démarrage).

Le calendrier courant et les comptes administrateurs existants ne sont pas
réinitialisés. Pour l'année courante : 40 maquettes, 531 UE, 779 ECUE,
5 000 étudiants fictifs paritaires et affectation de chaque ECUE à un
enseignant fictif spécialisé, sans dépasser la charge annuelle autorisée.
Les autres modules reçoivent leurs scénarios d'exemple existants.

La commande n'effectue AUCUNE sauvegarde : l'opérateur doit faire un dump
vérifié hors conteneur AVANT --appliquer. Une erreur peut laisser un
remplissage partiel ; relancer la commande après correction (seeds idempotents).
"""
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from formations.models import Formateur, Participant, RefFormation
from scolarite.models import (
    AffectationPedagogique, AnneeAcademique, ECUE, InscriptionAdministrative,
    Maquette, Niveau, Parcours, Semestre, TypeFormation, UE,
)

ETAPES = (
    'init_referentiels_lmd',
    'configurer_referentiel_injs',
    'completer_referentiel_lmd',
    'peupler_charges_pedagogiques_injs',
    'init_referentiels_admission',
    'seed_candidatures_demo',
    'seed_equivalences_demo',
    'reconstruire_journal_parcours',
    'seed_stages_demo',
    'seed_administration_demo',
    'seed_personnel_demo',
    'seed_jurys_demo',
    'seed_diplomation_demo',
    'seed_evaluations_demo',
    'seed_finances_demo',
)


class Command(BaseCommand):
    help = 'Prépare ou vérifie la démonstration complète, sans toucher au calendrier.'

    def add_arguments(self, parser):
        parser.add_argument('--effectif', type=int, default=5000,
                            help='Effectif pair de la cohorte fictive (défaut : 5000).')
        parser.add_argument('--base', required=True,
                            help='Nom EXACT de la base cible (garde-fou).')
        parser.add_argument('--appliquer', action='store_true',
                            help='Exécuter les seeds après sauvegarde externe vérifiée.')
        parser.add_argument('--confirmer', default='',
                            help='Avec --appliquer, saisir DEMO_FICTIVE pour confirmer.')

    def _cohorte(self):
        return Participant.objects.filter(email__regex=r'\.\d+@exemple\.ci$')

    def _etat(self, annee):
        cohorte = self._cohorte()
        maquettes = Maquette.objects.filter(annee_academique=annee)
        actives = maquettes.filter(statut=Maquette.Statut.ACTIVE)
        ue = UE.objects.filter(maquette__in=maquettes)
        ecue = ECUE.objects.filter(ue__in=ue)
        inscrits = InscriptionAdministrative.objects.filter(
            annee_academique=annee, etudiant__participant__in=cohorte,
            statut=InscriptionAdministrative.Statut.VALIDEE,
        )
        couverture = AffectationPedagogique.objects.filter(
            annee_academique=annee, ecue__in=ecue,
        ).exclude(statut=AffectationPedagogique.Statut.ANNULEE)
        return {
            'formations': RefFormation.objects.filter(actif=True).count(),
            'maquettes_actives': actives.count(),
            'ue': ue.count(), 'ecue': ecue.count(),
            'niveaux': Niveau.objects.count(), 'parcours': Parcours.objects.count(),
            'semestres': Semestre.objects.count(),
            'types_formation': TypeFormation.objects.count(),
            'etudiants_fictifs': cohorte.count(),
            'femmes': cohorte.filter(sexe='FEMININ').count(),
            'hommes': cohorte.filter(sexe='MASCULIN').count(),
            'inscriptions_validees': inscrits.count(),
            'enseignants_fictifs': Formateur.objects.filter(
                numerobadge__startswith='ENS-DEMO-').count(),
            'ecue_affectees': couverture.values('ecue_id').distinct().count(),
        }

    def handle(self, *args, **options):
        cible = str(settings.DATABASES['default']['NAME'])
        if options['base'] != cible:
            raise CommandError(f'Base refusée : cible déclarée {options["base"]!r}, réelle {cible!r}.')
        if connection.vendor not in ('postgresql', 'sqlite'):
            raise CommandError('Moteur de base non pris en charge.')
        n = options['effectif']
        if not 2 <= n <= 100000 or n % 2:
            raise CommandError('--effectif doit être pair et compris entre 2 et 100000.')
        annee = AnneeAcademique.objects.filter(courante=True).first()
        if annee is None:
            raise CommandError('Année courante manquante : ne pas inventer le calendrier.')
        calendrier_initial = (
            annee.date_debut, annee.date_fin, annee.courante,
            annee.cloturee, annee.actif,
        )
        self.stdout.write(f'Base : {cible} ({connection.vendor}) ; année préservée : '
                          f'{annee.libelle} ({annee.date_debut} → {annee.date_fin})')
        if options['appliquer']:
            if options['confirmer'] != 'DEMO_FICTIVE':
                raise CommandError('Sauvegarde vérifiée requise ; confirmer avec '
                                   '--confirmer DEMO_FICTIVE pour écrire.')
            deja = self._cohorte().count()
            if deja and deja != n:
                raise CommandError(f'{deja} étudiants fictifs présents, cible {n} : '
                                   'aucun mélange de cohortes de tailles différentes.')
            for commande in ETAPES:
                self.stdout.write(f'→ {commande}' + (f' --effectif {n}' if commande == 'seed_candidatures_demo' else ''))
                if commande == 'seed_candidatures_demo':
                    call_command(commande, effectif=n, stdout=self.stdout)
                else:
                    call_command(commande, stdout=self.stdout)
            annee.refresh_from_db()
            if (annee.date_debut, annee.date_fin, annee.courante,
                    annee.cloturee, annee.actif) != calendrier_initial:
                raise CommandError('Calendrier modifié pendant le remplissage : '
                                   'contrôle manuel et restauration à envisager.')
            self.stdout.write(self.style.SUCCESS('Démonstration exécutée.'))
        else:
            self.stdout.write('Aucune écriture : ajouter --appliquer --confirmer DEMO_FICTIVE après sauvegarde.')
            self.stdout.write('Étapes : ' + ', '.join(ETAPES))
        etat = self._etat(annee)
        for cle, valeur in etat.items():
            self.stdout.write(f'  {cle}: {valeur}')
        if options['appliquer']:
            attendus = {
                'formations': 16, 'maquettes_actives': 40, 'ue': 531, 'ecue': 779,
                'niveaux': 8, 'parcours': 16, 'semestres': 16,
                'types_formation': 4, 'etudiants_fictifs': n,
                'femmes': n // 2, 'hommes': n // 2,
                'inscriptions_validees': n, 'ecue_affectees': etat['ecue'],
            }
            ecarts = [f'{cle}={etat[cle]} (attendu {attendu})'
                      for cle, attendu in attendus.items() if etat[cle] != attendu]
            if etat['enseignants_fictifs'] < 1:
                ecarts.append('aucun enseignant fictif affecté')
            if ecarts:
                raise CommandError('Démonstration incomplète : ' + '; '.join(ecarts))
            self.stdout.write(self.style.SUCCESS('Contrôles chiffrés OK ; calendrier inchangé.'))
