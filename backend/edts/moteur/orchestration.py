"""LOT 3 — Génération COORDONNÉE des emplois du temps des 8 filières INJS.

Problème traité : le moteur ``generate_schedule`` place les besoins d'UN
périmètre dans un espace d'occupations qui ne voit que le run courant. Générer
successivement les EDT des 8 filières de l'INJS d'Abidjan — où les
enseignants, les salles et parfois les groupes sont partagés entre
formations — laissait donc possible des chevauchements C1/C2/C3 entre EDT,
seulement détectés a posteriori (``conflits_inter_edt``, LOT 1).

Principes du LOT 3 (aucun nouveau modèle, aucun solveur parallèle) :

* **coordination centrale séquentielle** — les formations sont traitées dans
  un ordre déterministe (identifiant croissant) et chaque run reçoit l'état
  d'occupation global : placements des runs antérieurs de la même opération +
  séances persistées des autres EDT de l'année ;
* **périmètre dérivé des données** — formations portant des affectations
  pédagogiques planifiables rattachées au référentiel INJS (L6). Jamais de
  liste envoyée par le client ;
* **réutilisation intégrale du moteur existant** — besoins, contraintes
  C1→C10, backtracking, persistance, validation et contrôle inter-EDT LOT 1 ;
* **bilan honnête** — une opération dont un seul EDT est incomplet, non
  persisté ou en conflit n'est JAMAIS présentée comme pleinement réussie ;
* **transaction par EDT** — chaque persistance est atomique ; un échec au
  milieu de l'opération n'écrit rien pour l'EDT concerné, sans masquer les
  persistance des autres (mais il dégrade le statut global).

Ce module orchestre uniquement : il ne publie jamais (la publication reste
``publier_emploi_du_temps`` et son contrôle de complétude du LOT 2) et
n'invente aucune donnée pédagogique.
"""

from django.db import transaction

from edts.moteur import generation as G
from edts.moteur.besoins import STATUTS_PLANIFIABLES
from formations.referentiel_injs_l6 import formations_injs

# ── Statuts globaux de l'opération coordonnée ─────────────────────────────────
COORDONNEE_OK = 'COORDONNEE_OK'
COORDONNEE_PARTIELLE = 'COORDONNEE_PARTIELLE'
COORDONNEE_CONFLITS = 'COORDONNEE_CONFLITS'
COORDONNEE_IMPOSSIBLE = 'COORDONNEE_IMPOSSIBLE'

#: Motifs d'échec global explicites (affichables tels quels).
MOTIF_AUCUNE_FORMATION = 'AUCUNE_FORMATION_INJS_PLANIFIABLE'
MOTIF_AUCUNE_PLACEMENT = 'AUCUN_EDT_PLACE'
MOTIF_CONFLITS_INTER_EDT = 'CONFLITS_INTER_EDT_NON_RESOLUS'
MOTIF_EDT_STATUT = 'EDT_STATUT_NON_MODIFIABLE'

#: Statuts d'EDT qui ouvrent l'écriture de séances — règle déjà appliquée par
#: ``api_lmd.generate_api`` (aucun écrasement d'un EDT validé ou publié).
EDT_STATUTS_ECRITURE = ('BROUILLON', 'EN_VALIDATION')


def formations_a_planifier(annee_academique_id):
    """Formations INJS portant des affectations planifiables — triées par id.

    Le périmètre de l'opération est **dérivé des données validées** de
    l'application : affectations pédagogiques ``VALIDEE``/``PLANIFIEE``
    rattachées à une formation qualifiée ``INJS`` au référentiel L6. Les
    cycles legacy (CPFAE, Sygepcpfae) n'entrent jamais dans l'opération.
    """
    from django.db.models import Count

    from scolarite.models import AffectationPedagogique

    lignes = (
        AffectationPedagogique.objects
        .filter(annee_academique_id=annee_academique_id,
                statut__in=STATUTS_PLANIFIABLES,
                ref_formation__in=formations_injs())
        .values('ref_formation_id')
        .annotate(nb_affectations=Count('pk'))
        .order_by('ref_formation_id')
    )
    return [ligne['ref_formation_id'] for ligne in lignes]


