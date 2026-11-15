"""Indicateurs de pilotage d'un emploi du temps (PHASE 5 / chantier 2 — §10).

Principes
---------
**Aucune deuxième source de vérité.** Le volume attendu n'est pas recalculé
ici : il vient de ``besoins.calculate_teaching_needs``, qui est déjà la
référence du moteur (``nb_seances = max(1, round(volume / duree))``). Un
indicateur qui produirait un chiffre différent du moteur serait un mensonge
de pilotage.

**Aucune écriture.** Ce module lit. Il ne déclenche notamment pas
``services.detecter_conflits``, qui crée et réactive des lignes
``ConflitCreneau`` : les conflits sont comptés depuis l'existant.

**Aucune exception avalée.** Un périmètre vide, une salle sans capacité ou un
effectif inconnu produisent une valeur explicite (``0`` ou ``None``), jamais
une erreur, jamais un taux inventé.

**Volume.** Les durées de créneaux sont chargées en une seule requête (le
canevas est petit : 56 lignes au maximum) puis jointes en mémoire ; les
séances sont chargées en ``values_list``. Deux requêtes par famille, quelle
que soit la taille de l'EDT — pas de requête par ligne.

Familles d'indicateurs
----------------------
1. couverture      — placé / attendu, en séances et en heures ;
2. occupation      — salles : heures occupées, taux, remplissage ;
3. charge          — enseignants : heures, dispersion ;
4. répartition     — par jour, niveau, semestre, UE ;
5. conflits        — comptés depuis ``ConflitCreneau`` ;
6. assiduité       — pointages rattachés aux séances (chaînage du chantier 1) ;
7. mutualisation   — séances partagées, effectifs cumulés.
"""

from collections import defaultdict

from django.db.models import Count

from edts.models import AffectationCreneau, ConflitCreneau, CreneauTemplate
from edts.moteur.besoins import calculate_teaching_needs


# ── Utilitaires ────────────────────────────────────────────────────────────


def _taux(numerateur, denominateur):
    """Pourcentage arrondi, ou ``None`` si le dénominateur est inconnu.

    Un taux sur une base inconnue est ``None``, pas ``0`` : afficher « 0 % »
    pour une donnée absente ferait croire à une contre-performance réelle.
    """
    if not denominateur:
        return None
    return round(100.0 * numerateur / denominateur, 2)


def _durees_par_creneau():
    """Durée (en heures) de chaque créneau du canevas — UNE requête.

    Le canevas est petit et stable : le charger entièrement coûte moins qu'une
    jointure par ligne de séance.
    """
    return {
        c.pk: (c.duree_heures or 0.0)
        for c in CreneauTemplate.objects.all().only('pk', 'duree_prevue_minutes')
    }


def _seances_brutes(qs):
    """Séances sous forme de tuples — une requête, sans instanciation d'objet.

    Champs ramenés : créneau, salle, capacité de la salle, effectif du
    groupe porteur, enseignant, UE, niveau, semestre, semaine, statut, actif.
    """
    return list(qs.values_list(
        'pk', 'creneau_template_id', 'creneau_template__jour', 'salle_id',
        'salle__nom', 'salle__capacite', 'groupe__capacite_max',
        'enseignant_nom', 'ue_id', 'ue__intitule',
        'affectation_pedagogique__niveau__code', 'semestre__libelle',
        'semaine_debut', 'statut', 'actif',
    ))


# ── 1. Couverture ──────────────────────────────────────────────────────────


