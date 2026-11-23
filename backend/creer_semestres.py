import os
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings'
import django
django.setup()
from scolarite.models import Semestre, Niveau

niveaux = list(Niveau.objects.all())  # L1, L2, L3, M1, M2
semestre_data = [
    ('S1', 'Séance 1'), ('S2', 'Séance 2'), ('S3', 'Séance 3'),
    ('S4', 'Séance 4'), ('S5', 'Séance 5'), ('S6', 'Séance 6'),
    ('S7', 'Séance 7'), ('S8', 'Séance 8'), ('S9', 'Séance 9'), ('S10', 'Séance 10'),
]
created = 0
existed = 0
for i, (code, libelle) in enumerate(semestre_data):
    numero = int(code.replace('S', ''))
    niveau = niveaux[i % 5]  # Distribute across 5 niveaus
    s, c = Semestre.objects.get_or_create(numero=numero, defaults={'libelle': libelle, 'niveau': niveau})
    if c: created += 1
    else: existed += 1
print(f'Semestres: {Semestre.objects.count()} (Created: {created}, Existed: {existed})')
