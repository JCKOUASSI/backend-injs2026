"""Supervision des séances LMD — bloc « Séances en direct » du dashboard.

Finalité
--------
Fournir à un administrateur INJS la liste des **séances réelles** d'une date,
contextualisées par la chaîne LMD et accompagnées du suivi des présences
**réellement rattachées à chaque séance** (``presences.Pointage.seance_edt``).

Modèle de données (relations FK, jamais de libellés)
----------------------------------------------------
``Formation → Parcours → Groupe → UE → ECUE → Enseignant → Séance → Salle``
sont lus par les **vraies clés étrangères** de l'EDT :

- la séance est ``edts.AffectationCreneau`` (créneau placé dans un EDT) ;
- son contexte pédagogique vient de ``AffectationCreneau.affectation_pedagogique``
  (``scolarite.AffectationPedagogique``) qui porte ECUE, UE, semestre, niveau,
  parcours, formation, groupe et enseignant ;
- l'effectif attendu vient de ``scolarite.AffectationGroupe`` (membres actifs
  du groupe), jamais d'un effectif deviné ;
- les présences viennent de ``Pointage`` filtré sur ``seance_edt`` + ``date_journee``.

Règles métier appliquées
------------------------
1. **Statut de séance = horaires planifiés** (``creneau_template`` + occurrence
   du jour). Une séance n'est « en cours » que si l'heure courante est comprise
   entre son début et sa fin. Le nombre de pointages ne détermine **jamais** un
   statut : une séance sans aucune présence n'est pas « en direct ».
2. **Effectif attendu = membres actifs du groupe** (``membres_groupe``). Une
   séance sans groupe n'a pas d'effectif : la valeur est ``None`` (« non
   renseigné »), jamais ``0``.
3. **Aucune invention de catégorie** : seules les valeurs réellement stockées
   dans ``Pointage.statut_assiduite`` sont exposées. Une absence n'est pas
   assimilée à une absence injustifiée : ``ABSENT`` et ``ABSENCE_JUSTIFIEE``
   sont deux colonnes distinctes, ``EXCUSE`` (dispensé) une troisième.
4. **NULL ≠ 0** : toute statistique dont le dénominateur est inconnu vaut
   ``None`` et l'API renvoie ``null`` (le front affiche « Non disponible »).
   Le taux de présence n'est calculé que si l'effectif attendu est connu et > 0.
5. **Double comptage impossible** : les présences sont dédoublonnées par
   participant et par séance avant comptage ; un participant hors du périmètre
   du groupe n'est pas compté dans les statistiques de la séance.
6. **Consultatif** : ce module n'écrit jamais. Aucune création de présence,
   aucun jeton QR, aucune clôture — le dashboard est un poste de supervision.

Périmètre strictement INJS-LMD : le modèle ``formations.SessionModule`` (legacy)
et tout référentiel hérité d'autres applications ne sont pas utilisés ici, pas
plus qu'un quelconque « module » comme périmètre.
"""
from collections import defaultdict

from django.db.models import Count, Q
from django.utils import timezone

from . import seances_edt_services as service
from .models import Pointage

__all__ = [
    'STATUTS_SEANCE', 'LIBELLES_STATUT', 'statut_seance', 'supervision_seances',
]

#: Statuts de séance. Aucun de ces codes n'est stocké en base : ce sont des
#: statuts de **présentation**, dérivés des horaires planifiés de la séance
#: (le modèle ``AffectationCreneau`` n'a pas de champ « statut de séance » :
#: il n'a qu'un drapeau ``actif`` qui porte l'annulation logique).
STATUTS_SEANCE = ('A_VENIR', 'EN_COURS', 'TERMINEE', 'ANNULEE')

LIBELLES_STATUT = {
    'A_VENIR': 'À venir',
    'EN_COURS': 'En cours',
    'TERMINEE': 'Terminée',
    'ANNULEE': 'Annulée',
}


