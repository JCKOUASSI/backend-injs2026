"""Services d'interopérabilité GET-INJS → futur module Présences.

Contrat posé par l'extension architecturale du prompt maître :

- chaque séance publiée possède une identité permanente (UUID) qui survit
  aux modifications de programmation et aux régénérations ;
- le cycle de vie est explicite (transitions autorisées) et toute
  modification d'une séance publiée est historisée et émise en événement ;
- une séance ne peut ouvrir une session officielle de présence que si elle
  est publiée (PUBLIEE, ou PUBLIEE puis MODIFIEE) ;
- les étudiants attendus se calculent depuis les affectations de groupe
  actives (même périmètre que ``presences.seances_supervision``), sans
  jamais confondre admission, inscription administrative et inscription
  pédagogique ;
- GET ne produit ni pointage, ni QR Code, ni statistique de présence.

Ce module ne dépend pas de l'application ``presences`` (aucune importation
circulaire) : la garde de suppression vit dans ``models_interop``.
"""

import hashlib

from django.db import transaction
from django.utils import timezone

from ..models import AffectationCreneau, EmploiDuTemps
from ..models_interop import (
    SalleGeolocalisation,
    SeanceEvenement,
    SeanceHistorique,
    SeanceInstantaneAttendus,
    SeanceRegistre,
)

# Transitions autorisées du cycle de vie d'une séance. ANNULEE et TERMINEE
# sont terminales : une reprogrammation crée une NOUVELLE séance reliée par
# ``seance_origine`` (l'annulée reste lisible, jamais ressuscitée).
TRANSITIONS_AUTORISEES = {
    SeanceRegistre.Statut.BROUILLON: {
        SeanceRegistre.Statut.SIMULATION,
        SeanceRegistre.Statut.EN_ATTENTE_VALIDATION,
        SeanceRegistre.Statut.ANNULEE,
    },
    SeanceRegistre.Statut.SIMULATION: {
        SeanceRegistre.Statut.BROUILLON,
        SeanceRegistre.Statut.ANNULEE,
    },
    SeanceRegistre.Statut.EN_ATTENTE_VALIDATION: {
        SeanceRegistre.Statut.VALIDEE,
        SeanceRegistre.Statut.BROUILLON,
        SeanceRegistre.Statut.ANNULEE,
    },
    SeanceRegistre.Statut.VALIDEE: {
        SeanceRegistre.Statut.PUBLIEE,
        SeanceRegistre.Statut.ANNULEE,
    },
    SeanceRegistre.Statut.PUBLIEE: {
        SeanceRegistre.Statut.MODIFIEE,
        SeanceRegistre.Statut.ANNULEE,
        SeanceRegistre.Statut.TERMINEE,
    },
    SeanceRegistre.Statut.MODIFIEE: {
        SeanceRegistre.Statut.PUBLIEE,
        SeanceRegistre.Statut.ANNULEE,
        SeanceRegistre.Statut.TERMINEE,
    },
    SeanceRegistre.Statut.ANNULEE: set(),
    SeanceRegistre.Statut.TERMINEE: set(),
}

# Statuts sous lesquels une séance est officiellement exploitable par le
# futur module de présence. Une simulation ne l'est JAMAIS (§4.1/4.2).
STATUTS_EXPLOITABLES_PRESENCE = {
    SeanceRegistre.Statut.PUBLIEE,
    SeanceRegistre.Statut.MODIFIEE,
}

_EVENEMENT_PAR_STATUT = {
    SeanceRegistre.Statut.PUBLIEE: SeanceEvenement.Type.SEANCE_PUBLIEE,
    SeanceRegistre.Statut.MODIFIEE: SeanceEvenement.Type.SEANCE_MODIFIEE,
    SeanceRegistre.Statut.ANNULEE: SeanceEvenement.Type.SEANCE_ANNULEE,
    SeanceRegistre.Statut.TERMINEE: SeanceEvenement.Type.SEANCE_CLOTUREE,
}


