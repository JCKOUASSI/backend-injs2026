"""Données d'exemple du module Équivalences et dispenses.

Crée, pour chaque cohorte réelle de l'année courante (formation × niveau
avec inscriptions VALIDEE), deux demandes de démonstration — une
**équivalence** et une **dispense** — portées par des étudiants inscrits
de la cohorte et ciblées sur une UE/ECUE de la maquette ACTIVE
correspondante. Les 9 statuts du workflow sont répartis en rotation
déterministe (BROUILLON → … → APPLIQUEE, REJETEE) : chaque type et
chaque statut sont représentés dans plusieurs formations et niveaux.

Chaque demande chemine par la vraie machine à états
(``workflow.appliquer_transition`` + ``services.appliquer``) : historique,
journal de scolarité, pièces justificatives et événements académiques
sont donc exactement ceux d'un traitement manuel. Le motif commence
par ``[Exemple]`` : repérage, idempotence (une demande d'exemple
existante n'est jamais retouchée) et purge ciblée (``--purger``, les
APPLIQUEE sont conservées — l'historique académique est engagé).

Exemples
--------
    python manage.py seed_equivalences_demo --dry-run
    python manage.py seed_equivalences_demo --utilisateur admin
    python manage.py seed_equivalences_demo --purger
"""

from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from equivalences import services, workflow
from equivalences.models import DemandeEquivalenceDispense, PieceEquivalence
from scolarite.models import (
    AnneeAcademique, InscriptionAdministrative, Maquette,
)

MARQUE = '[Exemple]'
S = DemandeEquivalenceDispense.Statut
D = DemandeEquivalenceDispense.Decision
PS = PieceEquivalence.Statut

#: Rotation des statuts cibles — les 9 états du workflow.
CIBLES = [
    S.BROUILLON, S.SOUMISE, S.EN_INSTRUCTION, S.A_COMPLETER,
    S.AVIS_PEDAGOGIQUE, S.DECISION, S.VALIDEE, S.APPLIQUEE, S.REJETEE,
]

ETABLISSEMENTS = [
    'Université Félix Houphouët-Boigny',
    'Université Nangui Abrogoua',
    'INP-HB Yamoussoukro',
    'Université Alassane Ouattara (Bouaké)',
]
DIPLOMES = [
    'Licence STAPS', 'Licence Sciences de l’éducation',
    'Master Management du sport', 'Licence Sciences de la vie',
]
MOTIFS = {
    'EQUIVALENCE': 'Reconnaissance d’acquis antérieurs (passerelle entrante)',
    'DISPENSE': 'UE déjà validée lors d’un cursus antérieur',
}
NOTES = [Decimal('11.00'), Decimal('12.50'), Decimal('13.25'), Decimal('14.00')]

#: Pièces (libellé, statut) selon l'avancement cible de la demande.
PIECES_PAR_CIBLE = {
    S.BROUILLON: [('Relevés de notes antérieurs', PS.FOURNIE),
                  ('Diplôme ou attestation de réussite', PS.MANQUANTE)],
    S.SOUMISE: [('Relevés de notes antérieurs', PS.FOURNIE),
                ('Diplôme ou attestation de réussite', PS.FOURNIE)],
    S.EN_INSTRUCTION: [('Relevés de notes antérieurs', PS.VALIDE),
                       ('Diplôme ou attestation de réussite', PS.FOURNIE)],
    S.A_COMPLETER: [('Relevés de notes antérieurs', PS.VALIDE),
                    ('Programme détaillé des enseignements suivis', PS.MANQUANTE)],
}
PIECES_VALIDEES = [('Relevés de notes antérieurs', PS.VALIDE),
                   ('Diplôme ou attestation de réussite', PS.VALIDE)]


