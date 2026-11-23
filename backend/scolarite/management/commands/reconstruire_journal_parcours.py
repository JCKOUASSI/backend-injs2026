"""Reconstitue le journal de parcours depuis les inscriptions validées.

Contexte : les chargements initiaux (effectifs étudiants, inscriptions
d'exemple) créent les inscriptions administratives en masse, sans passer
par les services métier qui journalisent (``groupes_services.reinscrire``,
``enregistrer_evenement``). Résultat constaté : 9 événements de parcours en
base pour 1 867 flux de continuité — le « Journal de scolarité » était vide
alors que les parcours existent.

Cette commande **déduit** les événements des inscriptions administratives
déjà en base (aucune donnée inventée) :

- seules les inscriptions **effectives** (VALIDEE / TERMINEE) et de
  **continuité** (hors PREMIERE) produisent un événement ;
- correspondance des types : REINSCRIPTION → PASSAGE, REDOUBLEMENT →
  REDOUBLEMENT, TRANSFERT → TRANSFERT, REORIENTATION → REORIENTATION,
  REPRISE → REPRISE ;
- la date est celle de l'inscription, la valeur nouvelle le niveau atteint ;
  la valeur ancienne reste vide (aucune inscription de l'année précédente
  en base : on ne la devine pas) ;
- chaque ligne est marquée « [Reconstitué] » et sans auteur, pour rester
  distinguishable des événements saisis par un opérateur ;
- aucune entrée d'audit (``JournalScolarite``) n'est fabriquée : une
  reconstitution n'est pas une opération d'acteur.

Idempotente : la clé (étudiant, inscription, type) évite tout doublon.
``--dry-run`` affiche le prévisionnel sans écrire.
"""
from django.core.management.base import BaseCommand

from scolarite.journal_api import MARQUE_RECONSTITUE
from scolarite.models import EvenementScolarite, InscriptionAdministrative

CORRESPONDANCES = {
    InscriptionAdministrative.Type.REINSCRIPTION: EvenementScolarite.Type.PASSAGE,
    InscriptionAdministrative.Type.REDOUBLEMENT: EvenementScolarite.Type.REDOUBLEMENT,
    InscriptionAdministrative.Type.TRANSFERT: EvenementScolarite.Type.TRANSFERT,
    InscriptionAdministrative.Type.REORIENTATION: EvenementScolarite.Type.REORIENTATION,
    InscriptionAdministrative.Type.REPRISE: EvenementScolarite.Type.REPRISE,
}

COMMENTAIRE = (
    f'{MARQUE_RECONSTITUE} Événement déduit de l’inscription administrative '
    'validée (chargement initial antérieur à la journalisation).'
)


class Command(BaseCommand):
    help = 'Déduit les événements de parcours manquants des inscriptions validées.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Affiche le nombre d’événements qui seraient créés, sans écrire.',
        )

    def handle(self, *args, **options):
        cibles = (
            InscriptionAdministrative.objects
            .filter(
                statut__in=[
                    InscriptionAdministrative.Statut.VALIDEE,
                    InscriptionAdministrative.Statut.TERMINEE,
                ],
                type_inscription__in=list(CORRESPONDANCES),
            )
            .select_related('etudiant', 'niveau')
            .order_by('date_inscription', 'pk')
        )
        existants = set(
            EvenementScolarite.objects
            .exclude(inscription__isnull=True)
            .values_list('etudiant_id', 'inscription_id', 'type_evenement'),
        )

        a_creer = []
        par_type = {}
        for inscription in cibles:
            type_evenement = CORRESPONDANCES[inscription.type_inscription]
            clef = (inscription.etudiant_id, inscription.pk, type_evenement)
            if clef in existants:
                continue
            existants.add(clef)
            par_type[type_evenement] = par_type.get(type_evenement, 0) + 1
            a_creer.append(EvenementScolarite(
                etudiant_id=inscription.etudiant_id,
                inscription=inscription,
                type_evenement=type_evenement,
                date_evenement=inscription.date_inscription,
                ancienne_valeur='',
                nouvelle_valeur=inscription.niveau.code if inscription.niveau else '',
                commentaire=COMMENTAIRE,
                enregistre_par=None,
            ))

        detail = ', '.join(
            f'{EvenementScolarite.Type(code).label} : {total}'
            for code, total in sorted(par_type.items(), key=lambda item: -item[1])
        ) or 'aucun'
        if options['dry_run']:
            self.stdout.write(
                f'[Simulation] {len(a_creer)} événement(s) seraient créés ({detail}).',
            )
            return

        EvenementScolarite.objects.bulk_create(a_creer, batch_size=500)
        self.stdout.write(self.style.SUCCESS(
            f'Journal de parcours : {len(a_creer)} événement(s) reconstitué(s) '
            f'({detail}) ; total en base : {EvenementScolarite.objects.count()}.',
        ))
