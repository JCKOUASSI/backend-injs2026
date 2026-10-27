"""Lot C — service des séances LMD (créneaux d'EDT) pour la présence QR/émargement.

Modèle fonctionnel de référence, MODULE 08 : la chaîne
`EDT → SÉANCE → ÉMARGEMENT (QR auto | cases enseignant | administratif habilité)
→ JUSTIFICATION (forçage à motif) → CLÔTURE (auto)` s'exerce ici sur
``edts.AffectationCreneau`` (la séance planifiée) sans toucher au flux legacy
``formations.SessionModule`` (empilement, non-remplacement).

Conventions héritées du socle présences (préserver) :
- statut de badgeage ``Pointage.Statut`` (EN_COURS/TERMINE/FORCE_DFRC/SORTIE_AUTO/…)
- résultat pédagogique ``Pointage.StatutAssiduite`` (PRESENT/RETARD/ABSENT/…)
- ``AuditLog`` pour tout geste sensible (scan, forçage avec motif, clôture auto).
"""
from datetime import datetime, timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from formations.models import Participant, QRToken
from parametres.models import Parametre

from .models import AuditLog, Pointage

#: Index lundi=0..dimanche=6 aligné sur les codes `JOUR_CHOICES` de l'EDT.
_JOURS = {'LUNDI': 0, 'MARDI': 1, 'MERCREDI': 2, 'JEUDI': 3,
          'VENDREDI': 4, 'SAMEDI': 5, 'DIMANCHE': 6}

#: Tolérances (minutes), configurables par paramètre — modèle 08.3/08.5.
CLE_OUVERTURE_ANTICIPEE = 'presences.edt.ouverture_anticipee_minutes'
CLE_TOLERANCE_RETARD = 'presences.edt.tolerance_retard_minutes'
CLE_TOLERANCE_CLOTURE = 'presences.edt.tolerance_cloture_minutes'
CLE_NOTIFIER_CLOTURE = 'presences.edt.notifier_a_cloture'

DEFAUTS = {CLE_OUVERTURE_ANTICIPEE: 10, CLE_TOLERANCE_RETARD: 10, CLE_TOLERANCE_CLOTURE: 15,
           CLE_NOTIFIER_CLOTURE: 1}


def _parametre(cle):
    objet = Parametre.get_by_cle(cle, None)
    if objet is None:
        return DEFAUTS[cle]
    try:
        valeur = objet.get_valeur_typed()
        return int(valeur) if valeur is not None else DEFAUTS[cle]
    except (TypeError, ValueError, AttributeError):
        return DEFAUTS[cle]


# ---------------------------------------------------------------------------
# Résolution « séance du jour » : une AffectationCreneau couvre des semaines
# académiques ; l'occurrence du jour est déterminée par (jour de semaine,
# n° de semaine depuis le début de l'année académique).
# ---------------------------------------------------------------------------

def semaine_academique(affectation, date):
    """Numéro de semaine académique de `date` (1-based) pour l'EDT donné."""
    annee = getattr(affectation.emploi_du_temps, 'annee_academique', None)
    if annee is None or annee.date_debut is None:
        return None
    return (date - annee.date_debut).days // 7 + 1


def est_seance_du_jour(affectation, date):
    """True si `affectation` a séance ce jour-là (jour + plage de semaines)."""
    if not affectation.actif:
        return False
    numero = semaine_academique(affectation, date)
    if numero is None:
        return False
    if not (affectation.semaine_debut <= numero <= affectation.semaine_fin):
        return False
    code_jour = getattr(affectation.creneau_template, 'jour', None)
    return _JOURS.get(code_jour) == date.weekday()


def horodatages(affectation, date):
    """(début, fin) datés de l'occurrence de séance pour `date`."""
    ct = affectation.creneau_template
    debut = timezone.make_aware(datetime.combine(date, ct.heure_debut))
    fin = timezone.make_aware(datetime.combine(date, ct.heure_fin))
    if fin <= debut:  # créneau nocturne résiduel : borne haute + 1 jour
        fin += timedelta(days=1)
    return debut, fin


def fenetre_scan(affectation, date):
    """Fenêtre d'ouverture du QR : début − tolérance anticipée → fin + tolérance clôture."""
    debut, fin = horodatages(affectation, date)
    return (debut - timedelta(minutes=_parametre(CLE_OUVERTURE_ANTICIPEE)),
            fin + timedelta(minutes=_parametre(CLE_TOLERANCE_CLOTURE)))


