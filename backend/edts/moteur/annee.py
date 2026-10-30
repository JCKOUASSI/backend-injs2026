"""GET-INJS — génération des emplois du temps d'une **année académique entière**.

**Besoin métier.** Le commanditaire demande de générer « tous les emplois du
temps d'une année académique donnée, par filière, formation, groupe, vague,
semestre, pour tous les étudiants inscrits (au moins 3 500 par année) ».

**Orchestration retenue.** Une année n'est pas un seul emploi du temps : c'est
un **ensemble d'emplois du temps par groupe pédagogique**, coordonnés entre
eux. Le groupe porte déjà la promotion (arbitrage : pas de table
``Promotion``), avec sa formation, son parcours, son niveau et sa vague.

Pour chaque groupe de l'année :

1. les besoins viennent des ``AffectationPedagogique`` **quand elles existent**
   (chaîne LMD interne, comportement historique) ;
2. sinon — cas des **cohortes importées**, inscrites hors parcours — ils sont
   dérivés de la **maquette active** (``besoins_maquette``) ;
3. l'effectif est le **dénombrement réel** des inscriptions importées, à
   défaut la capacité déclarée du groupe, à défaut inconnu (jamais inventé) ;
4. la génération est coordonnée : les placements d'un groupe interdisent les
   conflits d'enseignant, de salle et de groupe dans les suivants (C1/C2/C3) ;
5. chaque plan est validé puis persisté **séparément** (transaction par EDT).

**Aucune publication.** La génération produit des brouillons ; la validation
et la publication restent des gestes humains explicites (règle du lot L8).

**Aucune donnée inventée.** Un groupe sans maquette active, ou dont les ECUE
n'ont aucun volume, n'est pas planifié : il est listé avec son motif.
"""

from __future__ import annotations

from edts.moteur import generation as G
from edts.moteur import orchestration as O
from edts.moteur.besoins import calculate_teaching_needs
from edts.moteur.besoins_maquette import besoins_depuis_maquette

# ── Statuts globaux (mêmes conventions que l'orchestration coordonnée) ───────
ANNEE_COMPLETE = 'COMPLETE'
ANNEE_PARTIELLE = 'PARTIELLE'
ANNEE_IMPOSSIBLE = 'IMPOSSIBLE'

#: Motifs de non-planification d'un groupe (explicites, affichables).
MOTIF_AUCUN_BESOIN = 'AUCUN_BESOIN_PLANIFIABLE'
MOTIF_EDT_NON_MODIFIABLE = 'EDT_STATUT_NON_MODIFIABLE'
MOTIF_VALIDATION = 'VALIDATION_BLOQUANTE'


def _edt_du_groupe(annee_academique_id, groupe, semaines, *, creer):
    """EDT cible d'un groupe (version 1) — créé en BROUILLON si demandé."""
    from edts.models import EmploiDuTemps

    existant = EmploiDuTemps.objects.filter(
        annee_academique_id=annee_academique_id,
        population_type='GROUPE',
        population_id=groupe.pk,
        version=1,
    ).order_by('pk').first()
    if existant is not None:
        return {'edt': existant, 'cree': False}
    if not creer:
        return {'edt': None, 'cree': False}

    libelle = f'{groupe.ref_formation.intitule} — {groupe.niveau.code} {groupe.nom}'
    edt, _ = EmploiDuTemps.objects.get_or_create(
        annee_academique_id=annee_academique_id,
        population_type='GROUPE',
        population_id=groupe.pk,
        version=1,
        defaults={
            'population_denominateur': libelle,
            'titre': f'EDT {libelle}',
            'statut': 'BROUILLON',
            'semaine_debut': min(semaines),
            'semaine_fin': max(semaines),
        },
    )
    return {'edt': edt, 'cree': True}