def _occupation_depuis_affectation(aff):
    """Dict d'occupation (format ``contraintes.conflit_ressource``).

    Enseignant : FK métier ``formateur_id`` — source de vérité identique à
    ``edts.services.types_conflit``. Retourne ``None`` sans créneau type.
    """
    creneau = aff.creneau_template
    if creneau is None:
        return None
    return {
        'enseignant_id': aff.formateur_id,
        'groupe_id': aff.groupe_id,
        'salle_id': aff.salle_id,
        'jour': creneau.jour,
        'heure_debut': creneau.heure_debut,
        'heure_fin': creneau.heure_fin,
    }



def occupations_persistees(annee_academique_id, *, semaines, exclure_edt_ids=()):
    """Occupations des séances déjà persistées par d'autres EDT de l'année.

    Seules les séances dont la fenêtre ``[semaine_debut, semaine_fin]``
    chevauche la période planifiée sont retenues : ``conflit_ressource``
    compare des créneaux hebdomadaires sans notion de période (même règle
    que ``edts.services.conflits_inter_edt``). Lecture seule.
    """
    from edts.models import AffectationCreneau
    from edts.services import semaines_en_chevauchement

    debut, fin = min(semaines), max(semaines)
    occupations = []
    queryset = (
        AffectationCreneau.objects
        .filter(actif=True,
                emploi_du_temps__annee_academique_id=annee_academique_id)
        .exclude(emploi_du_temps_id__in=list(exclure_edt_ids))
        .select_related('creneau_template')
    )
    for aff in queryset:
        if not semaines_en_chevauchement(aff.semaine_debut, aff.semaine_fin,
                                         debut, fin):
            continue
        occupation = _occupation_depuis_affectation(aff)
        if occupation is not None:
            occupations.append(occupation)
    return occupations


