import os
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings'
import django
django.setup()
from scolarite.models import TypeFormation

type_formation_data = [
    ('LICENCE', 'Licence'),
    ('MASTER', 'Master'),
    ('DOCTORAT', 'Doctorat'),
    ('PROFESSIONNALISANT', 'Cycle professionnalisant'),
]
created = 0
existed = 0
for code, libelle in type_formation_data:
    t, c = TypeFormation.objects.get_or_create(code=code, defaults={'libelle': libelle})
    if c: created += 1
    else: existed += 1
print(f'TypeFormation: {TypeFormation.objects.count()} (Created: {created}, Existed: {existed})')
