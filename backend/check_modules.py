import os
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings'
import django
django.setup()
from scolarite.models import Semestre, Parcours, TypeFormation
from referentiels.models import RefTypeCursus, RefTypeEnseignement
from formations.models import RefFormation

print('=== Modules Referentiels ===')
print('RefTypeCursus:', RefTypeCursus.objects.count())
for m in RefTypeCursus.objects.all(): print(' ', m.code, m.libelle)

print('\nRefTypeEnseignement:', RefTypeEnseignement.objects.count())
for m in RefTypeEnseignement.objects.all(): print(' ', m.code, m.libelle)

print('\n=== Scolarite ===')
print('Semestre:', Semestre.objects.count())
for s in Semestre.objects.all()[:5]: print(' ', s.code, s.libelle)

print('\nParcours:', Parcours.objects.count())
for p in Parcours.objects.all()[:5]: print(' ', p.code, p.libelle)
for p in Parcours.objects.all()[:5]: print(' ', p.code, p.libelle)
belle)
CRIPT'
objects.all()[:5]: print(' ', t.code, t.libelle)
