"""Services métier Finances Étudiantes (L6).

Cohérent avec ``finances_etudiantes.models`` (champs et FO réelles).
Idempotence via ``Paiement.transaction_externe`` (unique) — un paiement
déjà enregistré avec la même référence externe est retourné sans
duplication, ce qui protège des réessais mobile-money.
"""
from decimal import Decimal
from datetime import date, timedelta

from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .models import (
    Echeancier, Facture, LigneEcheancier, Paiement,
    Quittance, RapprochementComptable, Remboursement, Tarification,
)


def generer_echeancier_pour_etudiant(etudiant, annee_academique):
    """Génère un échéancier pour un DossierEtudiant à partir des tarifs actifs.

    ``etudiant`` est une instance de ``scolarite.DossierEtudiant``. Le périmètre
    Tarification est (formation/parcours/niveau/année) — on prend l'inscription
    administrative VALIDEE la plus récente pour obtenir le niveau et le parcours.
    Retourne l'échéancier créé ou None si aucune tarification n'existe.
    """
    inscription = etudiant.inscriptions.filter(
        annee_academique=annee_academique,
    ).order_by('-annee_academique__libelle').first()
    if not inscription:
        return None

    tarifs = Tarification.objects.filter(
        formation=inscription.ref_formation,
        annee_academique=annee_academique,
        actif=True,
    )
    if inscription.parcours_id:
        tarifs = tarifs.filter(parcours=inscription.parcours) | tarifs.filter(parcours__isnull=True)
    if inscription.niveau_id:
        tarifs = tarifs.filter(niveau=inscription.niveau) | tarifs.filter(niveau__isnull=True)
    tarifs = tarifs.distinct()
    if not tarifs.exists():
        return None

    echeancier = Echeancier.objects.create(etudiant=etudiant, annee_academique=annee_academique)
    echeance = date.today() + timedelta(days=30)
    lignes = []
    for t in tarifs.order_by('nature'):
        ligne = LigneEcheancier.objects.create(
            echeancier=echeancier, nature=t.nature,
            montant=t.montant_base, date_echeance=echeance, statut='IMPAYE',
        )
        lignes.append(ligne)
    echeancier.lignes.set(lignes)
    return echeancier


@transaction.atomic
def enregistrer_paiement_idempotent(
    *, etudiant=None, candidat=None, nature, montant, devise, mode,
    transaction_externe, utilisateur=None, statut_initie='INITIE',
):
    """Enregistre un paiement de manière idempotente.

    Idempotence : si un paiement existe déjà avec la même
    ``transaction_externe``, il est retourné tel quel (pas de duplication).
    Lève ValidationError si aucun étudiant/candidat fourni, ou si le montant
    est nul.
    """
    if not etudiant and not candidat:
        raise ValidationError("Un paiement doit avoir un étudiant ou un candidat.")
    montant = Decimal(str(montant))
    if montant <= 0:
        raise ValidationError("Le montant doit être strictement positif.")

    paiement_existant = Paiement.objects.filter(
        transaction_externe=transaction_externe,
    ).first()
    if paiement_existant:
        return paiement_existant, False

    source = etudiant or candidat
    paiement = Paiement.objects.create(
        # La clé générique (GenericForeignKey « source ») est NOT NULL :
        # on la renseigne systématiquement à partir de l'étudiant ou du candidat.
        content_type=ContentType.objects.get_for_model(source),
        object_id=source.pk,
        etudiant=etudiant, candidat=candidat, nature=nature,
        montant=montant, devise=devise, mode=mode,
        statut=statut_initie, utilisateur=utilisateur,
        transaction_externe=transaction_externe,
    )
    return paiement, True


def confirmer_paiement(paiement, utilisateur, date_echeance=None):
    """Confirme un paiement (create Quittance, exige une preuve).

    Préconditions : paiement.statut ∈ {INITIE, EN_ATTENTE}, ET preuve fournie.
    La transition vers CONFIRME crée une Quittance unique. ``date_echeance``
    est horodatée au jour de la confirmation lorsqu'elle n'est pas fournie.
    """
    if paiement.statut == 'CONFIRME':
        return paiement
    if paiement.statut in ('ANNULE', 'ECHOUE', 'REMBOLSE'):
        raise ValidationError(f"Paiement {paiement.statut} ne peut être confirmé.")
    if not paiement.preuve:
        raise ValidationError(
            "Une preuve (pièce justificative) est obligatoire pour confirmer un paiement."
        )
    paiement.statut = 'CONFIRME'
    paiement.date_rapprochement = timezone.now()
    paiement.save(update_fields=['statut', 'date_rapprochement'])
    Quittance.objects.get_or_create(
        paiement=paiement,
        defaults={'date_echeance': date_echeance or timezone.localdate()},
    )
    return paiement


def valider_paiement_par_transaction(transaction_externe):
    """Retourne le paiement associé à une référence externe ou None."""
    if not transaction_externe:
        return None
    return Paiement.objects.filter(transaction_externe=transaction_externe).first()


def generer_facture(echeancier, utilisateur=None):
    """Génère une facture à partir d'un échéancier (somme des lignes, statut EMIS)."""
    lignes = list(echeancier.lignes.all())
    if not lignes:
        raise ValidationError("L'échéancier ne contient aucune ligne à facturer.")
    total = sum(ligne.montant for ligne in lignes)
    numero = f'FAC-{echeancier.id}-{date.today():%Y%m%d}'
    facture = Facture.objects.create(
        echeancier=echeancier, numero=numero, total=total, statut='EMISE',
    )
    facture.lignes.set(lignes)
    return facture