def seances_du_jour(user, date=None, *, inclure_toutes=False):
    """Séances du jour lisibles par `user` (les siennes + toutes pour DFRC/secrétariat)."""
    from edts.models import AffectationCreneau

    if date is None:
        date = timezone.localdate()
    roles = {'ADMIN', 'INJS_ADMIN', 'CHEF_INJS_ADMIN', 'SECRETARIAT', 'CHEF_SECRETARIAT',
             'DIRECTION'}
    peut_voir_tout = inclure_toutes or (user.role or '').upper() in roles
    qs = (AffectationCreneau.objects
          .filter(actif=True, emploi_du_temps__statut__in=('VALIDE', 'PUBLIE'))
          .select_related('creneau_template', 'emploi_du_temps', 'emploi_du_temps__annee_academique',
                          'groupe', 'formation')
          .order_by('creneau_template__heure_debut'))
    resultat = []
    for affectation in qs:
        if not est_seance_du_jour(affectation, date):
            continue
        if not peut_voir_tout and affectation.enseignant_id != user.id:
            continue
        debut, fin = horodatages(affectation, date)
        resultat.append({
            'id': affectation.id,
            'date': date.isoformat(),
            'intitule': affectation.intitule or str(affectation.creneau_template),
            'nature': affectation.nature,
            'salle': affectation.salle_nom,
            'groupe': affectation.groupe_id,
            'groupe_libelle': (getattr(affectation.groupe, 'nom', '')
                               or getattr(affectation.groupe, 'libelle', ''))
            if affectation.groupe_id else '',
            'formation': affectation.formation_id,
            'formation_libelle': getattr(affectation.formation, 'intitule', '') if affectation.formation_id else '',
            'enseignant_nom': affectation.enseignant_nom,
            'debut': debut.isoformat(),
            'fin': fin.isoformat(),
            'peut_gerer': peut_gerer_seance(user, affectation),
        })
    return resultat


# ---------------------------------------------------------------------------
# Droits et effectifs
# ---------------------------------------------------------------------------

def peut_gerer_seance(user, affectation):
    """Enseignant affecté, encadrant, secrétariat ou DFRC — jamais le simple auditeur."""
    role = (getattr(user, 'role', '') or '').upper()
    if role in {'ADMIN', 'INJS_ADMIN', 'CHEF_INJS_ADMIN', 'SECRETARIAT',
                'CHEF_SECRETARIAT', 'DIRECTION'}:
        return True
    if role in {'ENCADRANT', 'FORMATEUR'} and affectation.enseignant_id == user.id:
        return True
    return False


def membres_groupe(affectation):
    """Participants LMD du groupe de la séance (affectations de groupe actives)."""
    if not affectation.groupe_id:
        return Participant.objects.none()
    from scolarite.models import AffectationGroupe

    ids = (AffectationGroupe.objects
           .filter(groupe_id=affectation.groupe_id, active=True,
                   inscription__etudiant__participant__isnull=False)
           .values_list('inscription__etudiant__participant_id', flat=True))
    return Participant.objects.filter(pk__in=set(ids)).order_by('nom', 'prenom')


def pointages_du_jour(affectation, date):
    return {p.participant_id: p for p in Pointage.objects.filter(
        seance_edt=affectation, date_journee=date, participant__isnull=False)}


def ecue_de_seance(affectation):
    """ECUE de la séance via **son** affectation pédagogique (chaîne LMD).

    Retourne ``None`` si la séance n'est pas rattachée à une affectation
    pédagogique : aucune déduction depuis un module ou un groupe n'est tentée
    (convention « rattachement manuel et explicite » de l'EDT).
    """
    if not affectation.affectation_pedagogique_id:
        return None
    return getattr(affectation.affectation_pedagogique, 'ecue', None)


# ---------------------------------------------------------------------------
# Personnes du badgeage (auditeur, enseignant, encadrant)
# ---------------------------------------------------------------------------

def filtres_personne(type_personne, personne):
    """Champs de ``Pointage`` identifiant la personne selon son type.

    Le socle présences porte trois FK distinctes (``participant``,
    ``formateur``, ``encadrant``) : cette fonction est la seule à savoir
    laquelle utiliser, pour que les deux canaux (EDT/LMD et legacy mobile)
    appliquent la même convention sans dupliquer la Table de correspondance.
    """
    if type_personne == 'formateur':
        return {'formateur': personne}
    if type_personne == 'encadrant':
        return {'encadrant': personne}
    return {'participant': personne}


def libelle_personne(personne, type_personne='participant'):
    """``(numero, nom, prenom)`` d'une personne de badgeage, quel que soit son type."""
    numero = (
        getattr(personne, 'matricule', None)
        or getattr(personne, 'numerobadge', None)
        or getattr(personne, 'numero', '')
        or ''
    )
    nom = getattr(personne, 'nom', None) or getattr(personne, 'last_name', '') or ''
    prenom = getattr(personne, 'prenom', None) or getattr(personne, 'first_name', '') or ''
    if not nom and hasattr(personne, 'get_full_name'):
        nom = (personne.get_full_name() or '').strip()
    if not nom:
        nom = getattr(personne, 'username', '') or ''
    return numero, nom, prenom


def enseignant_autorise(affectation, user):
    """L'intervenant désigné de la séance est-il cet utilisateur ?

    La référence est **l'affectation elle-même**, jamais un rapprochement par
    nom : ``AffectationCreneau.enseignant_id`` (compte enseignant/encadrant du
    créneau) puis ``affectation_pedagogique.enseignant.user`` (socle LMD).
    Un encadrant désigné sur le créneau est donc couvert par la même règle.
    """
    if user is None or not getattr(user, 'pk', None):
        return False
    if affectation.enseignant_id and affectation.enseignant_id == user.pk:
        return True
    formateur = affectation.formateur if affectation.formateur_id else None
    if formateur is not None and formateur.user_id == user.pk:
        return True
    if not affectation.affectation_pedagogique_id:
        return False
    enseignant = getattr(affectation.affectation_pedagogique, 'enseignant', None)
    return bool(enseignant is not None and enseignant.user_id == user.pk)


