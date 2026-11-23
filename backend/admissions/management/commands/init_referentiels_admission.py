"""Initialise les référentiels d'admission (types de candidature, voies d'accès, pièces).

Commande idempotente, alignée sur les pratiques de recrutement de l'INJS.

    python manage.py init_referentiels_admission
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from admissions.models import TypeCandidature, TypePiece, VoieAcces

TYPES_CANDIDATURE = [
    ('CONCOURS_DIRECT', 'Concours direct'),
    ('CONCOURS_PROFESSIONNEL', 'Concours professionnel'),
    ('SUR_TITRE', 'Admission sur titre'),
    ('TRANSFERT', 'Transfert'),
    ('REORIENTATION', 'Réorientation'),
]

VOIES_ACCES = [
    ('BAC', 'Baccalauréat'),
    ('DIPLOME_EQUIVALENT', 'Diplôme équivalent'),
    ('VAE', 'Validation des acquis de l’expérience'),
    ('PASSERELLE', 'Passerelle interne'),
    ('DETACHEMENT', 'Détachement administratif'),
]

# (code, libellé, obligatoire par défaut, comporte une date de validité)
TYPES_PIECE = [
    ('ACTE_NAISSANCE', 'Extrait d’acte de naissance', True, False),
    ('PIECE_IDENTITE', 'Pièce d’identité', True, True),
    ('DIPLOME', 'Diplôme requis', True, False),
    ('RELEVE_NOTES', 'Relevés de notes', True, False),
    ('PHOTO', 'Photo d’identité', True, False),
    ('CERTIFICAT_MEDICAL', 'Certificat médical d’aptitude', True, True),
    ('CERTIFICAT_NATIONALITE', 'Certificat de nationalité', False, False),
    ('RECU_PAIEMENT', 'Reçu de paiement des frais', True, False),
    ('ACTE_ENGAGEMENT', 'Acte d’engagement / autorisation hiérarchique', False, False),
    ('CV', 'Curriculum vitae', False, False),
]


class Command(BaseCommand):
    help = "Initialise les référentiels d'admission (types de candidature, voies d'accès, pièces)."

    @transaction.atomic
    def handle(self, *args, **options):
        crees = 0
        for code, libelle in TYPES_CANDIDATURE:
            _, cree = TypeCandidature.objects.get_or_create(code=code, defaults={'libelle': libelle})
            crees += int(cree)
        self.stdout.write(f'Types de candidature : {crees} créé(s).')

        crees = 0
        for code, libelle in VOIES_ACCES:
            _, cree = VoieAcces.objects.get_or_create(code=code, defaults={'libelle': libelle})
            crees += int(cree)
        self.stdout.write(f"Voies d'accès : {crees} créée(s).")

        crees = 0
        for code, libelle, obligatoire, expiration in TYPES_PIECE:
            _, cree = TypePiece.objects.get_or_create(
                code=code,
                defaults={
                    'libelle': libelle,
                    'obligatoire_par_defaut': obligatoire,
                    'avec_date_expiration': expiration,
                },
            )
            crees += int(cree)
        self.stdout.write(f'Types de pièce : {crees} créé(s).')

        self.stdout.write(self.style.SUCCESS("Référentiels d'admission initialisés."))
