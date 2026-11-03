"""Hub Finances étudiantes premium (consultation — tâche 34).

Lecture enrichie : barème de tarification (les lignes d'exemple sont
inactives et n'alimentent aucune facturation), échéanciers avec
soldes, factures, paiements, remboursements, relances et situation par
étudiant. Aucune écriture ici : confirmations, quittances et
rapprochements restent dans le flux financier officiel.
"""
from decimal import Decimal

from django.db.models import Count, Sum
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from .models import (
    Echeancier, Facture, LigneEcheancier, Paiement, Quittance,
    RapprochementComptable, Relance, Remboursement, Tarification,
)
from .permissions import IsFinancesReadOnly

ZERO = Decimal('0')


def _detailler_echeancier(echeancier, lignes):
    total = sum((l.montant for l in lignes), ZERO)
    paye = sum((l.montant for l in lignes if l.statut == 'PAYE'), ZERO)
    return {
        'id': echeancier.id,
        'etudiant_id': echeancier.etudiant_id,
        'matricule': echeancier.etudiant.matricule,
        'nom_complet': echeancier.etudiant.nom_complet,
        'annee': str(echeancier.annee_academique),
        'nb_lignes': len(lignes),
        'total': float(total),
        'paye': float(paye),
        'reste': float(total - paye),
        'statut_global': echeancier.statut_global,
    }


@api_view(['GET'])
@permission_classes([IsFinancesReadOnly])
def stats_api(request):
    montant_attendu = LigneEcheancier.objects.aggregate(
        s=Sum('montant'),
    )['s'] or ZERO
    montant_paye = LigneEcheancier.objects.filter(
        statut='PAYE',
    ).aggregate(s=Sum('montant'))['s'] or ZERO
    encaisse = Paiement.objects.filter(
        statut__in=('CONFIRME', 'RAPPROCHE'),
    ).aggregate(s=Sum('montant'))['s'] or ZERO
    return Response({
        'tarifications_actives': Tarification.objects.filter(actif=True).count(),
        'tarifications_inactives': Tarification.objects.filter(actif=False).count(),
        'echeanciers': Echeancier.objects.count(),
        'montant_attendu': float(montant_attendu),
        'montant_lignes_payees': float(montant_paye),
        'montant_reste': float(montant_attendu - montant_paye),
        'factures': Facture.objects.count(),
        'factures_par_statut': dict(
            Facture.objects.values_list('statut')
            .annotate(n=Count('id')).order_by()
        ),
        'paiements': Paiement.objects.count(),
        'paiements_par_statut': dict(
            Paiement.objects.values_list('statut')
            .annotate(n=Count('id')).order_by()
        ),
        'montant_encaisse_confirme': float(encaisse),
        'quittances': Quittance.objects.count(),
        'remboursements': Remboursement.objects.count(),
        'relances': Relance.objects.count(),
        'rapprochements': RapprochementComptable.objects.count(),
    })


@api_view(['GET'])
@permission_classes([IsFinancesReadOnly])
def tarifications_api(request):
    qs = Tarification.objects.select_related(
        'formation', 'niveau', 'annee_academique',
    ).order_by('formation__intitule', 'nature')
    return Response({'results': [
        {
            'id': t.id, 'formation': t.formation.intitule,
            'niveau': t.niveau.code if t.niveau_id else 'Tous niveaux',
            'nature': t.nature, 'nature_display': t.get_nature_display(),
            'montant_base': float(t.montant_base), 'devise': t.devise,
            'actif': t.actif,
        } for t in qs
    ]})


@api_view(['GET'])
@permission_classes([IsFinancesReadOnly])
def echeanciers_api(request):
    qs = (
        Echeancier.objects.select_related('etudiant__participant', 'etudiant')
        .prefetch_related('lignes').order_by('etudiant__participant__nom')
    )
    filieres = request.GET.get('statut')
    results = [
        _detailler_echeancier(e, list(e.lignes.all())) for e in qs
    ]
    if filieres:
        results = [r for r in results if r['statut_global'] == filieres]
    return Response({'results': results})