def generer_annee(annee_academique_id, *, semaines=None, persister=False,
                  remplacer=True, budget=G.BUDGET_PLACEMENTS_DEFAUT,
                  inclure_maquette=True):
    """Génère les EDT de tous les groupes INJS d'une année académique.

    :param annee_academique_id: année cible (obligatoire).
    :param semaines: semaines académiques planifiées (défaut ``[1]``).
    :param persister: écrit les plans validés dans des EDT BROUILLON.
    :param remplacer: désactive les séances générées antérieures avant réécriture
        (idempotence d'une régénération).
    :param inclure_maquette: complète les besoins par la maquette pour les
        cohortes sans affectation pédagogique (cohortes importées).
    :returns: bilan structuré, par groupe et global — jamais d'exception métier.
    """
    from django.db.models import Count

    from edts.moteur.import_inscrits import effectifs_par_groupe
    from formations.referentiel_injs_l6 import formations_injs
    from scolarite.models import Groupe

    semaines = sorted({int(s) for s in (semaines or [1])})
    perimetre = set(formations_injs().values_list('pk', flat=True))

    groupes = list(
        Groupe.objects.filter(annee_academique_id=annee_academique_id, actif=True)
        .select_related('ref_formation', 'parcours', 'niveau', 'vague')
        .order_by('ref_formation__intitule', 'niveau__ordre', 'nom')
    )
    groupes_injs = [g for g in groupes if g.ref_formation_id in perimetre]
    hors_perimetre = len(groupes) - len(groupes_injs)

    if not groupes_injs:
        return {
            'status_global': ANNEE_IMPOSSIBLE,
            'motif_echec': 'AUCUN_GROUPE_INJS',
            'annee_academique_id': annee_academique_id,
            'semaines': {'debut': min(semaines), 'fin': max(semaines)},
            'groupes': [],
            'totaux': {},
            'detail': {
                'explication': (
                    'Aucun groupe pédagogique actif dans le périmètre INJS pour '
                    'cette année académique : il n’y a rien à planifier.'
                ),
                'action_recommandee': (
                    'Importez le fichier des inscrits (GET-INJS → Import des '
                    'inscrits) ou créez les groupes dans Scolarité.'
                ),
                'groupes_hors_perimetre': hors_perimetre,
            },
        }

    effectifs = effectifs_par_groupe(annee_academique_id)

    # ── 1. Besoins : affectations pédagogiques d'abord ────────────────────────
    besoins_par_groupe = {}
    resultat_affectations = calculate_teaching_needs(
        annee_academique_id=annee_academique_id,
        duree_seance_heures=None,
    )
    for besoin in resultat_affectations.besoins:
        if besoin.groupe_id is None:
            continue
        besoins_par_groupe.setdefault(besoin.groupe_id, []).append(besoin)

    # ── 2. Cohortes sans affectation : maquette active ────────────────────────
    sans_affectation = [g for g in groupes_injs if g.pk not in besoins_par_groupe]
    detail_maquette = {}
    if inclure_maquette and sans_affectation:
        resultat_maquette = besoins_depuis_maquette(
            annee_academique_id=annee_academique_id,
            groupe_ids=[g.pk for g in sans_affectation],
            effectifs=effectifs,
        )
        for besoin in resultat_maquette.besoins:
            besoins_par_groupe.setdefault(besoin.groupe_id, []).append(besoin)
        detail_maquette = {
            'motif_echec': resultat_maquette.motif_echec,
            'detail': resultat_maquette.detail,
        }

    # ── 3. Génération coordonnée, groupe par groupe ───────────────────────────
    occupations = O.occupations_persistees(annee_academique_id, semaines=semaines)
    lignes = []
    for groupe in groupes_injs:
        besoins = besoins_par_groupe.get(groupe.pk, [])
        libelle = f'{groupe.ref_formation.intitule} — {groupe.niveau.code} {groupe.nom}'
        effectif = effectifs.get(groupe.pk) or groupe.capacite_max or None

        if not besoins:
            lignes.append({
                'groupe_id': groupe.pk,
                'groupe': groupe.nom,
                'formation': groupe.ref_formation.intitule,
                'parcours': groupe.parcours.intitule if groupe.parcours else None,
                'niveau': groupe.niveau.code,
                'vague': groupe.vague.libelle if groupe.vague else None,
                'effectif': effectif,
                'statut': 'NON_PLANIFIE',
                'motif_echec': MOTIF_AUCUN_BESOIN,
                'seances_attendues': 0,
                'seances_placees': 0,
                'seances_non_placees': 0,
            })
            continue

        resultat = G.generate_schedule(
            annee_academique_id=annee_academique_id,
            groupe_ids=[groupe.pk],
            semaines=semaines,
            budget=budget,
            occupations_initiales=occupations,
            besoins=besoins,
        )

        # Coordination : ces placements pèsent sur les groupes suivants.
        for place in resultat.placements:
            occupations.append({
                'enseignant_id': place.enseignant_id,
                'groupe_id': place.groupe_id,
                'salle_id': place.salle_id,
                'jour': place.jour,
                'heure_debut': place.heure_debut,
                'heure_fin': place.heure_fin,
            })

        ligne = {
            'groupe_id': groupe.pk,
            'groupe': groupe.nom,
            'formation': groupe.ref_formation.intitule,
            'parcours': groupe.parcours.intitule if groupe.parcours else None,
            'niveau': groupe.niveau.code,
            'vague': groupe.vague.libelle if groupe.vague else None,
            'effectif': effectif,
            'statut': resultat.status,
            'motif_echec': resultat.motif_echec,
            # Comptabilité du moteur lui-même (`metrics`) : un placement porte
            # un bloc hebdomadaire récurrent, `nb_seances` en donne le nombre de
            # séances. Recalculer ces valeurs à la main ferait diverger le bilan
            # annuel du bilan unitaire.
            'seances_attendues': resultat.metrics['seances_attendues'],
            'seances_placees': resultat.metrics['seances_placees'],
            'seances_non_placees': resultat.metrics['seances_non_placees'],
            'blocs_placees': len(resultat.placements),
            'heures_attendues': resultat.metrics['heures_attendues'],
            'taux_couverture': resultat.metrics['taux_couverture'],
            'conflits': len(resultat.conflits),
            'edt_id': None,
            'edt_cree': False,
        }

        # ── 4. Persistance éventuelle (transaction par EDT) ───────────────────
        if persister and resultat.placements:
            cible = _edt_du_groupe(annee_academique_id, groupe, semaines, creer=True)
            persistance = O._persister_si_possible(cible, resultat, remplacer=remplacer)
            ligne['persistance'] = persistance
            ligne['edt_id'] = cible['edt'].pk if cible['edt'] else None
            ligne['edt_cree'] = cible['cree']
            if not persistance.get('effectuee'):
                ligne['statut'] = 'NON_PERSISTE'
                ligne['motif_echec'] = persistance.get('motif_refus')

        lignes.append(ligne)

    # ── 5. Bilan honnête ──────────────────────────────────────────────────────
    planifies = [l for l in lignes if l['statut'] not in ('NON_PLANIFIE', 'NON_PERSISTE')]
    complet = [
        l for l in planifies
        if l['seances_non_placees'] == 0 and l['conflits'] == 0
    ]
    if not planifies:
        status_global = ANNEE_IMPOSSIBLE
    elif len(complet) == len(lignes):
        status_global = ANNEE_COMPLETE
    else:
        status_global = ANNEE_PARTIELLE

    total_etudiants = sum(
        l['effectif'] or 0 for l in lignes
    )

    # Une année IMPOSSIBLE doit toujours dire POURQUOI au niveau global : sans
    # cela l'écran afficherait « Impossible » sans motif, et l'utilisateur ne
    # saurait pas s'il manque des groupes, des besoins ou une maquette.
    motif_global = None
    detail_global = {}
    if status_global == ANNEE_IMPOSSIBLE:
        if all(l['motif_echec'] == MOTIF_AUCUN_BESOIN for l in lignes):
            motif_global = MOTIF_AUCUN_BESOIN
            detail_global = {
                'explication': (
                    'Les groupes existent mais aucun besoin horaire n’a pu être '
                    'calculé : ni affectation pédagogique, ni maquette active ne '
                    'couvre ces cohortes. Aucune séance n’est inventée.'
                ),
                'action_recommandee': (
                    'Renseignez les affectations pédagogiques du groupe, ou '
                    'activez une maquette (UE/ECUE) pour sa formation et son '
                    'niveau, puis relancez la génération.'
                ),
            }
        else:
            motif_global = 'AUCUN_PLACEMENT_POSSIBLE'
            detail_global = {
                'explication': (
                    'Aucune séance n’a pu être placée pour les groupes de cette '
                    'année. Le détail par groupe donne le motif de chaque échec.'
                ),
                'action_recommandee': (
                    'Consultez la colonne « Motif » du bilan par groupe, puis '
                    'corrigez l’occupation des salles ou des enseignants.'
                ),
            }

    return {
        'status_global': status_global,
        'motif_echec': motif_global,
        'detail': detail_global,
        'annee_academique_id': annee_academique_id,
        'semaines': {'debut': min(semaines), 'fin': max(semaines)},
        'groupes': lignes,
        'totaux': {
            'nb_groupes': len(lignes),
            'nb_groupes_planifies': len(planifies),
            'nb_groupes_complets': len(complet),
            'nb_groupes_non_planifies': len([l for l in lignes if l['statut'] == 'NON_PLANIFIE']),
            'etudiants_couverts': total_etudiants,
            'seances_attendues': sum(l['seances_attendues'] for l in lignes),
            'seances_placees': sum(l['seances_placees'] for l in lignes),
            'seances_non_placees': sum(l['seances_non_placees'] for l in lignes),
            'heures_attendues': round(sum(l.get('heures_attendues', 0) for l in lignes), 2),
            'edts_persistes': len([l for l in lignes if l.get('edt_id')]),
            'groupes_hors_perimetre': hors_perimetre,
        },
        'sources': {
            'affectations_pedagogiques': {
                'groupes': len(groupes_injs) - len(sans_affectation),
                'motif_echec': resultat_affectations.motif_echec,
            },
            'maquette': detail_maquette,
        },
        'persistence_demandee': persister,
    }


