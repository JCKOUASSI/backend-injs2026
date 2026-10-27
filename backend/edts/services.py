"""Moteur du module GET-INJS : détection de conflits, placement contrôlé,
génération de brouillon, grille hebdomadaire.

Règles structurantes (validées par l'audit du 2026-09-15) :
- aucune dépendance à des lookups JSON non portables (`contains` est interdit
  sur SQLite) : l'appariement des conflits est fait en Python ;
- la détection est GLOBALE : un enseignant, un groupe ou une salle en
  chevauchement compte en conflit même si les affectations vivent dans des
  emplois du temps différents ;
- toute détection rafraîchit l'état des conflits enregistrés : les paires
  toujours en conflit sont maintenues/réactivées, les paires résolues sont
  clôturées automatiquement (les signalements manuels restent à la main de
  l'agent qui les a ouverts) ;
- la génération de brouillon (P06, version pragmatique) place les
  affectations pédagogiques validées du socle dans le canevas de créneaux
  types, en respectant les disponibilités et en évitant les conflits ;
  elle produit un BROUILLON, jamais un EDT publié (conformément à ADR-003).
"""

from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from .models import AffectationCreneau, ConflitCreneau


# ---------------------------------------------------------------------------
# Primitives pures (testables sans base)
# ---------------------------------------------------------------------------

def semaines_en_chevauchement(a_debut, a_fin, b_debut, b_fin):
    """Vrai si les intervalles de semaines [a_debut, a_fin] et [b_debut, b_fin] se recouvrent."""
    if None in (a_debut, a_fin, b_debut, b_fin):
        return False
    return not (a_fin < b_debut or b_fin < a_debut)


def horaires_en_chevauchement(ct_a, ct_b):
    """Vrai si deux créneaux types (même jour) ont des horaires qui se recouvrent."""
    if not ct_a or not ct_b or ct_a.jour != ct_b.jour:
        return False
    return ct_a.heure_debut < ct_b.heure_fin and ct_b.heure_debut < ct_a.heure_fin


def types_conflit(a, b):
    """Retourne la liste des types de conflit applicables entre deux affectations.

    Un même couple peut cumuler plusieurs types (ex. même enseignant ET même salle).

    Source de vérité : les **clés étrangères réelles** de l'affectation.
    - L'enseignant est ``AffectationCreneau.formateur_id`` (FK ``Formateur``,
      identifiant métier INJS) ; ``enseignant_id`` (compte utilisateur) n'est
      qu'un vestige de l'historique mobile et ne sert que de repli.
    - La salle est ``AffectationCreneau.salle_id`` (FK ``RefSalle``). Le champ
      texte ``salle_nom`` est dénormalisé et ne sert que de repli : comparer
      deux libellés fusionnerait ou séparerait à tort des salles distinctes.
    """
    types = []
    # -- Enseignant : FK métier d'abord, compte utilisateur en repli --------
    a_ens, b_ens = a.formateur_id, b.formateur_id
    if not (a_ens and b_ens and a_ens == b_ens):
        a_ens, b_ens = a.enseignant_id, b.enseignant_id
    if a_ens and b_ens and a_ens == b_ens:
        types.append('HORAIRE_ENSEIGNANT')
    # -- Groupe : FK LMD ---------------------------------------------------
    if a.groupe_id and b.groupe_id and a.groupe_id == b.groupe_id:
        types.append('HORAIRE_GROUPETUDIANT')
    # -- Salle : la FK RefSale prime ; le libellé n'est consulté QUE si l'au
    # moins une des deux FK est absente. Deux salles distinctes (FK différentes)
    # ne sont jamais un conflit, même si leur libellé se ressemble.
    a_salle, b_salle = a.salle_id, b.salle_id
    if a_salle and b_salle:
        if a_salle == b_salle:
            types.append('HORAIRE_SALLE')
    elif a.salle_nom and b.salle_nom and \
            a.salle_nom.strip().casefold() == b.salle_nom.strip().casefold():
        types.append('HORAIRE_SALLE')
    if not types and a.formation_id and b.formation_id and a.formation_id == b.formation_id \
            and not a.groupe_id and not b.groupe_id:
        # Deux volumes d'une même formation sans groupe distinct : conflit de module.
        types.append('HORAIRE_MODULE')
    return types


