"""L6 — API du référentiel officiel INJS-LMD.

Un seul point d'entrée : ``GET /api/formations/lmd/formations/``, qui
renvoie la chaîne

    FORMATIONS INJS → PARCOURS → NIVEAUX → SEMESTRES → MAQUETTES → UE → ECUE

La garantie de séparation est **serveur** : elle repose sur
``formations.referentiel_injs_l6.formations_injs()``, jamais sur un filtre
React (L6 §11). Les données legacy restent en base et sont simplement hors
de ce périmètre (L6 §9).

Aucun modèle n'est créé ici : les modèles existants
``RefFormation → Parcours → Niveau → Semestre → Maquette → UE → ECUE``
suffisent à représenter le référentiel INJS (L6 §4).
"""

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from formations.api_access import IsOperationalWebStaff
from formations.referentiel_injs_l6 import (
    FILIERES_INJS,
    formations_injs,
    signaler_ecarts,
)
from scolarite.models import Maquette, Niveau, Parcours, Semestre

#: ECTS par semestre — barème métier INJS (A-4.5 §3, source O8). Non modifiable.
CREDITS_PAR_SEMESTRE = 30
#: ECTS par niveau — A-4.5 §3. Non modifiable.
CREDITS_PAR_NIVEAU = 60


def _serialiser_parcours(queryset):
    return [
        {
            'id': p.id,
            'code': p.code,
            'intitule': p.intitule,
            'type_formation_id': p.type_formation_id,
            'actif': p.actif,
        }
        for p in queryset
    ]


def _serialiser_niveaux(queryset):
    """Niveaux LMD et leurs semestres — S1..S6 (Licence), S7..S10 (Master)."""
    par_niveau = {}
    for semestre in Semestre.objects.filter(actif=True).order_by('numero'):
        par_niveau.setdefault(semestre.niveau_id, []).append({
            'id': semestre.id,
            'libelle': semestre.libelle,
            'numero': semestre.numero,
            'credits': CREDITS_PAR_SEMESTRE,
        })
    return [
        {
            'id': n.id,
            'code': n.code,
            'libelle': n.libelle,
            'cycle': n.cycle,
            'ordre': n.ordre,
            'credits_requis': n.credits_requis or CREDITS_PAR_NIVEAU,
            'semestres': par_niveau.get(n.id, []),
        }
        for n in queryset
    ]


def _serialiser_maquette(maquette):
    """Maquette → UE → ECUE, sans jamais inventer d'UE absente des sources."""
    ues = []
    for ue in maquette.unites_enseignement.all():
        ues.append({
            'id': ue.id,
            'code': ue.code,
            'intitule': ue.intitule,
            'credits': ue.credits,
            'caractere': ue.caractere,
            'ordre': ue.ordre,
            'semestre_id': ue.semestre_id,
            'ecues': [
                {
                    'id': e.id,
                    'code': e.code,
                    'intitule': e.intitule,
                    'credits': e.credits,
                    'coefficient': float(e.coefficient),
                    'volume_cm': float(e.volume_cm),
                    'volume_td': float(e.volume_td),
                    'volume_tp': float(e.volume_tp),
                    'archive': e.archive,
                }
                for e in ue.ecues.all()
            ],
        })
    return {
        'id': maquette.id,
        'libelle': maquette.libelle or str(maquette),
        'version': maquette.version,
        'statut': maquette.statut,
        'annee_academique': maquette.annee_academique.libelle,
        'niveau_id': maquette.niveau_id,
        'parcours_id': maquette.parcours_id,
        'total_credits': sum(ue['credits'] for ue in ues),
        'ues': ues,
    }


def _serialiser_cycle(cycle, filiere_code):
    """Un cycle RefFormation INJS + ses parcours, niveaux, maquettes, UE, ECUE."""
    maquettes = (
        Maquette.objects.filter(ref_formation=cycle)
        .select_related('annee_academique', 'niveau', 'parcours')
        .prefetch_related('unites_enseignement__ecues')
        .order_by('-annee_academique__libelle', 'niveau__ordre', '-version')
    )
    return {
        'id': cycle.id,
        'intitule': cycle.intitule,
        'code': cycle.code,
        'filiere_code': filiere_code or cycle.filiere_code,
        'type_diplome': cycle.type_diplome,
        'domaine': cycle.domaine,
        'mention': cycle.mention,
        'duree_annees': cycle.duree_annees,
        'nb_semestres': cycle.nb_semestres,
        'nb_credites': cycle.nb_credites,
        'source': cycle.source,
        'parcours': _serialiser_parcours(
            Parcours.objects.filter(ref_formation=cycle).order_by('code')
        ),
        'niveaux': _serialiser_niveaux(
            Niveau.objects.filter(actif=True).order_by('ordre')
        ),
        'maquettes': [_serialiser_maquette(m) for m in maquettes],
    }


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsOperationalWebStaff])
def formations_lmd_api(request):
    """GET /api/formations/lmd/formations/ — référentiel INJS validé.

    Ne retourne **que** les formations relevant de la source métier INJS
    (A-4.5 §2). Aucun corpus étranger ne peut y figurer :
    le queryset filtre ``perimetre = INJS`` **et** exclut explicitement les
    intitulés porteurs de marqueurs étrangers (L6 §10).
    """
    cycles = list(
        formations_injs(actif_only=True).order_by(
            'filiere_code', 'type_diplome', 'intitule'
        )
    )
    filieres = []
    for code, sigle, libelle, ecole, domaine, diplomes in FILIERES_INJS:
        cycles_filiere = [c for c in cycles if c.filiere_code == code]
        filieres.append({
            'code': code,
            'sigle': sigle,
            'libelle': libelle,
            'ecole': ecole,
            'domaine': domaine,
            'diplomes_attestes': list(diplomes),
            # Filière non chargée : déclarée, jamais comblée par approximation
            # ni par un cycle d'une autre filière (L6 §1).
            'chargee': bool(cycles_filiere),
            'cycles': [_serialiser_cycle(c, code) for c in cycles_filiere],
        })

    return Response({
        'source': 'A-4.5 §2 (O7/PDF/O2/O6/O9)',
        'credits_par_semestre': CREDITS_PAR_SEMESTRE,
        'credits_par_niveau': CREDITS_PAR_NIVEAU,
        'nb_filieres_attendues': len(FILIERES_INJS),
        'nb_filieres_chargees': sum(1 for f in filieres if f['chargee']),
        'filieres': filieres,
        'integrite': signaler_ecarts(),
    })