def effectif_importe(annee_academique_id):
    """Nombre d'inscriptions importées pour une année (dénombrement réel)."""
    from edts.models import InscriptionImportee

    return InscriptionImportee.objects.filter(
        annee_academique_id=annee_academique_id,
        statut=InscriptionImportee.Statut.INSCRIT,
    ).count()


def repartition_importee(annee_academique_id):
    """Répartition des inscriptions importées par formation / niveau / groupe."""
    from django.db.models import Count

    from edts.models import InscriptionImportee

    lignes = (
        InscriptionImportee.objects
        .filter(annee_academique_id=annee_academique_id,
                statut=InscriptionImportee.Statut.INSCRIT)
        .values(
            'ref_formation__intitule', 'filiere_code', 'parcours__intitule',
            'niveau__code', 'groupe__nom', 'vague__libelle',
        )
        .annotate(effectif=Count('pk'))
        .order_by('ref_formation__intitule', 'niveau__code', 'groupe__nom')
    )
    return [
        {
            'formation': ligne['ref_formation__intitule'],
            'filiere_code': ligne['filiere_code'],
            'parcours': ligne['parcours__intitule'],
            'niveau': ligne['niveau__code'],
            'groupe': ligne['groupe__nom'],
            'vague': ligne['vague__libelle'],
            'effectif': ligne['effectif'],
        }
        for ligne in lignes
    ]