def autorisation_badgeage(user, personne, type_personne, affectation):
    """Contrôle d'accès au badgeage QR d'une séance LMD.

    Retourne ``(ok, code, detail, status_code)`` :

    - **auditeur** : doit être inscrit dans le groupe de la séance ;
    - **enseignant / encadrant** : doit être l'intervenant désigné du créneau
      (cf. ``enseignant_autorise``), jamais déduit de son nom.
    """
    if type_personne == 'participant':
        if affectation.groupe_id is None:
            return True, None, None, None
        if membres_groupe(affectation).filter(pk=personne.pk).exists():
            return True, None, None, None
        return (
            False,
            'NOT_IN_LIST',
            "Vous n'êtes pas inscrit(e) dans le groupe de cette séance.",
            403,
        )
    if enseignant_autorise(affectation, user):
        return True, None, None, None
    return (
        False,
        'UTILISATEUR_NON_AUTORISE',
        "Vous n'êtes pas l'intervenant affecté à cette séance.",
        403,
    )


# ---------------------------------------------------------------------------
# QR de séance
# ---------------------------------------------------------------------------

def jeton_actif(affectation, date):
    return (QRToken.objects
            .filter(seance_edt=affectation, actif=True, expire_at__gt=timezone.now())
            .order_by('-created_at').first())


@transaction.atomic
def generer_jeton(request, affectation, date):
    """Désactive les jetons du jour et émet un QR valable jusqu'à fin + tolérance."""
    QRToken.objects.filter(seance_edt=affectation, actif=True).update(actif=False)
    _, fin = horodatages(affectation, date)
    expire = fin + timedelta(minutes=_parametre(CLE_TOLERANCE_CLOTURE))
    jeton = QRToken.objects.create(
        seance_edt=affectation, actif=True, expire_at=expire,
        genere_par=request.user if request.user.is_authenticated else None,
    )
    AuditLog.objects.create(
        action=AuditLog.Action.FORMATION_QR_GENERATE,
        acteur=request.user, acteur_label=request.user.get_full_name() or request.user.username,
        cible_type='seance_edt', cible_numero=str(affectation.pk),
        cible_nom=affectation.intitule or str(affectation.creneau_template),
        extra={'date': date.isoformat(), 'token': str(jeton.token), 'canal': 'EDT_LMD'},
    )
    return jeton


def resoudre_jeton_lmd(token):
    """Résout un jeton QR de séance LMD.

    Retourne ``(jeton, erreur)``. Un QR **remplacé** (régénéré par
    l'enseignant) est suivi automatiquement tant que son remplaçant est valide ;
    un QR expiré ou dont la séance n'a plus de jeton actif est refusé
    (``TOKEN_EXPIRED``) — c'est la partie serveur de l'anti-rejeu.
    """
    from django.core.exceptions import ValidationError

    try:
        jeton = (QRToken.objects
                 .select_related(
                     'seance_edt__creneau_template',
                     'seance_edt__emploi_du_temps__annee_academique',
                     'seance_edt__groupe', 'seance_edt__formation',
                     'seance_edt__affectation_pedagogique__enseignant',
                 )
                 .filter(token=token).first())
    except (ValidationError, ValueError, TypeError):
        jeton = None
    if jeton is None or jeton.seance_edt_id is None:
        return None, {'code': 'INVALID_TOKEN',
                      'detail': 'QR code inconnu ou hors séance LMD.'}
    if not jeton.is_valid:
        remplacement = (QRToken.objects
                        .filter(seance_edt=jeton.seance_edt, actif=True)
                        .select_related('seance_edt')
                        .order_by('-created_at').first())
        if remplacement is None or not remplacement.is_valid:
            return None, {'code': 'TOKEN_EXPIRED',
                          'detail': 'QR code expiré — demandez un réaffichage.'}
        jeton = remplacement
    return jeton, None


# ---------------------------------------------------------------------------
# Badgeage automatique (scan du QR)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Contrôle de périmètre géographique (décision métier A-02 du 26/09/2026)
# ---------------------------------------------------------------------------

def _controle_geofence_edt(affectation, coords):
    """Vérifie la position transmise par le client face au site de la séance.

    Retourne ``(ok, code, detail, distance_m, rayon_m)`` avec la même convention
    que le canal legacy (`presences/views.py:_check_geofence`).

    Le site est déduit de la salle planifiée (cf. ``geofence.site_de_seance_edt``).
    Si aucun site n'est déterminable, ou si ce site n'a pas de géofence
    configurée, le contrôle est neutralisé : le comportement historique est
    alors conservé.
    """
    from . import geofence

    site = geofence.site_de_seance_edt(affectation)
    if geofence.site_non_localise(site):
        return True, None, None, None, None

    latitude = (coords or {}).get('last_latitude')
    longitude = (coords or {}).get('last_longitude')
    if latitude is None or longitude is None:
        return (
            False,
            'LOCATION_REQUIRED',
            'La géolocalisation est obligatoire pour badger cette séance.',
            None,
            None,
        )

    return geofence.verifier_position(
        site, latitude, longitude, (coords or {}).get('last_accuracy_m'))


