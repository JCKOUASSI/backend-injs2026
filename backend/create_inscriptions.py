import os, sys
sys.path.insert(0, '/Users/jckouassi/injs-arena-source/backend')
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings'
import django
django.setup()
from scolarite.models import InscriptionPedagogique, AnneeAcademique, Groupe, Semestre
from referentiels.models import RefFiliere
from formations.models import Participant
from datetime import date
p = Participant.objects.first()
g = Groupe.objects.first()
s = Semestre.objects.first()
ins, c = InscriptionPedagogique.objects.get_or_create(
    participant=p, semestre=s, groupe=g,
    defaults={'statut': 'VALIDE', 'date_inscription': date.today()}
)
print(f'Inscription created: {c}')
