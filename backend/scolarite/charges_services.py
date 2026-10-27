"""Lot L3/L7 — calculs et détections des charges pédagogiques.

Charge prévue : Σ volumes des ECUE des maquettes ACTIVE de l'année.
Charge affectée : Σ volumes des affectations non annulées d'un enseignant.
Charge planifiée / réalisée : Σ par statut.
Anomalies détectées : module sans enseignant, volume non couvert, double
affectation, conflit de disponibilité, maquette incompatible, surcharge
(seuil paramétrable via la clé ``volume_horaire_max_enseignant`` du module
parametres, défaut 192 h/an).
"""
from scolarite.models import (
    AffectationPedagogique,
    ECUE,
    IndisponibiliteEnseignant,
    Maquette,
)

from parametres.models import Parametre

SEUIL_DEFAUT_SURCHARGE = 192  # heures/an (surcharge au-delà)


def _seuil_surcharge():
    parametre = Parametre.get_by_cle('volume_horaire_max_enseignant')
    if parametre is None:
        return SEUIL_DEFAUT_SURCHARGE
    try:
        return float(parametre.valeur)
    except (TypeError, ValueError):
        return SEUIL_DEFAUT_SURCHARGE


def maquettes_actives(annee):
    return Maquette.objects.filter(
        annee_academique=annee, statut=Maquette.Statut.ACTIVE,
    ).select_related('ref_formation', 'niveau')


def charge_enseignant(enseignant, annee):
    """Résumé des charges d'un enseignant pour une année."""
    affectations = AffectationPedagogique.objects.filter(
        enseignant=enseignant, annee_academique=annee,
    ).exclude(statut=AffectationPedagogique.Statut.ANNULEE).select_related(
        'ecue__ue__maquette', 'ue__maquette', 'groupe',
    )
    volumetrie = AffectationPedagogique.volumetrie(enseignant, annee)

    # Charge prévue : Σ volumes des ECUE des maquettes actives couvertes
    # par les affectations de l'enseignant.
    perimetres = {
        (a.ref_formation_id, a.niveau_id) for a in affectations
    }
    prevue = 0.0
    for formation_id, niveau_id in perimetres:
        maquette = Maquette.objects.filter(
            annee_academique=annee, ref_formation_id=formation_id,
            niveau_id=niveau_id, statut=Maquette.Statut.ACTIVE,
        ).first()
        if maquette:
            prevue += sum(
                float(ecue.volume_total)
                for ecue in ECUE.objects.filter(ue__maquette=maquette)
            )

    seuil = _seuil_surcharge()
    return {
        'enseignant_id': enseignant.pk,
        'enseignant': f'{enseignant.nom} {enseignant.prenom}',
        'prevue': round(prevue, 2),
        'affectee': round(volumetrie['affectee'], 2),
        'validee': round(volumetrie['validee'], 2),
        'planifiee': round(volumetrie['planifiee'], 2),
        'realisee': round(volumetrie['realisee'], 2),
        'surcharge': volumetrie['affectee'] > seuil,
        'seuil': seuil,
        'nb_affectations': affectations.count(),
    }


def anomalies(annee):
    """Détections L3 : module sans enseignant, volume non couvert, double
    affectation, conflit de disponibilité, maquette incompatible, surcharge."""
    problemes = []
    for maquette in maquettes_actives(annee):
        for ecue in ECUE.objects.filter(ue__maquette=maquette).select_related('ue'):
            affectations = AffectationPedagogique.objects.filter(
                annee_academique=annee, ecue=ecue,
            ).exclude(statut=AffectationPedagogique.Statut.ANNULEE).select_related('enseignant')
            if not affectations.exists():
                problemes.append({
                    'type': 'MODULE_SANS_ENSEIGNANT',
                    'detail': f'ECUE {ecue.code} ({maquette.ref_formation.intitule}) '
                              'sans enseignant affecté.',
                })
                continue
            volume_affecte = sum(float(a.volume_horaire) for a in affectations)
            if volume_affecte < float(ecue.volume_total):
                problemes.append({
                    'type': 'VOLUME_NON_COUVERT',
                    'detail': f'ECUE {ecue.code} : {volume_affecte} h affectées '
                              f'pour {ecue.volume_total} h prévues.',
                })
            if affectations.values('enseignant').distinct().count() > 1:
                problemes.append({
                    'type': 'DOUBLE_AFFECTATION',
                    'detail': f'ECUE {ecue.code} confiée à plusieurs enseignants.',
                })
            for affectation in affectations:
                conflits = IndisponibiliteEnseignant.objects.filter(
                    enseignant=affectation.enseignant,
                    date_debut__lte=affectation.date_fin or annee.date_fin,
                    date_fin__gte=affectation.date_debut or annee.date_debut,
                )
                if conflits.exists():
                    problemes.append({
                        'type': 'CONFLIT_DISPONIBILITE',
                        'detail': f'{affectation.enseignant} : indisponibilité '
                                  f'pendant l’affectation de {ecue.code}.',
                    })

    # Affectations hors maquette active (maquette incompatible).
    for affectation in AffectationPedagogique.objects.filter(
        annee_academique=annee, ecue__isnull=False,
    ).exclude(statut=AffectationPedagogique.Statut.ANNULEE).select_related(
        'enseignant', 'ecue', 'ecue__ue__maquette',
    ):
        if not affectation._ecue_de_maquette_active():
            problemes.append({
                'type': 'MAQUETTE_INCOMPATIBLE',
                'detail': f'ECUE {affectation.ecue.code} affectée hors maquette '
                          f'ACTIVE ({affectation.enseignant}).',
            })

    # Surcharge par enseignant.
    from formations.models import Formateur
    for enseignant in Formateur.objects.filter(
        affectations_pedagogiques__annee_academique=annee,
    ).distinct():
        resume = charge_enseignant(enseignant, annee)
        if resume['surcharge']:
            problemes.append({
                'type': 'SURCHARGE',
                'detail': f"{resume['enseignant']} : {resume['affectee']} h affectées "
                          f"(seuil {resume['seuil']} h).",
            })
    return problemes


def occupation_par_enseignant(annee):
    """Rapport d'occupation : résumé de charge pour chaque enseignant concerné."""
    from formations.models import Formateur
    rapports = []
    for enseignant in Formateur.objects.filter(
        affectations_pedagogiques__annee_academique=annee,
    ).distinct():
        rapports.append(charge_enseignant(enseignant, annee))
    return sorted(rapports, key=lambda r: -r['affectee'])