@transaction.atomic
def badger_scan(request, *, affectation, date, personne=None, participant=None,
                device_id='', coords=None, type_personne='participant'):
    """Entrée/sortie au scan du QR — anti-fraude : 1 entrée + 1 sortie par séance.

    Le contrôle de périmètre géographique est appliqué **à l'entrée** : la sortie
    referme le pointage déjà ouvert et n'est pas re-vérifiée.

    ``participant`` est conservé comme alias historique du paramètre
    ``personne`` (appelants existants : commande de démonstration), mais seul
    ``type_personne`` décide de la FK portée par le ``Pointage``
    (auditeur / enseignant / encadrant).

    Retourne (action, pointage, None) ou (None, None, réponse-dict d'erreur).
    """
    personne = personne if personne is not None else participant
    now = timezone.now()
    debut, fin = horodatages(affectation, date)
    ouverture, cloture = fenetre_scan(affectation, date)
    if now < ouverture:
        return None, None, {'code': 'TROP_TOT',
                            'detail': 'Le QR de cette séance n’est pas encore actif.'}
    if now > cloture:
        return None, None, {'code': 'HORS_FENETRE',
                            'detail': 'La fenêtre de badgeage de cette séance est fermée.'}

    filtre_personne = filtres_personne(type_personne, personne)
    verrou = (Pointage.objects
              .filter(seance_edt=affectation, date_journee=date, **filtre_personne)
              .select_for_update())
    termine_existant = verrou.filter(timestamp_sortie__isnull=False).first()
    ouvert = verrou.filter(timestamp_sortie__isnull=True).order_by('-timestamp_entree').first()

    if ouvert is not None:
        ouvert.timestamp_sortie = min(now, cloture)
        ouvert.statut = Pointage.Statut.TERMINE
        ouvert.calculer_duree()
        if ouvert.statut_assiduite == Pointage.StatutAssiduite.NON_RENSEIGNE or not ouvert.statut_assiduite:
            seuil_retard = debut + timedelta(minutes=_parametre(CLE_TOLERANCE_RETARD))
            if ouvert.timestamp_entree <= seuil_retard:
                ouvert.statut_assiduite = Pointage.StatutAssiduite.PRESENT
        ouvert.save()
        _log_scan(AuditLog.Action.SCAN_SECURE_SORTIE, request, personne, affectation,
                  ouvert, device_id, {'duree_minutes': float(ouvert.duree_presence_minutes or 0)},
                  type_personne=type_personne)
        return 'SORTIE', ouvert, None

    if termine_existant is not None:
        return None, None, {'code': 'ALREADY_SCANNED',
                            'detail': 'Vous avez déjà pointé (entrée + sortie) pour cette séance.'}

    # Décision métier A-02 : alerte ET refus hors périmètre. Le refus précède la
    # création du pointage — aucun pointage n'est écrit si la position est rejetée.
    geo_ok, geo_code, geo_detail, distance_m, rayon_m = _controle_geofence_edt(affectation, coords)
    if not geo_ok:
        _log_scan(AuditLog.Action.OUT_OF_GEOFENCE, request, personne, affectation,
                  None, device_id, {
                      'code': geo_code,
                      'detail': geo_detail,
                      'distance_m': distance_m,
                      'rayon_m': rayon_m,
                      'latitude': (coords or {}).get('last_latitude'),
                      'longitude': (coords or {}).get('last_longitude'),
                  }, type_personne=type_personne)
        return None, None, {'code': geo_code, 'detail': geo_detail}

    seuil_retard = debut + timedelta(minutes=_parametre(CLE_TOLERANCE_RETARD))
    pointage = Pointage.objects.create(
        seance_edt=affectation,
        session=None,
        date_journee=date,
        timestamp_entree=now,
        statut=Pointage.Statut.EN_COURS,
        statut_assiduite=(Pointage.StatutAssiduite.RETARD if now > seuil_retard
                          else Pointage.StatutAssiduite.PRESENT),
        device_id=(device_id or '')[:255],
        annee_academique_id=affectation.emploi_du_temps.annee_academique_id,
        groupe_lmd_id=affectation.groupe_id,
        # Comme le canal legacy, l'entrée ouvre le suivi de présence : le
        # heartbeat démarre côté client juste après (last_heartbeat_at = entrée).
        last_heartbeat_at=now,
        ecue_lmd=ecue_de_seance(affectation),
        **filtre_personne,
        **(coords or {}),
    )
    _log_scan(AuditLog.Action.SCAN_SECURE_ENTREE, request, personne, affectation,
              pointage, device_id, {
                  'retard': pointage.statut_assiduite == Pointage.StatutAssiduite.RETARD,
                  'distance_m': distance_m,
                  'rayon_m': rayon_m,
              }, type_personne=type_personne)
    return 'ENTREE', pointage, None


def _log_scan(action, request, personne, affectation, pointage, device_id, extra,
              type_personne='participant'):
    numero, nom, prenom = libelle_personne(personne, type_personne)
    AuditLog.objects.create(
        action=action,
        acteur=request.user if request and request.user.is_authenticated else None,
        acteur_label=(request.user.get_full_name() or request.user.username)
        if request and request.user.is_authenticated else 'Mobile',
        cible_type=type_personne,
        cible_numero=numero,
        cible_nom=f'{nom} {prenom}'.strip(),
        pointage=pointage,
        device_id=device_id or '',
        extra={'canal': 'EDT_LMD', 'seance_edt': affectation.pk, **(extra or {})},
    )


# ---------------------------------------------------------------------------
# Heartbeat d'une séance LMD (app mobile : /api/scan/secure/heartbeat/)
# ---------------------------------------------------------------------------