def calculer_cle_metier(affectation):
    """Empreinte déterministe de l'activité pédagogique d'une séance.

    Ne contient ni l'horaire, ni la salle, ni l'enseignant : ce sont des
    attributs modifiables de la même activité. Avec une affectation
    pédagogique, son identifiant suffit (elle encode année, formation,
    niveau, semestre, UE, ECUE, groupe, type). Sans elle, repli sur le
    périmètre de l'EDT et les rattachements directs de la ligne.
    """
    if affectation.affectation_pedagogique_id:
        source = f'AP:{affectation.affectation_pedagogique_id}'
        return hashlib.sha256(source.encode('utf-8')).hexdigest()
    emploi = affectation.emploi_du_temps
    morceaux = [
        f'annee:{emploi.annee_academique_id}',
        f'population:{emploi.population_type}:{emploi.population_id}',
        f'formation:{affectation.formation_id}',
        f'groupe:{affectation.groupe_id}',
        f'nature:{affectation.nature}',
        f'intitule:{(affectation.intitule or "").strip().lower()}',
        f'semaines:{affectation.semaine_debut}-{affectation.semaine_fin}',
    ]
    return hashlib.sha256('|'.join(morceaux).encode('utf-8')).hexdigest()


def _historiser(registre, action, acteur=None, motif='', statut_avant='',
                statut_apres='', details=None):
    return SeanceHistorique.objects.create(
        registre=registre,
        action=action,
        statut_avant=statut_avant or '',
        statut_apres=statut_apres or registre.statut,
        acteur=acteur,
        motif=motif or '',
        details=details or {},
    )


def emettre_evenement(registre, type_evenement):
    """Émet l'événement contractuel correspondant à l'état de la séance."""
    affectation = registre.affectation
    charge = {
        'seance_uuid': str(registre.uuid),
        'statut': registre.statut,
        'version': registre.version,
    }
    if affectation is not None:
        creneau = affectation.creneau_template
        charge.update({
            'affectation_id': affectation.id,
            'jour': creneau.jour if creneau else None,
            'heure_debut': creneau.heure_debut.strftime('%H:%M') if creneau else None,
            'heure_fin': creneau.heure_fin.strftime('%H:%M') if creneau else None,
            'salle_id': affectation.salle_id,
            'groupe_id': affectation.groupe_id,
            'formateur_id': affectation.formateur_id,
        })
    return SeanceEvenement.objects.create(
        type=type_evenement,
        registre=registre,
        charge_utile=charge,
    )


@transaction.atomic
def assurer_registre(affectation, acteur=None):
    """Retourne le registre de la séance, en le créant ou le rattachant.

    Ordre de résolution : registre déjà lié à cette ligne de placement ;
    sinon registre orphelin (ligne supprimée par une régénération) portant
    la même clé métier — il est rattaché, l'UUID est conservé ; sinon
    création d'un nouveau registre en BROUILLON.
    """
    registre = SeanceRegistre.objects.filter(affectation=affectation).first()
    if registre is not None:
        return registre, False

    cle = calculer_cle_metier(affectation)
    registre = (
        SeanceRegistre.objects
        .filter(cle_metier=cle, affectation__isnull=True)
        .order_by('id')
        .first()
    )
    if registre is not None:
        registre.affectation = affectation
        registre.modifie_par = acteur
        registre.save(update_fields=['affectation', 'modifie_par', 'updated_at'])
        _historiser(
            registre, SeanceHistorique.Action.RATTACHEMENT, acteur=acteur,
            details={'affectation_id': affectation.id, 'cle_metier': cle},
        )
        return registre, False

    registre = SeanceRegistre.objects.create(
        affectation=affectation,
        cle_metier=cle,
        cree_par=acteur,
        modifie_par=acteur,
    )
    _historiser(
        registre, SeanceHistorique.Action.CREATION, acteur=acteur,
        details={'affectation_id': affectation.id, 'cle_metier': cle},
    )
    return registre, True


