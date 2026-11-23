import os
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings'
import django
django.setup()
from referentiels.models import *
from admissions.models import TypeCandidature, VoieAcces, Candidature
from scolarite.models import Niveau, Groupe, InscriptionPedagogique
from formations.models import Participant

print('=== REFERENTIEL HUB STATE ===')
models = [RefFiliere,RefEcole,RefMention,RefTypeCursus,RefTypeEnseignement,RefTypeEvaluation,RefTypeDocument,RefGradeEnseignant,RefTypeFrais,RefModePaiement,RefTypeDecision,RefTypeNotification,RefTypeEspaceSportif,RefVolumeHoraireFormation,RefModuleOfficiel]
for m in models:
    print(f'  {m.__name__}: {m.objects.count()}')

print('\n=== ADMISSIONS STATE ===')
print(f'  TypeCandidature: {TypeCandidature.objects.count()}')
print(f'  VoieAcces: {VoieAcces.objects.count()}')
print(f'  Candidature: {Candidature.objects.count()}')

print('\n=== SCOLARITE STATE ===')
print(f'  Niveau: {Niveau.objects.count()}')
print(f'  Groupe: {Groupe.objects.count()}')
print(f'  InscriptionPedagogique: {InscriptionPedagogique.objects.count()}')

print('\n=== FORMATIONS STATE ===')
from formations.models import Participant
print(f'  Participant: {Participant.objects.count()}')
