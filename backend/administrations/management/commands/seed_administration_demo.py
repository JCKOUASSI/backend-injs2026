"""Données d'exemple du module Administration générale (tâche 34).

Alimente, de façon strictement idempotente et étiquetée « [Exemple] » :
- l'organigramme : 5 directions génériques, 10 départements, 14 services
  (responsables non désignés : aucun titulaire de poste n'est inventé) ;
- 40 courriers (références EX-2026/…, objets génériques) ;
- 12 documents officiels, 16 réunions/commissions, 12 missions
  (budget laissé à 0 : aucun montant n'est inventé).

``--purger`` retire uniquement les lignes d'exemple (signatures
[Exemple] / EX-2026 / codes d'unités du seed).
"""
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from administrations.models import (
    Courrier, Departement, Direction, DocumentOfficiel, Mission,
    ReunionCommission,
)
from ressources_humaines.models import Service

User = get_user_model()

DIRECTIONS = [
    ('DG', 'Direction Générale'),
    ('DFRC', 'Direction des formations et de la recherche'),
    ('DFC', 'Direction des finances et de la comptabilité'),
    ('DRH', 'Direction des ressources humaines'),
    ('DSLM', 'Direction des services logistiques et du matériel'),
]

DEPARTEMENTS = [
    ('DG', 'DG-COM', 'Département communication et relations extérieures'),
    ('DG', 'DG-CIQ', 'Département contrôle interne et qualité'),
    ('DFRC', 'DFRC-SCOL', 'Département scolarité et vie étudiante'),
    ('DFRC', 'DFRC-PED', 'Département pédagogie et programmes'),
    ('DFRC', 'DFRC-RECH', 'Département recherche et coopération'),
    ('DFC', 'DFC-BUD', 'Département budget et ordonnancement'),
    ('DFC', 'DFC-CPT', 'Département comptabilité et trésorerie'),
    ('DRH', 'DRH-PERS', 'Département gestion du personnel'),
    ('DRH', 'DRH-FC', 'Département formation continue'),
    ('DSLM', 'DSLM-LOG', 'Département logistique et infrastructures'),
]

SERVICES = [
    ('DG-COM', 'SRV-COM', 'Service communication et relations publiques'),
    ('DG-CIQ', 'SRV-QUAL', 'Service qualité et évaluation interne'),
    ('DFRC-SCOL', 'SRV-ADM', 'Service des admissions et des inscriptions'),
    ('DFRC-SCOL', 'SRV-EXAM', 'Service des examens et concours'),
    ('DFRC-PED', 'SRV-PROG', 'Service des programmes et maquettes'),
    ('DFRC-PED', 'SRV-DOC', 'Service documentation et bibliothèque'),
    ('DFRC-RECH', 'SRV-RECH', 'Service de la recherche et des publications'),
    ('DFC-BUD', 'SRV-BUD', 'Service du budget'),
    ('DFC-CPT', 'SRV-TRE', 'Service de la trésorerie'),
    ('DRH-PERS', 'SRV-CAR', 'Service des carrières et dossiers du personnel'),
    ('DRH-FC', 'SRV-FC', 'Service des stages et du perfectionnement'),
    ('DSLM-LOG', 'SRV-MAIN', 'Service maintenance et patrimoine'),
    ('DSLM-LOG', 'SRV-INFRA', 'Service des infrastructures sportives'),
    ('DG-COM', 'SRV-ACC', 'Service accueil et courrier'),
]