def statut_seance(affectation, date, maintenant=None):
    """Statut de séance déduit de ses horaires — jamais du nombre de pointages.

    ``ANNULEE`` : annulation logique du modèle EDT (``actif=False``, motif
    tracé par ``edts.item_cancel_api``). Elle prime sur l'horaire.

    Sinon la comparaison est purement temporelle :
    ``maintenant < début`` → à venir ; ``début ≤ maintenant ≤ fin`` → en cours ;
    ``maintenant > fin`` → terminée.
    """
    if not affectation.actif:
        return 'ANNULEE'
    debut, fin = service.horodatages(affectation, date)
    maintenant = maintenant or timezone.now()
    if maintenant < debut:
        return 'A_VENIR'
    if maintenant <= fin:
        return 'EN_COURS'
    return 'TERMINEE'


def _contexte_pedagogique(affectation):
    """Chaîne LMD de la séance via **sa** affectation pédagogique.

    Aucune déduction depuis un module, un groupe ou un libellé n'est tentée :
    si la séance n'est pas rattachée à une affectation pédagogique, l'ECUE et
    l'UE restent ``None`` (« non renseigné »), conformément à la convention
    « rattachement manuel et explicite » de l'EDT.
    """
    affectation_pedagogique = getattr(affectation, 'affectation_pedagogique', None)
    ecue = getattr(affectation_pedagogique, 'ecue', None) if affectation_pedagogique else None
    ue = getattr(ecue, 'ue', None) if ecue else None
    formation = getattr(affectation, 'formation', None)
    return {
        'affectation_pedagogique_id': affectation.affectation_pedagogique_id,
        'formation_id': (affectation.formation_id
                         or getattr(affectation_pedagogique, 'ref_formation_id', None)),
        'formation_libelle': (getattr(formation, 'intitule', '') or None),
        'parcours_id': getattr(affectation_pedagogique, 'parcours_id', None),
        'parcours_libelle': (getattr(getattr(affectation_pedagogique, 'parcours', None),
                                    'intitule', '') or None),
        'niveau_id': getattr(affectation_pedagogique, 'niveau_id', None),
        'niveau_libelle': (getattr(getattr(affectation_pedagogique, 'niveau', None),
                                  'libelle', '') or None),
        'semestre_libelle': (getattr(getattr(affectation_pedagogique, 'semestre', None),
                                    'libelle', '') or None),
        'ue_id': getattr(ue, 'id', None),
        'ue_code': getattr(ue, 'code', '') or None,
        'ue_libelle': getattr(ue, 'intitule', '') or None,
        'ecue_id': getattr(ecue, 'id', None),
        'ecue_code': getattr(ecue, 'code', '') or None,
        'ecue_libelle': getattr(ecue, 'intitule', '') or None,
    }


def _libelle_enseignant(affectation):
    """Enseignant réellement affecté à la séance (``formateur`` FK prioritaire)."""
    formateur = getattr(affectation, 'formateur', None)
    if formateur is not None:
        nom = ' '.join(part for part in (formateur.nom, formateur.prenom) if part).strip()
        return {
            'formateur_id': formateur.id,
            'enseignant_id': affectation.enseignant_id,
            'libelle': nom or affectation.enseignant_nom or None,
            'specialite': formateur.specialite or None,
        }
    return {
        'formateur_id': None,
        'enseignant_id': affectation.enseignant_id,
        'libelle': affectation.enseignant_nom or None,
        'specialite': None,
    }


def _salle(affectation):
    """Salle réelle de la séance : FK ``RefSalle`` prioritaire, sinon ``salle_nom``."""
    salle = getattr(affectation, 'salle', None)
    if salle is None:
        return {
            'salle_id': None,
            'salle_libelle': affectation.salle_nom or None,
            'salle_type': None,
            'salle_capacite': None,
        }
    return {
        'salle_id': salle.id,
        'salle_libelle': salle.nom or affectation.salle_nom or None,
        'salle_type': salle.get_type_lieu_display() if salle.type_lieu else None,
        'salle_capacite': salle.capacite,
    }


