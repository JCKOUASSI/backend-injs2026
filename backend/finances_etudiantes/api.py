"""API Finances Étudiantes (L6).

Pattern @api_view (cohérent avec graduation/jurys/equivalences). Permissions :
lecture pour authentifié gestion (IsAuthenticated) ; opérations sensibles
(confirmer paiement, remboursement, rapprochement) réservées à FINANCE/DIRECTION.
"""
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from authentication.permissions import IsDFRC
from habilitations.permissions import ExigePermission
from scolarite.models import DossierEtudiant
from admissions.models import Candidat

from .models import (
    Echeancier, Facture, LigneEcheancier, Paiement,
    Quittance, RapprochementComptable, Relance, Remboursement, Tarification,
)
from .services import (
    confirmer_paiement, enregistrer_paiement_idempotent,
    generer_echeancier_pour_etudiant,
    generer_facture, valider_paiement_par_transaction,
)


def _serialize_paiement(p):
    return {
        'id': p.id, 'etudiant_id': p.etudiant_id, 'candidat_id': p.candidat_id,
        'nature': p.nature, 'montant': str(p.montant), 'devise': p.devise,
        'mode': p.mode, 'statut': p.statut, 'date': p.date.isoformat(),
        'transaction_externe': p.transaction_externe or '',
        'preuve_url': p.preuve.url if p.preuve else None,
    }


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def echeanciers_list_api(request):
    """Liste des échéanciers (GET) ; génération pour etudiant_id + annee_id (POST)."""
    if request.method == 'GET':
        qs = Echeancier.objects.select_related('etudiant', 'annee_academique').all()
        return Response({'results': [{
            'id': e.id, 'etudiant_id': e.etudiant_id,
            'annee_academique': str(e.annee_academique),
            'statut_global': e.statut_global, 'lignes_count': e.lignes.count(),
        } for e in qs]})
    etudiant_id = request.data.get('etudiant_id')
    annee_id = request.data.get('annee_academique_id')
    if not etudiant_id or not annee_id:
        return Response(
            {'error': "etudiant_id et annee_academique_id sont obligatoires."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    try:
        etudiant = DossierEtudiant.objects.get(pk=etudiant_id)
    except DossierEtudiant.DoesNotExist:
        return Response({'error': 'Dossier étudiant introuvable.'}, status=404)
    from scolarite.models import AnneeAcademique
    try:
        annee = AnneeAcademique.objects.get(pk=annee_id)
    except AnneeAcademique.DoesNotExist:
        return Response({'error': 'Année académique introuvable.'}, status=404)
    echeancier = generer_echeancier_pour_etudiant(etudiant, annee)
    if not echeancier:
        return Response(
            {'error': "Aucune tarification active pour ce périmètre."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    return Response({'id': echeancier.id, 'statut_global': echeancier.statut_global}, status=201)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def echeancier_detail_api(request, pk):
    try:
        e = Echeancier.objects.get(pk=pk)
    except Echeancier.DoesNotExist:
        return Response({'error': 'Échéancier introuvable.'}, status=404)
    lignes = e.lignes.all()
    return Response({
        'id': e.id, 'etudiant_id': e.etudiant_id,
        'annee_academique': str(e.annee_academique),
        'statut_global': e.statut_global,
        'lignes': [{
            'id': l.id, 'nature': l.nature, 'get_nature_display': l.get_nature_display(),
            'montant': str(l.montant), 'date_echeance': l.date_echeance.isoformat(),
            'statut': l.statut,
        } for l in lignes],
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def lignes_echeancier_api(request, pk):
    try:
        e = Echeancier.objects.get(pk=pk)
    except Echeancier.DoesNotExist:
        return Response({'error': 'Échéancier introuvable.'}, status=404)
    return Response({'results': [{
        'id': l.id, 'nature': l.nature, 'montant': str(l.montant),
        'date_echeance': l.date_echeance.isoformat(), 'statut': l.statut,
    } for l in e.lignes.all()]})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def facture_generer_api(request, pk):
    """Génère une facture pour l'échéancier <pk>."""
    try:
        e = Echeancier.objects.get(pk=pk)
    except Echeancier.DoesNotExist:
        return Response({'error': 'Échéancier introuvable.'}, status=404)
    try:
        facture = generer_facture(e, request.user)
    except Exception as exc:
        return Response({'error': str(exc)}, status=400)
    return Response({
        'id': facture.id, 'numero': facture.numero, 'total': str(facture.total),
        'statut': facture.statut, 'date_emission': facture.date_emission.isoformat(),
    }, status=201)


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def paiements_list_api(request):
    """Liste des paiements (GET) ; enregistrement idempotent (POST)."""
    if request.method == 'GET':
        qs = Paiement.objects.select_related('etudiant', 'candidat').all()
        return Response({'results': [_serialize_paiement(p) for p in qs]})
    tx_externe = request.data.get('transaction_externe')
    if not tx_externe:
        return Response(
            {'error': "transaction_externe est obligatoire (anti-doublon)."}, status=400,
        )
    etudiant = DossierEtudiant.objects.filter(pk=request.data.get('etudiant_id')).first() \
        if request.data.get('etudiant_id') else None
    candidat = Candidat.objects.filter(pk=request.data.get('candidat_id')).first() \
        if request.data.get('candidat_id') else None
    try:
        paiement, created = enregistrer_paiement_idempotent(
            etudiant=etudiant, candidat=candidat,
            nature=request.data['nature'], montant=request.data['montant'],
            devise=request.data.get('devise', 'XOF'), mode=request.data['mode'],
            transaction_externe=tx_externe, utilisateur=request.user,
        )
    except KeyError as exc:
        return Response({'error': f"Champ obligatoire manquant : {exc.args[0]}."}, status=400)
    except Exception as exc:
        return Response({'error': str(exc)}, status=400)
    return Response(_serialize_paiement(paiement), status=201 if created else 200)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def paiement_detail_api(request, pk):
    try:
        p = Paiement.objects.get(pk=pk)
    except Paiement.DoesNotExist:
        return Response({'error': 'Paiement introuvable.'}, status=404)
    return Response(_serialize_paiement(p))


@api_view(['POST'])
@permission_classes([IsAuthenticated, IsDFRC,
                     ExigePermission.pour('finances_etud.paiement.valider')])
def paiement_confirmer_api(request, pk):
    """Confirme un paiement (exige une preuve) — réservé à FINANCE/DIRECTION.

    LOT 5 / U8 : première vue « acte critique » branchée sur le moteur
    (permission ``finances_etud.paiement.valider``). Le branchement est
    inerte tant que le mode livré reste OBSERVATION (comptage des écarts,
    aucune réponse modifiée) ; le kill-switch ``HABILITATIONS_APPLICATION``
    rendrait seul le refus effectif, vue par vue.
    """
    try:
        p = Paiement.objects.get(pk=pk)
    except Paiement.DoesNotExist:
        return Response({'error': 'Paiement introuvable.'}, status=404)
    try:
        confirmer_paiement(p, request.user)
    except Exception as exc:
        return Response({'error': str(exc)}, status=400)
    return Response(_serialize_paiement(p))


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def quittances_list_api(request):
    qs = Quittance.objects.select_related('paiement').all()
    return Response({'results': [{
        'id': q.id, 'paiement_id': q.paiement_id, 'numero': q.numero,
        'date_echeance': q.date_echeance.isoformat(),
    } for q in qs]})


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated, IsDFRC])
def remboursements_list_api(request):
    """Liste des remboursements (GET) ; création (POST) — réservé FINANCE/DIRECTION."""
    if request.method == 'GET':
        qs = Remboursement.objects.select_related('paiement_original').all()
        return Response({'results': [{
            'id': r.id, 'paiement_original_id': r.paiement_original_id,
            'montant': str(r.montant), 'devise': r.devise,
            'motif': r.motif, 'statut': r.statut, 'date': r.date.isoformat(),
        } for r in qs]})
    try:
        paiement = Paiement.objects.get(pk=request.data['paiement_original_id'])
    except (KeyError, Paiement.DoesNotExist):
        return Response({'error': "paiement_original_id invalide."}, status=400)
    try:
        r = Remboursement.objects.create(
            paiement_original=paiement,
            montant=request.data['montant'],
            devise=request.data.get('devise', 'XOF'),
            motif=request.data['motif'],
            utilisateur=request.user,
        )
    except KeyError as exc:
        return Response({'error': f"Champ obligatoire manquant : {exc.args[0]}."}, status=400)
    except Exception as exc:
        return Response({'error': str(exc)}, status=400)
    return Response({'id': r.id, 'statut': r.statut}, status=201)


@api_view(['POST'])
@permission_classes([IsAuthenticated, IsDFRC])
def remboursement_creer_api(request):
    """Alias POST create (renvoie vers la liste POST)."""
    return remboursements_list_api(request)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def relances_list_api(request):
    qs = Relance.objects.select_related('echeancier').all()
    return Response({'results': [{
        'id': r.id, 'echeancier_id': r.echeancier_id,
        'type_relance': r.type_relance, 'message': r.message,
        'date_creation': r.date_creation.isoformat(),
    } for r in qs]})


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated, IsDFRC])
def rapprochements_list_api(request):
    """Liste des rapprochements (GET) ; création (POST) — réservé FINANCE/DIRECTION."""
    if request.method == 'GET':
        qs = RapprochementComptable.objects.all()
        return Response({'results': [{
            'id': r.id, 'date_periode': r.date_periode.isoformat(),
            'solde': str(r.solde), 'commentaire': r.commentaire,
            'transactions_count': r.transactions.count(),
        } for r in qs]})
    return _rapprochement_creer(request)


def _rapprochement_creer(request):
    from datetime import datetime
    try:
        date_periode = datetime.strptime(request.data['date_periode'], '%Y-%m-%d').date()
    except (KeyError, ValueError):
        return Response({'error': "date_periode (YYYY-MM-DD) obligatoire."}, status=400)
    r = RapprochementComptable.objects.create(
        date_periode=date_periode,
        solde=request.data.get('solde', 0),
        commentaire=request.data.get('commentaire', ''),
    )
    tx_ids = request.data.get('transactions', [])
    if tx_ids:
        r.transactions.set(Paiement.objects.filter(id__in=tx_ids))
    return Response({'id': r.id, 'date_periode': r.date_periode.isoformat()}, status=201)


@api_view(['POST'])
@permission_classes([IsAuthenticated, IsDFRC])
def rapprochement_creer_api(request):
    """Crée un rapprochement comptable (FINANCE/DIRECTION)."""
    return _rapprochement_creer(request)


