import os
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings'
import django
django.setup()
from scolarite.models import Groupe, Niveau, AnneeAcademique
from referentiels.models import RefFiliere, RefTypeCursus
from formations.models import RefFormation

annee = AnneeAcademique.objects.first()
niveaux = Niveau.objects.all()
filieres = RefFiliere.objects.all()

# Get the first formation as fallback
formation_totale = RefFormation.objects.first()

created_count = 0
existed_count = 0

for niveau in niveaux:
    for filiere in filieres:
        # Trouver la formation correspondante à cette filière
        formation = None
        try:
            formation = RefFormation.objects.get(filiere_code=filiere.code)
        except RefFormation.DoesNotExist:
            pass
        
        # Utiliser la formation totale comme fallback
        if formation is None:
            formation = formation_totale
        
        nom = f"{niveau.code}-{filiere.code}"
        defaults = {
            'annee_academique': annee,
            'niveau': niveau,
            'ref_formation': formation,
            'nom': nom,
            'capacite_max': 60,
            'actif': True,
        }
        g, created = Groupe.objects.get_or_create(nom=nom, defaults=defaults)
        if created:
            created_count += 1
            print(f'Created groupe: {g}')
        else:
            existed_count += 1

print(f'Total groupes: {Groupe.objects.count()}')
print(f'Created: {created_count}, Existed: {existed_count}')