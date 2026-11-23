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

from edts.moteur import contraintes as C
from edts.moteur import generation as G
from edts.moteur import orchestration as O
from edts.moteur.besoins import calculate_teaching_needs
from edts.moteur.besoins_maquette import (
    MOTIF_AUCUNE_MAQUETTE, MOTIF_VOLUMES_ABSENTS, besoins_depuis_maquette,
)

# ── Statuts globaux (mêmes conventions que l'orchestration coordonnée) ───────
ANNEE_COMPLETE = 'COMPLETE'
ANNEE_PARTIELLE = 'PARTIELLE'
ANNEE_IMPOSSIBLE = 'IMPOSSIBLE'

#: Motifs de non-planification d'un groupe (explicites, affichables).
MOTIF_AUCUN_BESOIN = 'AUCUN_BESOIN_PLANIFIABLE'
MOTIF_EDT_NON_MODIFIABLE = 'EDT_STATUT_NON_MODIFIABLE'
MOTIF_VALIDATION = 'VALIDATION_BLOQUANTE'


def _generer_occurrences_par_semaine(*, annee_id, groupe_id, semaines, besoins,
                                    occupations, creneaux, budget, politique):
    """Réutilise le solveur existant sur des occurrences unitaires par semaine.

    Aucun bloc pluri-hebdomadaire n'est inventé : chaque placement porte sa
    semaine exacte. Les occupations déjà posées ne bloquent que leurs semaines
    réelles ; une période disjointe peut réutiliser une salle/enseignant.
    Les occurrences sont affectées aux semaines les moins chargées pour éviter
    de concentrer les besoins à faible volume au début du semestre.
    Une année multi-semestre requiert encore un calendrier institutionnel
    explicite : l'appelant refuse ce cas au lieu d'inventer ses bornes.
    """
    from dataclasses import replace

    par_semaine = {s: [] for s in semaines}
    for besoin in besoins:
        for _ in range(besoin.nb_seances):
            semaine = min(semaines, key=lambda s: len(par_semaine[s]))
            par_semaine[semaine].append(replace(
                besoin, nb_seances=1, volume_horaire=besoin.duree_seance_heures,
            ))

    placements, non_places, warnings = [], [], []
    reste = budget
    for semaine, unitaires in par_semaine.items():
        if not unitaires:
            continue
        if reste <= 0:
            non_places.extend(G.BesoinNonPlace(b, 'Budget de recherche épuisé.')
                              for b in unitaires)
            continue
        occ_semaine = [o for o in occupations if (
            o.get('semaine_debut', semaine) <= semaine <= o.get('semaine_fin', semaine))]
        occ_semaine.extend(p for p in placements if p.semaine_debut == semaine)
        resultat = G.generate_schedule(
            annee_academique_id=annee_id, groupe_ids=[groupe_id],
            semaines=[semaine], budget=reste, besoins=unitaires,
            occupations_initiales=occ_semaine, creneaux=creneaux,
            contraintes_souples=politique,
        )
        placements.extend(resultat.placements)
        non_places.extend(resultat.non_places)
        warnings.extend(resultat.warnings)
        reste = max(0, reste - resultat.metrics['creneaux_explores'])

    attendues = sum(b.nb_seances for b in besoins)
    placees = len(placements)
    heures_attendues = round(sum(b.volume_horaire for b in besoins), 2)
    heures_placees = round(sum(p.besoin.duree_seance_heures for p in placements), 2)
    statut = (G.GENERATION_OK if placees == attendues else
              G.GENERATION_PARTIELLE if placements else G.GENERATION_IMPOSSIBLE)
    return G.GenerationResult(
        status=statut, placements=placements, non_places=non_places,
        finalite=(G.FINALITE_COMPLETE if statut == G.GENERATION_OK else
                  G.FINALITE_PARTIAL if placements else G.FINALITE_IMPOSSIBLE),
        warnings=warnings, motif_echec=(None if statut == G.GENERATION_OK else
                                         'OCCURRENCES_NON_PLACEES'),
        metrics={
            'seances_attendues': attendues, 'seances_placees': placees,
            'seances_non_placees': attendues - placees,
            'heures_attendues': heures_attendues, 'heures_placees': heures_placees,
            'taux_couverture': round(100 * placees / attendues, 2) if attendues else 0,
            'creneaux_explores': budget - reste,
            'budget_configured': budget, 'budget_restant': reste,
            'nb_placements_effectues': placees,
            'contraintes_souples': C.resume_souples(placements, politique),
        },
    )


