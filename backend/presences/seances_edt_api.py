"""Lot C — API « présence par QR, séance LMD » (automatique + émargement manuel).

Modèle fonctionnel MODULE 08 appliqué aux séances d'EDT (``edts.AffectationCreneau``) :

- `GET  /api/presences/seances-edt/du-jour/?date=JJJJ-MM-JJ` — séances du jour ;
- `GET  /api/presences/seances-edt/<affectation>/qr/?date=` — état du QR ;
- `POST /api/presences/seances-edt/<affectation>/qr/?date=` — générer/rafraîchir ;
- `POST /api/presences/seances-edt/scan/` {token_qr, device_id} — badge auto
  (anti-fraude : identité déduite du compte, groupe contrôlé, 1 E + 1 S) ;
- `GET  /api/presences/seances-edt/<affectation>/presences/?date=` — liste nominative ;
- `POST /api/presences/seances-edt/<affectation>/emargement/?date=` {entries, motif}
  — cases de l'enseignant / administratif habilité ; motif obligatoire pour
  corriger un badge existant (forçage contrôlé) ;
- `POST /api/presences/seances-edt/<affectation>/autoclore/?date=` — clôture auto.

Gating : classes legacy étendues (jamais restreintes) + codes CURP du catalogue
(`presences.qr.generer`, `presences.emargement.*`, `presences.seance_emargement.*`)
branchés en pilote, moteur en observation (règle du LOT 5).
"""
from datetime import date as _date_cls
from uuid import UUID

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from authentication.throttles import ScanRateThrottle
from edts.models import AffectationCreneau
from habilitations.permissions import ExigePermission

from . import seances_edt_services as service
from . import seances_supervision as supervision
from .models import Pointage
from .views import _require_mobile_device_id, _resolve_authenticated_personne


def _date(request):
    brut = (request.query_params.get('date') or '').strip()
    if not brut:
        from django.utils import timezone
        return timezone.localdate(), None
    try:
        annee, mois, jour = (int(x) for x in brut.split('-'))
        return _date_cls(annee, mois, jour), None
    except (TypeError, ValueError):
        return None, {'detail': 'Paramètre « date » invalide (JJJJ-MM-JJ attendu).'}


def _affectation_ou_404(pk):
    return AffectationCreneau.objects.select_related(
        'creneau_template', 'emploi_du_temps', 'emploi_du_temps__annee_academique',
        'groupe', 'formation').filter(pk=pk).first()


def _erreur(serviceErreur):
    return Response({'code': serviceErreur.code, 'detail': serviceErreur.detail},
                    status=serviceErreur.status_code)


def _entier(request, nom):
    """Entier optionnel : absent → ``None`` (filtre non appliqué, jamais 0)."""
    brut = (request.query_params.get(nom) or '').strip()
    if not brut:
        return None
    try:
        return int(brut)
    except (TypeError, ValueError):
        return None


@api_view(['GET'])
@permission_classes([IsAuthenticated, ExigePermission.pour('presences.emargement.consulter')])
def supervision_api(request):
    """Séances d'une journée + suivi de leurs présences (bloc « Séances en direct »).

    `GET /api/presences/seances-edt/supervision/?date=&statut=&formation_id=&groupe_id=&enseignant_id=`

    Vue **consultative** : statut de séance dérivé des horaires planifiés,
    contexte LMD par clés étrangères, présences réellement rattachées
    (``Pointage.seance_edt``). Aucune écriture, aucun badgeage, aucun QR
    généré, aucune clôture : ouvrir, filtrer ou rafraîchir le dashboard est
    sans effet de bord.
    """
    jour, err = _date(request)
    if err:
        return Response(err, status=status.HTTP_400_BAD_REQUEST)
    statut = (request.query_params.get('statut') or '').strip().upper() or None
    if statut and statut not in supervision.STATUTS_SEANCE:
        return Response(
            {'detail': 'Statut inconnu. Valeurs acceptées : '
                       + ', '.join(supervision.STATUTS_SEANCE) + '.'},
            status=status.HTTP_400_BAD_REQUEST)
    return Response(supervision.supervision_seances(
        request.user, jour,
        statut=statut,
        formation_id=_entier(request, 'formation_id'),
        groupe_id=_entier(request, 'groupe_id'),
        enseignant_id=_entier(request, 'enseignant_id'),
    ))


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def seances_du_jour(request):
    date, err = _date(request)
    if err:
        return Response(err, status=400)
    return Response(service.seances_du_jour(request.user, date))


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated, ExigePermission.pour('presences.qr.generer')])
def qr_seance(request, pk):
    affectation = _affectation_ou_404(pk)
    if affectation is None:
        return Response({'detail': 'Séance introuvable.'}, status=404)
    date, err = _date(request)
    if err:
        return Response(err, status=400)
    if not service.est_seance_du_jour(affectation, date):
        return Response({'detail': 'Aucune séance planifiée ce jour pour ce créneau.'}, status=400)
    jeton = service.jeton_actif(affectation, date)
    if request.method == 'GET':
        if jeton is None:
            return Response({'actif': False, 'token': None, 'expire_a': None})
        return Response({'actif': True, 'token': str(jeton.token),
                         'expire_a': jeton.expire_at.isoformat()})
    if not service.peut_gerer_seance(request.user, affectation):
        return Response({'detail': 'Seul l’enseignant de la séance (ou un compte habilité) '
                                   'peut ouvrir le QR.'}, status=403)
    jeton = service.generer_jeton(request, affectation, date)
    debut, _ = service.horodatages(affectation, date)
    return Response({
        'actif': True,
        'token': str(jeton.token),
        'expire_a': jeton.expire_at.isoformat(),
        'ouvre_a': debut.isoformat(),
        'url_badgeage': f'/presences/scan-edt?token={jeton.token}',
    }, status=201)