def _description_conflit(type_conflit, a, b):
    """Explication lisible du conflit (qui, quand, où) — exigence P07."""
    libelle = {
        'HORAIRE_ENSEIGNANT': 'même enseignant',
        'HORAIRE_GROUPETUDIANT': 'même groupe',
        'HORAIRE_SALLE': 'même salle',
        'HORAIRE_MODULE': 'même formation (sans groupe distinct)',
        'MANUEL': 'signalé manuellement',
    }.get(type_conflit, type_conflit)

    def _nom(aff):
        return aff.enseignant_nom or (f"groupe #{aff.groupe_id}" if aff.groupe_id
                                      else (aff.intitule or f'affectation #{aff.pk}'))

    return (
        f"Chevauchement ({libelle}) : « {a.intitule or _nom(a)} » ({a.horaire}, "
        f"s{a.semaine_debut}–s{a.semaine_fin}, {_nom(a)}"
        f"{', salle ' + a.salle_nom if a.salle_nom else ''}) vs "
        f"« {b.intitule or _nom(b)} » ({b.horaire}, s{b.semaine_debut}–s{b.semaine_fin}, "
        f"{_nom(b)}{', salle ' + b.salle_nom if b.salle_nom else ''})."
    )


# ---------------------------------------------------------------------------
# Détection de conflits
# ---------------------------------------------------------------------------

def _collecter_affectations_melees(affectations):
    """Affectations actives d'autres EDT partageant un enseignant/groupe/salle.

    Une seule requête (pas de N+1) : on récupère les affectations actives hors
    de l'EDT courant dont l'enseignant, le formateur, le groupe ou la salle
    apparaît dans l'EDT courant.
    """
    from django.db.models import Q

    enseignants = {a.enseignant_id for a in affectations if a.enseignant_id}
    formateurs = {a.formateur_id for a in affectations if a.formateur_id}
    groupes = {a.groupe_id for a in affectations if a.groupe_id}
    salles = {a.salle_nom.strip().casefold() for a in affectations if a.salle_nom.strip()}
    edt_ids = {a.emploi_du_temps_id for a in affectations}

    condition = Q()
    if enseignants:
        condition |= Q(enseignant_id__in=enseignants)
    if formateurs:
        condition |= Q(formateur_id__in=formateurs)
    if groupes:
        condition |= Q(groupe_id__in=groupes)
    if not condition:
        return []
    externes = (
        AffectationCreneau.objects.exclude(emploi_du_temps_id__in=edt_ids)
        .filter(actif=True)
        .filter(condition)
        .select_related('creneau_template', 'emploi_du_temps', 'formateur')
    )
    # Le filtre par salle se fait en Python (correspondance insensible à la casse).
    if salles:
        externes = [x for x in externes
                    if x.salle_nom.strip().casefold() in salles
                    or x.enseignant_id in enseignants
                    or x.formateur_id in formateurs
                    or x.groupe_id in groupes]
    return list(externes)


def _paires_en_conflit(affectations, externes):
    """Toutes les paires (a, b) en conflit, y compris a↔externe. Sans doublons."""
    paires = []
    vus = set()
    n = len(affectations)
    for i in range(n):
        a = affectations[i]
        candidats = list(affectations[i + 1:]) + externes
        for b in candidats:
            if b.pk == a.pk:
                continue
            cle = tuple(sorted((a.pk, b.pk)))
            if cle in vus:
                continue
            if not semaines_en_chevauchement(a.semaine_debut, a.semaine_fin,
                                             b.semaine_debut, b.semaine_fin):
                continue
            if not horaires_en_chevauchement(a.creneau_template, b.creneau_template):
                continue
            if not types_conflit(a, b):
                continue
            vus.add(cle)
            paires.append((a, b))
    return paires


