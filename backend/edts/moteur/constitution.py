"""Constitution intelligente des groupes GET-INJS2026.

Le dimensionnement (:mod:`edts.moteur.dimensionnement`) calcule, par
promotion réelle, le nombre de groupes nécessaires pour une capacité
cible. Ce service crée les **groupes manquants** — l'étape suivante,
la répartition des étudiants dans les groupes, réutilise l'existant
(``scolarite.groupes_services.repartir_automatiquement``, exposée par
l'écran Groupes de la Scolarité).

Garanties :
- les noms prolongent la numérotation existante (``L1-G1`` → ``L1-G2``…)
  et respectent la contrainte d'unicité (année, formation, niveau, nom) ;
- l'opération est **idempotente** : une fois les groupes constitués, le
  déficit recalculé vaut zéro et un nouvel appel ne crée rien ;
- le mode **simulation** renvoie le plan complet sans écrire ;
- aucun étudiant n'est affecté ici, aucune donnée pédagogique inventée :
  seuls des contenants (groupes vides, capacité = capacité cible) sont
  créés, rattachés à la formation, au niveau et au parcours réels de la
  promotion.
"""

import re

from django.db import transaction

from edts.moteur.dimensionnement import CAPACITE_CIBLE_DEFAUT, dimensionner

_MOTIF_NOM = re.compile(r'-G(\d+)$', re.IGNORECASE)


def _noms_a_creer(annee_academique_id, ref_formation_id, niveau_id,
                  niveau_code, nombre, reserves=None):
    """Prochains noms libres ``<NIVEAU>-G<n>`` pour (année, formation, niveau).

    La contrainte d'unicité du nom ne tient pas compte du parcours : le
    pool de noms est donc celui de la formation et du niveau, toutes
    promotions confondues. ``reserves`` contient les noms déjà alloués
    par le plan en cours (autres parcours de la même formation/niveau),
    pour ne jamais proposer deux fois le même nom dans un même plan.
    """
    from scolarite.models import Groupe

    existants = Groupe.objects.filter(
        annee_academique_id=annee_academique_id,
        ref_formation_id=ref_formation_id,
        niveau_id=niveau_id,
    ).values_list('nom', flat=True)
    pris = {str(nom).strip().lower() for nom in existants}
    if reserves:
        pris |= {str(nom).strip().lower() for nom in reserves}
    indexes = [
        int(m.group(1))
        for nom in existants
        if (m := _MOTIF_NOM.search(str(nom or '').strip()))
    ]
    suivant = (max(indexes) if indexes else 0) + 1
    noms = []
    while len(noms) < nombre:
        candidat = f'{niveau_code}-G{suivant}'
        suivant += 1
        if candidat.lower() in pris:
            continue
        pris.add(candidat.lower())
        noms.append(candidat)
    return noms


def plan_constitution(annee_academique_id, *, capacite_cible=CAPACITE_CIBLE_DEFAUT):
    """Plan de constitution : groupes à créer par promotion en déficit.

    Lecture seule — aucune écriture. Basé sur le rapport de
    dimensionnement recalculé à l'instant de l'appel.
    """
    capacite_cible = max(1, int(capacite_cible or CAPACITE_CIBLE_DEFAUT))
    rapport = dimensionner(annee_academique_id, capacite_cible=capacite_cible)

    creations = []
    reserves_par_promotion = {}
    for promo in rapport['promotions']:
        if promo['deficit_groupes'] <= 0:
            continue
        cle_pool = (promo['ref_formation_id'], promo['niveau_id'])
        reserves = reserves_par_promotion.setdefault(cle_pool, set())
        noms = _noms_a_creer(
            annee_academique_id, promo['ref_formation_id'], promo['niveau_id'],
            promo['niveau'], promo['deficit_groupes'], reserves=reserves,
        )
        reserves.update(noms)
        creations.append({
            'ref_formation_id': promo['ref_formation_id'],
            'formation': promo['formation'],
            'niveau_id': promo['niveau_id'],
            'niveau': promo['niveau'],
            'parcours_id': promo['parcours_id'],
            'effectif': promo['effectif'],
            'groupes_existants': promo['groupes_existants'],
            'groupes_a_creer': [
                {'nom': nom, 'capacite_max': capacite_cible} for nom in noms
            ],
        })

    return {
        'annee_academique_id': annee_academique_id,
        'capacite_cible_par_groupe': capacite_cible,
        'creations': creations,
        'total_a_creer': sum(len(c['groupes_a_creer']) for c in creations),
    }


def constituer_groupes(annee_academique_id, *, capacite_cible=CAPACITE_CIBLE_DEFAUT,
                       simulation=False):
    """Crée les groupes manquants (ou simule et renvoie le plan).

    :param simulation: si vrai, aucune écriture — le plan est renvoyé
        tel quel pour prévisualisation et confirmation explicite.
    :returns: bilan ``{simulation, groupes_crees, total_crees, plan}``.
    """
    from scolarite.models import Groupe

    plan = plan_constitution(annee_academique_id, capacite_cible=capacite_cible)
    if simulation or plan['total_a_creer'] == 0:
        return {
            'simulation': bool(simulation),
            'groupes_crees': [],
            'total_crees': 0,
            'plan': plan,
        }

    crees = []
    with transaction.atomic():
        for bloc in plan['creations']:
            for groupe_plan in bloc['groupes_a_creer']:
                groupe = Groupe.objects.create(
                    annee_academique_id=annee_academique_id,
                    ref_formation_id=bloc['ref_formation_id'],
                    parcours_id=bloc['parcours_id'],
                    niveau_id=bloc['niveau_id'],
                    nom=groupe_plan['nom'],
                    capacite_max=groupe_plan['capacite_max'],
                    actif=True,
                )
                crees.append({
                    'id': groupe.pk,
                    'nom': groupe.nom,
                    'formation': bloc['formation'],
                    'niveau': bloc['niveau'],
                    'parcours_id': bloc['parcours_id'],
                    'capacite_max': groupe.capacite_max,
                })

    return {
        'simulation': False,
        'groupes_crees': crees,
        'total_crees': len(crees),
        'plan': plan,
    }