def _filtres_besoins(edt):
    """Traduit la population d'un EDT en filtres de besoins.

    Sans cela, les besoins seraient calculés sur TOUTE l'année alors que l'EDT
    ne couvre qu'un groupe : le taux de couverture affiché serait faux
    (mesuré : 0,08 % pour un EDT réellement complet), ce qui est pire que pas
    d'indicateur du tout.

    L'EDT 1 est de population ENSEIGNANT : les besoins du moteur ne se filtrent
    pas par enseignant, le périmètre reste donc annuel — et le fait est signalé
    pour que le taux ne soit pas pris pour une contre-performance.
    """
    if edt is None:
        return {}, False
    if edt.population_type == 'GROUPE':
        return {'groupe_ids': [edt.population_id]}, True
    if edt.population_type == 'FORMATION':
        return {'ref_formation_id': edt.population_id}, True
    return {}, False


def couverture(qs, *, edt=None, annee_academique_id=None,
               duree_seance_heures=None):
    """Séances et heures placées rapportées au volume attendu.

    L'attendu vient du moteur (``calculate_teaching_needs``) : même formule,
    mêmes chiffres. Les non-placés sont déduits de l'écart, et le motif
    d'échec du moteur est relayé tel quel — un blocage reste nommé.
    """
    durees = _durees_par_creneau()

    heures_placees = 0.0
    actives = 0
    annulees = 0
    par_statut = defaultdict(int)
    for row in qs.values_list('creneau_template_id', 'statut', 'actif'):
        creneau_id, statut, actif = row
        if actif:
            actives += 1
            heures_placees += durees.get(creneau_id) or 0.0
        else:
            annulees += 1
        par_statut[statut] += 1

    filtres, perimetre_restreint = _filtres_besoins(edt)
    besoins = calculate_teaching_needs(
        annee_academique_id=annee_academique_id,
        duree_seance_heures=duree_seance_heures,
        **filtres,
    )

    seances_attendues = besoins.total_seances_attendues
    heures_attendues = besoins.total_heures_attendues

    return {
        'seances_placees': actives,
        'seances_annulees': annulees,
        'seances_attendues': seances_attendues,
        'seances_manquantes': max(0, seances_attendues - actives),
        'heures_placees': round(heures_placees, 2),
        'heures_attendues': heures_attendues,
        'heures_manquantes': round(max(0.0, heures_attendues - heures_placees), 2),
        'taux_couverture_seances': _taux(actives, seances_attendues),
        'taux_couverture_heures': _taux(heures_placees, heures_attendues),
        'par_statut': dict(par_statut),
        # Le motif du moteur est relayé : « 0 % » sans explication ne pilote rien.
        'motif_echec': besoins.motif_echec,
        'complet': bool(seances_attendues) and actives >= seances_attendues,
        # Sans ce drapeau, un EDT dont la population n'est pas filtrable par
        # le moteur (population ENSEIGNANT) afficherait un taux calculé sur
        # l'année entière : le chiffre serait juste, l'interprétation fausse.
        'perimetre_besoins': (
            'EDT' if perimetre_restreint
            else 'ANNEE' if edt is not None else 'GLOBAL'
        ),
    }


# ── 2. Occupation des salles ───────────────────────────────────────────────


