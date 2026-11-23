"""ADR-006 — vérification (LECTURE SEULE) des doublons de libellé.

Dépiste, dans les huit référentiels socles, les libellés qui, une fois
normalisés (insensible à la casse et aux accents — ADR-006), sont portés
par plusieurs lignes. La commande ne modifie rien : elle signale, ce qui
permet de décider d'un assainissement éventuel (archivage motivé des
doublons, jamais de suppression physique — règle 2).

    python manage.py verifier_doublons_referentiels [--json]
"""
import json

from django.core.management.base import BaseCommand

from referentiels.models import (
    RefGradeEnseignant,
    RefModePaiement,
    RefTypeDecision,
    RefTypeDocument,
    RefTypeEspaceSportif,
    RefTypeEvaluation,
    RefTypeFrais,
    RefTypeNotification,
)
from referentiels.utils import normaliser_libelle

MODELES = (
    RefTypeEvaluation,
    RefTypeDocument,
    RefGradeEnseignant,
    RefTypeFrais,
    RefModePaiement,
    RefTypeDecision,
    RefTypeNotification,
    RefTypeEspaceSportif,
)


class Command(BaseCommand):
    help = (
        'Signale les doublons de libellé (casse/accent-insensibles) dans les '
        'référentiels socles (ADR-006) — lecture seule.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--json', action='store_true',
            help='Émission au format JSON (pour outillage).',
        )

    def handle(self, *args, **options):
        resultat = []
        for modele in MODELES:
            par_forme = {}
            for pk, libelle in modele._default_manager.values_list(
                    'pk', 'libelle').order_by('pk'):
                forme = normaliser_libelle(libelle)
                par_forme.setdefault(forme, []).append(
                    {'pk': pk, 'libelle': libelle})
            doublons = {
                forme: lignes for forme, lignes in sorted(par_forme.items())
                if forme and len(lignes) > 1
            }
            for forme, lignes in doublons.items():
                resultat.append({
                    'modele': modele.__name__,
                    'forme_normalisee': forme,
                    'lignes': lignes,
                })
                self.stdout.write(
                    self.style.WARNING(
                        f'{modele.__name__}: {forme!r} — '
                        f"pk {', '.join(str(l['pk']) for l in lignes)}"
                    )
                )
        if options['json']:
            self.stdout.write(json.dumps(resultat, ensure_ascii=False, indent=2))
        if not resultat:
            self.stdout.write(self.style.SUCCESS(
                'Aucun doublon de libellé (normalisation ADR-006) détecté.'))
        else:
            self.stdout.write(
                f'{len(resultat)} groupe(s) de doublon(s) signalé(s) '
                '(lecture seule — aucun changement effectué).')