@transaction.atomic
def detecter_conflits(emploi_du_temps):
    """Détecte les conflits d'un EDT (en interne ET avec les autres EDT).

    - crée/réactive une ligne ConflitCreneau par paire en conflit ;
    - clôture les conflits automatiques qui ne se vérifient plus ;
    - ne touche pas aux signalements manuels (type MANUEL) ouverts par un agent.

    Retourne un dictionnaire de statistiques (et jamais une exception côté
    vue, quelle que soit la base : SQLite inclus).
    """
    affectations = list(
        AffectationCreneau.objects.filter(emploi_du_temps=emploi_du_temps, actif=True)
        .select_related('creneau_template', 'formateur')
        .order_by('pk')
    )
    externes = _collecter_affectations_melees(affectations)
    paires = _paires_en_conflit(affectations, externes)

    existants = {
        frozenset(c.lignes_creneaux or []): c
        for c in ConflitCreneau.objects.filter(emploi_du_temps=emploi_du_temps, actif=True)
        if c.type_conflit != 'MANUEL'
    }

    maintenant = timezone.now()
    detectes = 0
    for a, b in paires:
        cle = frozenset((a.pk, b.pk))
        premier_type = types_conflit(a, b)[0]
        description = _description_conflit(premier_type, a, b)
        conflit = existants.pop(cle, None)
        if conflit is not None:
            if conflit.description != description:
                conflit.description = description
                conflit.save(update_fields=['description', 'recalcule_le'])
            detectes += 1
            continue
        ConflitCreneau.objects.create(
            emploi_du_temps=emploi_du_temps,
            type_conflit=premier_type,
            description=description,
            lignes_creneaux=[a.pk, b.pk],
        )
        detectes += 1

    clotures = 0
    for obsolete in existants.values():
        obsolete.actif = False
        obsolete.save(update_fields=['actif', 'recalcule_le'])
        clotures += 1
        obsolete.recalcule_le = maintenant

    return {
        'affectations_analysees': len(affectations),
        'conflits_detectes': detectes,
        'conflits_clotures': clotures,
        'horodatage': maintenant.isoformat(),
    }


def verifier_affectation(affectation):
    """Avant-placement contrôlé (P08) : conflits potentiels d'UNE affectation.

    Retourne la liste de descriptions lisibles (vide si placement sans souci).
    N'enregistre rien en base — sert d'avertissement à l'appelant.
    """
    if not affectation.creneau_template_id:
        return []
    from django.db.models import Q

    condition = Q(emploi_du_temps=affectation.emploi_du_temps)
    partages = Q()
    if affectation.enseignant_id:
        partages |= Q(enseignant_id=affectation.enseignant_id)
    if affectation.formateur_id:
        partages |= Q(formateur_id=affectation.formateur_id)
    if affectation.groupe_id:
        partages |= Q(groupe_id=affectation.groupe_id)
    if affectation.salle_nom.strip():
        partages |= Q(salle_nom__iexact=affectation.salle_nom.strip())
    if not partages:
        return []

    candidates = (
        AffectationCreneau.objects.filter(actif=True)
        .filter(partages)
        .exclude(pk=affectation.pk)
        .select_related('creneau_template', 'formateur')
    )
    avertissements = []
    for autre in candidates:
        if not semaines_en_chevauchement(affectation.semaine_debut, affectation.semaine_fin,
                                         autre.semaine_debut, autre.semaine_fin):
            continue
        if not horaires_en_chevauchement(affectation.creneau_template, autre.creneau_template):
            continue
        types = types_conflit(affectation, autre)
        if not types:
            continue
        # Un conflit intra-EDT de même population peut être légitime (deux groupes
        # d'une même salle) : on ne signale que les correspondances dures.
        if types == ['HORAIRE_MODULE'] and affectation.emploi_du_temps_id == autre.emploi_du_temps_id:
            continue
        avertissements.append(_description_conflit(types[0], affectation, autre))
    return avertissements


# ---------------------------------------------------------------------------
# Grille hebdomadaire (P17)
# ---------------------------------------------------------------------------

