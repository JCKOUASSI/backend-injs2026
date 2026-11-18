"""Import transactionnel du registre Participants (sans créer d'inscriptions pédagogiques).

Le vieil import-excel rattache aussi aux modules : ce comportement ne convient
pas à la page du registre. On réutilise seulement sa normalisation de colonnes.
"""
from io import BytesIO
from itertools import islice

from django.db import IntegrityError, transaction
from openpyxl import load_workbook
from rest_framework.response import Response

from .management.commands.import_excel import Command
from .models import Participant
from .serializers import ParticipantSerializer

CHAMPS = (
    'matricule', 'nom', 'prenom', 'sexe', 'date_naissance', 'lieu_naissance',
    'email', 'telephone', 'telephone2', 'type_concours', 'libelle_concours',
    'categorie', 'grade', 'groupe', 'grade_groupe', 'vague', 'site', 'salle',
)
MAX_LIGNES = 10000
MAX_OCTETS = 20 * 1024 * 1024


def importer_registre(request, fichier):
    nom = fichier.name.lower()
    if not nom.endswith(('.csv', '.xlsx')) or fichier.size > MAX_OCTETS:
        return Response({'error': 'Fichier CSV ou XLSX de 20 Mo maximum requis.'}, status=400)
    try:
        content = fichier.read()
        commande = Command()
        # Command attend stdout pour le diagnostic des en-têtes.
        commande.stdout = type('Silencieux', (), {'write': lambda self, text: None})()
        if nom.endswith('.csv'):
            feuille = commande._load_csv_from_bytes(content)
            classeur = None
        else:
            classeur = load_workbook(BytesIO(content), read_only=True, data_only=True)
            feuille = classeur['Participants'] if 'Participants' in classeur.sheetnames else classeur.active
        brutes = list(islice(feuille.iter_rows(values_only=True), MAX_LIGNES + 2))
        if len(brutes) > MAX_LIGNES + 1:
            if classeur:
                classeur.close()
            return Response({'error': f'{MAX_LIGNES} lignes maximum.'}, status=400)
        trou = False
        for row in brutes[1:]:
            vide = not any(v is not None and str(v).strip() for v in row)
            if trou and not vide:
                if classeur:
                    classeur.close()
                return Response({'error': 'Ligne vide au milieu du fichier : import annulé.'}, status=400)
            trou = trou or vide
        lignes = list(commande._rows(feuille))
        if classeur:
            classeur.close()
    except (UnicodeError, ValueError, OSError, KeyError, TypeError) as exc:
        return Response({'error': f'Fichier illisible ou en-têtes invalides : {exc}'}, status=400)
    except Exception:
        return Response({'error': 'Fichier Excel invalide.'}, status=400)

    if not lignes or len(lignes) > MAX_LIGNES:
        return Response({'error': f'Le fichier doit contenir entre 1 et {MAX_LIGNES} étudiants.'}, status=400)
    erreurs = []
    valides = []
    seen = set()
    # Vérifier l'intégralité AVANT toute écriture. Garder les champs manquants
    # inchangés pour les matricules existants (pas de suppression implicite).
    for numero, brut in lignes:
        matricule = str(brut.get('matricule') or '').strip()
        nom_ligne = str(brut.get('nom') or '').strip()
        prenom = str(brut.get('prenom') or '').strip()
        if not matricule or not nom_ligne or not prenom:
            erreurs.append(f'Ligne {numero} : matricule, nom et prénom obligatoires.')
            continue
        if matricule in seen:
            erreurs.append(f'Ligne {numero} : matricule répété dans le fichier.')
            continue
        seen.add(matricule)
        donnees = {'matricule': matricule, 'nom': nom_ligne, 'prenom': prenom}
        for champ in CHAMPS[3:]:
            value = brut.get(champ)
            if value is not None and str(value).strip():
                donnees[champ] = value.isoformat() if hasattr(value, 'isoformat') else str(value).strip()
        instance = Participant.objects.filter(matricule=matricule).first()
        if instance and request.user.role in ('SECRETARIAT', 'CHEF_SECRETARIAT'):
            if instance.secretariat_id != request.user.secretariat_id:
                erreurs.append(f'Ligne {numero} : étudiant hors de votre secrétariat.')
                continue
        if not instance and request.user.role in ('SECRETARIAT', 'CHEF_SECRETARIAT'):
            if not request.user.secretariat_id:
                erreurs.append(f'Ligne {numero} : aucun secrétariat associé au compte.')
                continue
            donnees['secretariat'] = request.user.secretariat_id
        serializer = ParticipantSerializer(instance, data=donnees, partial=bool(instance))
        if not serializer.is_valid():
            erreurs.append(f'Ligne {numero} : {serializer.errors}')
        else:
            valides.append((serializer, instance is None))
        if len(erreurs) >= 20:
            break
    if erreurs:
        return Response({'error': 'Import annulé : aucune ligne enregistrée.', 'errors': erreurs}, status=400)

    try:
        with transaction.atomic():
            for serializer, _created in valides:
                serializer.save()
    except IntegrityError:
        return Response({'error': 'Import annulé : matricule en conflit avec une autre opération.'}, status=409)
    return Response({
        'created': sum(1 for _serializer, created in valides if created),
        'updated': sum(1 for _serializer, created in valides if not created),
        'processed': len(valides),
        'errors': [],
    })
