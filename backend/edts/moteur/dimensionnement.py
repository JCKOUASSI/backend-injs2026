"""Dimensionnement dynamique GET-INJS2026 (mission complémentaire, Phase 3-4).

Calcule, à partir des **données réellement enregistrées** (inscriptions
administratives VALIDÉE de l'année, groupes pédagogiques actifs,
maquettes actives, salles, formateurs), les besoins de planification :

- promotions à planifier (formation × niveau × parcours ayant des
  inscrits validés — jamais supposées sur les dix semestres) ;
- groupes nécessaires par promotion, pour une capacité cible
  paramétrable (aucun nombre d'emplois du temps n'est imposé : le
  nombre d'EDT à produire est **dérivé** des groupes nécessaires,
  un EDT de groupe par groupe) ;
- séances à programmer, dérivées des maquettes actives via le moteur
  de besoins existant (:func:`besoins_maquette.besoins_depuis_maquette`) ;
- insuffisances de capacité signalées comme anomalies explicites
  (promotion sans groupe, promotion sans maquette active, effectif
  supérieur à la plus grande salle, groupes manquants).

Aucune donnée n'est inventée : lorsqu'une information indispensable
manque, elle apparaît dans ``anomalies`` avec son motif. Le calcul ne
fait que des agrégats SQL (comptages distincts, sommes) : il reste
exploitable aux paliers 3 500 et 15 000 étudiants.
"""

from math import ceil

from django.db.models import Count, Max, Sum

#: Capacité cible par groupe utilisée par défaut (cohérente avec le
#: découpage des cohortes du banc de charge `benchmark_getinjs`).
#: Toujours surchargeable par l'appelant (paramètre métier).
CAPACITE_CIBLE_DEFAUT = 60


def _promotions(annee_academique_id):
    """Promotions réelles : inscrits VALIDÉE par formation×niveau×parcours."""
    from scolarite.models import InscriptionAdministrative

    return list(
        InscriptionAdministrative.objects.filter(
            annee_academique_id=annee_academique_id,
            statut=InscriptionAdministrative.Statut.VALIDEE,
        )
        .values('ref_formation_id', 'ref_formation__intitule',
                'niveau_id', 'niveau__code', 'parcours_id')
        .annotate(effectif=Count('etudiant', distinct=True))
        .order_by('ref_formation__intitule', 'niveau__ordre', 'parcours_id')
    )


def _groupes_par_promotion(annee_academique_id):
    """Groupes actifs existants, regroupés par promotion."""
    from scolarite.models import Groupe

    lignes = (
        Groupe.objects.filter(annee_academique_id=annee_academique_id, actif=True)
        .values('ref_formation_id', 'niveau_id', 'parcours_id')
        .annotate(nb=Count('id'), capacite_totale=Sum('capacite_max'))
    )
    return {
        (l['ref_formation_id'], l['niveau_id'], l['parcours_id']): l
        for l in lignes
    }