def grille_hebdomadaire(emploi_du_temps, semaine=None):
    """Organise les affectations d'un EDT en vues journalières pour une semaine.

    Retourne {'jours': [{'jour', 'libelle', 'creneaux': [...]}], 'semaine': n}
    où chaque créneau porte la liste des affectations qui l'occupent.
    """
    from .models import JOUR_CHOICES

    queryset = (
        AffectationCreneau.objects.filter(emploi_du_temps=emploi_du_temps, actif=True)
        .select_related('creneau_template', 'formateur', 'groupe', 'formation')
    )
    if semaine:
        queryset = queryset.filter(semaine_debut__lte=semaine, semaine_fin__gte=semaine)
    affectations = list(queryset)

    jours = {}
    for aff in affectations:
        ct = aff.creneau_template
        if not ct:
            continue
        vue = jours.setdefault(ct.jour, {})
        creneau = vue.setdefault(ct.pk, {
            'creneau_template_id': ct.pk,
            'jour': ct.jour,
            'heure_debut': ct.heure_debut.isoformat(timespec='minutes'),
            'heure_fin': ct.heure_fin.isoformat(timespec='minutes'),
            'affectations': [],
        })
        creneau['affectations'].append({
            'id': aff.pk,
            'nature': aff.nature,
            'intitule': aff.intitule,
            'enseignant_nom': aff.enseignant_nom,
            'groupe': str(aff.groupe) if aff.groupe_id else '',
            'formation': str(aff.formation) if aff.formation_id else '',
            'salle_nom': aff.salle_nom,
            'commentaire': aff.commentaire,
            'semaine_debut': aff.semaine_debut,
            'semaine_fin': aff.semaine_fin,
        })

    jours_tries = []
    for jour, _libelle in JOUR_CHOICES:
        vues = jours.get(jour, {})
        lignes = sorted(vues.values(), key=lambda c: c['heure_debut'])
        if lignes:
            jours_tries.append({'jour': jour, 'creneaux': lignes})
    return {'jours': jours_tries, 'semaine': semaine}


# ---------------------------------------------------------------------------
# Génération de brouillon (P06 — version pragmatique, voir audit 2026-09-15)
# ---------------------------------------------------------------------------

def _disponibilites_generantes(enseignant_user_ids, formateur_ids, semaine_refs):
    """Ensemble des (formateur_id, jour) rendus indisponibles par le socle.

    Les indisponibilités du socle (scolarite.IndisponibiliteEnseignant) sont
    datées ; on les projette sur les jours de semaine couverts. Sans date de
    rentrée sur l'EDT, la projection temporelle est impossible : on ignore
    alors ce filtre (retour vide) plutôt que de bloquer la génération.
    """
    ids = {i for i in formateur_ids if i}
    if not ids or not semaine_refs:
        return set()
    from scolarite.models import IndisponibiliteEnseignant

    dates = [d for d in semaine_refs if d]
    if not dates:
        return set()
    debut = min(dates)
    fin = max(dates)
    generes = set()
    NOMS_JOURS = ['LUNDI', 'MARDI', 'MERCREDI', 'JEUDI', 'VENDREDI', 'SAMEDI', 'DIMANCHE']
    for indispo in IndisponibiliteEnseignant.objects.filter(
            enseignant_id__in=ids, date_debut__lte=fin, date_fin__gte=debut):
        date_courante = max(indispo.date_debut, debut)
        butee = min(indispo.date_fin, fin)
        while date_courante <= butee:
            generes.add((indispo.enseignant_id, NOMS_JOURS[date_courante.weekday()]))
            date_courante += timedelta(days=1)
    return generes