def _generer_calendrier_provisoire(*, annee_id, groupe_id, besoins, calendrier,
                                    occupations, creneaux, budget, politique):
    """Planifie chaque semestre dans sa plage, puis réunit UN plan par EDT.

    Aucun besoin sans semestre connu n'est attribué par supposition. Le
    résultat n'est complet que si chaque occurrence des deux périodes l'est.
    """
    from scolarite.models import Semestre

    numeros = dict(Semestre.objects.values_list('id', 'numero'))
    placements, non_places, warnings = [], [], []
    reste = budget
    for parite, cle in ((1, 'impairs'), (0, 'pairs')):
        selection = [b for b in besoins if numeros.get(b.semestre_id, 0) % 2 == parite
                     and numeros.get(b.semestre_id) is not None]
        if not selection:
            continue
        resultat = _generer_occurrences_par_semaine(
            annee_id=annee_id, groupe_id=groupe_id,
            semaines=calendrier[cle], besoins=selection,
            occupations=occupations + [
                {'enseignant_id': p.enseignant_id, 'groupe_id': p.groupe_id,
                 'salle_id': p.salle_id, 'jour': p.jour,
                 'heure_debut': p.heure_debut, 'heure_fin': p.heure_fin,
                 'semaine_debut': p.semaine_debut, 'semaine_fin': p.semaine_fin}
                for p in placements
            ], creneaux=creneaux, budget=reste, politique=politique,
        )
        placements.extend(resultat.placements)
        non_places.extend(resultat.non_places)
        warnings.extend(resultat.warnings)
        reste = max(0, reste - resultat.metrics['creneaux_explores'])
    inconnus = [b for b in besoins if numeros.get(b.semestre_id) is None]
    non_places.extend(G.BesoinNonPlace(b, 'Semestre non identifiable.') for b in inconnus)
    attendues = sum(b.nb_seances for b in besoins)
    placees = len(placements)
    statut = (G.GENERATION_OK if placees == attendues and not inconnus else
              G.GENERATION_PARTIELLE if placements else G.GENERATION_IMPOSSIBLE)
    return G.GenerationResult(
        status=statut, placements=placements, non_places=non_places,
        warnings=warnings, motif_echec=None if statut == G.GENERATION_OK else
        ('SEMESTRE_NON_IDENTIFIABLE' if inconnus else 'OCCURRENCES_NON_PLACEES'),
        metrics={'seances_attendues': attendues, 'seances_placees': placees,
                 'seances_non_placees': attendues - placees,
                 'heures_attendues': round(sum(b.volume_horaire for b in besoins), 2),
                 'heures_placees': round(sum(p.besoin.duree_seance_heures for p in placements), 2),
                 'taux_couverture': round(100 * placees / attendues, 2) if attendues else 0,
                 'creneaux_explores': budget - reste,
                 'contraintes_souples': C.resume_souples(placements, politique)},
    )


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
                  inclure_maquette=True, formation_ids=None,
                  niveau_ids=None, groupe_ids=None, semestre_numeros=None,
                  inclure_samedi=True, eviter_pause_meridienne=False,
                  max_seances_par_groupe_semaine=None,
                  calendrier_previsionnel=None):
    """Génère les EDT de tous les groupes INJS d'une année académique.

    :param annee_academique_id: année cible (obligatoire).
    :param semaines: semaines académiques planifiées (défaut ``[1]``).
    :param persister: écrit les plans validés dans des EDT BROUILLON.
    :param remplacer: désactive les séances générées antérieures avant réécriture
        (idempotence d'une régénération).
    :param inclure_maquette: complète les besoins par la maquette pour les
        cohortes sans affectation pédagogique (cohortes importées).
    :param formation_ids: périmètre optionnel — restreint la génération aux
        groupes de ces formations (une campagne à périmètre « formations »
        ne doit pas générer toute l'année). ``None`` = année entière.
    :param niveau_ids: périmètre optionnel — restreint aux groupes de ces
        niveaux. ``None`` = tous les niveaux du périmètre formations.
    :param groupe_ids: périmètre optionnel — restreint à ces groupes précis.
    :param semestre_numeros: périmètre optionnel — ne planifie que les
        besoins du ou des semestres demandés (numéros globaux, ex. ``[3]``
        pour S3). Les besoins sans semestre identifiable sont écartés.
    :param inclure_samedi: faux = le canevas ne propose aucun créneau du
        samedi (les créneaux types du samedi sont retirés avant recherche).
    :param eviter_pause_meridienne: vrai = aucun créneau chevauchant
        12h00–14h00 n'est proposé au moteur.
    :param max_seances_par_groupe_semaine: quota hebdomadaire par groupe —
        les besoins sont plafonnés (ordre déterministe conservé) et les
        séances écrêtées restent comptées comme **attendues non placées**
        dans le bilan : le quota ne masque aucune séance.
    :returns: bilan structuré, par groupe et global — jamais d'exception métier.
    """
    from django.db.models import Count

    from edts.moteur.import_inscrits import effectifs_par_groupe
    from formations.referentiel_injs_l6 import formations_injs
    from scolarite.models import Groupe

    semaines = sorted({int(s) for s in (semaines or [1])})
    # B14 : budget dynamique adapté au périmètre — garantit au moins
    # 1 essai par groupe par semaine, mais s'adapte à la taille du périmètre.
    groupes_initiaux = Groupe.objects.filter(
        annee_academique_id=annee_academique_id, actif=True
    ).select_related('ref_formation', 'niveau')
    perimetre = set(formations_injs().values_list('pk', flat=True))
    groupes_filtres = [g for g in groupes_initiaux if g.ref_formation_id in perimetre]
    groupes_count = len(groupes_filtres)
    semaines_count = len(semaines)
    # Budget : 500 placements par groupe par semaine maximum, minimum 1000
    budget = max(1000, groupes_count * semaines_count * 500)
    perimetre = set(formations_injs().values_list('pk', flat=True))

    groupes = list(
        Groupe.objects.filter(annee_academique_id=annee_academique_id, actif=True)
        .select_related('ref_formation', 'parcours', 'niveau', 'vague')
        .order_by('ref_formation__intitule', 'niveau__ordre', 'nom')
    )
    groupes_injs = [g for g in groupes if g.ref_formation_id in perimetre]
    hors_perimetre = len(groupes) - len(groupes_injs)

    # Périmètre de campagne éventuel : une génération restreinte à certaines
    # formations ne touche pas les autres cohortes de l'année.
    formations_filtrees = None
    if formation_ids:
        formations_filtrees = sorted({int(f) for f in formation_ids})
        selection = set(formations_filtrees)
        groupes_injs = [g for g in groupes_injs if g.ref_formation_id in selection]

    # Périmètres fins de l'écran « Génération » (niveaux, puis groupes
    # précis) : ils bornent les groupes réellement planifiés, jamais
    # seulement l'affichage du bilan.
    niveaux_filtres = None
    if niveau_ids:
        niveaux_filtres = sorted({int(n) for n in niveau_ids})
        groupes_injs = [g for g in groupes_injs if g.niveau_id in set(niveaux_filtres)]
    groupes_filtres = None
    if groupe_ids:
        groupes_filtres = sorted({int(g) for g in groupe_ids})
        groupes_injs = [g for g in groupes_injs if g.pk in set(groupes_filtres)]
    semestres_filtres = None
    groupes_autres_semestres = set()

    if not groupes_injs:
        return {
            'status_global': ANNEE_IMPOSSIBLE,
            'motif_echec': 'AUCUN_GROUPE_INJS',
            'annee_academique_id': annee_academique_id,
            'formations_filtrees': formations_filtrees,
            'niveaux_filtres': niveaux_filtres,
            'groupes_filtres': groupes_filtres,
            'semestres_filtres': semestres_filtres,
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

    # B15 : calculer la couverture indicative seulement après constitution des
    # besoins affectations/maquette. Cette position évite de lire une variable
    # non initialisée et tient compte du sous-périmètre sélectionné.
    groupes_count = len(groupes_injs)
    total_seances_attendues_annee = sum(
        b.nb_seances
        for g in groupes_injs
        for b in besoins_par_groupe.get(g.pk, [])
    )
    seances_maximales_possibles = groupes_count * semaines_count * 30
    couverture_theorique_pct = (
        round(min(100, seances_maximales_possibles / total_seances_attendues_annee * 100), 2)
        if total_seances_attendues_annee else 100
    )
    annee_couverture_theorique = {
        'groupes_count': groupes_count,
        'semaines_count': semaines_count,
        'seances_maximales_possibles': seances_maximales_possibles,
        'total_seances_attendues_annee': total_seances_attendues_annee,
        'couverture_theorique_pct': couverture_theorique_pct,
    }

    detail_sources_maquette = detail_maquette.get('detail') or {}
    sans_volume_ids = set(detail_sources_maquette.get('groupes_sans_volume_ids') or [])
    sans_maquette_ids = set(detail_sources_maquette.get('groupes_sans_maquette_ids') or [])

    # ── 2 bis. Contraintes de périmètre demandées à l'écran ─────────────
    # Semestre ciblé : ne conserver que les besoins de ce semestre. Un
    # besoin sans semestre rattaché ne peut pas prouver qu'il appartient
    # au périmètre demandé : il est écarté, pas supposé.
    if semestre_numeros:
        from scolarite.models import Semestre

        semestres_filtres = sorted({int(n) for n in semestre_numeros})
        numero_par_semestre = dict(
            Semestre.objects.values_list('id', 'numero'))
        for gid, besoins_groupe in list(besoins_par_groupe.items()):
            filtres = [
                b for b in besoins_groupe
                if numero_par_semestre.get(b.semestre_id) in semestres_filtres
            ]
            if besoins_groupe and not filtres and all(
                numero_par_semestre.get(b.semestre_id) is not None
                for b in besoins_groupe
            ):
                groupes_autres_semestres.add(gid)
            besoins_par_groupe[gid] = filtres
        # Les groupes de l'autre semestre restent dans le bilan pour rendre
        # visible le périmètre exclu, sans devenir des anomalies du semestre.

    # Canevas proposé au moteur : samedi et pause méridienne sont des
    # retraits explicites de créneaux types, pas des préférences.
    from datetime import time as _heure

    from edts.models import CreneauTemplate

    creneaux_annee = list(CreneauTemplate.objects.order_by('jour', 'heure_debut'))
    if not inclure_samedi:
        creneaux_annee = [c for c in creneaux_annee if c.jour != 'SAMEDI']
    if eviter_pause_meridienne:
        creneaux_annee = [
            c for c in creneaux_annee
            if not (c.heure_debut < _heure(14, 0) and c.heure_fin > _heure(12, 0))
        ]

    # ── 3. Génération coordonnée, groupe par groupe ───────────────────────────
    occupations = O.occupations_persistees(
        annee_academique_id, semaines=semaines, inclure_edt_id=persister and remplacer,
    )
    cibles_remplacables = {}
    if persister and remplacer:
        from edts.models import EmploiDuTemps

        cibles_remplacables = dict(EmploiDuTemps.objects.filter(
            annee_academique_id=annee_academique_id,
            population_type='GROUPE',
            population_id__in=[g.pk for g in groupes_injs
                               if besoins_par_groupe.get(g.pk)],
            version=1,
            statut__in=O.EDT_STATUTS_ECRITURE,
        ).values_list('population_id', 'pk'))
    # Politique souple lue UNE fois pour toute l'année : tous les groupes sont
    # jugés par la même règle, même si quelqu'un modifie le réglage pendant la
    # génération. Cela évite aussi une lecture par groupe (59 pour 3 500
    # étudiants, mesuré).
    politique_souples = C.politique_souples()
    lignes = []
    for groupe in groupes_injs:
        besoins = besoins_par_groupe.get(groupe.pk, [])
        libelle = f'{groupe.ref_formation.intitule} — {groupe.niveau.code} {groupe.nom}'
        effectif = effectifs.get(groupe.pk) or groupe.capacite_max or None

        if not besoins:
            hors_semestre = groupe.pk in groupes_autres_semestres
            motif_sans_besoin = (
                MOTIF_VOLUMES_ABSENTS
                if groupe.pk in sans_volume_ids else
                MOTIF_AUCUNE_MAQUETTE
                if groupe.pk in sans_maquette_ids else MOTIF_AUCUN_BESOIN
            )
            lignes.append({
                'groupe_id': groupe.pk,
                'groupe': groupe.nom,
                'formation': groupe.ref_formation.intitule,
                'parcours': groupe.parcours.intitule if groupe.parcours else None,
                'niveau': groupe.niveau.code,
                'vague': groupe.vague.libelle if groupe.vague else None,
                'effectif': effectif,
                'statut': 'HORS_SEMESTRE' if hors_semestre else 'NON_PLANIFIE',
                'motif_echec': None if hors_semestre else motif_sans_besoin,
                'seances_attendues': 0,
                'seances_placees': 0,
                'seances_persistees': 0,
                'seances_non_placees': 0,
            })
            continue

        # Quota hebdomadaire demandé : les besoins sont plafonnés dans
        # leur ordre déterministe ; les séances écrêtées restent comptées
        # comme attendues (voir l'ajustement de la ligne de bilan).
        attendues_avant_quota = sum(b.nb_seances for b in besoins)
        besoins_quotas = besoins
        if (max_seances_par_groupe_semaine
                and attendues_avant_quota > max_seances_par_groupe_semaine):
            import dataclasses

            restant = int(max_seances_par_groupe_semaine)
            besoins_quotas = []
            for besoin in besoins:
                if restant <= 0:
                    break
                if besoin.nb_seances <= restant:
                    besoins_quotas.append(besoin)
                    restant -= besoin.nb_seances
                else:
                    besoins_quotas.append(
                        dataclasses.replace(besoin, nb_seances=restant))
                    restant = 0

        semestres_besoins = {b.semestre_id for b in besoins_quotas if b.semestre_id}
        # Les semaines ne sont attribuables à un semestre que si l'appelant
        # a explicitement ciblé CE semestre (génération manuelle). L'appel
        # automatique annuel n'a pas de calendrier S1/S2 en base et ne doit
        # jamais répartir S1 arbitrairement sur toute l'année.
        occurrences_unitaires = (len(semaines) > 1
                                 and semestres_filtres is not None
                                 and len(semestres_filtres) == 1
                                 and len(semestres_besoins) == 1
                                 and not max_seances_par_groupe_semaine)
        edt_remplace = cibles_remplacables.get(groupe.pk)
        occupations_groupe = (
            [o for o in occupations if o.get('emploi_du_temps_id') != edt_remplace]
            if edt_remplace is not None else occupations
        )
        if calendrier_previsionnel:
            resultat = _generer_calendrier_provisoire(
                annee_id=annee_academique_id, groupe_id=groupe.pk,
                besoins=besoins_quotas, calendrier=calendrier_previsionnel,
                occupations=occupations_groupe, creneaux=creneaux_annee,
                budget=budget, politique=politique_souples,
            )
        elif occurrences_unitaires:
            resultat = _generer_occurrences_par_semaine(
                annee_id=annee_academique_id, groupe_id=groupe.pk,
                semaines=semaines, besoins=besoins_quotas,
                occupations=occupations_groupe, creneaux=creneaux_annee,
                budget=budget, politique=politique_souples,
            )
        else:
            resultat = G.generate_schedule(
                annee_academique_id=annee_academique_id,
                groupe_ids=[groupe.pk],
                semaines=semaines,
                budget=budget,
                occupations_initiales=occupations_groupe,
                besoins=besoins_quotas,
                contraintes_souples=politique_souples,
                creneaux=creneaux_annee,
            )

        # Contrôle conservateur des récurrences multi-semaines. Le solveur
        # historique compte `nb_seances` sur un bloc [min,max] ; la base et le
        # QR exécutent pourtant UNE séance à chaque semaine de l'intervalle.
        # Ne jamais enregistrer ni qualifier COMPLETE un tel plan lorsque le
        # nombre d'occurrences/les heures diffèrent des besoins. Les périmètres
        # à une seule semaine conservent pour l'instant leur contrat historique.
        repartition_invalide = False
        occurrences_reelles = heures_reelles = 0
        if len(semaines) > 1 and resultat.placements:
            for place in resultat.placements:
                duree_minutes = (
                    (place.heure_fin.hour * 60 + place.heure_fin.minute)
                    - (place.heure_debut.hour * 60 + place.heure_debut.minute)
                ) % (24 * 60)
                semaines_recurrentes = place.semaine_fin - place.semaine_debut + 1
                occurrences_reelles += semaines_recurrentes
                heures_reelles += semaines_recurrentes * duree_minutes / 60
            # Un plan annuel incomplet n'a pas encore une répartition à
            # valider : conserver le vrai motif des séances non placées.
            if not (calendrier_previsionnel
                    and resultat.status != G.GENERATION_OK):
                repartition_invalide = (
                    not (occurrences_unitaires or calendrier_previsionnel)
                    or occurrences_reelles != attendues_avant_quota
                    or abs(heures_reelles - sum(b.volume_horaire for b in besoins)) > 0.01
                    or (not calendrier_previsionnel
                        and len({b.semestre_id for b in besoins if b.semestre_id}) > 1)
                    or any(s not in semaines for p in resultat.placements
                           for s in range(p.semaine_debut, p.semaine_fin + 1))
                )

        placements_salle_cadrage = [
            place for place in resultat.placements
            if place.salle is not None and place.salle.fiabilite == 'CADRAGE'
        ]
        salles_cadrage = {
            place.salle.pk: {
                'id': place.salle.pk,
                'nom': place.salle.nom,
                'type_lieu': place.salle.type_lieu,
                'capacite': place.salle.capacite,
                'fiabilite': place.salle.fiabilite,
                'source_document': place.salle.source_document,
            }
            for place in placements_salle_cadrage
        }
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
            'affectations_salle_cadrage': len(placements_salle_cadrage),
            'salles_cadrage': sorted(salles_cadrage.values(), key=lambda salle: salle['nom']),
            'heures_attendues': resultat.metrics['heures_attendues'],
            'taux_couverture': resultat.metrics['taux_couverture'],
            'conflits': len(resultat.conflits),
            # Contraintes souples : le bilan annuel doit dire ce que la
            # politique active a produit. Sans cela, activer les règles dans
            # l'admin resterait invisible là où l'INJS arbitre réellement.
            'contraintes_souples': resultat.metrics.get('contraintes_souples'),
            'penalites_souples': sum(
                1 for place in resultat.placements for p in place.penalites
                if p.code in C.CODES_SOUPLES
            ),
            'edt_id': None,
            'edt_cree': False,
        }

        if len(semaines) > 1 and resultat.placements:
            ligne['occurrences_recurrentes'] = occurrences_reelles
            ligne['heures_recurrentes'] = round(heures_reelles, 2)
            ligne['heures_prevues'] = round(sum(b.volume_horaire for b in besoins), 2)
            ligne['repartition_verifiee'] = (
                None
                if calendrier_previsionnel and resultat.status != G.GENERATION_OK
                else not repartition_invalide
            )
            if repartition_invalide:
                ligne['statut'] = G.GENERATION_PARTIELLE
                ligne['motif_echec'] = 'REPARTITION_ANNUELLE_NON_CONFORME'

        if attendues_avant_quota > ligne['seances_attendues']:
            # Le quota a écrêté des séances : elles redeviennent des
            # attendues non placées explicites (jamais masquées).
            ligne['seances_attendues'] = attendues_avant_quota
            ligne['seances_non_placees'] = (
                attendues_avant_quota - ligne['seances_placees'])
            ligne['taux_couverture'] = (
                round(ligne['seances_placees'] / attendues_avant_quota, 4)
                if attendues_avant_quota else 0)
            ligne['quota_seances_semaine'] = max_seances_par_groupe_semaine
            if ligne['statut'] == 'GENERATION_OK':
                ligne['statut'] = 'GENERATION_PARTIELLE'

        # ── 4. Persistance éventuelle (transaction par EDT) ───────────────────
        if persister and resultat.placements:
            from edts.moteur import validation as V

            if calendrier_previsionnel and resultat.status != G.GENERATION_OK:
                ligne['persistance'] = {
                    'effectuee': False, 'motif_refus': resultat.motif_echec or 'ANNEE_INCOMPLETE',
                }
                ligne['statut'] = 'NON_PERSISTE'
                ligne['motif_echec'] = ligne['persistance']['motif_refus']
            elif repartition_invalide:
                ligne['persistance'] = {
                    'effectuee': False,
                    'motif_refus': 'REPARTITION_ANNUELLE_NON_CONFORME',
                }
                ligne['statut'] = 'NON_PERSISTE'
                ligne['motif_echec'] = ligne['persistance']['motif_refus']
            else:
                rapport = V.validate_schedule(resultat.placements, resultat.non_places)
                if not rapport.valide:
                    persistance = {
                        'effectuee': False,
                        'motif_refus': 'VALIDATION_BLOQUANTE',
                        'violations': [v.as_dict() for v in rapport.violations],
                        'warnings': rapport.warnings,
                    }
                else:
                    cible = _edt_du_groupe(annee_academique_id, groupe, semaines, creer=True)
                    persistance = O._persister_si_possible(cible, resultat, remplacer=remplacer)
                    ligne['edt_id'] = cible['edt'].pk if cible['edt'] else None
                    ligne['edt_cree'] = cible['cree']
                ligne['persistance'] = persistance
                if not persistance.get('effectuee'):
                    ligne['statut'] = 'NON_PERSISTE'
                    ligne['motif_echec'] = persistance.get('motif_refus')

        ecrite = bool(ligne.get('persistance', {}).get('effectuee'))
        ligne['seances_persistees'] = ligne['seances_placees'] if ecrite else 0
        ligne['affectations_salle_cadrage_calculees'] = len(placements_salle_cadrage)
        ligne['affectations_salle_cadrage_persistees'] = (
            len(placements_salle_cadrage) if ecrite else 0
        )
        if persister:
            ligne['affectations_salle_cadrage'] = ligne['affectations_salle_cadrage_persistees']
            ligne['salles_cadrage_calculees'] = ligne['salles_cadrage']
            ligne['salles_cadrage'] = ligne['salles_cadrage'] if ecrite else []
        if not persister or ecrite:
            if ecrite and edt_remplace is not None:
                occupations = [o for o in occupations
                               if o.get('emploi_du_temps_id') != edt_remplace]
            occupations.extend({
                'enseignant_id': place.enseignant_id,
                'groupe_id': place.groupe_id,
                'salle_id': place.salle_id,
                'jour': place.jour,
                'heure_debut': place.heure_debut,
                'heure_fin': place.heure_fin,
                'semaine_debut': place.semaine_debut,
                'semaine_fin': place.semaine_fin,
            } for place in resultat.placements)
        lignes.append(ligne)

    # ── 5. Bilan honnête ──────────────────────────────────────────────────────
    # Définitions alignées sur l'affichage et sur les anomalies : un groupe
    # est « planifié » s'il a AU MOINS une séance placée, « non planifié »
    # s'il avait des séances attendues et qu'aucune n'est placée. Avant, un
    # groupe IMPOSSIBLE à 0 séance placée comptait comme « planifié » (135
    # planifiés / 0 non planifiés affichés alors que 127 groupes n'avaient
    # rien placé et que les anomalies disaient l'inverse).
    planifies = [l for l in lignes if (l['seances_placees'] or 0) > 0]
    # Un groupe sans besoin calculable appartient tout de même au périmètre :
    # l'omettre du dénominateur déclarait l'année COMPLETE à tort si les
    # autres groupes étaient planifiés.
    a_planifier = [l for l in lignes if l['statut'] != 'HORS_SEMESTRE']
    complet = [
        l for l in planifies
        if (l['seances_non_placees'] == 0 and l['conflits'] == 0
            and l['statut'] == G.GENERATION_OK
            and (not persister or l.get('persistance', {}).get('effectuee')))
    ]
    if not planifies:
        status_global = ANNEE_IMPOSSIBLE
    elif len(complet) == len(a_planifier):
        status_global = ANNEE_COMPLETE
    else:
        status_global = ANNEE_PARTIELLE

    from collections import Counter

    groupes_enregistres = [l for l in planifies
                           if l.get('persistance', {}).get('effectuee')]
    groupes_couverts = groupes_enregistres if persister else planifies
    groupes_complets_ids = {l['groupe_id'] for l in complet}
    motifs_partiels = dict(sorted(Counter(
        l['motif_echec'] or l.get('persistance', {}).get('motif_refus')
        or 'PLAN_INCOMPLET'
        for l in a_planifier if l['groupe_id'] not in groupes_complets_ids
    ).items())) if status_global == ANNEE_PARTIELLE else {}
    salles_cadrage_utilisees = {
        salle['id']: salle
        for ligne in lignes
        for salle in ligne.get('salles_cadrage', [])
    }

    # Une année IMPOSSIBLE doit toujours dire POURQUOI au niveau global : sans
    # cela l'écran afficherait « Impossible » sans motif, et l'utilisateur ne
    # saurait pas s'il manque des groupes, des besoins ou une maquette.
    motif_global = None
    detail_global = {}
    if status_global == ANNEE_PARTIELLE:
        motif_global = 'GROUPES_INCOMPLETS_OU_NON_PERSISTES'
        detail_global = {'motifs_groupes': motifs_partiels}
    if status_global == ANNEE_IMPOSSIBLE:
        if lignes and all(l['statut'] == 'HORS_SEMESTRE' for l in lignes):
            motif_global = 'AUCUN_GROUPE_DANS_SEMESTRE'
            detail_global = {
                'explication': 'Les groupes ont des besoins connus uniquement dans d’autres semestres.',
                'action_recommandee': 'Vérifiez le semestre ciblé et les maquettes des groupes.',
            }
        elif all(l['seances_attendues'] == 0 for l in lignes):
            motifs = {l['motif_echec'] for l in lignes}
            motif_global = motifs.pop() if len(motifs) == 1 else MOTIF_AUCUN_BESOIN
            detail_global = {
                'explication': (
                    'Les groupes existent mais aucun besoin horaire calculable '
                    'n’a été trouvé. Chaque groupe porte son motif précis.'
                ),
                'action_recommandee': (
                    'Vérifiez les affectations ou les maquettes actives et les '
                    'volumes CM/TD/TP des ECUE ; ne renseignez que les volumes officiels.'
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
        'formations_filtrees': formations_filtrees,
        'niveaux_filtres': niveaux_filtres,
        'groupes_filtres': groupes_filtres,
        'semestres_filtres': semestres_filtres,
        'calendrier_previsionnel': calendrier_previsionnel,
        'semaines': {'debut': min(semaines), 'fin': max(semaines)},
        'groupes': lignes,
        'totaux': {
            'nb_groupes': len(lignes),
            'nb_groupes_planifies': len(groupes_couverts),
            'nb_groupes_planifies_calcules': len(planifies),
            'nb_groupes_complets': len(complet),
            'nb_groupes_non_planifies': len(a_planifier) - len(groupes_couverts),
            'etudiants_total': sum(l['effectif'] or 0 for l in lignes),
            'etudiants_couverts': sum(l['effectif'] or 0 for l in groupes_couverts),
            'etudiants_couverts_calcules': sum(l['effectif'] or 0 for l in planifies),
            'seances_attendues': sum(l['seances_attendues'] for l in lignes),
            'seances_placees': sum(
                l['seances_persistees'] if persister else l['seances_placees']
                for l in lignes
            ),
            'seances_calculees': sum(l['seances_placees'] for l in lignes),
            'seances_persistees': sum(l['seances_persistees'] for l in lignes),
            'seances_non_placees': sum(l['seances_attendues'] for l in lignes) - sum(
                l['seances_persistees'] if persister else l['seances_placees']
                for l in lignes
            ),
            'conflits': sum(l.get('conflits', 0) for l in lignes),
            'affectations_salle_cadrage': sum(
                l.get('affectations_salle_cadrage', 0) for l in lignes
            ),
            'affectations_salle_cadrage_calculees': sum(
                l.get('affectations_salle_cadrage_calculees', 0) for l in lignes
            ),
            'affectations_salle_cadrage_persistees': sum(
                l.get('affectations_salle_cadrage_persistees', 0) for l in lignes
            ),
            'salles_cadrage_utilisees': sorted(
                salles_cadrage_utilisees.values(), key=lambda salle: salle['nom']
            ),
            'heures_attendues': round(sum(l.get('heures_attendues', 0) for l in lignes), 2),
            'edts_persistes': len(groupes_enregistres),
            'groupes_hors_perimetre': hors_perimetre,
            'contraintes_souples': {
                'active': any((l.get('contraintes_souples') or {}).get('active') for l in lignes),
                'trous': sum((l.get('contraintes_souples') or {}).get('trous', 0) for l in lignes),
                'series_trop_longues': sum((l.get('contraintes_souples') or {}).get('series_trop_longues', 0) for l in lignes),
                'journees_surchargees': sum((l.get('contraintes_souples') or {}).get('journees_surchargees', 0) for l in lignes),
                'penalites': sum(l.get('penalites_souples', 0) for l in lignes),
            },
            'couverture_theorique': annee_couverture_theorique,
        },
        'sources': {
            'nb_groupes': len(lignes),
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
