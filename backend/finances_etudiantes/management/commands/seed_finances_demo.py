"""Données d'exemple des Finances étudiantes (tâche 34).

Garde-fous financiers (aucun acte financier réel ne peut naître de ces
données) :
- barème de démonstration créé INACTIF (`actif=False`) : le service de
  génération d'échéanciers ne lit que les barèmes actifs, donc aucune
  facturation réelle ne peut utiliser ces montants indicatifs ;
- factures en BROUILLON uniquement (numéros EX-FAC-…), paiements en
  INITIALISÉ ou EN ATTENTE (jamais CONFIRMÉ : une confirmation exige
  une pièce justificative), aucune quittance, aucun remboursement
  exécuté (INITIE avec motif [Exemple]) ;
- lignes d'échéancier IMPAYÉ ou PARTIELLEMENT PAYÉ, jamais PAYÉE
  (aucun faux acquittement) ;
- transactions externes EX-TXN-… uniques pour l'idempotence.

``--purger`` retire barème inactif d'exemple, échéanciers rattachés,
factures EX-, paiements EX-TXN (et remboursements associés),
relances [Exemple] et le rapprochement d'exemple.
"""
from datetime import datetime, timezone
from datetime import date as date_type
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from finances_etudiantes.models import (
    Echeancier, Facture, LigneEcheancier, Paiement,
    RapprochementComptable, Relance, Remboursement, Tarification,
)
from formations.models import RefFormation
from scolarite.models import (
    AnneeAcademique, DossierEtudiant, InscriptionAdministrative,
)

User = get_user_model()
MARQUEUR = '[Exemple]'
NB_ETUDIANTS = 60

# Barème INDICATIF de démonstration (inactif) — jamais officiel.
BAREME = {
    'DOSSIER': Decimal('10000'),
    'INSCRIPTION': Decimal('25000'),
    'SCOLARITE_LICENCE': Decimal('150000'),
    'SCOLARITE_MASTER': Decimal('200000'),
    'EXAMEN': Decimal('15000'),
    'DOCUMENT': Decimal('5000'),
}
ECHEANCES = [
    ('DOSSIER', date_type(2026, 10, 30)),
    ('INSCRIPTION', date_type(2026, 10, 30)),
    ('SCOLARITE', date_type(2026, 11, 30)),
    ('EXAMEN', date_type(2027, 1, 15)),
    ('DOCUMENT', date_type(2027, 2, 28)),
]
MODES = ['CAISSE', 'ELEPHANT_MONEY', 'MTN_MONEY', 'VIREMENT', 'MOOV_MONEY']
NATURES_PAIEMENT = ['DOSSIER', 'INSCRIPTION', 'SCOLARITE', 'EXAMEN', 'DOCUMENT']


def montant_scolarite(formation):
    return (
        BAREME['SCOLARITE_MASTER'] if 'MASTER' in formation.intitule.upper()
        else BAREME['SCOLARITE_LICENCE']
    )