@api_view(['POST'])
@throttle_classes([ScanRateThrottle])
@permission_classes([IsAuthenticated])
def scan_seance(request):
    """Scan du QR de séance LMD par le mobile de l'auditeur (ou de l'enseignant).

    Sont acceptés : l'auditeur inscrit au groupe de la séance, ainsi que
    l'enseignant / l'encadrant **désigné sur le créneau** (affectation
    planifiée ou affectation pédagogique) — jamais un rapprochement par nom.
    """
    from uuid import UUID as _UUID

    token = (request.data.get('token_qr') or '').strip()
    if not token:
        return Response({'detail': '« token_qr » requis.'}, status=400)
    try:
        token = _UUID(token)
    except ValueError:
        return Response({'code': 'INVALID_TOKEN', 'detail': 'QR code invalide.'}, status=400)
    if getattr(request.user, 'must_change_password', False):
        return Response({'code': 'PASSWORD_CHANGE_REQUIRED',
                         'detail': 'Changez votre mot de passe avant de badger.'}, status=403)
    device_id = (request.data.get('device_id') or '').strip()
    personne, type_str, erreur = _resolve_authenticated_personne(request.user)
    if erreur is not None:
        return erreur
    device_err = _require_mobile_device_id(type_str, device_id)
    if device_err is not None:
        return device_err

    jeton, erreur = service.resoudre_jeton_lmd(token)
    if erreur is not None:
        return Response(erreur, status=400)

    affectation = jeton.seance_edt
    from django.utils import timezone
    date = timezone.localdate()
    if not service.est_seance_du_jour(affectation, date):
        return Response({'code': 'HORS_SEANCE',
                         'detail': 'Ce créneau n’a pas séance aujourd’hui.'}, status=400)

    autorise, code, detail, statut_http = service.autorisation_badgeage(
        request.user, personne, type_str, affectation)
    if not autorise:
        return Response({'code': code, 'detail': detail}, status=statut_http or 403)

    coords = {}
    for cle, champ in (('latitude', 'last_latitude'), ('longitude', 'last_longitude'),
                       ('accuracy_m', 'last_accuracy_m'), ('battery_level', 'last_battery_level'),
                       ('is_charging', 'last_is_charging')):
        if cle in (request.data or {}):
            coords[champ] = request.data.get(cle)

    action, pointage, erreur = service.badger_scan(
        request, personne=personne, affectation=affectation, date=date,
        device_id=device_id, coords=coords or None, type_personne=type_str)
    if erreur:
        return Response(erreur, status=400)
    return Response({
        'action': action,
        'canal': 'EDT_LMD',
        'type_personne': type_str,
        'seance': {'id': affectation.pk,
                   'libelle': affectation.intitule or str(affectation.creneau_template),
                   'date': date.isoformat()},
        'statut_assiduite': pointage.statut_assiduite,
        'pointage_id': pointage.pk,
    }, status=status.HTTP_201_CREATED if action == 'ENTREE' else status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated, ExigePermission.pour('presences.emargement.consulter')])