@transaction.atomic
def generer_brouillon(emploi_du_temps, *, remplace_existant=False, max_par_semaine=2):
    """Génère un brouillon d'EDT à partir des affectations pédagogiques validées.

    Algorithme (glouton à contraintes, déterministe) :
    1. source = scolarite.AffectationPedagogique statut VALIDEE/PLANIFIEE de
       l'année de l'EDT, restreinte à la population (formation/groupe) ;
    2. volume horaire → nombre de séances hebdomadaires (÷ durée moyenne des
       créneaux types, borné par max_par_semaine) ;
    3. placement sur la grille des créneaux types, en évitant : enseignant/groupe
       déjà pris (EDT courant + autres EDT actifs), même salle, indisponibilités
       datées du socle quand la rentrée est connue ;
    4. écrit dans l'EDT (BROUILLON uniquement, sinon 409 géré par la vue).

    Retourne des statistiques détaillées et l'explication des échecs de placement.
    """
    from scolarite.models import AffectationPedagogique

    if emploi_du_temps.statut != 'BROUILLON':
        raise ValueError("La génération n'est permise que sur un emploi du temps en brouillon.")

    if remplace_existant:
        # Ne remplace QUE les lignes générées (cree_par = None) : les poses
        # manuelles d'un agent sont toujours conservées.
        emploi_du_temps.affectations.filter(cree_par=None).delete()

    besoins = (
        AffectationPedagogique.objects.filter(
            annee_academique=emploi_du_temps.annee_academique,
            statut__in=[AffectationPedagogique.Statut.VALIDEE,
                        AffectationPedagogique.Statut.PLANIFIEE],
        )
        .select_related('enseignant', 'ecue', 'ue', 'groupe', 'niveau')
        .order_by('pk')
    )
    if emploi_du_temps.population_type == 'FORMATION':
        besoins = besoins.filter(ref_formation_id=emploi_du_temps.population_id)
    elif emploi_du_temps.population_type == 'GROUPE':
        besoins = besoins.filter(groupe_id=emploi_du_temps.population_id)

    from .models import CreneauTemplate
    canevas = list(CreneauTemplate.objects.order_by('jour', 'heure_debut'))
    if not canevas:
        return {'seances_placees': 0, 'seances_non_placees': 0,
                'motif_echec': 'Aucun créneau type disponible : créez le canevas horaire d’abord.'}

    duree_moyenne = sum(c.duree_prevue_minutes or 120 for c in canevas) / max(len(canevas), 1)

    # Occupation existante (toutes EDT actives) indexée pour tests O(1).
    occupation = {}  # (ressource, jour, heure_debut, semaine) -> True
    def cle(ressource, ct, semaine):
        return (ressource, ct.jour, ct.heure_debut, semaine)

    for aff in AffectationCreneau.objects.filter(actif=True).select_related('creneau_template'):
        if not aff.creneau_template:
            continue
        for ressource in _ressources_occupees(aff):
            for sem in range(aff.semaine_debut, aff.semaine_fin + 1):
                occupation.setdefault(cle(ressource, aff.creneau_template, sem), []).append(aff.pk)

    debut = emploi_du_temps.semaine_debut or 1
    fin = emploi_du_temps.semaine_fin or debut
    semaines = list(range(debut, fin + 1))
    references_dates = []
    if emploi_du_temps.rentree:
        for sem in semaines:
            references_dates.append(emploi_du_temps.rentree + timedelta(days=7 * (sem - 1)))
    indispo_generants = _disponibilites_generantes(
        set(), {b.enseignant_id for b in besoins}, references_dates,
    )

    placees = 0
    echecs = []
    index_creneau = 0
    for besoin in besoins:
        volume = float(besoin.volume_horaire or 0)
        nb_requises = max(1, min(max_par_semaine, round(volume / max(duree_moyenne, 1)) or 1))
        intitule = (besoin.ecue.intitule if besoin.ecue_id else
                    (besoin.ue.intitule if besoin.ue_id else 'Enseignement'))
        nature = {'CM': 'COURS', 'TD': 'TD', 'TP': 'TP'}.get(besoin.type_enseignement, 'COURS')
        posees = 0
        tentatives = 0
        while posees < nb_requises and tentatives < len(canevas) * 3:
            ct = canevas[index_creneau % len(canevas)]
            index_creneau += 1
            tentatives += 1
            if (besoin.enseignant_id, ct.jour) in indispo_generants:
                continue
            ressources_a_tester = _ressources_besoin(besoin)
            semaines_libres = [
                sem for sem in semaines
                if all(cle(r, ct, sem) not in occupation or not occupation[cle(r, ct, sem)]
                       for r in ressources_a_tester)
            ]
            if not semaines_libres:
                continue
            # Regrouper sur un intervalle de semaines contiguës.
            sem_debut = semaines_libres[0]
            sem_fin = sem_debut
            for sem in semaines_libres[1:]:
                if sem == sem_fin + 1:
                    sem_fin = sem
                else:
                    break
            with transaction.atomic():
                aff = AffectationCreneau.objects.create(
                    emploi_du_temps=emploi_du_temps,
                    creneau_template=ct,
                    semaine_debut=sem_debut,
                    semaine_fin=sem_fin,
                    # -- Chaîne LMD : la séance est rattachée à son affectation
                    # pédagogique, seule source de l'ECUE/UE/semestre/enseignant.
                    # Sans ce FK, la séance reste orpheline côté pédagogie et
                    # inexploitable par les présences QR.
                    affectation_pedagogique_id=besoin.id,
                    formation_id=besoin.ref_formation_id,
                    groupe_id=besoin.groupe_id,
                    formateur_id=besoin.enseignant_id,
                    enseignant_nom=f"{besoin.enseignant.prenom} {besoin.enseignant.nom}".strip()
                                   if besoin.enseignant_id else '',
                    nature=nature,
                    intitule=intitule[:255],
                    commentaire='Généré automatiquement — à contrôler avant validation.',
                    actif=True,
                )
            for r in ressources_a_tester:
                for sem in range(sem_debut, sem_fin + 1):
                    occupation.setdefault(cle(r, ct, sem), []).append(aff.pk)
            placees += 1
            posees += 1
        if posees < nb_requises:
            echecs.append(
                f"{intitule} ({nature}) : {posees}/{nb_requises} séance(s) placée(s) — "
                "plus aucun créneau libre compatible (salle/enseignant/groupe/indisponibilités)."
            )

    stats = {
        'seances_placees': placees,
        'seances_non_placees': len(echecs),
        'explications_echecs': echecs,
        'avertissement': (
            'Brouillon généré automatiquement : à contrôler, puis soumettre à validation. '
            'Lancez la détection de conflits après tout ajustement manuel.'
        ),
    }
    return stats