COURRIERS_OBJETS = [
    ('ENTRANT', 'Transmission de la liste des admis aux concours d’entrée',
     'Cabinet du ministère de tutelle', 'Direction Générale'),
    ('ENTRANT', 'Demande de mise à disposition d’équipements sportifs',
     'Direction régionale des sports', 'Direction des services logistiques'),
    ('ENTRANT', 'Invitation au comité national de pilotage de la formation',
     'Direction des ressources humaines du ministère', 'Direction Générale'),
    ('ENTRANT', 'Demande d’homologation des infrastructures sportives',
     'Fédération sportive nationale', 'Service des infrastructures sportives'),
    ('ENTRANT', 'Transmission du calendrier des compétitions universitaires',
     'Office national des sports scolaires et universitaires',
     'Département scolarité et vie étudiante'),
    ('ENTRANT', 'Demande de partenariat pour l’encadrement des stages',
     'Collectivité territoriale', 'Service des stages et du perfectionnement'),
    ('ENTRANT', 'Notification des crédits de fonctionnement 2026-2027',
     'Direction des affaires financières', 'Direction des finances'),
    ('ENTRANT', 'Demande d’audience — délégation des anciens élèves',
     'Association des anciens apprenants', 'Direction Générale'),
    ('ENTRANT', 'Transmission des maquettes pédagogiques révisées',
     'Conseil de perfectionnement', 'Service des programmes et maquettes'),
    ('ENTRANT', 'Demande de renseignements sur les capacités d’accueil',
     'Mission d’évaluation externe', 'Service qualité et évaluation interne'),
    ('SORTANT', 'Convocation des membres du conseil de direction',
     'Direction Générale', 'Directeurs et chefs de département'),
    ('SORTANT', 'Transmission du budget prévisionnel 2026-2027',
     'Direction des finances', 'Cabinet du ministère de tutelle'),
    ('SORTANT', 'Notification des résultats des concours d’entrée',
     'Service des examens et concours', 'Directions régionales'),
    ('SORTANT', 'Compte rendu de la réunion de rentrée 2026-2027',
     'Direction Générale', 'Ensemble du personnel'),
    ('SORTANT', 'Demande de financement des travaux de réhabilitation',
     'Direction Générale', 'Direction des affaires financières'),
    ('SORTANT', 'Transmission du rapport d’activités annuel',
     'Direction Générale', 'Cabinet du ministère de tutelle'),
    ('SORTANT', 'Invitation à la cérémonie de remise des diplômes',
     'Direction Générale', 'Partenaires institutionnels'),
    ('SORTANT', 'Note d’information sur le calendrier des évaluations',
     'Département scolarité et vie étudiante', 'Enseignants et étudiants'),
    ('SORTANT', 'Réponse à la demande d’homologation des infrastructures',
     'Direction des services logistiques', 'Fédération sportive nationale'),
    ('SORTANT', 'Accusé de réception de la demande de partenariat',
     'Direction Générale', 'Collectivité territoriale'),
]

DOCUMENTS = [
    ('NOTE_SERVICE', 'Note de service — organisation de la rentrée 2026-2027',
     'PUBLIE'),
    ('NOTE_SERVICE', 'Note de service — calendrier des congés du personnel',
     'SIGNE'),
    ('NOTE_SERVICE', 'Note de service — port de la tenue lors des activités',
     'EN_VALIDATION'),
    ('DECISION', 'Décision portant composition de la commission pédagogique',
     'PUBLIE'),
    ('DECISION', 'Décision portant création du comité qualité interne', 'SIGNE'),
    ('DECISION', 'Décision portant ouverture des concours d’entrée 2027',
     'BROUILLON'),
    ('CIRCULAIRE', 'Circulaire relative à la conservation des archives',
     'PUBLIE'),
    ('CIRCULAIRE', 'Circulaire — procédure de demande de mission',
     'EN_VALIDATION'),
    ('ARRETE', 'Arrêté portant règlement intérieur des résidences étudiantes',
     'PUBLIE'),
    ('ARRETE', 'Arrêté fixant les jurys de fin de cycle 2026-2027', 'SIGNE'),
    ('AUTRE', 'Charte d’utilisation des infrastructures sportives', 'BROUILLON'),
    ('NOTE_SERVICE', 'Note d’information — inventaire annuel du matériel',
     'ARCHIVE'),
]