def presences_seance(request, pk):
    """Liste nominative de la séance avec états (pour les « cases » de l'écran)."""
    affectation = _affectation_ou_404(pk)
    if affectation is None:
        return Response({'detail': 'Séance introuvable.'}, status=404)
    if not service.peut_gerer_seance(request.user, affectation):
        return Response({'detail': 'Accès réservé à l’enseignant de la séance et aux '
                                   'comptes habilités.'}, status=403)
    date, err = _date(request)
    if err:
        return Response(err, status=400)
    pointages = service.pointages_du_jour(affectation, date)
    lignes = []
    membres = list(service.membres_groupe(affectation))
    for membre in membres:
        pointage = pointages.get(membre.pk)
        lignes.append({
            'participant': membre.pk,
            'matricule': getattr(membre, 'matricule', '') or getattr(membre, 'numero', ''),
            'nom': f'{membre.nom} {membre.prenom or ""}'.strip(),
            'badge_entree': pointage.timestamp_entree.isoformat() if pointage else None,
            'badge_sortie': (pointage.timestamp_sortie.isoformat()
                             if pointage and pointage.timestamp_sortie else None),
            'statut_badgeage': pointage.statut if pointage else None,
            'statut': pointage.statut_assiduite if pointage else None,
            'pointage_id': pointage.pk if pointage else None,
        })
    effectif = len(lignes)
    presents = sum(1 for l in lignes if l['statut'] in (Pointage.StatutAssiduite.PRESENT,
                                                        Pointage.StatutAssiduite.RETARD))
    retards = sum(1 for l in lignes if l['statut'] == Pointage.StatutAssiduite.RETARD)
    absents = sum(1 for l in lignes if l['statut'] in (
        Pointage.StatutAssiduite.ABSENT, Pointage.StatutAssiduite.ABSENCE_JUSTIFIEE,
        Pointage.StatutAssiduite.EXCUSE))
    # Anomalies et gestes manuels : lus sur les pointages (jamais déduits).
    presences_manuelles = sum(1 for p in pointages.values()
                              if p.device_id == 'EMARGEMENT_MANUEL')
    anomalies_gps = sum(1 for p in pointages.values()
                        if (p.outside_geofence_count or 0) > 0)
    sorties_automatiques = sum(1 for p in pointages.values()
                               if p.statut == Pointage.Statut.SORTIE_AUTO)
    absents_non_badges = sum(1 for p in pointages.values()
                             if p.statut == Pointage.Statut.ABSENT_NON_BADGE)
    return Response({
        'seance': {'id': affectation.pk, 'date': date.isoformat(),
                   'groupe_libelle': (getattr(affectation.groupe, 'nom', '')
                                      or getattr(affectation.groupe, 'libelle', ''))
                   if affectation.groupe_id else '',
                   'intitule': affectation.intitule or str(affectation.creneau_template)},
        'effectif': effectif,
        'attendus': effectif,
        'presents': presents,
        'retards': retards,
        'absents': absents,
        'non_pointes': max(0, effectif - len(pointages)),
        'presences_manuelles': presences_manuelles,
        'anomalies_gps': anomalies_gps,
        'sorties_automatiques': sorties_automatiques,
        'absents_non_badges': absents_non_badges,
        'lignes': lignes,
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated, ExigePermission.pour('presences.emargement.saisir')])
def emargement_seance(request, pk):
    """Émargement manuel de masse (badger tout le monde, puis exceptions)."""
    affectation = _affectation_ou_404(pk)
    if affectation is None:
        return Response({'detail': 'Séance introuvable.'}, status=404)
    if not service.peut_gerer_seance(request.user, affectation):
        return Response({'detail': 'Seuls l’enseignant de la séance, le secrétariat et la '
                                   'direction émargent.'}, status=403)
    date, err = _date(request)
    if err:
        return Response(err, status=400)
    if not service.est_seance_du_jour(affectation, date):
        return Response({'detail': 'Aucune séance planifiée ce jour pour ce créneau.'}, status=400)
    entries = request.data.get('entries')
    if not isinstance(entries, list) or not entries:
        return Response({'detail': '« entries » : liste non vide attendue '
                                   '([{participant, statut, motif?}]).'}, status=400)
    motif_global = (request.data.get('motif') or '').strip()
    try:
        journal = service.emarger(request, affectation, date, entries, motif_global=motif_global)
    except service.ErreurEmargement as exc:
        return _erreur(exc)
    return Response({'detail': f'{len(journal)} ligne(s) d’émargement enregistrée(s).',
                     'journal': journal}, status=201)


@api_view(['POST'])
@permission_classes([IsAuthenticated, ExigePermission.pour('presences.seance_emargement.cloturer')])
def autoclore_seance(request, pk):
    """Clôture de séance à la demande (les commandes planifiées restent actives)."""
    affectation = _affectation_ou_404(pk)
    if affectation is None:
        return Response({'detail': 'Séance introuvable.'}, status=404)
    if not service.peut_gerer_seance(request.user, affectation):
        return Response({'detail': 'Clôture réservée à l’enseignant de la séance et aux '
                                   'comptes habilités.'}, status=403)
    date, err = _date(request)
    if err:
        return Response(err, status=400)
    resultat = service.auto_clore(request, affectation, date)
    return Response(resultat)
