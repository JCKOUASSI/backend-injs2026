import os
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings'
import django
django.setup()
from referentiels.models import *
models = [RefFiliere,RefEcole,RefMention,RefTypeCursus,RefTypeEnseignement,RefTypeEvaluation,RefTypeDocument,RefGradeEnseignant,RefTypeFrais,RefModePaiement,RefTypeDecision,RefTypeNotification,RefTypeEspaceSportif,RefVolumeHoraireFormation,RefModuleOfficiel]
for m in models:
    print(f'{m.__name__}: {m.objects.count()}')
