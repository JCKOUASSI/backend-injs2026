import os
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings'
import django
django.setup()
from admissions.models import TypeCandidature, VoieAcces, TypePiece

# Create TypeCandidature
tc_data = [
    {'code': 'EXTER', 'libelle': 'Concours externe'},
    {'code': 'INTER', 'libelle': 'Concours interne'},
    {'code': 'SUR_TITRE', 'libelle': 'Sur titres'},
]
for tc_d in tc_data:
    TypeCandidature.objects.get_or_create(code=tc_d['code'], defaults={'libelle': tc_d['libelle']})
print(f'TypeCandidature: {TypeCandidature.objects.count()}')

# Create VoieAcces
va_data = [
    {'code': 'CONCOURS', 'libelle': 'Concours direct'},
    {'code': 'VAE', 'libelle': 'Validation des Acquis de lExperience'},
    {'code': 'TRANSFERT', 'libelle': 'Transfert letablissement'},
]
for va_d in va_data:
    VoieAcces.objects.get_or_create(code=va_d['code'], defaults={'libelle': va_d['libelle']})
print(f'VoieAcces: {VoieAcces.objects.count()}')

# Create TypePiece
tp_data = [
    {'code': 'BACC', 'libelle': 'Baccalaureat', 'obligatoire_par_defaut': True},
    {'code': 'PC', 'libelle': 'Premier Cycle', 'obligatoire_par_defaut': True},
    {'code': 'CERTIF', 'libelle': 'Certificat de scolarite', 'obligatoire_par_defaut': False},
    {'code': 'PICTO', 'libelle': 'Piece identite', 'obligatoire_par_defaut': True},
]
for tp_d in tp_data:
    TypePiece.objects.get_or_create(code=tp_d['code'], defaults={'libelle': tp_d['libelle'], 'obligatoire_par_defaut': tp_d['obligatoire_par_defaut']})
print(f'TypePiece: {TypePiece.objects.count()}')

print('Done creating admission types')