def _ressources_occupees(aff):
    ressources = set()
    if aff.enseignant_id:
        ressources.add(('user', aff.enseignant_id))
    if aff.formateur_id:
        ressources.add(('formateur', aff.formateur_id))
    if aff.groupe_id:
        ressources.add(('groupe', aff.groupe_id))
    if aff.salle_nom.strip():
        ressources.add(('salle', aff.salle_nom.strip().casefold()))
    return ressources


def _ressources_besoin(besoin):
    ressources = set()
    if besoin.enseignant_id:
        ressources.add(('formateur', besoin.enseignant_id))
    if besoin.groupe_id:
        ressources.add(('groupe', besoin.groupe_id))
    return ressources
def _position(affectation):
    """Position légère d'une ``AffectationCreneau`` lisible pour les
    contrôles de ressources partagées (C1/C2/C3). Lecture seule."""
    creneau = affectation.creneau_template
    return {
        'id': affectation.pk,
        'emploi_du_temps_id': affectation.emploi_du_temps_id,
        'jour': creneau.jour,
        'heure_debut': creneau.heure_debut,
        'heure_fin': creneau.heure_fin,
        'semaine_debut': affectation.semaine_debut,
        'enseignant_id': affectation.enseignant_id,
        'groupe_id': affectation.groupe_id,
        'salle_id': affectation.salle_id,
    }


def _chevauche_position(pos_a, pos_b):
    """Vrai si deux positions (dictionnaire) se chevauchent sur le jour et
    la semaine (contrôle C2), puis horaire (contrôle C1/C3)."""
    if pos_a['jour'] != pos_b['jour']:
        return False
    if pos_a['semaine_debut'] != pos_b['semaine_debut']:
        return False
    return pos_a['heure_debut'] < pos_b['heure_fin'] and pos_b['heure_debut'] < pos_a['heure_fin']


