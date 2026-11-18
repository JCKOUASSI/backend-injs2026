"""Rapprochement en lecture seule des volumes ECUE, sans décision implicite d'import.

Un intitulé partagé entre formations/années ne prouve pas l'identité d'une
ECUE. Les rapprochements exacts restent des candidats à valider : les ECUE
n'ont pas de champ de provenance pour leurs volumes et les données de démo
peuvent être mélangées aux données réelles.
"""

from collections import defaultdict
from decimal import Decimal

from django.db.models import Q

from formations.models import RefModule, RefModuleVolumeHoraire
from referentiels.models import RefVolumeHoraireFormation
from scolarite.models import AnneeAcademique, ECUE, Maquette


def _normaliser(texte):
    return ' '.join((texte or '').split()).casefold()


def _triplet(obj, prefixe='volume_'):
    return tuple(str(getattr(obj, prefixe + type_)) if getattr(obj, prefixe + type_) is not None
                 else None for type_ in ('cm', 'td', 'tp'))


def _positif(triplet):
    return any(Decimal(v or '0') > 0 for v in triplet)


def rapprocher(annee_libelle):
    """Parcourt TOUTES les années/formations/maquettes, cible une année en sortie."""
    annees = list(AnneeAcademique.objects.values('id', 'libelle', 'courante'))
    cible = next((a for a in annees if a['libelle'] == annee_libelle), None)
    if cible is None:
        raise ValueError(f'Année {annee_libelle} introuvable dans cette base.')

    # Les versions archivées sont gardées comme indices historiques, mais
    # jamais qualifiées de preuve institutionnelle à elles seules.
    maquettes = list(Maquette.objects.select_related(
        'annee_academique', 'ref_formation', 'parcours', 'niveau').order_by('pk'))
    ecues = list(ECUE.objects.select_related(
        'ue__semestre', 'ue__maquette__annee_academique',
        'ue__maquette__ref_formation', 'ue__maquette__parcours',
        'ue__maquette__niveau').order_by('pk'))
    indexes = defaultdict(list)
    for ecue in ecues:
        maq = ecue.ue.maquette
        # Formation, parcours (None != parcours précis), niveau, numéro de
        # semestre, code de l'UE ET code de l'ECUE : pas de match approximatif.
        cle = (maq.ref_formation_id, maq.parcours_id, maq.niveau_id,
               ecue.ue.semestre.numero, _normaliser(ecue.ue.code),
               _normaliser(ecue.code))
        indexes[cle].append(ecue)

    ref_volumes = list(RefVolumeHoraireFormation.objects.select_related('formation'))
    ref_index = defaultdict(list)
    for ref in ref_volumes:
        ref_index[(ref.formation_id, _normaliser(ref.intitule_module))].append(ref)

    # Inventaire des autres supports : totaux seulement, sans ventilation
    # CM/TD/TP ; ils ne peuvent pas remplir les trois champs d'une ECUE.
    autres_totaux = {
        'ref_modules_avec_volume_total': RefModule.objects.filter(volume_horaire__gt=0).count(),
        'modules_formation_categorie_avec_total':
            RefModuleVolumeHoraire.objects.filter(volume_horaire__gt=0).count(),
    }

    # Inventaire par année et formation, même quand la cible est une seule
    # année : les sources historiques (ou leur absence) restent visibles.
    couverture = defaultdict(lambda: {'maquettes': 0, 'ecues': 0, 'ecues_avec_volume_positif': 0})
    for maq in maquettes:
        couverture[(maq.annee_academique.libelle, maq.ref_formation_id,
                    maq.ref_formation.filiere_code, maq.ref_formation.intitule)]['maquettes'] += 1
    for ecue in ecues:
        maq = ecue.ue.maquette
        ligne_couverture = couverture[(maq.annee_academique.libelle,
                                      maq.ref_formation_id,
                                      maq.ref_formation.filiere_code,
                                      maq.ref_formation.intitule)]
        ligne_couverture['ecues'] += 1
        ligne_couverture['ecues_avec_volume_positif'] += int(_positif(_triplet(ecue)))

    lignes = []
    for ecue in ecues:
        maq = ecue.ue.maquette
        if maq.annee_academique_id != cible['id'] or ecue.archive:
            continue
        cle = (maq.ref_formation_id, maq.parcours_id, maq.niveau_id,
               ecue.ue.semestre.numero, _normaliser(ecue.ue.code),
               _normaliser(ecue.code))
        # N'accepter que les valeurs positives de versions DISTINCTES de la
        # même clé ; des zéros ne sont jamais des preuves de volume nul.
        sources = [e for e in indexes[cle] if e.pk != ecue.pk
                   and not e.archive and _positif(_triplet(e))]
        valeurs = defaultdict(list)
        for source in sources:
            valeurs[_triplet(source)].append(source)
        courant = _triplet(ecue)
        refs = ref_index[(maq.ref_formation_id, _normaliser(ecue.intitule))]
        refs_indicatives = [{
            'id': r.pk, 'cm': str(r.heures_cm) if r.heures_cm is not None else None,
            'td': str(r.heures_td) if r.heures_td is not None else None,
            'tp': str(r.heures_tp) if r.heures_tp is not None else None,
            'fiabilite': r.fiabilite, 'source_document': r.source_document,
            'actif': r.actif, 'archive': r.archive,
        } for r in refs]
        correspondances = [{
            'ecue_id': e.pk, 'maquette_id': e.ue.maquette_id,
            'annee': e.ue.maquette.annee_academique.libelle,
            'maquette_statut': e.ue.maquette.statut,
            'cm': _triplet(e)[0], 'td': _triplet(e)[1], 'tp': _triplet(e)[2],
        } for e in sources]
        if len(valeurs) > 1 or (_positif(courant) and valeurs and courant not in valeurs):
            statut = 'CONTRADICTION_A_ARBITRER'
        elif _positif(courant):
            statut = 'VOLUME_PRESENT_PROVENANCE_A_VERIFIER'
        elif len(valeurs) == 1:
            statut = 'CANDIDAT_EXACT_A_VALIDER'
        elif refs_indicatives:
            statut = 'REFERENCE_MODULE_INDICATIVE_A_VERIFIER'
        else:
            statut = 'AUCUNE_SOURCE_VERIFIABLE'
        lignes.append({
            'statut': statut, 'annee': maq.annee_academique.libelle,
            'formation_id': maq.ref_formation_id,
            'formation': maq.ref_formation.intitule,
            'filiere': maq.ref_formation.filiere_code,
            'parcours_id': maq.parcours_id, 'parcours': maq.parcours.intitule if maq.parcours else None,
            'niveau_id': maq.niveau_id, 'niveau': maq.niveau.code,
            'semestre': ecue.ue.semestre.numero,
            'maquette_id': maq.pk, 'maquette_version': maq.version,
            'maquette_statut': maq.statut,
            'ue_id': ecue.ue_id, 'ue_code': ecue.ue.code,
            'ecue_id': ecue.pk, 'ecue_code': ecue.code, 'ecue_intitule': ecue.intitule,
            'ref_module_id': ecue.ref_module_id,
            'cm': courant[0], 'td': courant[1], 'tp': courant[2],
            'sources_exactes': correspondances,
            'references_module_indicatives': refs_indicatives,
        })
    comptes = {statut: sum(l['statut'] == statut for l in lignes)
               for statut in ('VOLUME_PRESENT_PROVENANCE_A_VERIFIER',
                              'CANDIDAT_EXACT_A_VALIDER',
                              'CONTRADICTION_A_ARBITRER',
                              'REFERENCE_MODULE_INDICATIVE_A_VERIFIER',
                              'AUCUNE_SOURCE_VERIFIABLE')}
    return {
        'annee_cible': annee_libelle,
        'regle': ('Lecture seule. Même clé formation/parcours/niveau/semestre/UE/ECUE '
                  'pour les candidats exacts ; aucune copie automatique. '
                  'Un volume positif sans provenance attestée n’est pas institutionnel. '
                  'Les références de module sont indicatives, pas une ECUE prouvée.'),
        'inventaire_toutes_annees': {
            'annees': annees, 'maquettes': len(maquettes),
            'maquettes_par_statut': {s: sum(m.statut == s for m in maquettes)
                                     for s in Maquette.Statut.values},
            'ecues': len(ecues),
            'ecues_avec_volume_positif': sum(_positif(_triplet(e)) for e in ecues),
            'references_module_cm_td_tp': len(ref_volumes),
            'references_module_avec_volume_positif': sum(
                _positif(_triplet(r, 'heures_')) for r in ref_volumes),
            'couverture_par_annee_formation': [
                {'annee': annee, 'formation_id': fid, 'filiere': filiere,
                 'formation': formation, **details}
                for (annee, fid, filiere, formation), details in sorted(couverture.items())
            ],
            'references_module_detail': [{
                'id': r.pk, 'formation_id': r.formation_id,
                'formation': r.formation.intitule,
                'intitule_module': r.intitule_module,
                'cm': str(r.heures_cm) if r.heures_cm is not None else None,
                'td': str(r.heures_td) if r.heures_td is not None else None,
                'tp': str(r.heures_tp) if r.heures_tp is not None else None,
                'total': str(r.heures_total) if r.heures_total is not None else None,
                'fiabilite': r.fiabilite, 'source_document': r.source_document,
                'actif': r.actif, 'archive': r.archive,
            } for r in ref_volumes],
            **autres_totaux,
        },
        'comptes_cible': comptes,
        'ecues_cible': lignes,
    }
