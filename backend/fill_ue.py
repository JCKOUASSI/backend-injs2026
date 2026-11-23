import os
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings'
import django
django.setup()
from scolarite.models import Maquette, UE, ECUE

print("Creating Maquettes...")
m1 = Maquette(code="UE1", libelle="UE de test")
m1.save()
print(f"Maquette created: {m1.id}")

ue_data = [
    ("FR-S1", "Francais S1", 6, m1.id),
    ("MATH-S1", "Mathématiques S1", 6, m1.id),
    ("PHYS-S1", "Physique S1", 6, m1.id),
    ("CHIM-S1", "Chimie S1", 6, m1.id),
]
for code, libelle, credits, m_id in ue_data:
    u, c = UE.objects.get_or_create(code=code, defaults={'intitule': libelle, 'credits': credits, 'maquette_id': m_id})
    if c: print(f"  UE {code} created")
    else: print(f"  UE {code} exists")

ece_data = [
    ('ECUE-M1', 'ÉMCUE M1', 8),
    ('ECUE-M2', 'ÉMCUE M2', 8),
]
for code, libelle, credits in ecue_data:
    e, c = ECUE.objects.get_or_create(code=code, defaults={'libelle': libelle, 'credits': credits})
    if c: print(f"  ECUE {code} created")
    else: print(f"  ECUE {code} exists")

print(f"Total: UE={UE.objects.count()}, ECUE={ECUE.objects.count()}")