def _heartbeat_audit_du(previous_heartbeat_at):
    """Un heartbeat conforme n'est tracé au journal que périodiquement."""
    interval = int(getattr(settings, 'MOBILE_HEARTBEAT_AUDIT_INTERVAL_SECONDS', 600))
    if previous_heartbeat_at is None:
        return True
    return (timezone.now() - previous_heartbeat_at).total_seconds() >= interval


@transaction.atomic
def heartbeat_seance(request, *, personne, affectation, date, device_id='', coords=None,
                     type_personne='participant'):
    """Heartbeat du pointage **ouvert** d'une séance LMD.

    Retourne ``(payload, erreur)`` : ``payload`` est le corps de réponse (200) à
    renvoyer tel quel, ``erreur`` un dict ``{code, detail}`` (400).

    Règles identiques au canal legacy (``presences.views.secure_scan_heartbeat``) :
    la position est vérifiée **côté serveur** ; une sortie temporaire du périmètre
    ne supprime pas la présence déjà validée, elle alimente
    ``outside_geofence_count`` (anomalie tracée) et la sortie automatique n'est
    déclenchée qu'après ``MOBILE_GEOFENCE_OUTSIDE_CONFIRMATIONS`` confirmations
    consécutives hors zone.
    """
    pointage = (Pointage.objects.select_for_update()
                .filter(seance_edt=affectation, date_journee=date,
                        timestamp_sortie__isnull=True,
                        **filtres_personne(type_personne, personne))
                .order_by('-timestamp_entree').first())
    if pointage is None:
        return None, {'code': 'NO_OPEN_SESSION',
                      'detail': 'Aucune présence ouverte à mettre à jour pour ce QR.'}
    return appliquer_heartbeat(
        request, pointage, affectation=affectation, coords=coords,
        device_id=device_id, type_personne=type_personne,
    )




def appliquer_heartbeat(request, pointage, *, affectation, coords=None, device_id='',
                        type_personne='participant'):
    """Applique un heartbeat géolocalisé à un pointage ouvert (source unique).

    Utilisé par le canal LMD ; la logique est celle du canal legacy, factorisée
    ici pour qu'aucune règle de périmètre ne puisse diverger entre les canaux.
    """
    now = timezone.now()
    coords = coords or {}
    latitude = coords.get('last_latitude')
    longitude = coords.get('last_longitude')
    accuracy_m = coords.get('last_accuracy_m')

    geo_ok, geo_code, geo_detail, distance_m, rayon_m = _controle_geofence_edt(
        affectation, coords)
    outside_limit = max(1, int(getattr(settings, 'MOBILE_GEOFENCE_OUTSIDE_CONFIRMATIONS', 2)))
    previous_heartbeat_at = pointage.last_heartbeat_at

    pointage.last_heartbeat_at = now
    pointage.last_latitude = latitude
    pointage.last_longitude = longitude
    pointage.last_accuracy_m = accuracy_m
    pointage.last_battery_level = coords.get('last_battery_level')
    pointage.last_is_charging = coords.get('last_is_charging')
    champs_position = [
        'last_heartbeat_at', 'last_latitude', 'last_longitude', 'last_accuracy_m',
        'last_battery_level', 'last_is_charging', 'updated_at',
    ]

    if geo_ok:
        pointage.outside_geofence_count = 0
        if pointage.statut == Pointage.Statut.HORS_LIGNE_SUSPECT:
            pointage.statut = Pointage.Statut.EN_COURS
        pointage.save(update_fields=champs_position + ['outside_geofence_count', 'statut'])
        if _heartbeat_audit_du(previous_heartbeat_at):
            _log_scan(AuditLog.Action.SCAN_HEARTBEAT, request, pointage.personne,
                      affectation, pointage, device_id, {
                          'distance_m': round(distance_m, 1) if distance_m is not None else None,
                          'rayon_m': round(rayon_m, 1) if rayon_m is not None else None,
                          'accuracy_m': accuracy_m,
                          'battery_level': coords.get('last_battery_level'),
                          'is_charging': coords.get('last_is_charging'),
                      }, type_personne=type_personne)
        return ({
            'detail': 'Heartbeat enregistré.',
            'canal': 'EDT_LMD',
            'statut': pointage.statut,
            'outside_geofence_count': pointage.outside_geofence_count,
            'distance_m': round(distance_m, 1) if distance_m is not None else None,
            'rayon_m': round(rayon_m, 1) if rayon_m is not None else None,
            'geofence_code': None,
        }, None)

    pointage.outside_geofence_count = (pointage.outside_geofence_count or 0) + 1
    extra = {
        'code': geo_code,
        'detail': geo_detail,
        'distance_m': round(distance_m, 1) if distance_m is not None else None,
        'rayon_m': round(rayon_m, 1) if rayon_m is not None else None,
        'accuracy_m': accuracy_m,
        'outside_geofence_count': pointage.outside_geofence_count,
        'outside_geofence_limit': outside_limit,
    }

    if pointage.outside_geofence_count >= outside_limit:
        _, cloture = fenetre_scan(affectation, pointage.date_journee)
        pointage.timestamp_sortie = min(now, cloture)
        pointage.statut = Pointage.Statut.SORTIE_AUTO
        pointage.calculer_duree()
        pointage.save(update_fields=champs_position + [
            'timestamp_sortie', 'statut', 'duree_presence_minutes',
            'outside_geofence_count',
        ])
        _log_scan(AuditLog.Action.OUT_OF_GEOFENCE, request, pointage.personne,
                  affectation, pointage, device_id, extra, type_personne=type_personne)
        _log_scan(AuditLog.Action.AUTO_EXIT, request, pointage.personne,
                  affectation, pointage, device_id, extra, type_personne=type_personne)
        return ({
            'detail': 'Sortie automatique déclenchée (hors périmètre).',
            'action': 'SORTIE_AUTO',
            'canal': 'EDT_LMD',
            'statut': pointage.statut,
            'timestamp_sortie': pointage.timestamp_sortie,
            'duree_session_minutes': float(pointage.duree_presence_minutes or 0),
            'motif': geo_code or 'OUT_OF_GEOFENCE',
            **extra,
        }, None)

    pointage.statut = Pointage.Statut.HORS_LIGNE_SUSPECT
    pointage.save(update_fields=champs_position + ['statut', 'outside_geofence_count'])
    _log_scan(AuditLog.Action.SCAN_HEARTBEAT, request, pointage.personne,
              affectation, pointage, device_id, extra, type_personne=type_personne)
    return ({
        'detail': geo_detail or 'Position hors périmètre enregistrée (présence conservée).',
        'canal': 'EDT_LMD',
        'statut': pointage.statut,
        'distance_m': extra['distance_m'],
        'rayon_m': extra['rayon_m'],
        'geofence_code': geo_code,
        'outside_geofence_count': pointage.outside_geofence_count,
    }, None)