def conflits_inter_edt(edt_ids):
    """Contrôle de cohérence inter-EDT (C1 / C2 / C3) — lecture.

    Compare les affectations d'un ou plusieurs emplois du temps qui portent
    sur une fenêtre horaire commune. Conçu pour croiser les générations de
    périmètres partageant des ressources (enseignant, groupe, salle) avant
    publication globale : aucun éditeur, aucune suppression de données.

    Entrée : ``edt_ids`` — identifiants d'emplois du temps à croiser.
    Sortie : dictionnaire structuré
        statut   : 'OK' | 'CONFLITS' | 'DONNEE_INCONNUE' | 'INTERDIT'
        conflits : liste de dictionnaires
            type_conflit, description, edt_a, edt_b, affectation_a, affectation_b,
            creneau_jour, creneau_semaine_debut, heure_debut, heure_fin
        detail   : edt_ids, edt_sans_affectation, affectations_analyses
    """
    from edts.models import AffectationCreneau

    edt_ids = sorted({int(e) for e in edt_ids if str(e).strip()})
    if not edt_ids:
        return {
            'statut': 'OK',
            'conflits': [],
            'detail': {'edt_ids': [], 'edt_sans_affectation': [], 'affectations_analyses': 0},
        }

    existants = set(
        AffectationCreneau.objects.filter(emploi_du_temps_id__in=edt_ids)
        .values_list('emploi_du_temps_id', flat=True)
    )
    sans_effectuation = sorted(set(edt_ids) - existants)

    affectations = list(
        AffectationCreneau.objects.filter(emploi_du_temps_id__in=edt_ids)
        .select_related('emploi_du_temps', 'groupe', 'salle',
                         'creneau_template')
    )
    # Regroupement par (jour, semaine commencement) — seuls les créneaux
    # de la même fenêtre peuvent se confronter.
    par_creneau = {}
    for aff in affectations:
        cle = (aff.creneau_template.jour, aff.semaine_debut)
        par_creneau.setdefault(cle, []).append(aff)

    conflits = []
    vues = set()
    for (_, sem), affs in sorted(par_creneau.items()):
        positions = [_position(a) for a in affs]
        for i in range(len(positions)):
            for j in range(i + 1, len(positions)):
                a, b = positions[i], positions[j]
                if not _chevauche_position(a, b):
                    continue
                if a['emploi_du_temps_id'] == b['emploi_du_temps_id']:
                    continue  # conflit intra-EDT déjà géré ailleurs
                cle_couple = frozenset((a['id'], b['id']))
                if cle_couple in vues:
                    continue
                vues.add(cle_couple)
                if a['enseignant_id'] == b['enseignant_id']:
                    conflits.append({
                        'type_conflit': 'C1_CONFLIT_ENSEIGNANT',
                        'description': (
                            f'Enseignant {a["enseignant_id"]} occupé deux fois '
                            f'le {a["jour"]} (semaine {sem}).'
                        ),
                        'edt_a': a['emploi_du_temps_id'],
                        'edt_b': b['emploi_du_temps_id'],
                        'affectation_a': a['id'],
                        'affectation_b': b['id'],
                        'creneau_jour': a['jour'],
                        'creneau_semaine_debut': sem,
                        'heure_debut': a['heure_debut'],
                        'heure_fin': a['heure_fin'],
                    })
                elif a['groupe_id'] == b['groupe_id']:
                    conflits.append({
                        'type_conflit': 'C2_CONFLIT_GROUPE',
                        'description': (
                            f'Groupe {a["groupe_id"]} occupé deux fois '
                            f'le {a["jour"]} (semaine {sem}).'
                        ),
                        'edt_a': a['emploi_du_temps_id'],
                        'edt_b': b['emploi_du_temps_id'],
                        'affectation_a': a['id'],
                        'affectation_b': b['id'],
                        'creneau_jour': a['jour'],
                        'creneau_semaine_debut': sem,
                        'heure_debut': a['heure_debut'],
                        'heure_fin': a['heure_fin'],
                    })
                elif a['salle_id'] == b['salle_id']:
                    conflits.append({
                        'type_conflit': 'C3_CONFLIT_SALLE',
                        'description': (
                            f'Salle {a["salle_id"]} occupée deux fois '
                            f'le {a["jour"]} (semaine {sem}).'
                        ),
                        'edt_a': a['emploi_du_temps_id'],
                        'edt_b': b['emploi_du_temps_id'],
                        'affectation_a': a['id'],
                        'affectation_b': b['id'],
                        'creneau_jour': a['jour'],
                        'creneau_semaine_debut': sem,
                        'heure_debut': a['heure_debut'],
                        'heure_fin': a['heure_fin'],
                    })

    if sans_effectuation:
        # Une EDT sans affectation rend la cohérence inter-EDT
        # indécidable : on ne peut garantir l'absence de conflit.
        statut = 'DONNEE_INCONNUE'
    elif conflits:
        statut = 'CONFLITS'
    else:
        statut = 'OK'
    return {
        'statut': statut,
        'conflits': conflits,
        'detail': {
            'edt_ids': edt_ids,
            'edt_sans_affectation': sans_effectuation,
            'affectations_analyses': len(affectations),
        },
    }
