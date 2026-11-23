import os
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings'
import django
django.setup()
from scolarite.models import Niveau

niveau_data = [
    {'code': 'L1', 'libelle': 'Licence 1', 'cycle': 'LMD', 'ordre': 1},
    {'code': 'L2', 'libelle': 'Licence 2', 'cycle': 'LMD', 'ordre': 2},
    {'code': 'L3', 'libelle': 'Licence 3', 'cycle': 'LMD', 'ordre': 3},
    {'code': 'M1', 'libelle': 'Master 1', 'cycle': 'LMD', 'ordre': 4},
    {'code': 'M2', 'libelle': 'Master 2', 'cycle': 'LMD', 'ordre': 5},
]

for nd in niveau_data:
    n, created = Niveau.objects.get_or_create(code=nd['code'], defaults={
        'libelle': nd['libelle'],
        'cycle': nd['cycle'],
        'ordre': nd['ordre'],
    })
    if created:
        print(f'Created niveau: {n}')
    else:
        print(f'Existed: {n}')

print(f'Total niveaux: {Niveau.objects.count()}')