def _effectifs_groupes(groupe_ids):
    """``{groupe_id: effectif attendu}`` en **une** requête (anti N+1).

    Même périmètre que ``seances_edt_services.membres_groupe`` : affectations
    de groupe actives rattachées à un dossier ayant un participant.

    Les identifiants demandés sont **pré-chargés à 0** : un groupe sans membre
    vaut 0 (c'est un décompte connu), tandis qu'une séance sans groupe reste
    ``None`` (donnée inconnue) — les deux cas ne doivent jamais se confondre.
    """
    from scolarite.models import AffectationGroupe

    if not groupe_ids:
        return {}
    resultat = {groupe_id: 0 for groupe_id in groupe_ids}
    lignes = (AffectationGroupe.objects
              .filter(groupe_id__in=groupe_ids, active=True,
                      inscription__etudiant__participant__isnull=False)
              .values('groupe_id')
              .annotate(effectif=Count('inscription__etudiant__participant', distinct=True)))
    for ligne in lignes:
        resultat[ligne['groupe_id']] = ligne['effectif']
    return resultat


def _participants_groupes(groupe_ids):
    """``{groupe_id: {participant_id}}`` — périmètre réel, pour écarter
    toute présence d'un participant n'appartenant pas au groupe de la séance."""
    from scolarite.models import AffectationGroupe

    if not groupe_ids:
        return {}
    lignes = (AffectationGroupe.objects
              .filter(groupe_id__in=groupe_ids, active=True,
                      inscription__etudiant__participant__isnull=False)
              .values_list('groupe_id', 'inscription__etudiant__participant_id'))
    resultat = defaultdict(set)
    for groupe_id, participant_id in lignes:
        if participant_id:
            resultat[groupe_id].add(participant_id)
    return dict(resultat)


def _presences_par_seance(affectation_ids, date):
    """``{seance_id: {participant_id: row}}`` — dernière ligne par participant.

    Un même participant peut porter plusieurs pointages sur une séance (scan
    puis correction manuelle, sortie automatique…). On ne retient que la ligne
    la plus récente : le comptage est ainsi immunisé contre le double comptage.
    """
    lignes = (Pointage.objects
              .filter(seance_edt_id__in=affectation_ids, date_journee=date,
                      participant__isnull=False)
              .order_by('seance_edt_id', 'timestamp_entree', 'id')
              .values('seance_edt_id', 'participant_id', 'statut', 'statut_assiduite',
                      'device_id', 'timestamp_entree', 'timestamp_sortie',
                      'outside_geofence_count'))
    resultat = defaultdict(dict)
    for ligne in lignes:
        resultat[ligne['seance_edt_id']][ligne['participant_id']] = ligne
    return resultat

    debut, fin = service.horodatages(affectation, date)
    maintenant = maintenant or timezone.now()
    if maintenant < debut:
        return 'A_VENIR'
def _compter(rows, attendus_ids):
    """Décompte par catégorie d'assiduité, sans double comptage.

    ``rows`` : lignes de la séance dédoublonnées par participant.
    ``attendus_ids`` : ensemble des participants du groupe (vide si la séance
    n'a pas de périmètre pédagogique : on ne filtre alors sur rien).

    Ne sont retenus que les participants **du groupe** ; les colonnes sont
    celles du modèle ``Pointage.statut_assiduite``, sans regroupement :
    ``ABSENT`` (absence non justifiée) et ``ABSENCE_JUSTIFIEE`` restent
    distinctes, ``EXCUSE`` (dispensé) et ``NON_RENSEIGNE`` aussi.
    """
    presents = absents_justifies = absents_injustifies = dispenses = 0
    non_renseignes = retards = qr = manuel = 0
    hors_perimetre = 0
    for participant_id, ligne in rows.items():
        if attendus_ids and participant_id not in attendus_ids:
            # Présence d'un participant hors du groupe : jamais imputée à la
            # séance (sinon double comptage avec sa séance d'origine).
            hors_perimetre += 1
            continue
        assiduite = (ligne['statut_assiduite']
                     or Pointage.MAPPING_ASSIDUITE().get(
                         ligne['statut'], Pointage.StatutAssiduite.NON_RENSEIGNE))
        if assiduite == Pointage.StatutAssiduite.PRESENT:
            presents += 1
        elif assiduite == Pointage.StatutAssiduite.ABSENCE_JUSTIFIEE:
            absents_justifies += 1
        elif assiduite == Pointage.StatutAssiduite.ABSENT:
            absents_injustifies += 1
        elif assiduite == Pointage.StatutAssiduite.EXCUSE:
            dispenses += 1
        elif assiduite == Pointage.StatutAssiduite.NON_RENSEIGNE:
            non_renseignes += 1
        elif assiduite == Pointage.StatutAssiduite.RETARD:
            retards += 1
        if ligne['device_id'] == 'EMARGEMENT_MANUEL':
            manuel += 1
        else:
            qr += 1
    return {
        'presents': presents,
        'absents_justifies': absents_justifies,
        'absents_injustifies': absents_injustifies,
        'dispenses': dispenses,
        'non_renseignes': non_renseignes,
        'retards': retards,
        'source_qr': qr,
        'source_manuelle': manuel,
        'presences_hors_perimetre': hors_perimetre,
    }


