import os
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings'
import django
django.setup()
from admissions.models import TypeCandidature, VoieAcces, Candidature
from formations.models import Participant
from scolarite.models import AnneeAcademique, Groupe, InscriptionPedagogique, Niveau
from referentiels.models import RefFiliere
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import date

User = get_user_model()
annee = AnneeAcademique.objects.first()
tc = TypeCandidature.objects.get(code='EXTER')
va = VoieAcces.objects.get(code='CONCOURS')
participants = Participant.objects[:5]

created_count = 0
existed_count = 0

for i, participant in enumerate(participants):
    # CAS A: Complete candidature validated
    candid_a, a_c = Candidature.objects.get_or_create(
        participant=participant,
        defaults={
            'type_candidature': tc,
            'voie_acces': va,
            'import os
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings'
im
           import django
django.setup()
from admissions.models impdadjango.setup  from admissio ifrom formations.models import Participant
from scolarite.models impo Ifrom scolarite.models import AnneeAcadem= from referentiels.models import RefFiliere
from django.contrib.auth import get_users=from django.contrib.auth import get_user_  from django.utils import timezone
from dateti: from datetime import date

User ':
User = get_user_model() maannentes',
            'tc = TypeCandidature.objects.get(code=zova = VoieAcces.objects.get(code='CONCOURS')
p bparticipants = Participant.objects[:5]

crou
created_count = 0
existed_count = 0
eriexisted_count = di
for i, participdat    # CAS A: Complete candidature validated
 t=    candid_a, a_c = Candidature.objects.ge          participant=participant,
        _acces': va,
         defaults={
            E',
            'moti            'voie_acces': va,
    es            'import os
os.en_cos.environ['DJANGO_SEayim
           import django
django.setup()
from)
    if c c:django.setup()
from adm else: existed_cofrom scolarite.models impo Ifrom scolarite.models impordidature.objects.get_or_create(
        partfrom django.contrib.auth import get_users=from django.contrib.auth import get_user_  from django.utils import t  from dateti: from datetime import date

User ':
User = get_user_model() maannentes',
                'date_candidature'
User ':
User = get_user_model() maanaysUser =              'tc = TypeCandidature.ooup bparticipants = Participant.objects[:5]

crou
created_count = 0
existed_count = 0
ed_e, e_c = C
crou
created_count = 0
existed_count =   pcreicexisted_count = t,eriexisted_counts=for i, participdat  ca t=    candid_a, a_c = Candidature.objects.ge          partita        _acces': va,
         defaults={
            E',
            'moti    en         defaults={at            E',
  te            'mez    es            'import os
os.en_cos.enviro eos.en_cos.environ['DJANGO_Sel           import django
django'Cdjango.setup()
from)
   {created_count},    stfrom adm else: existed_cpr        partfrom django.contrib.auth import get_users=from django.contrib.auth import get_user_  fromates
print(
User ':
User = get_user_model() maannentes',
                'date_candidature'
User ':
User = get_user_model() maanaysUser =              'tc = TyInscriptionPedagoUser =ob          or_create(
            partUser ':
User = get_user_model() m  User =iv
crou
created_count = 0
existed_count = 0
ed_e, e_c = C
crou
created_count = 0
existed_count =   pcreicexisted_count),
cre  existed_efaults={'ed_e, e_c = C
cr',crou
createdipcren': date.today()}
           defaults={
            E',
            'moti    en         defaults={at            E',
  te            'mez    es            'import os
os.en_cos.enviro esc            E',
  po            'mti  te            'mez    es            'import os
os.en_costios.en_cos.enviro eos.en_cos.environ['DJANGO_Selpadticipant}: {e}')

print('\n=== CAS scenarios completed ===')
