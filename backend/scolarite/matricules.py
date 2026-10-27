"""Génération et validation des matricules étudiants.

Le matricule reste porté par ``formations.Participant.matricule``, déjà unique
et déjà référencé partout dans l'application. On n'en crée pas un second.

Les matricules existants, importés depuis Excel, ne suivent aucun format
imposé : la génération ne s'applique qu'aux nouveaux dossiers et n'invalide
jamais un matricule déjà en base.
"""

from django.conf import settings
from django.db import transaction
from django.db.models import Max
from django.db.models.functions import Length, Substr

from formations.models import Participant

# Format : <préfixe><année de début><séquence sur 4 chiffres>, ex. INJS26-0001.
PREFIXE_MATRICULE = getattr(settings, 'MATRICULE_PREFIXE', 'INJS')
LONGUEUR_SEQUENCE = 4


def prefixe_pour_annee(annee_academique):
    """Préfixe complet d'une année académique, ex. « INJS26- » pour 2026-2027."""
    annee_debut = annee_academique.libelle.split('-')[0]
    return f'{PREFIXE_MATRICULE}{annee_debut[-2:]}-'


def matricule_genere(matricule, annee_academique):
    """Indique si un matricule suit le format généré pour cette année."""
    return bool(matricule) and matricule.startswith(prefixe_pour_annee(annee_academique))


@transaction.atomic
def generer_matricule(annee_academique):
    """Retourne le prochain matricule disponible pour l'année académique.

    La séquence est calculée sur les matricules déjà générés pour cette année,
    en ignorant les matricules importés qui ne suivent pas le format.
    """
    prefixe = prefixe_pour_annee(annee_academique)
    debut_sequence = len(prefixe) + 1

    dernier = (
        Participant.objects
        .filter(matricule__startswith=prefixe)
        .annotate(sequence=Substr('matricule', debut_sequence, LONGUEUR_SEQUENCE))
        .annotate(longueur=Length('matricule'))
        .filter(longueur=len(prefixe) + LONGUEUR_SEQUENCE)
        .aggregate(maximum=Max('sequence'))['maximum']
    )

    prochain = int(dernier) + 1 if dernier and dernier.isdigit() else 1

    # Garde-fou : en cas de collision (matricule importé identique), on avance.
    while Participant.objects.filter(matricule=f'{prefixe}{prochain:0{LONGUEUR_SEQUENCE}d}').exists():
        prochain += 1

    return f'{prefixe}{prochain:0{LONGUEUR_SEQUENCE}d}'
