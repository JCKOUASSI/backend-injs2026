#!/usr/bin/env python3
"""Diagnostic QR agrégé, lecture seule, sur UNE année BENCHMARK locale isolée.

Aucun rapprochement Participant n'est inféré des matricules, aucun identifiant
personnel ou UUID n'est imprimé, aucune séance n'est modifiée ou publiée.
"""
import json
import os
from collections import Counter

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django  # noqa: E402
django.setup()

from django.conf import settings  # noqa: E402
from django.db import connection  # noqa: E402
from django.db.models import F, Q  # noqa: E402
from edts.models import AffectationCreneau, EmploiDuTemps, InscriptionImportee  # noqa: E402
from edts.models_interop import SeanceInstantaneAttendus, SeanceRegistre  # noqa: E402
from edts.moteur.qr_v2 import anomalies_publication_v2, BASE_IMPORTEE  # noqa: E402
from presences.models import Pointage  # noqa: E402
from scolarite.models import AnneeAcademique  # noqa: E402


def diagnostiquer():
    cfg = connection.settings_dict
    sqlite = connection.vendor == 'sqlite' and str(cfg['NAME']).startswith('/tmp/')
    pg = (connection.vendor == 'postgresql' and os.getenv('GETINJS_PG_ISOLATED') == '1'
          and cfg['HOST'] == '/tmp/getinjs-pg-socket' and str(cfg['PORT']) == '55432'
          and str(cfg['NAME']).startswith('getinjs_bench_'))
    if not (settings.DEBUG and os.getenv('GETINJS_PHASE6_ISOLATED') == '1' and
            (sqlite or pg)):
        raise RuntimeError('Diagnostic refusé hors base BENCH locale isolée et DEBUG.')

    # Filet de lecture seule du moteur SQL, pas seulement une convention Python.
    with connection.cursor() as cursor:
        if sqlite:
            cursor.execute('PRAGMA query_only = ON')
        else:
            cursor.execute('SET default_transaction_read_only = on')

    # Refuser aussi toute base qui mélangerait une année BENCH et une année
    # non synthétique : le préfixe du chemin seul ne suffit pas à l'attester.
    annees = list(AnneeAcademique.objects.all()[:2])
    if len(annees) != 1 or not annees[0].libelle.startswith('BENCHMARK-'):
        raise ValueError('Une et une seule année BENCHMARK est requise, sans année réelle.')
    annee = annees[0]
    edts = EmploiDuTemps.objects.filter(annee_academique=annee)
    occurrences = AffectationCreneau.objects.filter(emploi_du_temps__annee_academique=annee)
    v2 = occurrences.filter(Q(date_seance__isnull=False) | Q(cle_occurrence_v2__isnull=False))
    registres = SeanceRegistre.objects.filter(affectation__in=v2)
    instantanes = SeanceInstantaneAttendus.objects.filter(registre__in=registres)
    anomalies = Counter()
    edts_v2 = edts.filter(affectations__in=v2).distinct()
    for edt in edts_v2.iterator(chunk_size=100):
        anomalies.update(anomalies_publication_v2(edt))
    return {
        'nature': 'BENCHMARK_SYNTHETIQUE_QR_LECTURE_SEULE',
        'annee_fictive': annee.libelle,
        'edts_avec_v2': edts_v2.count(),
        'occurrences_v2_total': v2.count(),
        'occurrences_v2_inactives': v2.filter(actif=False).count(),
        'registres_lies': registres.count(),
        'registres_cles_differentes': registres.exclude(
            cle_metier=F('affectation__cle_occurrence_v2')).count(),
        'instantanes': instantanes.count(),
        'instantanes_effectif_seul': instantanes.filter(base_calculee=BASE_IMPORTEE).count(),
        'pointages': Pointage.objects.filter(seance_edt__in=v2).count(),
        'anomalies_publication_actives': dict(sorted(anomalies.items())),
        'publication_autorisee': False,  # Un diagnostic n'atteste jamais les identités.
    }


if __name__ == '__main__':
    print(json.dumps(diagnostiquer(), ensure_ascii=False, sort_keys=True))
