import os
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings'
import django
django.setup()
from scolarite.models import UE

ue_data = [
    ('FR-S1', 'Français S1', 6), ('MATH-S1', 'Mathématiques S1', 6),
    ('PHYS-S1', 'Physique S1', 6), ('CHIM-S1', 'Chimie S1', 6),
]
created = 0
existed = 0
for code, libelle, credits in ue_data:
    u, c = UE.objects.get_or_create(code=code, defaults={'intitule': libelle, 'credits': credits})
    if c: created += 1
    else: existed += 1
print(f'UE: {UE.objects.count()} (Created: {created}, Existed: {existed})')