class Command(BaseCommand):
    help = (
        "Demandes d'équivalence/dispense d'exemple : tous types, statuts, "
        'formations et niveaux (idempotent, --purger disponible).'
    )

    def add_arguments(self, parser):
        parser.add_argument('--annee', help="Libellé d'année (défaut : année courante).")
        parser.add_argument('--utilisateur', help="Nom d'utilisateur signataire des transitions.")
        parser.add_argument('--purger', action='store_true',
                            help='Supprimer les demandes [Exemple] non APPLIQUEE, puis quitter.')
        parser.add_argument('--dry-run', action='store_true', help='Simuler sans écrire.')

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

    # ── Cheminement d'une demande jusqu'au statut cible ───────────────────
    def _pieces(self, demande, cible, utilisateur):
        for libelle, statut in PIECES_PAR_CIBLE.get(cible, PIECES_VALIDEES):
            PieceEquivalence.objects.create(
                demande=demande, libelle=libelle, obligatoire=True, statut=statut,
                verifie_par=utilisateur if statut == PS.VALIDE else None,
            )

    def _avancer(self, demande, cible, utilisateur, rang_global):
        def aller(statut):
            workflow.appliquer_transition(
                demande, statut, utilisateur=utilisateur,
                commentaire=f'{MARQUE} Traitement de démonstration.',
            )

        if cible == S.BROUILLON:
            return
        aller(S.SOUMISE)
        if cible == S.SOUMISE:
            return
        aller(S.EN_INSTRUCTION)
        if cible == S.EN_INSTRUCTION:
            return
        if cible == S.A_COMPLETER:
            aller(S.A_COMPLETER)
            return
        aller(S.AVIS_PEDAGOGIQUE)
        if cible == S.AVIS_PEDAGOGIQUE:
            return
        aller(S.DECISION)
        if cible == S.DECISION:
            return
        favorable = cible in (S.VALIDEE, S.APPLIQUEE)
        demande.decision = D.FAVORABLE if favorable else D.DEFAVORABLE
        demande.autorite_validation = 'Direction des études INJS'
        demande.commission = 'Commission des équivalences et dispenses (exemple)'
        demande.date_commission = date(2026, 10, 15)
        if favorable:
            demande.credits_reconnus = (
                demande.ue.credits if demande.type_demande == 'EQUIVALENCE'
                else (demande.ecue.credits if demande.ecue_id else demande.ue.credits)
            )
            if demande.type_demande == 'EQUIVALENCE':
                demande.note_transferee = NOTES[rang_global % len(NOTES)]
            demande.analyse_pedagogique = (
                f'{MARQUE} Contenus et volumes horaires comparables à la cible ; '
                'acquis reconnus par la commission.'
            )
        else:
            demande.analyse_pedagogique = (
                f'{MARQUE} Écarts substantiels de contenu avec la cible ; '
                'acquis non reconnus.'
            )
        demande.save()
        aller(S.VALIDEE if favorable else S.REJETEE)
        if cible == S.APPLIQUEE:
            services.appliquer(
                demande, utilisateur=utilisateur,
                commentaire=f'{MARQUE} Application de démonstration.',
            )

    # ── Programme principal ───────────────────────────────────────────────
    def handle(self, *args, **options):
        dry_run = options['dry_run']
        annee = self._annee(options.get('annee'))
        utilisateur = self._utilisateur(options.get('utilisateur'))
        self.stdout.write(f"Année cible : {annee.libelle}{' (simulation)' if dry_run else ''}")

        if options['purger']:
            exemples = DemandeEquivalenceDispense.objects.filter(motif__startswith=MARQUE)
            a_purger = exemples.exclude(statut=S.APPLIQUEE)
            conservees = exemples.filter(statut=S.APPLIQUEE).count()
            nb = a_purger.count()
            if not dry_run:
                a_purger.delete()
            self.stdout.write(
                f"Exemples supprimés : {nb} ; APPLIQUEE conservées : {conservees}.",
            )
            return

        cohortes = (
            InscriptionAdministrative.objects.filter(
                annee_academique=annee,
                statut=InscriptionAdministrative.Statut.VALIDEE,
            )
            .values_list('ref_formation_id', 'niveau_id')
            .distinct()
            .order_by('ref_formation__intitule', 'niveau__ordre')
        )
        crees = ignores = sans_maquette = 0
        rang_global = 0
        for rang_cohorte, (formation_id, niveau_id) in enumerate(cohortes):
            maquette = (
                Maquette.objects.filter(
                    annee_academique=annee, ref_formation_id=formation_id,
                    niveau_id=niveau_id, parcours__isnull=True,
                    statut=Maquette.Statut.ACTIVE,
                ).order_by('-version').first()
            )
            if maquette is None:
                sans_maquette += 1
                continue
            ues = list(
                maquette.unites_enseignement.select_related('semestre')
                .prefetch_related('ecues').order_by('semestre__numero', 'ordre')
            )
            if not ues:
                sans_maquette += 1
                continue
            inscrits = list(
                InscriptionAdministrative.objects.filter(
                    annee_academique=annee, ref_formation_id=formation_id,
                    niveau_id=niveau_id,
                    statut=InscriptionAdministrative.Statut.VALIDEE,
                ).select_related('etudiant__participant')
                .order_by('etudiant__participant__matricule')[:8]
            )
            if len(inscrits) < 2:
                continue
            decalage = rang_cohorte % 5
            for k, type_demande in enumerate(('EQUIVALENCE', 'DISPENSE')):
                inscription = inscrits[min(decalage + k, len(inscrits) - 1)]
                dossier = inscription.etudiant
                cible = CIBLES[rang_global % len(CIBLES)]
                rang_global += 1
                existe = DemandeEquivalenceDispense.objects.filter(
                    etudiant=dossier, type_demande=type_demande,
                    annee_academique=annee, motif__startswith=MARQUE,
                ).exists()
                if existe:
                    ignores += 1
                    continue
                crees += 1
                if dry_run:
                    continue
                ue = ues[rang_cohorte % len(ues)]
                ecues = sorted(ue.ecues.all(), key=lambda e: (e.ordre, e.code))
                with transaction.atomic():
                    demande = DemandeEquivalenceDispense.objects.create(
                        type_demande=type_demande,
                        etudiant=dossier, annee_academique=annee,
                        ref_formation_id=formation_id, niveau_id=niveau_id,
                        semestre=ue.semestre, ue=ue,
                        ecue=ecues[0] if (type_demande == 'DISPENSE' and ecues) else None,
                        etablissement_origine=(
                            f"{ETABLISSEMENTS[rang_cohorte % len(ETABLISSEMENTS)]} (exemple)"
                        ),
                        diplome_origine=(
                            f"{DIPLOMES[rang_cohorte % len(DIPLOMES)]} (exemple)"
                            if type_demande == 'EQUIVALENCE'
                            else 'UE validée antérieurement (exemple)'
                        ),
                        annee_obtention=2023 + (rang_cohorte % 3),
                        motif=f'{MARQUE} {MOTIFS[type_demande]}.',
                        date_effet=annee.date_debut,
                    )
                    self._pieces(demande, cible, utilisateur)
                    self._avancer(demande, cible, utilisateur, rang_global)

        self.stdout.write(
            f'Demandes d’exemple créées : {crees} ; déjà présentes : {ignores} ; '
            f'cohortes sans maquette ACTIVE : {sans_maquette}.',
        )
