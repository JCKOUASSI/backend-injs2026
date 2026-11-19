#!/usr/bin/env python3
"""Contrôle agrégé non destructif des bases BENCHMARK locales isolées."""
import json
import os
import resource
from collections import Counter

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django  # noqa: E402
django.setup()

from django.conf import settings  # noqa: E402
from django.db import connection  # noqa: E402
from django.db.models import Count  # noqa: E402
from edts.models import AffectationCreneau, InscriptionImportee  # noqa: E402
from edts.models_interop import SeanceInstantaneAttendus, SeanceRegistre  # noqa: E402
from edts.moteur.occupation_v2 import indexer_affectations  # noqa: E402
from presences.models import Pointage  # noqa: E402
from scolarite.models import AnneeAcademique, Groupe  # noqa: E402

sqlite_isole = (connection.vendor == 'sqlite' and
    str(connection.settings_dict['NAME']).startswith('/tmp/'))
pg_isole = (connection.vendor == 'postgresql' and os.getenv('GETINJS_PG_ISOLATED') == '1' and
    connection.settings_dict['HOST'] == '/tmp/getinjs-pg-socket' and
    str(connection.settings_dict['PORT']) == '55432' and
    str(connection.settings_dict['NAME']).startswith('getinjs_bench_'))
if (os.getenv('GETINJS_PHASE6_ISOLATED') != '1' or not settings.DEBUG or
    not (sqlite_isole or pg_isole)):
    raise RuntimeError('Vérification interdite hors base BENCH locale jetable.')
from django.db.models import Q  # noqa: E402
annees = list(AnneeAcademique.objects.filter(
    Q(libelle__startswith='BENCHMARK-PHASE6-') | Q(libelle__startswith='BENCHMARK-P6-')))
if len(annees) != 1:
    raise ValueError('Une seule année fictive est attendue.')
a = annees[0]
qs = AffectationCreneau.objects.filter(emploi_du_temps__annee_academique=a,
                                       cle_occurrence_v2__isnull=False)
index = indexer_affectations(qs.iterator(chunk_size=256))
par_groupe = list(qs.values('groupe_id').annotate(n=Count('pk')))
reg = SeanceRegistre.objects.filter(affectation__emploi_du_temps__annee_academique=a)
inst = SeanceInstantaneAttendus.objects.filter(registre__in=reg)
pointages = Pointage.objects.filter(seance_edt__in=qs).count()
cles_diff = sum(r.cle_metier != r.affectation.cle_occurrence_v2
                for r in reg.select_related('affectation').iterator(chunk_size=256))
vides = sum(bool(s.participants) for s in inst.iterator(chunk_size=256))
print(json.dumps({'annee': a.libelle, 'groupes': Groupe.objects.filter(annee_academique=a).count(),
    'inscrits_synthetiques': InscriptionImportee.objects.filter(annee_academique=a).count(),
    'affectations': qs.count(), 'registres': reg.count(), 'instantanes': inst.count(),
    'groupes_avec_48': sum(x['n'] == 48 for x in par_groupe),
    'groupes_incomplets': sum(x['n'] != 48 for x in par_groupe),
    'ressources_dates': index.nombre_ressources_dates,
    'cles_qr_incoherentes': cles_diff, 'instantanes_avec_participants': vides,
    'pointages': pointages,
    'rss_max_kib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}, ensure_ascii=False))