# ---------------------------------------------------------------------------
# État du badgeage d'une séance (check-status mobile)
# ---------------------------------------------------------------------------

def etat_badgeage_seance(request, *, personne, affectation, date,
                         type_personne='participant', coords=None):
    """État du badgeage d'une séance LMD (pour ``/scan/secure/check-status/``).

    Reprend le contrat de la voie legacy (``statut``, ``action_suivante``,
    ``heure_entree``, ``seance_intitule``) et y ajoute l'état de périmètre calculé
    **côté serveur**, afin que l'application mobile affiche la même information
    sans jamais décider elle-même de la validité de la position.
    """
    from . import geofence

    debut, fin = horodatages(affectation, date)
    label = affectation.intitule or str(affectation.creneau_template)
    site = geofence.site_de_seance_edt(affectation)
    configure = not geofence.site_non_localise(site)
    info = {
        'canal': 'EDT_LMD',
        'seance_id': affectation.pk,
        'date': date.isoformat(),
        'type_personne': type_personne,
        'seance_intitule': label,
        'debut': debut.isoformat(),
        'fin': fin.isoformat(),
        'geofence_configured': configure,
        'geofence_latitude': float(site.geofence_latitude) if configure else None,
        'geofence_longitude': float(site.geofence_longitude) if configure else None,
        'geofence_rayon_m': geofence.rayon_du_site(site) if configure else None,
        'distance_m': None,
        'in_geofence': None,
        'accuracy_ok': None,
        'accuracy_max_m': float(getattr(settings, 'MOBILE_GEOFENCE_MAX_ACCURACY_M', 80)),
    }
    latitude = (coords or {}).get('last_latitude')
    longitude = (coords or {}).get('last_longitude')
    accuracy_m = (coords or {}).get('last_accuracy_m')
    if configure and latitude is not None and longitude is not None:
        distance = geofence.distance_meters(
            latitude, longitude, site.geofence_latitude, site.geofence_longitude)
        info['distance_m'] = round(distance, 1)
        info['in_geofence'] = distance <= info['geofence_rayon_m']
    if accuracy_m is not None:
        info['accuracy_ok'] = float(accuracy_m) <= info['accuracy_max_m']

    filtre = filtres_personne(type_personne, personne)
    ouvert = (Pointage.objects
              .filter(seance_edt=affectation, date_journee=date,
                      timestamp_sortie__isnull=True, **filtre)
              .order_by('-timestamp_entree').first())
    if ouvert is not None:
        info.update({
            'statut': 'EN_SALLE',
            'action_suivante': 'SORTIE',
            'heure_entree': timezone.localtime(ouvert.timestamp_entree).strftime('%H:%M'),
        })
        return info

    termine = Pointage.objects.filter(
        seance_edt=affectation, date_journee=date,
        timestamp_sortie__isnull=False, **filtre).exists()
    if termine:
        info.update({'statut': 'TERMINE', 'action_suivante': None, 'heure_entree': None})
        return info

    if not est_seance_du_jour(affectation, date):
        info.update({'statut': 'HORS_SEANCE', 'action_suivante': None, 'heure_entree': None})
        return info

    info.update({'statut': 'ABSENT', 'action_suivante': 'ENTREE', 'heure_entree': None})
    return info


# ---------------------------------------------------------------------------
# Émargement manuel de masse (cases enseignant / administratif habilité)
# ---------------------------------------------------------------------------

#: Statuts pédagogiques autorisés à l'émargement manuel (modèle 08.4).
STATUTS_EMARGEMENT = {
    'PRESENT': Pointage.StatutAssiduite.PRESENT,
    'RETARD': Pointage.StatutAssiduite.RETARD,
    'ABSENT': Pointage.StatutAssiduite.ABSENT,
    'ABSENCE_JUSTIFIEE': Pointage.StatutAssiduite.ABSENCE_JUSTIFIEE,
    'EXCUSE': Pointage.StatutAssiduite.EXCUSE,
}