@api_view(['GET'])
@permission_classes([IsFinancesReadOnly])
def factures_api(request):
    qs = Facture.objects.select_related(
        'echeancier__etudiant__participant',
    ).order_by('-date_emission')
    if request.GET.get('statut'):
        qs = qs.filter(statut=request.GET['statut'])
    return Response({'results': [
        {
            'id': f.id, 'numero': f.numero,
            'etudiant_id': f.echeancier.etudiant_id,
            'matricule': f.echeancier.etudiant.matricule,
            'nom_complet': f.echeancier.etudiant.nom_complet,
            'total': float(f.total), 'devise': 'XOF',
            'date_emission': f.date_emission.isoformat(),
            'statut': f.statut, 'statut_display': f.get_statut_display(),
        } for f in qs
    ]})


@api_view(['GET'])
@permission_classes([IsFinancesReadOnly])
def paiements_api(request):
    qs = Paiement.objects.select_related(
        'etudiant__participant',
    ).order_by('-date')
    if request.GET.get('statut'):
        qs = qs.filter(statut=request.GET['statut'])
    if request.GET.get('mode'):
        qs = qs.filter(mode=request.GET['mode'])
    return Response({'results': [
        {
            'id': p.id,
            'etudiant_id': p.etudiant_id,
            'matricule': p.etudiant.matricule if p.etudiant_id else '',
            'nom_complet': p.etudiant.nom_complet if p.etudiant_id else '',
            'nature': p.nature, 'nature_display': p.get_nature_display(),
            'montant': float(p.montant), 'devise': p.devise,
            'mode': p.mode, 'mode_display': p.get_mode_display(),
            'statut': p.statut, 'statut_display': p.get_statut_display(),
            'date': p.date.isoformat(),
            'transaction_externe': p.transaction_externe or '',
        } for p in qs[:1000]
    ]})


@api_view(['GET'])
@permission_classes([IsFinancesReadOnly])
def quittances_api(request):
    qs = Quittance.objects.select_related(
        'paiement__etudiant__participant',
    ).order_by('-id')
    return Response({'results': [
        {
            'id': q.id, 'numero': str(q.numero)[:18] + '…',
            'etudiant_id': q.paiement.etudiant_id,
            'matricule': (
                q.paiement.etudiant.matricule if q.paiement.etudiant_id else ''
            ),
            'montant': float(q.paiement.montant),
            'nature_display': q.paiement.get_nature_display(),
            'date_echeance': q.date_echeance.isoformat(),
        } for q in qs
    ]})


@api_view(['GET'])
@permission_classes([IsFinancesReadOnly])
def remboursements_api(request):
    qs = Remboursement.objects.select_related(
        'paiement_original__etudiant__participant',
    ).order_by('-date')
    return Response({'results': [
        {
            'id': r.id,
            'etudiant_id': r.paiement_original.etudiant_id,
            'matricule': (
                r.paiement_original.etudiant.matricule
                if r.paiement_original.etudiant_id else ''
            ),
            'montant': float(r.montant), 'devise': r.devise,
            'motif': r.motif,
            'statut': r.statut, 'statut_display': r.get_statut_display(),
            'date': r.date.isoformat(),
        } for r in qs
    ]})


@api_view(['GET'])
@permission_classes([IsFinancesReadOnly])
def relances_api(request):
    relances = Relance.objects.select_related(
        'echeancier__etudiant__participant',
    ).order_by('-date_creation')
    rapprochements = RapprochementComptable.objects.order_by('-date_periode')
    return Response({'results': [
        {
            'id': f'relance-{r.id}',
            'type_display': f'Relance {r.get_type_relance_display()}',
            'matricule': r.echeancier.etudiant.matricule,
            'nom_complet': r.echeancier.etudiant.nom_complet,
            'etudiant_id': r.echeancier.etudiant_id,
            'detail': r.message,
            'date': r.date_creation.isoformat(),
        } for r in relances
    ] + [
        {
            'id': f'rappro-{r.id}',
            'type_display': 'Rapprochement comptable',
            'matricule': '',
            'nom_complet': f'Solde {float(r.solde):,.0f}'.replace(',', ' ') + ' FCFA',
            'etudiant_id': None,
            'detail': r.commentaire,
            'date': r.date_periode.isoformat(),
        } for r in rapprochements
    ]})
