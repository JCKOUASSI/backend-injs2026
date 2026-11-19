#!/usr/bin/env python3
"""Fenêtre fictive de 4 jours sur une base BENCH annuelle déjà occupée."""
import argparse
import json
import os
import resource
import time
from collections import Counter
from datetime import date, timedelta

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django  # noqa: E402
django.setup()

from django.conf import settings  # noqa: E402
from django.db import connection  # noqa: E402
from edts.models import AffectationCreneau  # noqa: E402
from edts.models_interop import SeanceRegistre  # noqa: E402
from edts.moteur.application_v2 import appliquer_ligne, proposer_ligne  # noqa: E402
from edts.moteur.planification_v2 import TravailSeance  # noqa: E402
from formations.models import Formateur  # noqa: E402
from scolarite.models import AnneeAcademique, Groupe  # noqa: E402

p = argparse.ArgumentParser()
p.add_argument('--etudiants', choices=('5000', '10000', '15000'), required=True)
a = p.parse_args()
sqlite_isole = (connection.vendor == 'sqlite' and
    str(connection.settings_dict['NAME']).startswith('/tmp/'))
pg_isole = (connection.vendor == 'postgresql' and os.getenv('GETINJS_PG_ISOLATED') == '1' and
    connection.settings_dict['HOST'] == '/tmp/getinjs-pg-socket' and
    str(connection.settings_dict['PORT']) == '55432' and
    str(connection.settings_dict['NAME']).startswith('getinjs_bench_'))
if (os.getenv('GETINJS_PHASE6_ISOLATED') != '1' or not settings.DEBUG or
    not (sqlite_isole or pg_isole)):
    raise RuntimeError('Base BENCH locale jetable et DEBUG requis.')
settings.GETINJS_V2_EXPERIMENTAL_WRITE = True
from django.db.models import Q  # noqa: E402
annee = AnneeAcademique.objects.get(
    Q(libelle=f'BENCHMARK-PHASE6-{a.etudiants}') |
    Q(libelle=f'BENCHMARK-P6-{a.etudiants}'))
groupes = list(Groupe.objects.filter(annee_academique=annee).order_by('pk')[:30])
formateurs = list(Formateur.objects.filter(numerobadge__startswith=f'B-{a.etudiants}-').order_by('pk'))
latences = []
statuts, codes = Counter(), Counter()
sql = 0

def compte(execute, statement, params, many, context):
    global sql
    sql += 1
    return execute(statement, params, many, context)

with connection.execute_wrapper(compte):
    for index, groupe in enumerate(groupes):
        t0 = time.monotonic()
        for numero in range(4):
            travail = TravailSeance(annee.pk, groupe.pk, 0, 'CM', 49 + numero,
                120, 60, formateur_id=formateurs[index % len(formateurs)].pk,
                source_confirmee=True, source_document='SOURCE SYNTHETIQUE DE TEST NON OFFICIELLE')
            decision = proposer_ligne(travail, revision=1, jour=date(2099, 9, 14) + timedelta(days=numero))
            if decision.statut == 'PLACEE':
                decision = appliquer_ligne(travail, decision, revision=1)
            statuts[decision.statut] += 1
            codes[decision.code] += 1
        latences.append(time.monotonic() - t0)
latences.sort()
print(json.dumps({'etudiants_synthetiques': int(a.etudiants), 'groupes': len(groupes),
    'fenetre': '2099-09-14/17', 'occurrences': len(groupes) * 4,
    'p95_groupe_semaine_s': round(latences[int(0.95 * len(latences) + 0.9999) - 1], 3),
    'max_groupe_semaine_s': round(latences[-1], 3),
    'decisions': dict(statuts), 'codes': dict(codes), 'sql': sql,
    'affectations_annee': AffectationCreneau.objects.filter(
        emploi_du_temps__annee_academique=annee).count(),
    'registres_annee': SeanceRegistre.objects.filter(
        affectation__emploi_du_temps__annee_academique=annee).count(),
    'maxrss_kib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
    'source': 'FICTIVE_NON_OFFICIELLE'}, ensure_ascii=False))