class ErreurEmargement(Exception):
    def __init__(self, detail, status_code=400, code='EMARGEMENT_REFUSE'):
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code
        self.code = code


@transaction.atomic
def emarger(request, affectation, date, entries, *, motif_global=''):
    """Émargement manuel de masse. Règle « forçage contrôlé » (08.14) : toute
    correction d'un pointage existant exige un motif, tracé avant/après."""
    membres_ids = set(membres_groupe(affectation).values_list('id', flat=True))
    existants = pointages_du_jour(affectation, date)
    debut, fin = horodatages(affectation, date)
    journal = []
    lignes_traitees = set()

    for index, entree in enumerate(entries):
        statut_cible = (entree.get('statut') or '').upper()
        if statut_cible not in STATUTS_EMARGEMENT:
            raise ErreurEmargement(
                f"Ligne {index + 1} : statut « {entree.get('statut')} » inconnu "
                f"(attendu : {', '.join(sorted(STATUTS_EMARGEMENT))}).")
        pid = entree.get('participant')
        try:
            pid = int(pid)
        except (TypeError, ValueError):
            raise ErreurEmargement(f'Ligne {index + 1} : identifiant participant invalide.')
        if pid in lignes_traitees:
            raise ErreurEmargement(f'Ligne {index + 1} : participant {pid} dupliqué.')
        lignes_traitees.add(pid)
        if membres_ids and pid not in membres_ids:
            raise ErreurEmargement(
                f'Ligne {index + 1} : ce participant n’est pas inscrit dans le groupe de la séance '
                '(règle 1 — présence réservée aux inscrits).', status_code=403, code='NOT_IN_GROUP')
        participant = Participant.objects.filter(pk=pid).first()
        if participant is None:
            raise ErreurEmargement(f'Ligne {index + 1} : participant {pid} introuvable.')

        motif = (entree.get('motif') or motif_global or '').strip()
        assiduite = STATUTS_EMARGEMENT[statut_cible]
        pointage = existants.get(pid)
        avant = None

        if pointage is None:
            if statut_cible == 'PRESENT':
                pointage = Pointage.objects.create(
                    participant=participant, seance_edt=affectation, date_journee=date,
                    timestamp_entree=debut, statut=Pointage.Statut.TERMINE,
                    statut_assiduite=assiduite, device_id='EMARGEMENT_MANUEL',
                    annee_academique_id=affectation.emploi_du_temps.annee_academique_id,
                    groupe_lmd_id=affectation.groupe_id,
                )
                pointage.timestamp_sortie = fin
                pointage.calculer_duree()
                pointage.save()
            elif statut_cible == 'RETARD':
                seuil = debut + timedelta(minutes=_parametre(CLE_TOLERANCE_RETARD))
                pointage = Pointage.objects.create(
                    participant=participant, seance_edt=affectation, date_journee=date,
                    timestamp_entree=seuil + timedelta(minutes=1), statut=Pointage.Statut.TERMINE,
                    statut_assiduite=assiduite, device_id='EMARGEMENT_MANUEL',
                    annee_academique_id=affectation.emploi_du_temps.annee_academique_id,
                    groupe_lmd_id=affectation.groupe_id,
                )
                pointage.timestamp_sortie = fin
                pointage.calculer_duree()
                pointage.save()
            else:
                # Absence : ligne administrative de durée nulle (aucun badge),
                # pour que l'état nominal soit opposable et traçable.
                pointage = Pointage.objects.create(
                    participant=participant, seance_edt=affectation, date_journee=date,
                    timestamp_entree=debut, timestamp_sortie=debut,
                    statut=Pointage.Statut.FORCE_DFRC, statut_assiduite=assiduite,
                    device_id='EMARGEMENT_MANUEL',
                    annee_academique_id=affectation.emploi_du_temps.annee_academique_id,
                    groupe_lmd_id=affectation.groupe_id,
                )
                pointage.calculer_duree()
                pointage.save()
            action = AuditLog.Action.FORCE_ENTREE
        else:
            # Correction d'un pointage existant → motif OBLIGATOIRE (08.14).
            if not motif:
                raise ErreurEmargement(
                    f'Ligne {index + 1} : motif obligatoire pour corriger un pointage '
                    f'({participant.nom} {participant.prenom} a déjà un badgeage).')
            avant = {
                'statut': pointage.statut,
                'statut_assiduite': pointage.statut_assiduite,
                'entree': pointage.timestamp_entree.isoformat(),
                'sortie': pointage.timestamp_sortie.isoformat() if pointage.timestamp_sortie else None,
            }
            pointage.statut = Pointage.Statut.FORCE_DFRC
            pointage.statut_assiduite = assiduite
            if statut_cible in ('ABSENT', 'ABSENCE_JUSTIFIEE', 'EXCUSE'):
                pointage.timestamp_entree = debut
                pointage.timestamp_sortie = debut
            pointage.save()
            if pointage.timestamp_sortie is None:
                pointage.calculer_duree()
                pointage.save(update_fields=['duree_presence_minutes'])
            action = (AuditLog.Action.FORCE_SORTIE
                      if avant['sortie'] else AuditLog.Action.FORCE_ENTREE)

        # Raccordement ECUE (chaîne LMD) : la séance porte l'affectation
        # pédagogique, donc l'ECUE. Aucune déduction depuis le groupe.
        if pointage.ecue_lmd_id is None:
            ecue = ecue_de_seance(affectation)
            if ecue is not None:
                pointage.ecue_lmd = ecue
                pointage.save(update_fields=['ecue_lmd'])

        nouvelle = {
            'statut': pointage.statut,
            'statut_assiduite': pointage.statut_assiduite,
        }
        AuditLog.objects.create(
            action=action,
            acteur=request.user,
            acteur_label=request.user.get_full_name() or request.user.username,
            cible_type='participant',
            cible_numero=getattr(participant, 'matricule', '') or '',
            cible_nom=f'{participant.nom} {participant.prenom}'.strip(),
            pointage=pointage,
            extra={'canal': 'EDT_LMD', 'seance_edt': affectation.pk, 'date': date.isoformat(),
                   'motif': motif, 'avant': avant, 'apres': nouvelle,
                   'source': 'EMARGEMENT_MANUEL'},
        )
        journal.append({
            'participant': pid,
            'statut': assiduite,
            'pointage_id': pointage.pk,
            'corrige': avant is not None,
        })
    return journal