@transaction.atomic
def transitionner(registre, nouveau_statut, acteur=None, motif=''):
    """Applique une transition de cycle de vie contrôlée et tracée.

    Lève ``ValueError`` si la transition n'est pas autorisée depuis le
    statut courant. Toute arrivée en PUBLIEE/MODIFIEE/ANNULEE/TERMINEE émet
    l'événement contractuel correspondant.
    """
    nouveau = SeanceRegistre.Statut(nouveau_statut)
    avant = registre.statut
    if nouveau == avant:
        raise ValueError(f'La séance est déjà {avant}.')
    autorises = TRANSITIONS_AUTORISEES.get(SeanceRegistre.Statut(avant), set())
    if nouveau not in autorises:
        raise ValueError(
            f'Transition {avant} → {nouveau} non autorisée. '
            f'Issues possibles : {sorted(autorises) or "aucune (état terminal)"}.'
        )

    registre.statut = nouveau
    champs = ['statut', 'modifie_par', 'updated_at']
    registre.modifie_par = acteur
    if nouveau == SeanceRegistre.Statut.PUBLIEE:
        registre.publie_le = timezone.now()
        registre.publie_par = acteur
        champs += ['publie_le', 'publie_par']
    if nouveau == SeanceRegistre.Statut.ANNULEE:
        registre.motif_annulation = motif or ''
        champs.append('motif_annulation')
    registre.save(update_fields=champs)

    action = SeanceHistorique.Action.TRANSITION
    if nouveau == SeanceRegistre.Statut.PUBLIEE:
        action = SeanceHistorique.Action.PUBLICATION
    elif nouveau == SeanceRegistre.Statut.ANNULEE:
        action = SeanceHistorique.Action.ANNULATION
    _historiser(
        registre, action, acteur=acteur, motif=motif,
        statut_avant=avant, statut_apres=nouveau,
    )
    type_evenement = _EVENEMENT_PAR_STATUT.get(nouveau)
    if type_evenement is not None:
        emettre_evenement(registre, type_evenement)
    return registre


@transaction.atomic
def enregistrer_modification(registre, acteur=None, motif='', champs_modifies=None):
    """Trace une modification de programmation d'une séance publiée.

    L'identité (UUID) est conservée ; la version est incrémentée ; une
    séance PUBLIEE passe MODIFIEE (toujours exploitable, mais signalée) ;
    l'événement SEANCE_MODIFIEE est émis pour le futur module de présence.
    """
    avant = registre.statut
    registre.version += 1
    registre.modifie_par = acteur
    champs = ['version', 'modifie_par', 'updated_at']
    if avant == SeanceRegistre.Statut.PUBLIEE:
        registre.statut = SeanceRegistre.Statut.MODIFIEE
        champs.append('statut')
    registre.save(update_fields=champs)
    _historiser(
        registre, SeanceHistorique.Action.MODIFICATION, acteur=acteur,
        motif=motif, statut_avant=avant, statut_apres=registre.statut,
        details={'champs_modifies': champs_modifies or []},
    )
    if registre.statut in STATUTS_EXPLOITABLES_PRESENCE:
        emettre_evenement(registre, SeanceEvenement.Type.SEANCE_MODIFIEE)
    return registre


@transaction.atomic
def reprogrammer(registre_annule, nouvelle_affectation, acteur=None, motif=''):
    """Crée la séance qui reprogramme une séance annulée.

    L'annulée reste ANNULEE (traçabilité) ; la nouvelle reçoit sa propre
    identité et pointe vers l'ancienne via ``seance_origine`` ;
    l'événement SEANCE_REPROGRAMMEE relie les deux UUID.
    """
    if registre_annule.statut != SeanceRegistre.Statut.ANNULEE:
        raise ValueError('Seule une séance ANNULEE peut être reprogrammée.')
    nouveau, _ = assurer_registre(nouvelle_affectation, acteur=acteur)
    if nouveau.id == registre_annule.id:
        raise ValueError('La reprogrammation doit créer une nouvelle séance.')
    nouveau.seance_origine = registre_annule
    nouveau.modifie_par = acteur
    nouveau.save(update_fields=['seance_origine', 'modifie_par', 'updated_at'])
    _historiser(
        nouveau, SeanceHistorique.Action.REPROGRAMMATION, acteur=acteur,
        motif=motif,
        details={
            'seance_annulee_uuid': str(registre_annule.uuid),
            'motif_annulation': registre_annule.motif_annulation,
        },
    )
    evenement = emettre_evenement(nouveau, SeanceEvenement.Type.SEANCE_REPROGRAMMEE)
    evenement.charge_utile['seance_annulee_uuid'] = str(registre_annule.uuid)
    evenement.save(update_fields=['charge_utile'])
    return nouveau


