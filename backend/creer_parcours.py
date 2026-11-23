import os
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings'
import django
django.setup()
from scolarite.models import Parcours
from formations.models import RefFormation

parcours_data = [
    ('L1', 'Licence 1'), ('L2', 'Licence 2'), ('L3', 'Licence 3'),
    ('M1', 'Master 1'), ('M2', 'Master 2'),
]
created = 0
existed = 0
formations = RefFormation.objects.all()
for code, libelle in parcours_data:
    # Assign formation based on filiere code pattern
    formation = formations[0]  # Use first formation as default
    p, c = Parcours.objects.get_or_create(code=code, defaults={'intitule': libelle, 'ref_formation': formation})
    if c: created += 1
    else: existed += 1
print(f'Parcours: {Parcours.objects.count()} (Created: {created}, Existed: {existed})')