class Command(BaseCommand):
    help = 'Finances étudiantes d’exemple (barème inactif, aucun acte réel).'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true')
        parser.add_argument('--purger', action='store_true')

    def handle(self, *args, **options):
        if options['purger']:
            self._purger()
            return
        annee = AnneeAcademique.objects.filter(courante=True).first()
        if annee is None:
            raise CommandError('Aucune année académique courante.')
        utilisateur = User.objects.filter(is_active=True).order_by('id').first()
        content_type = ContentType.objects.get_for_model(DossierEtudiant)

        inscriptions = list(
            InscriptionAdministrative.objects.select_related(
                'etudiant', 'ref_formation',
            ).filter(
                annee_academique=annee,
                statut=InscriptionAdministrative.Statut.VALIDEE,
            ).order_by('id'),
        )
        pas = max(1, len(inscriptions) // NB_ETUDIANTS)
        choisitres = inscriptions[::pas][:NB_ETUDIANTS]

        with transaction.atomic():
            # 1) Barème indicatif INACTIF pour chaque formation.
            for formation in RefFormation.objects.order_by('intitule'):
                for nature in ('DOSSIER', 'INSCRIPTION', 'SCOLARITE', 'EXAMEN', 'DOCUMENT'):
                    montant = (
                        montant_scolarite(formation)
                        if nature == 'SCOLARITE' else BAREME[nature]
                    )
                    Tarification.objects.update_or_create(
                        formation=formation, parcours=None, niveau=None,
                        annee_academique=annee, nature=nature,
                        defaults={'montant_base': montant, 'actif': False},
                    )

            # 2) Échéanciers d'exemple (lignes jamais « payées »).
            echeanciers = []
            for rang, inscription in enumerate(choisitres):
                echeancier, _ = Echeancier.objects.get_or_create(
                    etudiant=inscription.etudiant, annee_academique=annee,
                )
                echeanciers.append((echeancier, inscription))
                for nature, date_e in ECHEANCES:
                    montant = (
                        montant_scolarite(inscription.ref_formation)
                        if nature == 'SCOLARITE' else BAREME[nature]
                    )
                    LigneEcheancier.objects.update_or_create(
                        echeancier=echeancier, nature=nature,
                        date_echeance=date_e,
                        defaults={
                            'montant': montant,
                            'statut': (
                                'PARTIELLEMENT_PAYE'
                                if (rang + hash(nature) % 5) % 3 == 0
                                else 'IMPAYE'
                            ),
                        },
                    )
                    # Rattachement M2M legacy attendu par statut_global.
                echeancier.lignes.set(
                    LigneEcheancier.objects.filter(echeancier=echeancier),
                )

            # 3) Factures BROUILLON EX- pour la moitié des échéanciers.
            for rang, (echeancier, _) in enumerate(echeanciers[:30], start=1):
                total = sum(
                    l.montant for l in echeancier.lignes.all()
                )
                facture, _ = Facture.objects.update_or_create(
                    numero=f'EX-FAC-2026-{rang:03d}',
                    defaults={
                        'echeancier': echeancier, 'total': total,
                        'date_emission': date_type(2026, 11, 2),
                        'statut': 'BROUILLON',
                    },
                )
                facture.lignes.set(echeancier.lignes.all())

            # 4) Paiements non confirmés (aucune preuve, aucun encaissement).
            paiements = []
            for rang, (_, inscription) in enumerate(echeanciers[:40], start=1):
                paiements.append(
                    Paiement.objects.update_or_create(
                        transaction_externe=f'EX-TXN-2026-{rang:04d}',
                        defaults={
                            'content_type': content_type,
                            'object_id': inscription.etudiant_id,
                            'etudiant': inscription.etudiant,
                            'candidat': None,
                            'nature': NATURES_PAIEMENT[rang % 5],
                            'montant': BAREME[NATURES_PAIEMENT[rang % 5]]
                            if NATURES_PAIEMENT[rang % 5] != 'SCOLARITE'
                            else montant_scolarite(inscription.ref_formation),
                            'devise': 'XOF',
                            'mode': MODES[rang % len(MODES)],
                            'statut': 'EN_ATTENTE' if rang % 2 else 'INITIE',
                            'date': datetime(2026, 11, 3, 9, 0, tzinfo=timezone.utc),
                            'utilisateur': utilisateur,
                            'audit_trail': {'exemple': True},
                        },
                    )[0],
                )

            # 5) Remboursements initialisés (jamais exécutés).
            for rang, paiement in enumerate(paiements[:4], start=1):
                Remboursement.objects.update_or_create(
                    paiement_original=paiement,
                    defaults={
                        'montant': paiement.montant, 'devise': 'XOF',
                        'motif': (
                            f'{MARQUEUR} Trop-perçu de démonstration '
                            'en attente d’instruction.'
                        ),
                        'statut': 'INITIE',
                        'transaction_externe': f'EX-RMB-2026-{rang:03d}',
                        'utilisateur': utilisateur,
                    },
                )

            # 6) Relances étiquetées + rapprochement d'exemple à solde nul.
            types_relance = ['EMAIL', 'SMS', 'LETTRE']
            for rang, (echeancier, _) in enumerate(echeanciers[:12], start=1):
                Relance.objects.update_or_create(
                    echeancier=echeancier,
                    type_relance=types_relance[rang % 3],
                    defaults={
                        'message': (
                            f'{MARQUEUR} Relance de démonstration : '
                            'des échéances restent dues pour 2026-2027.'
                        ),
                    },
                )
            _, _cree = RapprochementComptable.objects.update_or_create(
                date_periode=date_type(2026, 11, 30),
                defaults={
                    'solde': Decimal('0'),
                    'commentaire': (
                        f'{MARQUEUR} Rapprochement de démonstration : '
                        'aucune transaction réelle n’y est rattachée.'
                    ),
                },
            )

            if options['dry_run']:
                transaction.set_rollback(True)

        self.stdout.write(self.style.SUCCESS(
            'Finances d’exemple : '
            f'{Tarification.objects.filter(actif=False).count()} lignes de '
            'barème INACTIF, '
            f'{Echeancier.objects.count()} échéanciers, '
            f'{Facture.objects.filter(numero__startswith="EX-").count()} factures brouillons, '
            f'{Paiement.objects.filter(transaction_externe__startswith="EX-").count()} paiements non confirmés, '
            f'{Remboursement.objects.filter(motif__startswith=MARQUEUR).count()} remboursements initialisés, '
            f'{Relance.objects.filter(message__startswith=MARQUEUR).count()} relances.',
        ))

    def _purger(self):
        with transaction.atomic():
            Remboursement.objects.filter(motif__startswith=MARQUEUR).delete()
            Paiement.objects.filter(
                transaction_externe__startswith='EX-',
            ).delete()
            Relance.objects.filter(message__startswith=MARQUEUR).delete()
            RapprochementComptable.objects.filter(
                commentaire__startswith=MARQUEUR,
            ).delete()
            Facture.objects.filter(numero__startswith='EX-').delete()
            # Échéanciers de l'année dont les lignes correspondent au barème
            # d'exemple (les vraies lignes officielles ne sont pas touchées) :
            # on retire uniquement ceux créés par ce seed — tous leurs
            # montants appartiennent au barème inactif et aucune ligne
            # n'est « payée ».
            ids = [
                e.id for e in Echeancier.objects.all()
                if e.lignes.exists()
                and not e.lignes.filter(statut='PAYE').exists()
                and Tarification.objects.filter(
                    actif=False, annee_academique=e.annee_academique,
                    montant_base__in=e.lignes.values('montant'),
                ).exists()
            ]
            LigneEcheancier.objects.filter(echeancier_id__in=ids).delete()
            Echeancier.objects.filter(id__in=ids).delete()
            Tarification.objects.filter(actif=False).delete()
        self.stdout.write(self.style.SUCCESS(
            'Purge des finances d’exemple terminée.'
        ))