@transaction.atomic
def reconcilier_emploi_du_temps(emploi_du_temps, acteur=None):
    """Assure un registre par séance active d'un emploi du temps.

    Si l'EDT est PUBLIÉ, ses séances passent PUBLIEE (depuis BROUILLON,
    VALIDEE ou EN_ATTENTE_VALIDATION, en suivant le cycle) afin que le
    futur module de présence ne consomme que des séances officielles.
    Retourne un bilan comptable, jamais muet.
    """
    bilan = {'crees': 0, 'rattaches': 0, 'existants': 0, 'publiees': 0}
    affectations = (
        emploi_du_temps.affectations
        .filter(actif=True)
        .select_related('creneau_template', 'affectation_pedagogique')
    )
    for affectation in affectations:
        existait = SeanceRegistre.objects.filter(affectation=affectation).exists()
        registre, cree = assurer_registre(affectation, acteur=acteur)
        if cree:
            bilan['crees'] += 1
        elif existait:
            bilan['existants'] += 1
        else:
            bilan['rattaches'] += 1
        if emploi_du_temps.statut == 'PUBLIE' and registre.statut not in (
            SeanceRegistre.Statut.PUBLIEE,
            SeanceRegistre.Statut.MODIFIEE,
            SeanceRegistre.Statut.ANNULEE,
            SeanceRegistre.Statut.TERMINEE,
        ):
            chemin = {
                SeanceRegistre.Statut.BROUILLON: [
                    SeanceRegistre.Statut.EN_ATTENTE_VALIDATION,
                    SeanceRegistre.Statut.VALIDEE,
                    SeanceRegistre.Statut.PUBLIEE,
                ],
                SeanceRegistre.Statut.SIMULATION: [
                    SeanceRegistre.Statut.BROUILLON,
                    SeanceRegistre.Statut.EN_ATTENTE_VALIDATION,
                    SeanceRegistre.Statut.VALIDEE,
                    SeanceRegistre.Statut.PUBLIEE,
                ],
                SeanceRegistre.Statut.EN_ATTENTE_VALIDATION: [
                    SeanceRegistre.Statut.VALIDEE,
                    SeanceRegistre.Statut.PUBLIEE,
                ],
                SeanceRegistre.Statut.VALIDEE: [
                    SeanceRegistre.Statut.PUBLIEE,
                ],
            }[SeanceRegistre.Statut(registre.statut)]
            for etape in chemin:
                transitionner(registre, etape, acteur=acteur)
            bilan['publiees'] += 1
    return bilan


def peut_ouvrir_session_presence(registre):
    """True seulement si la séance est officiellement publiée.

    Ni une simulation, ni un brouillon, ni une séance validée mais non
    publiée, ni une séance annulée ou terminée ne peuvent ouvrir une
    session officielle de présence (§4.1 à 4.4 de l'extension).
    """
    return registre.statut in STATUTS_EXPLOITABLES_PRESENCE


def groupe_de_la_seance(affectation):
    """Groupe pédagogique de la séance (direct ou via l'affectation pédago.)."""
    if affectation is None:
        return None
    if affectation.groupe_id:
        return affectation.groupe
    ap = affectation.affectation_pedagogique
    if ap is not None and ap.groupe_id:
        return ap.groupe
    return None


def etudiants_attendus(affectation, date_seance=None):
    """Étudiants théoriquement attendus à la séance.

    Périmètre : membres actifs du groupe (``AffectationGroupe`` active
    rattachée à un dossier ayant un participant) — exactement le périmètre
    de ``presences.seances_supervision``. Ce sont des inscrits
    administratifs affectés au groupe ; la présence d'une inscription
    pédagogique est signalée par drapeau, jamais présumée.
    """
    from scolarite.models import AffectationGroupe

    groupe = groupe_de_la_seance(affectation)
    if groupe is None:
        return {'base': 'AUCUN_GROUPE', 'groupe_id': None, 'effectif': 0, 'etudiants': []}

    lignes = (
        AffectationGroupe.objects
        .filter(groupe=groupe, active=True, inscription__etudiant__participant__isnull=False)
        .select_related('inscription__etudiant__participant')
        .order_by(
            'inscription__etudiant__participant__nom',
            'inscription__etudiant__participant__prenom',
        )
    )
    vus = {}
    for ligne in lignes:
        participant = ligne.inscription.etudiant.participant
        if participant is None or participant.id in vus:
            continue
        vus[participant.id] = {
            'participant_id': participant.id,
            'matricule': participant.matricule,
            'nom': participant.nom,
            'prenom': participant.prenom,
            'dossier_id': ligne.inscription.etudiant_id,
            'inscription_administrative_id': ligne.inscription_id,
        }
    etudiants = list(vus.values())
    return {
        'base': 'AFFECTATION_GROUPE_ACTIVE',
        'groupe_id': groupe.id,
        'date_seance': date_seance.isoformat() if date_seance else None,
        'effectif': len(etudiants),
        'etudiants': etudiants,
    }


