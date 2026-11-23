import os, sys
sys.path.insert(0, '/Users/jckouassi/injs-arena-source/backend')
import os
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings'
import django
django.setup()
from admissions.models import TypeCandidature, VoieAcces, Candidature, Candidat
from formations.models import Participant
from scolarite.models import AnneeAcademique, Niveau, RefFiliere
from datetime import date
from django.utils import timezone

tc = TypeCandidature.objects.get(code='EXTER')
va = VoieAcces.objects.get(code='CONCOURS')

# Get or create Candidats linked to Participants
participants = list(Participant.objects.all()[:5])
candidats = []
for p in participants:
    c, _ = Candidat.objects.get_or_create(
        participant=p,
        defaults={
            'nom': p.nom,
            'prenom': p.prenom,
            'sexe': p.sexe,
                                                                                                                        scenarios = [
        ('CAS A', 'VALIDE', 30, 'Dossier complet et valide'),
        ('CAS B', 'EN_ATTENTE_DE_VERIFICATION', 15, 'Pièces justificatives manquantes'),
        ('CAS C', 'EN_ATTENTE_DE_VERIFICATION', 5, 'En attente vérification pièces'),
        ('CAS D', 'PIECES_INCOMPLETES', 10, 'Dossier incomplet pièces manquantes'),
        ('CAS E', 'ADMIS_NON_INSCRIT', 1, 'Admis inscription en attente'),
    ]
    for label, statut, days, motif in scenarios:
        obj, is_created = Candidature.objects.get_or_create(
            candidat=c,
            defaults={
                'type_candidature': tc,
                'voie_acces': va,
                'statut': statut,
                'date_candidature': date.today() - timezone.timedelta(days=days),
                'annee_academique': AnneeAcademique.objects.first(),
                'observations': motif,
            }
        )
        if is_created: created += 1
        else: existed += 1

print(f'Candidatures: {Candidature.objects.count()}, Created={created}, Existed={existed}')

# Create inscriptions for VALIDE candidates
print('\nInscriptions pédagogiques pour candidats VALIDÉS:')
for candid in Candidature.objects.filter(statut='VALIDE')[:5]:
    try:
        ins, i_c = InscriptionPedagogique.objects.get_or_create(
            participant=candid.candidat.participant,
            niveau=Niveau.objects.first(),
            filiere=RefFiliere.objects.first(),
            groupe=Groupe.objects.first(),
            defaults={'statut': 'VALIDE', 'date_inscription': date.today()}
        )
        if i_c:
            print(f'  {candid.candidat.nom} {candid.candidat.prenom}')
        else:
            print(f'  Existant: {candid.candidat.nom} {candid.candidat.prenom}')
    except Exception as e:
        print(f'  Erreur: {e}')

print(f'InscriptionPedagogique: {InscriptionPedagogique.objects.count()}')
print('\n=== CAS scenarios completed ===')
