import os
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings'
import django
django.setup()
from scolarite.models import InscriptionPedagogique, Participant, Niveau, RefFiliere, Groupe
from datetime import date

p = Participant.objects.first()
n = Niveau.objects.first()
f = RefFiliere.objects.first()
g = Groupe.objects.first()
ins, c = InscriptionPedagogique.objects.get_or_create(
    participant=p, niveau=n, filiere=f, groupe=g,
    defaults={'statut': 'VALIDE', 'date_inscription': date.today()}
)
print(f'Inscription created: {c}')
