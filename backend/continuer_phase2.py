import os
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings'
import django
django.setup()
from scolarite.models import Semestre, Parcours, TypeFormation
from formations.models import UE, ECUE
from datetime import date

print('=== PHASE 2: Modules Scolarité ===')

# 1. Semestres (Priorité 1)
print('\n1. Creation des Semestres S1-S10')
semestre_data = [
    ('S1', 'Séance 1'), ('S2', 'Séance 2'), ('S3', 'Séance 3'),
    ('S4', 'Séance 4'), ('S5', 'Séance 5'), ('S6', 'Séance 6'),
    ('S7', 'Séance 7'), ('S8', 'Séance 8'), ('S9', 'Séance 9'), ('S10', 'Séance 10'),
]
created_s = 0
existed_s = 0
for code, libelle in semestre_data:
    s, c = Semestre.objects.get_or_create(code=code, defaults={'libelle': libelle})
    if c: created_s += 1
    else: existed_s += 1
print(f'  Created: {created_s}, Existed: {existed_s}, Total: {Semestre.objects.count()}')

# 2. Parcours (Priorité 2)
print('\n2. Creation des Parcours Limport os
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings'
import django
d',os.envire 3'),
    ('M1', 'Master 1'), ('M2', 'Master 2'),
]
createdjango.setuptefrom scolaritodfrom formations.models import UE, ECUE
from datetime import dorfrom datetimecode, defaults={'libelle':
print('=== PHASE 2: create
# 1. Semestres (Priorité 1)
print('\n1. C Crprint('\n1. Creation des Se: semestre_data = [
    ('S1', 'Séance 1'),t(    ('S1', 'Séaor    ('S4', 'Séance 4'), ('S5', 'Séance 5'), ('S6', 'Séance 6')e_    ('S7', 'Séance 7'), ('S8', 'Séance 8'), ('S9', 'Séance 9')ER]
created_s = 0
existed_s = 0
for code, libelle in semestre_data:
    s, c = Semestre.obCyclexisted_s = nafor code, liJS    s, c = Semestre.objects.get_orfo    if c: created_s += 1
    else: existed_s += 1
print(f'  Created: {created_s}, s.    else: existed_s += , print(f'  Created: {crebe
# 2. Parcours (Priorité 2)
print('\n2. Creation des Parcours Limport os
os.environ['DJ  Cprint('\n2. Creation des Pedos.environ['DJANGO_SETTINGS_MODULE'] = 'cons.import django
d',os.envire 3'),
    ('M1', 'Master 1'),red',os.envire e    ('M1', 'Mast =]
createdjango.setuptefrom scolaritodfrom MATHfrom datetime import dorfrom datetimecode, defaults={'libelle':
print('=('print('=== PHASE 2: create
# 1. Semestres (Priorité 1)
= 0
for code, libelle, credits, coeprint('\n1. C Crprint('\n1.E.objects.get_or_create(code=code, defaults={'libelle': libelle, created_s = 0
existed_s = 0
for code, libelle in semestre_data:
    s, c = Semestre.obCyclexisted_s = nafor code, liJS    s, c = Semestre.objects.get_orfo    if c: created_s += 1M1existed_s = 1', 8, 3), ('ECUE-M2', 'ÉMCUE M2', 8, 3),
]
created    else: existed_s += 1
print(f'  Created: {created_s}, s.    data:
    e, c = ECUE.objects.get_or_create(code=codprint(aults={'libelle': l# 2. Parcours (Priorité 2)
print('\ient': coeff})
    if c: created_e += 1
    else: existed_e += 1
    print(f'os.environ['DJ  Cprint('\n2. Creation des Pd"d',os.envire 3'),
    ('M1', 'Master 1'),red',os.envire e    ('M1', 'Mast =]
createdjango.setuptefrom ,     ('M1', 'Mastd_createdjango.setuptefrom scolaritodfrom MATHfrom datetimtedprint('=('print('=== PHASE 2: create
# 1. Semestres (Priorité 1)
= 0
for code, libelle, credits, coeprintre# 1. Semestres (Priorité 1)
= 0
foin= 0
for code, libelle, cred} foreexisted_s = 0
for code, libelle in semestre_data:
    s, c = Semestre.obCyclexisted_s = : {created_e}, Existed: {existed_e})')
print('\n=forPHASE 2 Terminee ===')