def _seance_ligne(affectation, date, maintenant, rows, effectif, attendus_ids):
    """Payload d'une séance : identité, enseignement, public, presences."""
    debut, fin = service.horodatages(affectation, date)
    statut = statut_seance(affectation, date, maintenant)
    compteurs = _compter(rows, attendus_ids)
    # Effectif attendu : ``None`` si la séance n'a pas de groupe rattaché.
    # Jamais 0 par défaut — 0 signifierait « groupe vide », pas « inconnu ».
    attendu = effectif if affectation.groupe_id else None
    if attendu is None:
        non_pointes = None
        taux = None
    else:
        # Non pointés = membres du groupe sans **aucune** ligne de présence.
        traites = len([pid for pid in rows if not attendus_ids or pid in attendus_ids])
        non_pointes = max(0, attendu - traites)
        taux = round(compteurs['presents'] / attendu, 4) if attendu > 0 else None
    groupe = getattr(affectation, 'groupe', None)
    ligne = {
        'id': affectation.id,
        'date': date.isoformat(),
        'debut': debut.isoformat(),
        'fin': fin.isoformat(),
        'statut': statut,
        'statut_libelle': LIBELLES_STATUT[statut],
        'en_direct': statut == 'EN_COURS',
        'intitule': affectation.intitule or None,
        'nature': affectation.nature,
        'nature_libelle': affectation.get_nature_display() if affectation.nature else None,
        'semaine_debut': affectation.semaine_debut,
        'semaine_fin': affectation.semaine_fin,
        'groupe_id': affectation.groupe_id,
        'groupe_libelle': (getattr(groupe, 'nom', '') or None),
        'effectif_attendu': attendu,
        'presences': compteurs,
        'non_pointes': non_pointes,
        'taux_presence': taux,
    }
    ligne.update(_contexte_pedagogique(affectation))
    ligne.update(_libelle_enseignant(affectation))
    ligne.update(_salle(affectation))
    return ligne


