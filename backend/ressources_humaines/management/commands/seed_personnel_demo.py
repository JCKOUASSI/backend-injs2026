"""Données d'exemple du module Personnel (RH administrative, tâche 34).

Idempotent et étiqueté : fonctions génériques par service existant,
24 agents fictifs (matricules EX-AGT-…, courriels @exemple.injs.ci,
aucun compte de connexion), leurs affectations, indisponibilités et
métadonnées de documents RH. Les enseignants restent au registre
formateurs (grade métier) — ici, le personnel administratif et
technique. ``--purger`` retire uniquement ces lignes.
"""
from datetime import date, timedelta

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from ressources_humaines.models import (
    Agent, AffectationRH, DisponibiliteAgent, DocumentRH, Fonction, Service,
)

MARQUEUR = '[Exemple]'

PERSONNES = [
    ('DIABY', 'Aïcha'), ('Koffi', 'Jean-Bosco'), ('N’DRI', 'Sandrine'),
    ('TRAORÉ', 'Mamadou'), ('Yéo', 'Fatou'), ('Koné', 'Ibrahim'),
    ('TOURÉ', 'Adjoua'), ('BAKAYOKO', 'Yacouba'), ('Coulibaly', 'Rokia'),
    ('Konan', 'Eric Fabrice'), ('SORO', 'Windé'), ('Aka', 'Marie Reine'),
    ('Diakité', 'Mariam'), ('N’GUESSAN', 'Hervé'), ('Hervé', 'Patricia'),
    ('Sow', 'Alhassane'), ('Diallo', 'Hadja'), ('Nanglais', 'Sylviane'),
    ('Bamba', 'Amadou'), ('Tchoua', 'Laetitia'), ('Yapi', 'Constant'),
    ('Ibrahim', 'Nadia'), ('Blé', 'Ghislain'), ('Soumaro', 'Ouattara'),
]

TYPES_CONTRAT = [
    'FONCTIONNAIRE', 'FONCTIONNAIRE', 'CONTRAT', 'FONCTIONNAIRE',
    'CONTRAT', 'CONTRAT', 'FONCTIONNAIRE', 'VACATAIRE',
]

FONCTIONS_PAR_SERVICE = {
    'SRV-ADM': ['Chef du service des admissions', 'Agent d’accueil et d’inscription'],
    'SRV-EXAM': ['Chef du service des examens', 'Gestionnaire des concours'],
    'SRV-PROG': ['Chef du service des programmes', 'Assistant pédagogie'],
    'SRV-DOC': ['Documentaliste', 'Aide-documentaliste'],
    'SRV-RECH': ['Chargé de la recherche', 'Chargé des publications'],
    'SRV-BUD': ['Chef du service du budget', 'Gestionnaire budgétaire'],
    'SRV-TRE': ['Chef du service de la trésorerie', 'Comptable'],
    'SRV-CAR': ['Chef du service des carrières', 'Assistant RH'],
    'SRV-FC': ['Chef du service des stages', 'Gestionnaire des stages'],
    'SRV-MAIN': ['Chef du service maintenance', 'Technicien de maintenance'],
    'SRV-INFRA': ['Chef du service des infrastructures', 'Gestionnaire des infrastructures'],
    'SRV-COM': ['Chargé de communication', 'Photographe'],
    'SRV-QUAL': ['Responsable qualité', 'Chargé d’évaluation'],
    'SRV-ACC': ['Agent d’accueil', 'Agent du courrier'],
}


