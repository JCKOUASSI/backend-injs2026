import os
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings'
import django
django.setup()
from scolarite.models import UE, ECUE

ue_data = [
    ('FR-S1', 'Français S1', 6), ('MATH-S1', 'Mathématiques S1', 6),
    ('PHYS-S1', 'Physique S1', 6), ('CHIM-S1', 'Chimie S1', 6),
]
created_u = 0
existed_u = 0
for code, libelle, credits in ue_data:
    u, c = UE.objects.get_or_create(code=code, defaults={'intitule': libelle, 'credits': credits})
    if c: created_u += 1
    else: existed_u += 1
    print(f'  UE {code}: {"Created" if c else "Existed"}')

ecue_data = [
    ('ECUE-M1', 'ÉMCUE M1', 8), ('ECUE-M2', 'ÉMCUE M2', 8),
]
created_e = 0
existed_e = 0
for code, libelle in ecue_data:
    e, c = ECUE.objects.get_or_create(code=code, defaults={'libelle': libelle})
    if c: created_e += 1
    else: existed_e += 1
    print(f'  ECUE {code}: {"Created" if c else "Existed"}')

print(f'\nFinal: UE={UE.objects.count()} (Created: {created_u}, Existed: {existed_u})')
print(f'\nFinal: ECUE={ECUE.objects.count()} (Created: {created_e}, Existed: {existed_e})')