def supervision_seances(user, date=None, *, statut=None, formation_id=None,
                        groupe_id=None, enseignant_id=None):
    """Séances d'une date + suivi de leurs présences, pour le dashboard.

    :param date: jour de référence (défaut : aujourd'hui).
    :param statut: ne garder que ce statut de présentation (``A_VENIR``,
        ``EN_COURS``, ``TERMINEE``, ``ANNULEE``).
    :param formation_id / groupe_id / enseignant_id: filtres métier appliqués
        **côté serveur**, sur les vraies FK de la séance.
    :returns: ``{'date', 'genere_le', 'resume', 'seances'}``.

    Aucune écriture. Un filtre hors périmètre ne lève pas : il ramène une liste
    vide, qui est un résultat valide et non une erreur.
    """
    from edts.models import AffectationCreneau

    date = date or timezone.localdate()
    maintenant = timezone.now()
    base = (AffectationCreneau.objects
            .filter(emploi_du_temps__statut__in=('VALIDE', 'PUBLIE'))
            .select_related(
                'creneau_template', 'emploi_du_temps', 'emploi_du_temps__annee_academique',
                'groupe', 'formation', 'salle', 'formateur',
                'affectation_pedagogique', 'affectation_pedagogique__ecue',
                'affectation_pedagogique__ecue__ue', 'affectation_pedagogique__parcours',
                'affectation_pedagogique__niveau', 'affectation_pedagogique__semestre',
            ))
    if formation_id:
        base = base.filter(Q(formation_id=formation_id)
                           | Q(affectation_pedagogique__ref_formation_id=formation_id))
    if groupe_id:
        base = base.filter(Q(groupe_id=groupe_id)
                           | Q(affectation_pedagogique__groupe_id=groupe_id))
    if enseignant_id:
        base = base.filter(Q(enseignant_id=enseignant_id)
                           | Q(formateur_id=enseignant_id))

    # Périmètre de lecture : les comptes habilités (direction, secrétariat,
    # INJS admin) supervisent toutes les séances ; un enseignant ou encadrant
    # ne voit que les siennes — même règle que ``seances_du_jour``.
    role = (getattr(user, 'role', '') or '').upper()
    if role not in {'ADMIN', 'INJS_ADMIN', 'CHEF_INJS_ADMIN', 'SECRETARIAT',
                    'CHEF_SECRETARIAT', 'DIRECTION'} and getattr(user, 'id', None):
        base = base.filter(Q(enseignant_id=user.id) | Q(formateur_id=user.id))

    affectations = []
    for affectation in base.order_by('creneau_template__heure_debut', 'id'):
        # ``actif=False`` = annulation logique : elle reste visible (statut
        # ANNULEE) ; seules les séances actives sont discriminées par le jour.
        if affectation.actif and not service.est_seance_du_jour(affectation, date):
            continue
        affectations.append(affectation)

    if not affectations:
        return {
            'date': date.isoformat(),
            'genere_le': maintenant.isoformat(),
            'resume': {
                'seances_total': 0, 'seances_en_cours': 0, 'enseignants_actifs': 0,
                'salles_occupees': 0, 'participants_presents': 0, 'anomalies': 0,
            },
            'seances': [],
        }

    groupe_ids = {a.groupe_id for a in affectations if a.groupe_id}
    effectifs = _effectifs_groupes(groupe_ids)
    participants = _participants_groupes(groupe_ids)
    presences = _presences_par_seance({a.pk for a in affectations}, date)

    lignes = []
    for affectation in affectations:
        ligne = _seance_ligne(
            affectation, date, maintenant,
            presences.get(affectation.pk, {}),
            effectifs.get(affectation.groupe_id) if affectation.groupe_id else None,
            participants.get(affectation.groupe_id, set()) if affectation.groupe_id else set(),
        )
        if statut and ligne['statut'] != statut:
            continue
        lignes.append(ligne)

    resume = {
        'seances_total': len(lignes),
        'seances_en_cours': sum(1 for l in lignes if l['statut'] == 'EN_COURS'),
        'enseignants_actifs': len({
            l['formateur_id'] or l['enseignant_id'] or l['libelle']
            for l in lignes if l['statut'] == 'EN_COURS'
            and (l['formateur_id'] or l['enseignant_id'] or l['libelle'])}),
        'salles_occupees': len({
            l['salle_id'] or l['salle_libelle'] for l in lignes
            if l['statut'] == 'EN_COURS' and (l['salle_id'] or l['salle_libelle'])}),
        'participants_presents': sum(l['presences']['presents'] for l in lignes),
        # Anomalie = séance dont l'effectif attendu n'est pas déterminable
        # (aucun groupe rattaché) : y afficher un chiffre serait un mensonge.
        'anomalies': sum(1 for l in lignes if l['effectif_attendu'] is None),
    }
    return {
        'date': date.isoformat(),
        'genere_le': maintenant.isoformat(),
        'resume': resume,
        'seances': lignes,
    }
