import os
import django
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings'
django.setup()
from scolarite.models import UE, ECUE

# Create UE entries
ue_data = [
    ('FR-S1', 'Français S1', 6),
    ('MATH-S1', 'Mathématiques S1', 6),
    ('PHYS-S1', 'Physique S1', 6),
    ('CHIM-S1', 'Chimie S1', 6),
]
for code, libelle, credits in ue_data:
    u, c = UE.objects.get_or_create(code=code, defaults={'intitule': libelle, 'credits': credits})
    print(f'UE {code}: {"Created" if c else "Existed"}')

# Create ECUE entries
ecue_data = [
    ('ECUE-M1', 'ÉMCUE M1', 8),
    ('ECUE-M2', 'ÉMCUE M2', 8),
]
for code, libelle in ecue_data:
    e, c = ECUE.objects.get_or_create(code=code, defaults={'libelle': libelle})
    if c: print(f'ECUE {code}: Created')
    else: print(f'ECUE {code}: Existed')

print(f'Final UE: {UE.objects.count()}')
print(f'Final ECUE: {ECUE.objects.count()}')