# ---------------------------------------------------------------------------
# Clôture automatique de séance
# ---------------------------------------------------------------------------

@transaction.atomic
def auto_clore(request, affectation, date):
    """Clôture de séance : ouvertures sans sortie → sortie = fin (+ tolérance) ;
    inscrits sans aucun badge → ligne « absent non badgé »."""
    fin = horodatages(affectation, date)[1]
    cloture = fin + timedelta(minutes=_parametre(CLE_TOLERANCE_CLOTURE))
    ouverts = Pointage.objects.filter(
        seance_edt=affectation, date_journee=date, timestamp_sortie__isnull=True)
    nb_clotures = 0
    for pointage in ouverts:
        pointage.timestamp_sortie = min(timezone.now(), cloture)
        pointage.statut = Pointage.Statut.SORTIE_AUTO
        pointage.calculer_duree()
        pointage.save()
        AuditLog.objects.create(
            action=AuditLog.Action.AUTO_EXIT,
            acteur=request.user if request and request.user.is_authenticated else None,
            acteur_label=(request.user.get_full_name() or request.user.username)
            if request and getattr(request, 'user', None) and request.user.is_authenticated else 'Système',
            cible_type='participant',
            cible_numero=getattr(pointage.participant, 'matricule', '') or '' if pointage.participant else '',
            cible_nom=(f'{pointage.participant.nom} {pointage.participant.prenom}'.strip()
                       if pointage.participant else ''),
            pointage=pointage,
            extra={'canal': 'EDT_LMD', 'seance_edt': affectation.pk, 'date': date.isoformat(),
                   'source': 'AUTOCLOTURE'},
        )
        nb_clotures += 1

    badge = set(Pointage.objects.filter(seance_edt=affectation, date_journee=date)
                .values_list('participant_id', flat=True))
    nb_absents = 0
    absents_du_jour = []
    for membre in membres_groupe(affectation).exclude(pk__in=badge):
        absents_du_jour.append(membre.pk)
        Pointage.objects.create(
            participant=membre, seance_edt=affectation, date_journee=date,
            timestamp_entree=horodatages(affectation, date)[0],
            timestamp_sortie=horodatages(affectation, date)[0],
            statut=Pointage.Statut.ABSENT_NON_BADGE,
            statut_assiduite=Pointage.StatutAssiduite.ABSENT,
            device_id='AUTOCLOTURE',
            annee_academique_id=affectation.emploi_du_temps.annee_academique_id,
            groupe_lmd_id=affectation.groupe_id,
        )
        nb_absents += 1
    QRToken.objects.filter(seance_edt=affectation, actif=True).update(actif=False)
    # Alerte d'absence ciblée (rapport de refonte, écart n°2) : les absents de
    # cette séance ne déclenchent plus seulement l'agrégat manuel global —
    # chaque franchissement de seuil notifie immédiatement la chaîne
    # Direction/Secrétariat, une fois par séance et par niveau (contrainte DB).
    nb_alertes = 0
    if _parametre(CLE_NOTIFIER_CLOTURE) and absents_du_jour:
        from .stats_services import notifier_absences_seance
        nb_alertes = notifier_absences_seance(
            affectation, date, absents_du_jour,
            utilisateur=request.user if request and request.user.is_authenticated else None,
        )
    AuditLog.objects.create(
        action=AuditLog.Action.CLOSE_SESSION,
        acteur=request.user if request and request.user.is_authenticated else None,
        acteur_label=(request.user.get_full_name() or request.user.username)
        if request and request.user.is_authenticated else 'Système',
        cible_type='seance_edt', cible_numero=str(affectation.pk),
        cible_nom=affectation.intitule or str(affectation.creneau_template),
        extra={'canal': 'EDT_LMD', 'date': date.isoformat(),
               'pointages_clotures': nb_clotures, 'absents_marques': nb_absents,
               'alertes_absence': nb_alertes},
    )
    return {'pointages_clotures': nb_clotures, 'absents_marques': nb_absents,
            'alertes_absence': nb_alertes}