@transaction.atomic
def creer_instantane(registre, acteur=None, date_seance=None):
    """Fige la liste des attendus (cohérence historique, cf. §5 extension)."""
    if registre.affectation is None:
        raise ValueError('Séance sans placement courant : instantané impossible.')
    attendus = etudiants_attendus(registre.affectation, date_seance=date_seance)
    instantane = SeanceInstantaneAttendus.objects.create(
        registre=registre,
        date_seance=date_seance,
        base_calculee=attendus['base'],
        effectif=attendus['effectif'],
        participants=attendus['etudiants'],
        cree_par=acteur,
    )
    _historiser(
        registre, SeanceHistorique.Action.INSTANTANE, acteur=acteur,
        details={'instantane_id': instantane.id, 'effectif': attendus['effectif']},
    )
    return instantane


def contexte_seance(registre):
    """Contexte complet et contractuel d'une séance (lecture interop).

    Toutes les informations sont retrouvées par relations — aucune
    redondance stockée. ``None`` explicite quand la donnée n'existe pas.
    """
    affectation = registre.affectation
    contexte = {
        'seance_uuid': str(registre.uuid),
        'statut': registre.statut,
        'version': registre.version,
        'publie_le': registre.publie_le.isoformat() if registre.publie_le else None,
        'peut_ouvrir_session_presence': peut_ouvrir_session_presence(registre),
        'seance_origine_uuid': (
            str(registre.seance_origine.uuid) if registre.seance_origine_id else None
        ),
    }
    if affectation is None:
        contexte['placement'] = None
        return contexte

    emploi = affectation.emploi_du_temps
    creneau = affectation.creneau_template
    ap = affectation.affectation_pedagogique
    enseignant = None
    if ap is not None and ap.enseignant_id:
        enseignant = f'{ap.enseignant.nom} {ap.enseignant.prenom}'.strip()
    elif affectation.formateur_id:
        enseignant = f'{affectation.formateur.nom} {affectation.formateur.prenom}'.strip()
    elif affectation.enseignant_nom:
        enseignant = affectation.enseignant_nom

    salle = None
    if affectation.salle_id:
        geo = SalleGeolocalisation.objects.filter(salle_id=affectation.salle_id).first()
        salle = {
            'id': affectation.salle_id,
            'nom': affectation.salle.nom,
            'capacite': affectation.salle.capacite,
            'geolocalisation': {
                'latitude': str(geo.latitude) if geo and geo.latitude is not None else None,
                'longitude': str(geo.longitude) if geo and geo.longitude is not None else None,
                'rayon_tolerance_m': geo.rayon_tolerance_m if geo else None,
                'type_espace': geo.type_espace if geo else None,
                'statut_configuration': geo.statut_configuration if geo else 'NON_CONFIGUREE',
                'coordonnees_disponibles': bool(geo and geo.coordonnees_disponibles),
            },
        }

    contexte['placement'] = {
        'affectation_id': affectation.id,
        'emploi_du_temps_id': emploi.id,
        'emploi_du_temps_statut': emploi.statut,
        'annee_academique': emploi.annee_academique.libelle,
        'jour': creneau.jour if creneau else None,
        'heure_debut': creneau.heure_debut.strftime('%H:%M') if creneau else None,
        'heure_fin': creneau.heure_fin.strftime('%H:%M') if creneau else None,
        'duree_prevue_minutes': creneau.duree_prevue_minutes if creneau else None,
        'fuseau_horaire': 'Africa/Abidjan',
        'semaine_debut': affectation.semaine_debut,
        'semaine_fin': affectation.semaine_fin,
        'type_seance': affectation.nature,
        'intitule': affectation.intitule,
        'salle': salle,
        'enseignant': enseignant,
        'affectation_pedagogique_id': affectation.affectation_pedagogique_id,
        'formation': (
            ap.ref_formation.intitule if ap is not None
            else (affectation.formation.intitule if affectation.formation_id else None)
        ),
        'niveau': ap.niveau.code if ap is not None and ap.niveau_id else None,
        'semestre': (
            ap.semestre.libelle if ap is not None and ap.semestre_id else None
        ),
        'ue': ap.ue.code if ap is not None and ap.ue_id else None,
        'ecue': ap.ecue.code if ap is not None and ap.ecue_id else None,
        'groupe_id': groupe_de_la_seance(affectation).id if groupe_de_la_seance(affectation) else None,
    }
    return contexte