def dimensionner(annee_academique_id, *, capacite_cible=CAPACITE_CIBLE_DEFAUT):
    """Rapport de dimensionnement d'une année académique.

    :param capacite_cible: effectif cible maximal par groupe (paramètre
        métier, jamais codé en dur dans les résultats : il est rappelé
        dans le rapport).
    :returns: dict prêt à sérialiser (API / commande / tests).
    """
    from edts.models import EmploiDuTemps
    from formations.models import Formateur, RefSalle

    capacite_cible = max(1, int(capacite_cible or CAPACITE_CIBLE_DEFAUT))

    promotions_brutes = _promotions(annee_academique_id)
    groupes_map = _groupes_par_promotion(annee_academique_id)

    promotions = []
    anomalies = []
    total_groupes_existants = 0
    total_groupes_necessaires = 0

    capacite_max_salle = (
        RefSalle.objects.filter(actif=True).aggregate(m=Max('capacite'))['m'] or 0
    )

    for promo in promotions_brutes:
        cle = (promo['ref_formation_id'], promo['niveau_id'], promo['parcours_id'])
        existants = groupes_map.get(cle, {})
        nb_existants = existants.get('nb', 0)
        effectif = promo['effectif']
        necessaires = ceil(effectif / capacite_cible) if effectif else 0
        deficit = max(0, necessaires - nb_existants)
        total_groupes_existants += nb_existants
        total_groupes_necessaires += necessaires

        libelle = (
            f"{promo['ref_formation__intitule']} — {promo['niveau__code']}"
            + (f" (parcours {promo['parcours_id']})" if promo['parcours_id'] else '')
        )
        if nb_existants == 0:
            anomalies.append({
                'type': 'PROMOTION_SANS_GROUPE',
                'promotion': libelle,
                'detail': (
                    f"{effectif} inscrit(s) validé(s) sans aucun groupe "
                    "pédagogique actif : constitution de groupes requise "
                    "avant génération."
                ),
            })
        elif deficit:
            anomalies.append({
                'type': 'GROUPES_INSUFFISANTS',
                'promotion': libelle,
                'detail': (
                    f"{nb_existants} groupe(s) existant(s), {necessaires} "
                    f"requis à {capacite_cible} étudiants/groupe "
                    f"(déficit {deficit})."
                ),
            })
        if capacite_max_salle and effectif > capacite_max_salle:
            anomalies.append({
                'type': 'EFFECTIF_SUPERIEUR_PLUS_GRANDE_SALLE',
                'promotion': libelle,
                'detail': (
                    f"Effectif {effectif} > plus grande salle "
                    f"({capacite_max_salle} places) : les CM devront être "
                    "scindés ou mutualisés par sous-groupes."
                ),
            })

        promotions.append({
            'ref_formation_id': promo['ref_formation_id'],
            'formation': promo['ref_formation__intitule'],
            'niveau_id': promo['niveau_id'],
            'niveau': promo['niveau__code'],
            'parcours_id': promo['parcours_id'],
            'effectif': effectif,
            'groupes_existants': nb_existants,
            'capacite_groupes_existants': existants.get('capacite_totale') or 0,
            'groupes_necessaires': necessaires,
            'deficit_groupes': deficit,
        })

    # Séances à programmer : dérivées des maquettes actives par le moteur
    # de besoins existant (jamais estimées à la main). Un échec du moteur
    # (canevas vide, aucun groupe, aucune maquette) est une anomalie
    # explicite, pas un zéro silencieux.
    seances_a_programmer = None
    heures_a_programmer = None
    if total_groupes_existants:
        from edts.moteur.besoins_maquette import besoins_depuis_maquette

        resultat = besoins_depuis_maquette(
            annee_academique_id=annee_academique_id,
        )
        if resultat.motif_echec:
            anomalies.append({
                'type': 'BESOIN_NON_CALCULABLE',
                'promotion': None,
                'detail': (
                    f"{resultat.motif_echec} : "
                    f"{resultat.detail.get('explication', '')}"
                ),
            })
        else:
            seances_a_programmer = resultat.total_seances_attendues
            heures_a_programmer = resultat.total_heures_attendues
            for sans in resultat.detail.get('sans_maquette', []):
                anomalies.append({
                    'type': 'PROMOTION_SANS_MAQUETTE',
                    'promotion': (
                        f"{sans.get('formation', '')} — {sans.get('niveau', '')}"
                    ),
                    'detail': (
                        f"Groupe {sans.get('groupe', '')} sans maquette "
                        "active : aucun enseignement dérivable."
                    ),
                })

    edt_existants = EmploiDuTemps.objects.filter(
        annee_academique_id=annee_academique_id,
        population_type='GROUPE',
    ).count()

    return {
        'annee_academique_id': annee_academique_id,
        'capacite_cible_par_groupe': capacite_cible,
        'effectif_total_a_planifier': sum(p['effectif'] for p in promotions),
        'promotions': promotions,
        'totaux': {
            'promotions_a_planifier': len(promotions),
            'groupes_existants': total_groupes_existants,
            'groupes_necessaires': total_groupes_necessaires,
            'deficit_groupes': sum(p['deficit_groupes'] for p in promotions),
            # Un EDT de groupe par groupe nécessaire : nombre DÉRIVÉ des
            # données, jamais un objectif imposé.
            'emplois_du_temps_a_produire': total_groupes_necessaires,
            'emplois_du_temps_existants': edt_existants,
            'seances_a_programmer': seances_a_programmer,
            'heures_a_programmer': heures_a_programmer,
            'salles_actives': RefSalle.objects.filter(actif=True).count(),
            'capacite_max_salle': capacite_max_salle,
            'formateurs_enregistres': Formateur.objects.count(),
        },
        'anomalies': anomalies,
    }