def occupation_salles(qs, durees=None):
    """Heures occupées, taux d'occupation et remplissage par salle.

    * **occupation** = heures utilisées / heures ouvrables du canevas ;
    * **remplissage** = effectif / capacité — il répond à « cette salle est-elle
      trop grande pour ce qu'on y met ? ».

    Une salle sans capacité connue donne un remplissage ``None`` : la capacité
    NULL de la contrainte C4 n'est jamais traitée comme « suffisante ».
    """
    if durees is None:
        durees = _durees_par_creneau()

    # Dénominateur : ce que le canevas permet d'occuper au total.
    capacite_heures_canevas = round(sum(durees.values()), 2)

    heures = defaultdict(float)
    seances = defaultdict(int)
    noms = {}
    capacites = {}
    remplissages = defaultdict(list)

    for (pk, creneau_id, jour, salle_id, salle_nom, salle_capacite,
         groupe_capacite, _ens, _ue, _ue_nom, _niv, _sem, _semaine,
         _statut, actif) in _seances_brutes(qs):
        if not actif or not salle_id:
            continue
        duree = durees.get(creneau_id) or 0.0
        heures[salle_id] += duree
        seances[salle_id] += 1
        noms[salle_id] = salle_nom
        capacites[salle_id] = salle_capacite
        # Remplissage : effectif réel du groupe porteur, à défaut sa capacité.
        effectif = groupe_capacite
        if effectif and salle_capacite:
            remplissages[salle_id].append(effectif / salle_capacite)

    lignes = []
    for salle_id in sorted(heures, key=lambda s: -heures[s]):
        taux_rempl = remplissages.get(salle_id) or []
        lignes.append({
            'salle_id': salle_id,
            'salle': noms.get(salle_id),
            'capacite': capacites.get(salle_id),
            'seances': seances[salle_id],
            'heures_occupees': round(heures[salle_id], 2),
            'taux_occupation': _taux(heures[salle_id], capacite_heures_canevas),
            'taux_remplissage_moyen': (
                round(100.0 * sum(taux_rempl) / len(taux_rempl), 2)
                if taux_rempl else None
            ),
        })

    total_heures = round(sum(heures.values()), 2)
    return {
        'capacite_heures_canevas': capacite_heures_canevas,
        'heures_occupees': total_heures,
        'taux_occupation_global': _taux(total_heures, capacite_heures_canevas),
        'nb_salles_utilisees': len(heures),
        'salles': lignes,
    }


# ── 3. Charge des enseignants ──────────────────────────────────────────────


def charge_enseignants(qs, durees=None):
    """Heures et dispersion par enseignant.

    La dispersion (min / max / moyenne) est l'indicateur utile : deux
    enseignants à 18 h et 4 h ont la même moyenne qu'à 11 h chacun, mais ne
    sont pas dans la même situation. L'écart est donc affiché, pas seulement
    la moyenne.
    """
    if durees is None:
        durees = _durees_par_creneau()

    heures = defaultdict(float)
    seances = defaultdict(int)
    groupes = defaultdict(set)
    ue = defaultdict(set)

    for (pk, creneau_id, jour, salle_id, salle_nom, salle_capacite,
         groupe_capacite, enseignant, ue_id, ue_intitule, niveau, semestre,
         semaine, statut, actif) in _seances_brutes(qs.filter(actif=True)):
        if not enseignant:
            continue
        duree = durees.get(creneau_id) or 0.0
        heures[enseignant] += duree
        seances[enseignant] += 1
        if ue_id:
            ue[enseignant].add(ue_id)

    # Les groupes ne sont pas dans values_list (M2M) : une requête groupée.
    if heures:
        noms = set(heures)
        for row in (qs.filter(actif=True, enseignant_nom__in=noms)
                    .values_list('enseignant_nom', 'groupe_id')):
            if row[0] and row[1]:
                groupes[row[0]].add(row[1])

    lignes = []
    for nom in sorted(heures, key=lambda n: -heures[n]):
        lignes.append({
            'enseignant': nom,
            'heures': round(heures[nom], 2),
            'seances': seances[nom],
            'nb_groupes': len(groupes.get(nom, ())),
            'nb_ue': len(ue.get(nom, ())),
        })

    valeurs = [l['heures'] for l in lignes]
    if valeurs:
        moyenne = round(sum(valeurs) / len(valeurs), 2)
        dispersion = {
            'nb_enseignants': len(valeurs),
            'heures_min': round(min(valeurs), 2),
            'heures_max': round(max(valeurs), 2),
            'heures_moyenne': moyenne,
            'ecart_min_max': round(max(valeurs) - min(valeurs), 2),
        }
    else:
        dispersion = {
            'nb_enseignants': 0, 'heures_min': 0, 'heures_max': 0,
            'heures_moyenne': 0, 'ecart_min_max': 0,
        }

    return {'enseignants': lignes, 'dispersion': dispersion}


