"""Fiche pédagogique LMD d'un enseignant, distincte de la fiche de paie legacy.

Toutes les agrégations sont calculées ici. Les indicateurs sans source métier
reliée restent null : le frontend affiche « Non disponible », jamais zéro.
"""
from django.db.models import Sum
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from scolarite import charges_services
from scolarite.models import AffectationPedagogique, AnneeAcademique

from .access import formateurs_queryset_for_user
from .api_access import IsOperationalWebStaff
from .serializers import FormateurSerializer


def construire_fiche(enseignant, request):
    annee = AnneeAcademique.courante_ou_none()
    affectations = AffectationPedagogique.objects.filter(
        enseignant=enseignant,
    ).exclude(statut=AffectationPedagogique.Statut.ANNULEE)
    if annee:
        affectations = affectations.filter(annee_academique=annee)
    affectations = affectations.select_related(
        'ref_formation__filiere', 'niveau', 'semestre', 'ue', 'ecue', 'groupe',
    ).order_by('ref_formation__intitule', 'niveau__ordre', 'semestre__numero', 'ecue__code', 'pk')
    lignes = [{
        'id': a.pk,
        'ecue_id': a.ecue_id,
        'ecue_code': a.ecue.code if a.ecue_id else '',
        'ecue_intitule': a.ecue.intitule if a.ecue_id else '',
        'ue': a.ue.intitule if a.ue_id else '',
        'formation_id': a.ref_formation_id,
        'formation': a.ref_formation.intitule,
        'filiere': a.ref_formation.filiere.libelle if a.ref_formation.filiere_id else '',
        'niveau': a.niveau.code,
        'semestre': a.semestre.libelle,
        'groupe_id': a.groupe_id,
        'groupe': a.groupe.nom if a.groupe_id else None,
        'type_enseignement': a.get_type_enseignement_display(),
        'heures': float(a.volume_horaire),
        'statut': a.statut,
        'statut_label': a.get_statut_display(),
        'date_debut': a.date_debut,
        'date_fin': a.date_fin,
        'est_exemple': (a.observations or '').startswith('[Exemple]'),
    } for a in affectations]
    formations = list(dict.fromkeys(l['formation'] for l in lignes))
    identite = FormateurSerializer(enseignant, context={'request': request}).data
    return {
        **identite,
        'annee_academique': annee.libelle if annee else None,
        'grade_label': identite['grade']['libelle'] if identite.get('grade') else None,
        'est_exemple': (enseignant.observations or '').startswith('[Exemple]'),
        'nb_formations': len(formations),
        'nb_ecue': len({l['ecue_id'] for l in lignes if l['ecue_id']}),
        'heures_affectees': float(affectations.aggregate(total=Sum('volume_horaire'))['total'] or 0),
        'formations': formations,
        'affectations': lignes,
        'charge': charges_services.charge_enseignant(enseignant, annee) if annee else None,
        'heures_effectuees': None,
        'taux_presence': None,
        'satisfaction_etudiants': None,
        'disponibilite_indicateurs': (
            'Les pointages EDT mesurent l’assiduité des étudiants. '
            'Aucune source de présence enseignante, de satisfaction ou '
            'd’heures effectuées n’est encore reliée à cette fiche.'
        ),
    }


def _fiche_ou_404(request, pk):
    enseignant = formateurs_queryset_for_user(request.user).filter(pk=pk).first()
    if enseignant is None:
        return None, Response({'detail': 'Enseignant introuvable.'}, status=404)
    return construire_fiche(enseignant, request), None


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsOperationalWebStaff])
def fiche_api(request, pk):
    fiche, erreur = _fiche_ou_404(request, pk)
    return erreur if erreur else Response(fiche)


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsOperationalWebStaff])
def fiche_export(request, pk, format_export):
    if format_export not in ('pdf', 'xlsx'):
        return Response({'detail': 'Format attendu : pdf ou xlsx.'}, status=400)
    fiche, erreur = _fiche_ou_404(request, pk)
    if erreur:
        return erreur
    from .enseignant_export import exporter
    return exporter(fiche, format_export)