class Command(BaseCommand):
    help = 'Données d’exemple [Exemple] du module Personnel.'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true')
        parser.add_argument('--purger', action='store_true')

    def handle(self, *args, **options):
        if options['purger']:
            self._purger()
            return
        services = {s.code: s for s in Service.objects.filter(code__in=FONCTIONS_PAR_SERVICE)}
        if not services:
            # Repli : tout service actif existant (fonctions génériques).
            services = {f'S{i}': s for i, s in enumerate(
                Service.objects.filter(actif=True).order_by('id')[:5],
            )}
            for code in services:
                FONCTIONS_PAR_SERVICE.setdefault(code, [
                    'Chef de service', 'Agent administratif',
                ])
        if not services:
            raise CommandError(
                'Aucun service disponible : lancer d’abord '
                'seed_administration_demo.',
            )
        with transaction.atomic():
            fonctions = []
            for code, intitules in FONCTIONS_PAR_SERVICE.items():
                service = services.get(code)
                if service is None:
                    continue
                for intitule in intitules:
                    fonc, _ = Fonction.objects.update_or_create(
                        service=service, intitule=intitule,
                        defaults={'grade': '', 'actif': True},
                    )
                    fonctions.append(fonc)

            agents = []
            for rang, (nom, prenom) in enumerate(PERSONNES, start=1):
                inactif = rang in (23, 24)
                agent, _ = Agent.objects.update_or_create(
                    matricule=f'EX-AGT-{rang:03d}',
                    defaults={
                        'nom': nom, 'prenom': prenom,
                        'email': f'agent{rang:02d}@exemple.injs.ci',
                        'telephone': f'+225 07 07 45 {40 + rang:02d} 1{rang:02d}',
                        'type_contrat': TYPES_CONTRAT[(rang - 1) % 8],
                        'statut': (
                            Agent.Statut.INACTIF if inactif
                            else Agent.Statut.ACTIF
                        ),
                        'date_entree': date(2019 + (rang % 7), 9, 1),
                        'date_sortie': date(2026, 6, 30) if inactif else None,
                        'user': None,
                    },
                )
                agents.append(agent)

            for rang, agent in enumerate(agents):
                if agent.statut != Agent.Statut.ACTIF:
                    continue
                fonction = fonctions[rang % len(fonctions)]
                AffectationRH.objects.update_or_create(
                    agent=agent, fonction=fonction,
                    date_debut=agent.date_entree,
                    defaults={'date_fin': None},
                )

            types_indispo = [
                ('CONGE', 'Congé annuel', 12), ('MISSION', 'Supervision des stages', 4),
                ('FORMATION', 'Perfectionnement bureautique', 5),
                ('CONGE', 'Congé annuel (2e tranche)', 10),
                ('MISSION', 'Inventaire régional', 3),
                ('FORMATION', 'Gestion documentaire', 5),
            ]
            for rang, agent in enumerate(agents[:16]):
                type_i, motif, duree = types_indispo[rang % len(types_indispo)]
                debut = date(2026, 10, 5) + timedelta(days=rang * 7)
                DisponibiliteAgent.objects.update_or_create(
                    agent=agent, date_debut=debut,
                    defaults={
                        'type_indispo': type_i,
                        'motif': f'{MARQUEUR} {motif}',
                        'date_fin': debut + timedelta(days=duree - 1),
                    },
                )

            types_doc = [
                ('CONTRAT', 'Contrat de travail signé'),
                ('AVIS', 'Avis de situation administrative'),
                ('EVALUATION', 'Fiche d’évaluation annuelle'),
                ('ATTESTATION', 'Attestation de prise de service'),
            ]
            for rang, agent in enumerate(agents[:20]):
                type_d, intitule = types_doc[rang % len(types_doc)]
                DocumentRH.objects.update_or_create(
                    agent=agent, intitule=f'{MARQUEUR} {intitule}',
                    defaults={'type_document': type_d},
                )

            if options['dry_run']:
                transaction.set_rollback(True)

        self.stdout.write(self.style.SUCCESS(
            f'Personnel d’exemple : '
            f'{Fonction.objects.count()} fonctions, '
            f'{Agent.objects.filter(matricule__startswith="EX-AGT-").count()} agents, '
            f'{AffectationRH.objects.filter(agent__matricule__startswith="EX-AGT-").count()} affectations, '
            f'{DisponibiliteAgent.objects.filter(motif__startswith=MARQUEUR).count()} indisponibilités, '
            f'{DocumentRH.objects.filter(intitule__startswith=MARQUEUR).count()} documents.',
        ))

    def _purger(self):
        with transaction.atomic():
            Agent.objects.filter(matricule__startswith='EX-AGT-').delete()
        self.stdout.write(self.style.SUCCESS(
            'Purge personnel d’exemple terminée (affectations, '
            'indisponibilités et documents retirés en cascade).'
        ))