# ── 4. Répartition ─────────────────────────────────────────────────────────


def repartition(qs, durees=None):
    """Séances et heures par jour, niveau, semestre, UE et semaine.

    Sert à répondre aux questions d'équilibre : « le vendredi est-il vide ? »,
    « tel niveau est-il sous-doté ? ».
    """
    if durees is None:
        durees = _durees_par_creneau()

    def _cumul():
        return {'seances': 0, 'heures': 0.0}

    par_jour = defaultdict(_cumul)
    par_niveau = defaultdict(_cumul)
    par_semestre = defaultdict(_cumul)
    par_ue = defaultdict(_cumul)
    par_semaine = defaultdict(_cumul)

    for (pk, creneau_id, jour, salle_id, salle_nom, salle_capacite,
         groupe_capacite, enseignant, ue_id, ue_intitule, niveau, semestre,
         semaine, statut, actif) in _seances_brutes(qs.filter(actif=True)):
        duree = durees.get(creneau_id) or 0.0
        for cle, cible in (
            ((jour or 'NON RENSEIGNE'), par_jour),
            ((niveau or 'NON RENSEIGNE'), par_niveau),
            ((semestre or 'NON RENSEIGNE'), par_semestre),
            ((ue_intitule or 'SANS UE'), par_ue),
            ((semaine or 0), par_semaine),
        ):
            cible[cle]['seances'] += 1
            cible[cle]['heures'] += duree

    def _clore(cumul, tri_seances=True):
        items = sorted(
            cumul.items(),
            key=lambda kv: (-kv[1]['seances'], str(kv[0])),
        )
        return [
            {'cle': k, 'seances': v['seances'], 'heures': round(v['heures'], 2)}
            for k, v in items
        ]

    return {
        'par_jour': _clore(par_jour),
        'par_niveau': _clore(par_niveau),
        'par_semestre': _clore(par_semestre),
        'par_ue': _clore(par_ue),
        'par_semaine': _clore(par_semaine),
    }


# ── 5. Conflits ────────────────────────────────────────────────────────────


def conflits(edt):
    """Conflits **déjà détectés**, comptés par type et par gravité.

    Aucune détection n'est déclenchée ici : ``services.detecter_conflits``
    ÉCRIT en base (création, réactivation, clôture). Un tableau de bord ne
    doit jamais modifier ce qu'il mesure. Si aucun calcul n'a encore été
    lancé, le fait est dit explicitement plutôt que masqué par un zéro.
    """
    actifs = ConflitCreneau.objects.filter(emploi_du_temps=edt, actif=True)
    par_type = dict(actifs.values_list('type_conflit')
                    .annotate(n=Count('id')).values_list('type_conflit', 'n'))

    # Le code ne définit aucune échelle de gravité : elle n'est donc PAS
    # inventée ici. Seule une distinction factuelle est faite, entre ce que
    # la détection automatique a trouvé et ce qu'un agent a signalé à la main
    # — les deux n'appellent pas le même traitement.
    signales = par_type.get('MANUEL', 0)
    detectes = sum(nb for t, nb in par_type.items() if t != 'MANUEL')

    return {
        'nb_conflits': sum(par_type.values()),
        'nb_detectes': detectes,
        'nb_signales': signales,
        'par_type': par_type,
        # Distinguer « aucun conflit » de « jamais calculé » : sans cette clé,
        # un zéro affiché avant la première détection laisserait croire à un
        # EDT vérifié alors qu'il n'a jamais été contrôlé.
        'deja_calcule': ConflitCreneau.objects.filter(
            emploi_du_temps=edt).exists(),
    }


# ── 6. Assiduité ───────────────────────────────────────────────────────────