def _resoudre_edt_cible(annee_academique_id, ref_formation_id, semaines, *, creer):
    """EDT cible (population FORMATION, version 1) — créé en BROUILLON si besoin.

    Jamais d'écrasement : un EDT existant quel qu'il soit est tel quel
    retourné ; c'est son *statut* qui décidera (``EDT_STATUTS_ECRITURE``)
    si l'opération peut y écrire. Aucun EDT publié ou validé n'est modifié.
    """
    from edts.models import EmploiDuTemps

    existant = EmploiDuTemps.objects.filter(
        annee_academique_id=annee_academique_id,
        population_type='FORMATION',
        population_id=ref_formation_id,
        version=1,
    ).order_by('pk').first()
    if existant is not None:
        return {'edt': existant, 'cree': False}
    if not creer:
        return {'edt': None, 'cree': False}

    from formations.models import RefFormation

    formation = RefFormation.objects.filter(pk=ref_formation_id).first()
    libelle = formation.intitule if formation else f'Formation #{ref_formation_id}'
    edt, _cree = EmploiDuTemps.objects.get_or_create(
        annee_academique_id=annee_academique_id,
        population_type='FORMATION',
        population_id=ref_formation_id,
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



def _persister_si_possible(cible, resultat, *, remplacer):
    """Matérialise le plan d'un EDT dans son EDT cible — transaction par EDT.

    Refus explicites, **jamais d'écriture partielle** pour l'EDT concerné :

    * ``EDT_CREE_IMPOSSIBLE``   — aucune EDT cible (mode prévisualisation) ;
    * ``EDT_STATUT_NON_MODIFIABLE`` — statut n'ouvrant pas l'écriture
      (VALIDE, PUBLIE…) : l'EDT existant n'est jamais modifié ;
    * ``PLAN_VIDE``             — aucun placement : rien à écrire ;
    * ``VALIDATION_BLOQUANTE``  — le validateur C1→C10 refuse le plan.

    Un refus n'efface pas les persistance des autres EDT de l'opération, mais
    il dégrade le statut global (jamais d'opération présentée comme réussie
    alors qu'un EDT n'a pas été écrit).
    """
    from edts.moteur import publication as P
    from edts.moteur import validation as V

    edt = cible['edt']
    if edt is None:
        return {'effectuee': False, 'motif_refus': 'EDT_CREE_IMPOSSIBLE'}
    if edt.statut not in EDT_STATUTS_ECRITURE:
        return {'effectuee': False, 'motif_refus': MOTIF_EDT_STATUT,
                'statut': edt.statut}
    if not resultat.placements:
        return {'effectuee': False, 'motif_refus': 'PLAN_VIDE'}

    rapport = V.validate_schedule(resultat.placements, resultat.non_places)
    if not rapport.valide:
        return {'effectuee': False, 'motif_refus': 'VALIDATION_BLOQUANTE',
                'violations': [v.as_dict() for v in rapport.violations],
                'warnings': rapport.warnings}

    with transaction.atomic():
        nb = P.persister_plan(edt, resultat.placements, remplacer=remplacer)
    return {'effectuee': True, 'nb_seances': nb, 'version': edt.version,
            'edt_cree': cible['cree']}


def generer_coordonne(annee_academique_id, *, semaines=None, persister=False,
                      remplacer=True, budget=G.BUDGET_PLACEMENTS_DEFAUT):
    """Génère coordonnément les EDT de TOUTES les formations INJS de l'année.

    Orchestration séquentielle déterministe (formations triées par
    identifiant) : chaque run reçoit l'état d'occupation global — placements
    des runs antérieurs de la même opération + séances persistées des autres
    EDT de l'année (hors EDT cibles que le remplacement va désactiver) — de
    sorte qu'aucun placement d'un EDT ne rende possible un conflit C1/C2/C3
    dans un EDT suivant de la même opération.

    Si ``persister=True``, chaque plan validé est matérialisé dans l'EDT de sa
    formation (créé en BROUILLON, version 1, si absent) via
    ``publication.persister_plan`` — transaction par EDT. ``remplacer=True``
    désactive les séances générées antérieures de l'EDT avant ré-écriture :
    relancer l'opération ne duplique jamais de séances (idempotence).

    Le bilan retourne, par EDT : besoins attendus, séances placées et
    restantes, motifs ; et globalement : statut, conflits inter-EDT (LOT 1,
    lecture seule) et données inconnues. **Une opération dont un EDT est
    incomplet, non persisté ou en conflit n'est jamais présentée comme
    pleinement réussie.** Aucune publication n'est effectuée ici.
    """
    from edts.services import conflits_inter_edt

    if not semaines:
        semaines = [1]
    semaines = sorted({int(s) for s in semaines})
    formations = formations_a_planifier(annee_academique_id)

    if not formations:
        return {
            'status_global': COORDONNEE_IMPOSSIBLE,
            'motif_echec': MOTIF_AUCUNE_FORMATION,
            'annee_academique_id': annee_academique_id,
            'semaines': {'debut': min(semaines), 'fin': max(semaines)},
            'nb_formations': 0,
            'edts': [],
            'conflits': {'statut': 'NON_APPLIQUE', 'conflits': [], 'detail': {}},
            'totaux': {},
            'persistence_demandee': persister,
            'detail': {
                'explication': (
                    'Aucune formation INJS validée ne porte d’affectation '
                    'pédagogique planifiable pour cette année : rien à générer.'
                ),
                'action_recommandee': (
                    'Valider les affectations pédagogiques des filières INJS '
                    '(Maquette → UE → ECUE → affectation) avant la génération '
                    'coordonnée.'
                ),
            },
        }

    # 1. Résolution des EDT cibles (création seulement en mode persistance).
    cibles = {
        fid: _resoudre_edt_cible(annee_academique_id, fid, semaines,
                                 creer=persister)
        for fid in formations
    }
    # 2. État d'occupation de départ : séances persistées des autres EDT.
    #    En persistance avec remplacement, les séances des EDT cibles seront
    #    désactivées par `persister_plan` : elles ne freinent pas la
    #    génération. Sans persistance, elles restent actives et comptent.
    if persister and remplacer:
        a_exclure = [c['edt'].pk for c in cibles.values()
                     if c['edt'] is not None]
    else:
        a_exclure = []
    occupations = occupations_persistees(
        annee_academique_id, semaines=semaines, exclure_edt_ids=a_exclure)

    # 3. Runs coordonnés, dans l'ordre déterministe des formations.
    resultats = []
    edt_ids_persistes = []
    for fid in formations:
        resultat = G.generate_schedule(
            annee_academique_id=annee_academique_id,
            ref_formation_id=fid,
            semaines=semaines,
            budget=budget,
            occupations_initiales=occupations,
        )
        # Coordination : les placements de ce run pèsent sur les suivants.
        for place in resultat.placements:
            occupations.append({
                'enseignant_id': place.enseignant_id,
                'groupe_id': place.groupe_id,
                'salle_id': place.salle_id,
                'jour': place.jour,
                'heure_debut': place.heure_debut,
                'heure_fin': place.heure_fin,
            })

        cible = cibles[fid]
        entree = {
            'ref_formation_id': fid,
            'edt_id': cible['edt'].pk if cible['edt'] else None,
            'status': resultat.status,
            'finalite': resultat.finalite,
            'motif_echec': resultat.motif_echec,
            'metrics': resultat.metrics,
            'warnings': resultat.warnings,
            'detail': resultat.detail,
            'seances': [p.as_dict() for p in resultat.placements],
            'non_placees': [n.as_dict() for n in resultat.non_places],
            'persistence': None,
        }
        if persister:
            entree['persistence'] = _persister_si_possible(
                cible, resultat, remplacer=remplacer)
            if entree['persistence']['effectuee']:
                edt_ids_persistes.append(cible['edt'].pk)
        resultats.append(entree)

    # 4. Contrôle inter-EDT final (LOT 1, lecture seule) sur les EDT
    #    effectivement persistés par cette opération.
    if edt_ids_persistes:
        conflits_rapport = conflits_inter_edt(edt_ids_persistes)
    else:
        conflits_rapport = {'statut': 'NON_APPLIQUE', 'conflits': [], 'detail': {}}

    # 5. Statut global honnête. Le succès intégral exige : des plans complets,
    #    une persistance effective pour chaque EDT (si demandée) et l'absence
    #    de conflit inter-EDT. Un seul échec dégrade l'opération entière.
    totaux = {
        'seances_attendues': sum(e['metrics'].get('seances_attendues', 0)
                                 for e in resultats),
        'seances_placees': sum(e['metrics'].get('seances_placees', 0)
                               for e in resultats),
        'seances_non_placees': sum(e['metrics'].get('seances_non_placees', 0)
                                   for e in resultats),
        'nb_edt': len(resultats),
        'nb_edt_complets': sum(1 for e in resultats
                               if e['status'] == G.GENERATION_OK),
        'nb_edt_incomplets': sum(1 for e in resultats
                                 if e['status'] != G.GENERATION_OK),
        'nb_edt_persistes': len(edt_ids_persistes),
    }
    if totaux['seances_attendues']:
        totaux['taux_couverture'] = round(
            100 * totaux['seances_placees'] / totaux['seances_attendues'], 2)

    persistance_complete = (
        all(e['persistence'] is not None and e['persistence'].get('effectuee')
            for e in resultats)
        if persister else None)

    if conflits_rapport['statut'] == 'CONFLITS':
        status_global = COORDONNEE_CONFLITS
        motif = MOTIF_CONFLITS_INTER_EDT
    elif (totaux['nb_edt_complets'] == len(resultats)
            and persistance_complete in (True, None)):
        status_global = COORDONNEE_OK
        motif = None
    elif totaux['seances_placees'] > 0 or any(
            e['status'] == G.GENERATION_OK for e in resultats):
        status_global = COORDONNEE_PARTIELLE
        motif = MOTIF_AUCUNE_PLACEMENT if not totaux['seances_placees'] else None
    else:
        status_global = COORDONNEE_IMPOSSIBLE
        motif = MOTIF_AUCUNE_PLACEMENT

    return {
        'status_global': status_global,
        'motif_echec': motif,
        'annee_academique_id': annee_academique_id,
        'semaines': {'debut': min(semaines), 'fin': max(semaines)},
        'nb_formations': len(formations),
        'edts': resultats,
        'conflits': conflits_rapport,
        'totaux': totaux,
        'persistence_demandee': persister,
    }