REUNIONS = [
    ('Conseil de direction', 'Conseil de direction de rentrée 2026-2027',
     date(2026, 10, 6), 'PV_EMIS'),
    ('Commission pédagogique', 'Validation des maquettes 2026-2027',
     date(2026, 10, 13), 'PV_EMIS'),
    ('Commission budget', 'Examen du budget prévisionnel 2026-2027',
     date(2026, 10, 20), 'TENUE'),
    ('Comité qualité', 'Revue des indicateurs qualité — trimestre 1',
     date(2026, 10, 27), 'PV_EMIS'),
    ('Conseil de direction', 'Point sur les inscriptions et les groupes',
     date(2026, 11, 3), 'TENUE'),
    ('Commission des stages', 'Validation des organismes d’accueil 2026-2027',
     date(2026, 11, 10), 'PLANIFIEE'),
    ('Conseil scientifique', 'Programme de recherche 2026-2027',
     date(2026, 11, 17), 'PLANIFIEE'),
    ('Commission disciplinaire', 'Session ordinaire — dossiers en cours',
     date(2026, 11, 24), 'PLANIFIEE'),
    ('Conseil de direction', 'Préparation des examens de fin de semestre',
     date(2026, 12, 1), 'PLANIFIEE'),
    ('Commission pédagogique', 'Suivi des équivalences et des parcours',
     date(2026, 12, 8), 'PLANIFIEE'),
    ('Comité de pilotage numérique', 'Déploiement du portail étudiant',
     date(2026, 12, 15), 'PLANIFIEE'),
    ('Commission budget', 'Suivi de l’exécution budgétaire',
     date(2027, 1, 12), 'PLANIFIEE'),
    ('Conseil de direction', 'Bilan du premier semestre',
     date(2027, 1, 19), 'PLANIFIEE'),
    ('Assemblée du personnel', 'Assemblée générale de début d’année',
     date(2027, 1, 26), 'PLANIFIEE'),
    ('Commission des concours', 'Préparation des concours d’entrée 2027',
     date(2027, 2, 2), 'PLANIFIEE'),
    ('Réunion technique', 'Inventaire des infrastructures sportives',
     date(2026, 11, 5), 'ANNULEE'),
]

MISSIONS = [
    ('Mission d’encadrement — championnat universitaire', 'Yamoussoukro',
     date(2026, 10, 16), date(2026, 10, 18), 'TERMINEE'),
    ('Mission de supervision des stages pratiques', 'Bouaké',
     date(2026, 10, 26), date(2026, 10, 30), 'EN_COURS'),
    ('Mission d’évaluation des infrastructures régionales', 'Daloa',
     date(2026, 11, 9), date(2026, 11, 12), 'VALIDEE'),
    ('Atelier national sur les référentiels de formation', 'Grand-Bassam',
     date(2026, 11, 16), date(2026, 11, 18), 'VALIDEE'),
    ('Mission de prospection des organismes d’accueil', 'Divo',
     date(2026, 11, 23), date(2026, 11, 25), 'PROPOSEE'),
    ('Colloque régional sport et jeunesse', 'Abidjan',
     date(2026, 12, 7), date(2026, 12, 9), 'VALIDEE'),
    ('Mission d’audit interne qualité', 'Dimbokro',
     date(2026, 12, 14), date(2026, 12, 16), 'PROPOSEE'),
    ('Formation des tuteurs de stage', 'Abengourou',
     date(2027, 1, 18), date(2027, 1, 20), 'PROPOSEE'),
    ('Mission de recensement des équipements', 'Bouaflé',
     date(2026, 10, 19), date(2026, 10, 21), 'TERMINEE'),
    ('Réunion du réseau des instituts de sport', 'Abidjan',
     date(2026, 11, 2), date(2026, 11, 2), 'TERMINEE'),
    ('Mission d’accompagnement des délégations sportives', 'Dabou',
     date(2026, 12, 3), date(2026, 12, 5), 'REFUSEE'),
    ('Supervision des centres d’animation partenaires', 'Bingerville',
     date(2027, 1, 11), date(2027, 1, 13), 'VALIDEE'),
]