def assiduite(qs):
    """Présences rattachées aux séances — chaînage du chantier 1.

    Le lien passe par ``Pointage.seance_edt``. Une séance mutualisée totalise
    naturellement les présences de tous ses groupes : c'est le bénéfice
    direct de l'absence de duplication.
    """
    from presences.models import Pointage

    seance_ids = list(qs.values_list('pk', flat=True))
    if not seance_ids:
        return {
            'nb_pointages': 0, 'nb_seances_suivies': 0,
            'nb_seances_sans_pointage': 0, 'taux_presence': None,
            'par_statut': {},
        }

    par_statut = dict(
        Pointage.objects.filter(seance_edt_id__in=seance_ids)
        .values_list('statut').annotate(n=Count('id'))
        .values_list('statut', 'n')
    )
    suivies = (Pointage.objects.filter(seance_edt_id__in=seance_ids)
               .values_list('seance_edt_id', flat=True).distinct().count())
    total = sum(par_statut.values())

    presents = sum(
        nb for statut, nb in par_statut.items()
        if statut in ('PRESENT', 'TERMINE', 'FORCE_DFRC')
    )

    return {
        'nb_pointages': total,
        'nb_seances_suivies': suivies,
        'nb_seances_sans_pointage': len(seance_ids) - suivies,
        'taux_presence': _taux(presents, total),
        'par_statut': par_statut,
    }


# ── 7. Mutualisation ───────────────────────────────────────────────────────


def mutualisation(qs, durees=None):
    """Séances partagées entre plusieurs groupes (chantier 1).

    Une séance mutualisée économise une salle, un créneau et un enseignant :
    c'est un indicateur d'efficience, pas seulement une curiosité de modélisation.
    """
    if durees is None:
        durees = _durees_par_creneau()

    seances = list(qs.filter(actif=True).values_list('pk', 'creneau_template_id'))
    if not seances:
        return {
            'nb_seances': 0, 'nb_mutualisees': 0, 'taux_mutualisation': None,
            'nb_groupes_max': 0, 'heures_mutualisees': 0.0, 'detail': [],
        }

    ids = [pk for pk, _ in seances]
    nb_groupes = dict(
        AffectationCreneau.objects.filter(pk__in=ids)
        .annotate(n=Count('groupes_lies')).values_list('pk', 'n')
    )

    heures_mutualisees = 0.0
    detail = []
    nb_mutualisees = 0
    for pk, creneau_id in seances:
        lies = nb_groupes.get(pk, 0)
        # Le groupe porteur compte : 1 groupe lié → 2 groupes au total.
        total_groupes = lies + 1
        if lies:
            nb_mutualisees += 1
            heures_mutualisees += durees.get(creneau_id) or 0.0
        if lies:
            detail.append({
                'seance_id': pk, 'nb_groupes': total_groupes,
                'heures': round(durees.get(creneau_id) or 0.0, 2),
            })

    return {
        'nb_seances': len(seances),
        'nb_mutualisees': nb_mutualisees,
        'taux_mutualisation': _taux(nb_mutualisees, len(seances)),
        'nb_groupes_max': max((d['nb_groupes'] for d in detail), default=0),
        'heures_mutualisees': round(heures_mutualisees, 2),
        'detail': sorted(detail, key=lambda d: -d['nb_groupes'])[:20],
    }


# ── Agrégation ─────────────────────────────────────────────────────────────


def indicateurs(seances_qs, *, edt=None, annee_academique_id=None,
                duree_seance_heures=None):
    """Agrège les sept familles pour un périmètre donné."""
    durees = _durees_par_creneau()
    return {
        'couverture': couverture(
            seances_qs, edt=edt, annee_academique_id=annee_academique_id,
            duree_seance_heures=duree_seance_heures,
        ),
        'occupation_salles': occupation_salles(seances_qs, durees),
        'charge_enseignants': charge_enseignants(seances_qs, durees),
        'repartition': repartition(seances_qs, durees),
        'conflits': conflits(edt) if edt is not None else None,
        'assiduite': assiduite(seances_qs),
        'mutualisation': mutualisation(seances_qs, durees),
    }