class Command(BaseCommand):
    help = 'Données d’exemple [Exemple] du module Administration.'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true')
        parser.add_argument('--purger', action='store_true')

    def handle(self, *args, **options):
        if options['purger']:
            self._purger()
            return
        dry = options['dry_run']
        acteur = User.objects.filter(is_active=True).order_by('id').first()
        with transaction.atomic():
            directions = {}
            for ordre, (code, libelle) in enumerate(DIRECTIONS, start=1):
                obj, _ = Direction.objects.update_or_create(
                    code=code,
                    defaults={
                        'libelle': libelle,
                        'description': '[Exemple] Unité de démonstration.',
                        'ordre': ordre, 'actif': True,
                        'email': f'{code.lower()}@exemple.injs.ci',
                    },
                )
                directions[code] = obj
            departements = {}
            for ordre, (dir_code, code, libelle) in enumerate(
                DEPARTEMENTS, start=1,
            ):
                obj, _ = Departement.objects.update_or_create(
                    code=code,
                    defaults={
                        'libelle': libelle,
                        'description': '[Exemple] Unité de démonstration.',
                        'direction': directions[dir_code],
                        'ordre': ordre, 'actif': True,
                        'email': f'{code.lower()}@exemple.injs.ci',
                    },
                )
                departements[code] = obj
            for dep_code, code, nom in SERVICES:
                Service.objects.update_or_create(
                    nom=nom,
                    defaults={
                        'code': code, 'type_unite': Service.TypeUnite.SERVICE,
                        'description': '[Exemple] Unité de démonstration.',
                        'departement': departements[dep_code], 'actif': True,
                        'email': f'{code.lower()}@exemple.injs.ci',
                    },
                )

            nb_courriers = 0
            base = date(2026, 10, 5)
            statuts_courrier = [
                'CLASSE', 'REPONDU', 'EN_COURS', 'RECU', 'CLASSE', 'EN_COURS',
                'RECU', 'REPONDU',
            ]
            for tour in range(2):
                for rang, (sens, objet, exp, dest) in enumerate(
                    COURRIERS_OBJETS,
                ):
                    reference = (
                        f'EX-2026/{"CE" if sens == "ENTRANT" else "CS"}-'
                        f'{tour * 20 + rang + 1:03d}'
                    )
                    _, cree = Courrier.objects.update_or_create(
                        reference=reference,
                        defaults={
                            'sens': sens,
                            'objet': f'[Exemple] {objet}',
                            'expediteur': exp, 'destinataire': dest,
                            'date_courrier': base + timedelta(
                                days=(tour * 20 + rang) * 2,
                            ),
                            'statut': statuts_courrier[
                                (tour + rang) % len(statuts_courrier)
                            ],
                            'cree_par': acteur,
                        },
                    )
                    nb_courriers += int(cree)

            for type_doc, titre, statut in DOCUMENTS:
                DocumentOfficiel.objects.update_or_create(
                    titre=f'[Exemple] {titre}',
                    defaults={
                        'type_document': type_doc, 'statut': statut,
                        'contenu': (
                            'Document d’exemple généré pour la '
                            'démonstration du module Administration.'
                        ),
                        'cree_par': acteur,
                    },
                )
            for type_r, titre, date_r, statut in REUNIONS:
                ReunionCommission.objects.update_or_create(
                    titre=f'[Exemple] {titre}',
                    defaults={
                        'type_reunion': type_r, 'date_reunion': date_r,
                        'lieu': 'Salle de conseil — administration',
                        'ordre_du_jour': type_r, 'statut': statut,
                        'pv_contenu': (
                            'Procès-verbal d’exemple (démonstration).'
                            if statut == 'PV_EMIS' else ''
                        ),
                    },
                )
            for objet, lieu, debut, fin, statut in MISSIONS:
                Mission.objects.update_or_create(
                    objet=f'[Exemple] {objet}',
                    defaults={
                        'agent': acteur, 'lieu': lieu,
                        'date_debut': debut, 'date_fin': fin,
                        'statut': statut, 'budget': 0,
                    },
                )
            if dry:
                transaction.set_rollback(True)

        mode = 'seraient' if dry else 'prêtes'
        self.stdout.write(self.style.SUCCESS(
            f'Administration d’exemple ({mode}) : '
            f'{Direction.objects.count()} directions, '
            f'{Departement.objects.count()} départements, '
            f'{Service.objects.count()} services, '
            f'{Courrier.objects.filter(reference__startswith="EX-").count()} '
            'courriers, '
            f'{DocumentOfficiel.objects.filter(titre__startswith="[Exemple]").count()} '
            'documents, '
            f'{ReunionCommission.objects.filter(titre__startswith="[Exemple]").count()} '
            'réunions, '
            f'{Mission.objects.filter(objet__startswith="[Exemple]").count()} '
            'missions.',
        ))

    def _purger(self):
        with transaction.atomic():
            Mission.objects.filter(objet__startswith='[Exemple]').delete()
            ReunionCommission.objects.filter(
                titre__startswith='[Exemple]',
            ).delete()
            DocumentOfficiel.objects.filter(
                titre__startswith='[Exemple]',
            ).delete()
            Courrier.objects.filter(reference__startswith='EX-').delete()
            Service.objects.filter(
                description__startswith='[Exemple]',
            ).delete()
            Departement.objects.filter(
                description__startswith='[Exemple]',
            ).delete()
            Direction.objects.filter(
                description__startswith='[Exemple]',
            ).delete()
        self.stdout.write(self.style.SUCCESS(
            'Purge administration d’exemple terminée.'
        ))
