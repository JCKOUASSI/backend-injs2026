"""API du module GET-INJS (lot L8) — Emploi du temps.

Corrections appliquées (audit GET-INJS du 2026-09-15) :
- sérialiseurs alignés sur les champs RÉELS des modèles (plus de `_population_label`,
  `creneaux`, etc. — sources d'erreurs 500 systématiques) ;
- validation d'entrée : 400/409 explicites au lieu d'exceptions non traitées (500) ;
- filtres de listes effectifs (par EDT, semaine, enseignant, groupe, salle, statut…) —
  sans eux, l'écran affichait toutes les affectations de tous les EDT mélangées ;
- workflow verrouillé : BROUILLON → EN_VALIDATION → VALIDE → PUBLIE (+ archiver,
  dépublier) ; le statut n'est plus modifiable par PATCH, la validation reste
  réservée à DIRECTION/ADMIN (la faille d'escalade par écriture directe du statut
  est fermée) ;
- gel d'édition : un EDT VALIDÉ/PUBLIÉ/ARCHIVÉ refuse toute écriture d'affectation
  hors rôles de validation (qui doivent d'abord dépublier) ;
- export CSV à la demande d'un EDT donné (P20, côté module) ;
- journal d'audit via scolarite.journaliser() (opérations sensibles tracées) ;
- détection de conflits portée par `services.detecter_conflits` (portable SQLite,
  globale entre EDT, auto-clôture des conflits obsolètes).
"""

import csv

from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.db.models import Count, Q
from django.http import HttpResponse
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from . import services
from .models import (
    EDT_STATUT_CHOICES,
    NATURE_CHOICES,
    POPULATION_TYPE_CHOICES,
    AffectationCreneau,
    ConflitCreneau,
    CreneauTemplate,
    EmploiDuTemps,
)
from .permissions import (
    IsEdtPlanification,
    IsEdtReadOnlyOrPlanification,
    IsEdtValidation,
)

EDT_STATUTS = {clef for clef, _ in EDT_STATUT_CHOICES}
NATURES = {clef for clef, _ in NATURE_CHOICES}
POPULATION_TYPES = {clef for clef, _ in POPULATION_TYPE_CHOICES}

# Statuts dont l'EDT est « gelé » : plus de modification de placement sans
# passage par un rôle de validation (dépublication).
EDT_GELE = {'VALIDE', 'PUBLIE', 'ARCHIVE'}
EDT_MODIFIABLE = {'BROUILLON', 'EN_VALIDATION'}

# En-têtes de colonnes tolérés par la pagination légère des listes.
LIMITE_DEFAUT_LISTE = 1000


# ---------------------------------------------------------------------------
# Aides
# ---------------------------------------------------------------------------


def _reponse_validation(message, code=status.HTTP_400_BAD_REQUEST):
    return Response({'detail': message, 'erreurs': message}, status=code)


def _int_ou_none(valeur, nom_champ, requerre=False, mini=1, maxi=None):
    """Extrait un entier depuis `request.data` avec messages d'erreur clairs."""
    if valeur is None or valeur == '':
        if requerre:
            raise ValidationError({nom_champ: f'Le champ « {nom_champ} » est obligatoire.'})
        return None
    try:
        nombre = int(valeur)
    except (TypeError, ValueError):
        raise ValidationError({nom_champ: f'« {valeur} » n’est pas un entier valide pour {nom_champ}.'})
    if mini is not None and nombre < mini:
        raise ValidationError({nom_champ: f'{nom_champ} doit être ≥ {mini}.'})
    if maxi is not None and nombre > maxi:
        raise ValidationError({nom_champ: f'{nom_champ} doit être ≤ {maxi}.'})
    return nombre


def _chaine(valeur, clef='valeur'):
    if valeur is None:
        return ''
    texte = str(valeur).strip()
    if len(texte) > 255:
        raise ValidationError({clef: f'{clef} doit faire 255 caractères au plus.'})
    return texte


def _erreur_vers_statut(exc):
    """Traduit les exceptions métier en réponses HTTP propres (jamais de 500)."""
    from django.db.utils import IntegrityError
    if isinstance(exc, ValidationError):
        details = getattr(exc, 'message_dict', None) or {'detail': exc.messages}
        return Response(details, status=status.HTTP_400_BAD_REQUEST)
    if isinstance(exc, IntegrityError):
        return Response(
            {'detail': 'Contrainte d’intégrité refusée : vérifiez les références (année, population, créneau).'},
            status=status.HTTP_409_CONFLICT,
        )
    if isinstance(exc, ObjectDoesNotExist):
        return Response({'detail': 'Référence introuvable.'}, status=status.HTTP_404_NOT_FOUND)
    if isinstance(exc, ValueError):
        return Response({'detail': str(exc)}, status=status.HTTP_409_CONFLICT)
    raise exc


def _limiter_pagination(request, queryset, order_by):
    """Tri + slicing léger (limit/offset) sans changer la forme JSON (tableau)."""
    try:
        limite = int(request.query_params.get('limit', LIMITE_DEFAUT_LISTE))
    except (TypeError, ValueError):
        limite = LIMITE_DEFAUT_LISTE
    try:
        offset = int(request.query_params.get('offset', 0))
    except (TypeError, ValueError):
        offset = 0
    limite = max(1, min(limite, LIMITE_DEFAUT_LISTE))
    return queryset.order_by(*order_by)[offset:offset + limite]


def _journal(action, objet=None, acteur=None, **champs):
    from scolarite.models import journaliser
    journaliser(action, objet=objet, acteur=acteur, **champs)


def _peut_editer(request, emploi):
    """Le EDT est-il modifiable par l'utilisateur courant ? Retourne None ou une Response d'erreur.

    Un EDT soumis (EN_VALIDATION) est aussi gelé pour la planification : l'agent
    peut le retirer de la file (transition EN_VALIDATION → BROUILLON autorisée)
    pour corriger, ce qui garde le dossier d'examen cohérent pour la Direction.
    """
    from .permissions import _peut_valider
    if _peut_valider(request.user):
        return None
    if emploi.statut in (EDT_GELE | {'EN_VALIDATION'}):
        return Response(
            {'detail': (
                f'Emploi du temps {emploi.get_statut_display().lower()} : édition verrouillée. '
                'Un rôle Direction doit le dépublier avant toute modification.'
            )},
            status=status.HTTP_409_CONFLICT,
        )
    return None


def _label_population(cible_type, cible_id):
    """Vérifie l'existence de la population cible et retourne (label, erreur_response)."""
    if cible_type == 'FORMATION':
        from formations.models import RefFormation
        objet = RefFormation.objects.filter(pk=cible_id).first()
        if objet is None:
            return None, Response({'detail': f'Aucune formation id={cible_id}.'},
                                  status=status.HTTP_400_BAD_REQUEST)
        return str(objet), None
    if cible_type == 'GROUPE':
        from scolarite.models import Groupe
        objet = Groupe.objects.filter(pk=cible_id).first()
        if objet is None:
            return None, Response({'detail': f'Aucun groupe id={cible_id}.'},
                                  status=status.HTTP_400_BAD_REQUEST)
        return str(objet), None
    if cible_type == 'SALLE':
        from formations.models import RefSalle
        objet = RefSalle.objects.filter(pk=cible_id).first()
        if objet is None:
            return None, Response({'detail': f'Aucune salle id={cible_id}.'},
                                  status=status.HTTP_400_BAD_REQUEST)
        return str(objet), None
    if cible_type == 'ENSEIGNANT':
        from django.contrib.auth import get_user_model
        objet = get_user_model().objects.filter(pk=cible_id).first()
        if objet is None:
            return None, Response({'detail': f'Aucun utilisateur id={cible_id}.'},
                                  status=status.HTTP_400_BAD_REQUEST)
        nom = objet.get_full_name() or objet.username
        return nom, None
    return '', None


# ---------------------------------------------------------------------------
# Sérialiseurs (champs réels uniquement)
# ---------------------------------------------------------------------------


def _serialize_creneau_template(c):
    return {
        'id': c.id,
        'jour': c.jour,
        'jour_libelle': c.get_jour_display(),
        'heure_debut': c.heure_debut.isoformat(timespec='minutes') if c.heure_debut else None,
        'heure_fin': c.heure_fin.isoformat(timespec='minutes') if c.heure_fin else None,
        'duree_prevue_minutes': c.duree_prevue_minutes,
        'duree_heures': c.duree_heures,
    }


def _serialize_emploi_du_temps(e):
    return {
        'id': e.id,
        'titre': e.titre,
        'statut': e.statut,
        'statut_libelle': e.get_statut_display(),
        'annee_academique_id': e.annee_academique_id,
        'annee_academique': str(e.annee_academique),
        'population_type': e.population_type,
        'population_id': e.population_id,
        'population_label': e.population_label,
        'rentree': e.rentree.isoformat() if e.rentree else None,
        'semaine_debut': e.semaine_debut,
        'semaine_fin': e.semaine_fin,
        'affectations_count': getattr(e, 'nb_affectations', None),
        'conflits_count': getattr(e, 'nb_conflits', None),
        'cree_par': str(e.cree_par) if e.cree_par_id else None,
        'created_at': e.created_at.isoformat(),
        'updated_at': e.updated_at.isoformat(),
    }


def _serialize_affectation(a):
    return {
        'id': a.id,
        'emploi_du_temps_id': a.emploi_du_temps_id,
        'creneau_template_id': a.creneau_template_id,
        'creneau': _serialize_creneau_template(a.creneau_template) if a.creneau_template_id else None,
        'horaire': a.horaire,
        'semaine_debut': a.semaine_debut,
        'semaine_fin': a.semaine_fin,
        'formation_id': a.formation_id,
        'formation': str(a.formation) if a.formation_id else None,
        'groupe_id': a.groupe_id,
        'groupe': str(a.groupe) if a.groupe_id else None,
        'enseignant_id': a.enseignant_id,
        'formateur_id': a.formateur_id,
        'enseignant_nom': a.enseignant_nom,
        'nature': a.nature,
        'nature_libelle': a.get_nature_display(),
        'intitule': a.intitule,
        'commentaire': a.commentaire,
        'salle_nom': a.salle_nom,
        'actif': a.actif,
        'cree_par': str(a.cree_par) if a.cree_par_id else None,
        'created_at': a.created_at.isoformat(),
        'updated_at': a.updated_at.isoformat(),
    }


def _serialize_conflit(c):
    return {
        'id': c.id,
        'emploi_du_temps_id': c.emploi_du_temps_id,
        'emploi_du_temps': str(c.emploi_du_temps),
        'type_conflit': c.type_conflit,
        'type_conflit_libelle': c.get_type_conflit_display(),
        'description': c.description,
        'lignes_creneaux': c.lignes_creneaux,
        'actif': c.actif,
        'signale_par': str(c.signale_par) if c.signale_par_id else None,
        'created_at': c.created_at.isoformat(),
        'recalcule_le': c.recalcule_le.isoformat(),
    }


# ---------------------------------------------------------------------------
# Créneaux types (référentiel horaire — P01)
# ---------------------------------------------------------------------------


@api_view(['GET', 'POST'])
@permission_classes([IsEdtReadOnlyOrPlanification])
def creneaux_types_api(request):
    if request.method == 'GET':
        creneaux = _limiter_pagination(request, CreneauTemplate.objects.all(),
                                       ['jour', 'heure_debut'])
        return Response([_serialize_creneau_template(c) for c in creneaux])

    try:
        jour = _chaine(request.data.get('jour'), 'jour')
        heure_debut = request.data.get('heure_debut')
        heure_fin = request.data.get('heure_fin')
        if not jour or not heure_debut or not heure_fin:
            raise ValidationError({'detail': 'jour, heure_debut et heure_fin sont obligatoires.'})
        doublon = CreneauTemplate.objects.filter(jour=jour, heure_debut=heure_debut, heure_fin=heure_fin)
        if doublon.exists():
            return Response({'detail': 'Ce créneau existe déjà dans le référentiel.'},
                            status=status.HTTP_409_CONFLICT)
        c = CreneauTemplate(jour=jour, heure_debut=heure_debut, heure_fin=heure_fin)
        c.full_clean()
        c.save()
    except (ValidationError, ValueError) as exc:
        return _erreur_vers_statut(exc)
    return Response(_serialize_creneau_template(c), status=status.HTTP_201_CREATED)


@api_view(['GET', 'PUT', 'PATCH', 'DELETE'])
@permission_classes([IsEdtReadOnlyOrPlanification])
def creneau_template_detail_api(request, pk):
    c = CreneauTemplate.objects.filter(pk=pk).first()
    if c is None:
        return Response({'detail': 'Créneau type introuvable'}, status=status.HTTP_404_NOT_FOUND)

    if request.method == 'GET':
        return Response(_serialize_creneau_template(c))

    from .permissions import _peut_planifier
    if not _peut_planifier(request.user):
        return Response({'detail': 'Droits insuffisants pour modifier le référentiel des créneaux.'},
                        status=status.HTTP_403_FORBIDDEN)

    if request.method == 'DELETE':
        usage = c.affectations.count()
        if usage:
            return Response(
                {'detail': f'Impossible de supprimer : {usage} affectation(s) utilisent ce créneau. '
                           'Réaffectez-les d’abord.'},
                status=status.HTTP_409_CONFLICT,
            )
        c.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    try:
        for champ in ('jour', 'heure_debut', 'heure_fin'):
            if champ in request.data:
                setattr(c, champ, request.data[champ])
        c.full_clean()
        c.save()
    except (ValidationError, ValueError) as exc:
        return _erreur_vers_statut(exc)
    return Response(_serialize_creneau_template(c))


# ---------------------------------------------------------------------------
# Emplois du temps : liste, détail, création, édition, suppression
# ---------------------------------------------------------------------------


@api_view(['GET', 'POST'])
@permission_classes([IsEdtReadOnlyOrPlanification])
def emplois_du_temps_api(request):
    if request.method == 'GET':
        qp = request.query_params
        edts = EmploiDuTemps.objects.select_related('annee_academique', 'cree_par').annotate(
            nb_affectations=Count('affectations', filter=Q(affectations__actif=True), distinct=True),
            nb_conflits=Count('conflits', filter=Q(conflits__actif=True), distinct=True),
        )
        if qp.get('annee_academique_id'):
            edts = edts.filter(annee_academique_id=qp['annee_academique_id'])
        if qp.get('population_type'):
            edts = edts.filter(population_type=qp['population_type'])
        if qp.get('population_id'):
            edts = edts.filter(population_id=qp['population_id'])
        if qp.get('statut'):
            edts = edts.filter(statut__in=[s.strip().upper() for s in qp['statut'].split(',') if s.strip()])
        if qp.get('q'):
            edts = edts.filter(Q(titre__icontains=qp['q']) | Q(population_denominateur__icontains=qp['q']))
        if qp.get('selon_role') in ('1', 'true'):
            # Enseignants/encadrants : ne voir que les EDT où ils sont planifiés.
            if request.user.role in ('ENCADRANT', 'FORMATEUR', 'SUPERVISEUR'):
                from django.contrib.auth import get_user_model
                user_id = get_user_model().objects.filter(pk=request.user.pk).values_list('id', flat=True).first()
                edts = edts.filter(
                    Q(population_type='ENSEIGNANT', population_id=user_id)
                    | Q(affectations__enseignant_id=user_id)
                ).distinct()
        data = [_serialize_emploi_du_temps(e) for e in _limiter_pagination(request, edts, ['-updated_at'])]
        return Response(data)

    try:
        data = request.data
        annee_id = _int_ou_none(data.get('annee_academique_id'), 'annee_academique_id', requerre=True)
        cible_type = _chaine(data.get('population_type', 'FORMATION'), 'population_type').upper()
        if cible_type not in POPULATION_TYPES:
            raise ValidationError({'population_type': f'Type de population inconnu : {cible_type}.'})
        cible_id = _int_ou_none(data.get('population_id'), 'population_id', requerre=True)
        label, erreur = _label_population(cible_type, cible_id)
        if erreur is not None:
            return erreur
        if EmploiDuTemps.objects.filter(annee_academique_id=annee_id,
                                        population_type=cible_type,
                                        population_id=cible_id).exists():
            return Response(
                {'detail': 'Un emploi du temps existe déjà pour cette année et cette population. '
                           'Ouvrez-le plutôt que d’en créer un second.'},
                status=status.HTTP_409_CONFLICT,
            )
        semaine_debut = _int_ou_none(data.get('semaine_debut', 1) or 1, 'semaine_debut', mini=1, maxi=60)
        semaine_fin = _int_ou_none(data.get('semaine_fin', 36) or 36, 'semaine_fin', mini=1, maxi=60)
        if semaine_fin < semaine_debut:
            raise ValidationError({'semaine_fin': 'La semaine de fin doit être ≥ à la semaine de début.'})
        e = EmploiDuTemps(
            annee_academique_id=annee_id,
            population_type=cible_type,
            population_id=cible_id,
            population_denominateur=_chaine(data.get('population_denominateur'), 'population_denominateur') or label,
            titre=_chaine(data.get('titre'), 'titre'),
            statut='BROUILLON',
            semaine_debut=semaine_debut,
            semaine_fin=semaine_fin,
            rentree=data.get('rentree') or None,
            cree_par=request.user,
        )
        e.full_clean(exclude=['rentree'])
        e.save()
    except (ValidationError, ValueError) as exc:
        return _erreur_vers_statut(exc)
    _journal('EDT_CREE', objet=e, acteur=request.user,
             extra={'population': f'{cible_type}#{cible_id}'})
    return Response(_serialize_emploi_du_temps(e), status=status.HTTP_201_CREATED)


@api_view(['GET', 'PUT', 'PATCH', 'DELETE'])
@permission_classes([IsEdtReadOnlyOrPlanification])
def emploi_du_temps_detail_api(request, pk):
    e = EmploiDuTemps.objects.select_related('annee_academique', 'cree_par').annotate(
        nb_affectations=Count('affectations', filter=Q(affectations__actif=True), distinct=True),
        nb_conflits=Count('conflits', filter=Q(conflits__actif=True), distinct=True),
    ).filter(pk=pk).first()
    if e is None:
        return Response({'detail': 'Emploi du temps introuvable'}, status=status.HTTP_404_NOT_FOUND)

    if request.method == 'GET':
        return Response(_serialize_emploi_du_temps(e))

    if request.method == 'DELETE':
        from .permissions import _peut_planifier, _peut_valider
        est_validateur = _peut_valider(request.user)
        if e.statut == 'ARCHIVE':
            if not est_validateur:
                return Response({'detail': 'Seule la Direction peut supprimer un EDT archivé.'},
                                status=status.HTTP_403_FORBIDDEN)
        elif e.statut == 'BROUILLON':
            if not (est_validateur or _peut_planifier(request.user)):
                return Response({'detail': 'Seule la planification peut supprimer un brouillon.'},
                                status=status.HTTP_403_FORBIDDEN)
        else:
            return Response(
                {'detail': 'Seuls les brouillons et les archives (par la Direction) peuvent être supprimés. '
                           'Archivez d’abord cet emploi du temps, puis supprimez-le.'},
                status=status.HTTP_409_CONFLICT,
            )
        _journal('EDT_SUPPRIME', objet=e, acteur=request.user)
        e.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    # Écriture : seule la planification peut toucher un EDT non gelé ;
    # le statut, l'année et la cible ne sont plus modifiables ici (workflow).
    gel = _peut_editer(request, e)
    if gel is not None:
        return gel
    champs_modifiables = ('titre', 'population_denominateur', 'rentree',
                          'semaine_debut', 'semaine_fin')
    donnees = request.data
    if 'statut' in donnees:
        return Response(
            {'detail': 'Le statut se pilote par les actions du workflow (soumettre, valider, '
                       'publier, dépublier, archiver), pas par une édition directe.'},
            status=status.HTTP_400_BAD_REQUEST,
        )
    for clef in ('population_type', 'population_id', 'annee_academique_id'):
        valeur_envoyee = str(donnees.get(clef) or '')
        valeur_actuelle = str(getattr(e, clef, '') or '')
        if valeur_envoyee and valeur_envoyee != valeur_actuelle:
            return Response(
                {'detail': 'Le périmètre (année, type ou id de population) d’un emploi du temps '
                           'est immuable : créez un nouvel emploi du temps.'},
                status=status.HTTP_409_CONFLICT,
            )
    try:
        for clef in ('titre', 'population_denominateur'):
            if clef in donnees:
                setattr(e, clef, _chaine(donnees[clef], clef))
        if 'rentree' in donnees:
            e.rentree = donnees['rentree'] or None
        for clef in ('semaine_debut', 'semaine_fin'):
            if clef in donnees:
                setattr(e, clef, _int_ou_none(donnees[clef], clef, mini=1, maxi=60))
        if e.semaine_fin < e.semaine_debut:
            raise ValidationError({'semaine_fin': 'La semaine de fin doit être ≥ à la semaine de début.'})
        e.full_clean(exclude=['rentree'])
        e.save()
    except (ValidationError, ValueError) as exc:
        return _erreur_vers_statut(exc)
    _journal('EDT_AFFECTATION_MODIFIEE', objet=e, acteur=request.user, extra={'modification': 'métadonnées'})
    return Response(_serialize_emploi_du_temps(e))


# ---------------------------------------------------------------------------
# Workflow de validation / publication
# ---------------------------------------------------------------------------

TRANSITIONS = {
    # (depuis -> vers) : rôles autorisés
    ('BROUILLON', 'EN_VALIDATION'): 'planification',
    ('EN_VALIDATION', 'VALIDE'): 'validation',
    ('EN_VALIDATION', 'BROUILLON'): 'planification',   # retrait de soumission
    ('VALIDE', 'PUBLIE'): 'validation',
    ('VALIDE', 'EN_VALIDATION'): 'validation',          # renvoi en examen
    ('PUBLIE', 'BROUILLON'): 'validation',              # dépublication
    ('BROUILLON', 'ARCHIVE'): 'planification',
    ('EN_VALIDATION', 'ARCHIVE'): 'planification',
    ('VALIDE', 'ARCHIVE'): 'validation',
    ('PUBLIE', 'ARCHIVE'): 'validation',
    ('ARCHIVE', 'BROUILLON'): 'validation',             # réouverture encadrée
}


def _role_de_l_action(request):
    from .permissions import _peut_valider, _peut_planifier
    if _peut_valider(request.user):
        return 'validation'
    if _peut_planifier(request.user):
        return 'planification'
    return 'lecture'


def _transition(request, pk, vers):
    e = EmploiDuTemps.objects.select_related('annee_academique').filter(pk=pk).first()
    if e is None:
        return None, Response({'detail': 'Emploi du temps introuvable'}, status=status.HTTP_404_NOT_FOUND)
    role = _role_de_l_action(request)
    autorise = TRANSITIONS.get((e.statut, vers))
    if autorise is None:
        return e, Response(
            {'detail': f'Transition interdite : {e.statut} → {vers}. '
                       f'Chaîne attendue : BROUILLON → EN_VALIDATION → VALIDE → PUBLIE '
                       f'(dépublication et archivage encadrés).'},
            status=status.HTTP_409_CONFLICT,
        )
    if autorise == 'validation' and role != 'validation':
        return e, Response(
            {'detail': 'Cette transition est réservée aux rôles Direction/Administration.'},
            status=status.HTTP_403_FORBIDDEN,
        )
    if role == 'lecture':
        return e, Response({'detail': 'Droits insuffisants.'}, status=status.HTTP_403_FORBIDDEN)
    before = e.statut
    e.statut = vers
    e.save(update_fields=['statut', 'updated_at'])
    actions = {
        'EN_VALIDATION': 'EDT_SOUMIS',
        'VALIDE': 'EDT_VALIDE',
        'PUBLIE': 'EDT_PUBLIE',
        'ARCHIVE': 'EDT_ARCHIVE',
        'BROUILLON': 'EDT_DEPUBLIE' if before in ('PUBLIE', 'ARCHIVE') else 'EDT_SOUMIS',
    }
    _journal(actions.get(vers, 'EDT_AFFECTATION_MODIFIEE'), objet=e, acteur=request.user,
             extra={'transition': f'{before} → {vers}'})
    return e, None


@api_view(['POST'])
@permission_classes([IsEdtPlanification])
def emploi_du_temps_soumettre_api(request, pk):
    """BROUILLON → EN_VALIDATION. Refusé si l'EDT est vide ou contient des conflits actifs."""
    conflits_actifs = ConflitCreneau.objects.filter(emploi_du_temps_id=pk, actif=True).count()
    if conflits_actifs:
        return Response(
            {'detail': f'Soumission bloquée : {conflits_actifs} conflit(s) actif(s). '
                       'Résolvez-les (ou relancez la détection après correction) puis re-soumettez.'},
            status=status.HTTP_409_CONFLICT,
        )
    e, erreur = _transition(request, pk, 'EN_VALIDATION')
    if erreur is not None:
        return erreur
    if not e.affectations.filter(actif=True).exists():
        e.statut = 'BROUILLON'
        e.save(update_fields=['statut', 'updated_at'])
        return Response({'detail': 'Emploi du temps vide : ajoutez au moins une affectation avant de soumettre.'},
                        status=status.HTTP_409_CONFLICT)
    return Response(_serialize_emploi_du_temps(e))


@api_view(['POST'])
@permission_classes([IsEdtValidation])
def emploi_du_temps_valider_api(request, pk):
    """EN_VALIDATION → VALIDE (ou PUBLIE en un seul mouvement pour la Direction)."""
    vers = _chaine(request.data.get('statut', 'VALIDE'), 'statut').upper()
    if vers not in ('VALIDE', 'PUBLIE'):
        return _reponse_validation('Le champ statut accepte uniquement VALIDE ou PUBLIE.')
    e, erreur = _transition(request, pk, vers)
    if erreur is not None:
        return erreur
    return Response(_serialize_emploi_du_temps(e))


@api_view(['POST'])
@permission_classes([IsEdtValidation])
def emploi_du_temps_publier_api(request, pk):
    e, erreur = _transition(request, pk, 'PUBLIE')
    if erreur is not None:
        return erreur
    return Response(_serialize_emploi_du_temps(e))


@api_view(['POST'])
@permission_classes([IsEdtValidation])
def emploi_du_temps_depublier_api(request, pk):
    e, erreur = _transition(request, pk, 'BROUILLON')
    if erreur is not None:
        return erreur
    return Response(_serialize_emploi_du_temps(e))


@api_view(['POST'])
@permission_classes([IsEdtReadOnlyOrPlanification])
def emploi_du_temps_archiver_api(request, pk):
    e, erreur = _transition(request, pk, 'ARCHIVE')
    if erreur is not None:
        return erreur
    return Response(_serialize_emploi_du_temps(e))


# ---------------------------------------------------------------------------
# Détection & suivi des conflits (P07)
# ---------------------------------------------------------------------------


@api_view(['POST'])
@permission_classes([IsEdtPlanification])
def emploi_du_temps_detecter_conflits_api(request, pk):
    e = EmploiDuTemps.objects.filter(pk=pk).first()
    if e is None:
        return Response({'detail': 'Emploi du temps introuvable'}, status=status.HTTP_404_NOT_FOUND)
    try:
        stats = services.detecter_conflits(e)
    except Exception as exc:  # pragma: no cover — garde-fou, jamais de 500 sur détection
        return _erreur_vers_statut(exc)
    conflits = [_serialize_conflit(c) for c in
                e.conflits.filter(actif=True).order_by('-recalcule_le')[:100]]
    return Response({'stats': stats, 'conflits': conflits})


@api_view(['GET', 'POST'])
@permission_classes([IsEdtReadOnlyOrPlanification])
def affectations_api(request):
    if request.method == 'GET':
        qp = request.query_params
        affects = AffectationCreneau.objects.select_related(
            'emploi_du_temps', 'creneau_template', 'formation', 'groupe', 'formateur',
        )
        filtres = {
            'emploi_du_temps_id': 'emploi_du_temps_id',
            'creneau_template_id': 'creneau_template_id',
            'formation_id': 'formation_id',
            'groupe_id': 'groupe_id',
            'enseignant_id': 'enseignant_id',
            'formateur_id': 'formateur_id',
        }
        for parametre, champ in filtres.items():
            if qp.get(parametre):
                affects = affects.filter(**{champ: qp[parametre]})
        if qp.get('nature'):
            affects = affects.filter(nature__in=[n.strip().upper() for n in qp['nature'].split(',') if n.strip()])
        if qp.get('statut_edt'):
            affects = affects.filter(emploi_du_temps__statut__in=[
                s.strip().upper() for s in qp['statut_edt'].split(',') if s.strip()])
        if qp.get('actif') in ('true', 'false'):
            affects = affects.filter(actif=qp['actif'] == 'true')
        if qp.get('semaine'):
            try:
                semaine = int(qp['semaine'])
                affects = affects.filter(semaine_debut__lte=semaine, semaine_fin__gte=semaine)
            except ValueError:
                return _reponse_validation('Le paramètre semaine doit être un entier.')
        data = [_serialize_affectation(a) for a in
                _limiter_pagination(request, affects,
                                    ['creneau_template__jour', 'creneau_template__heure_debut', 'semaine_debut'])]
        return Response(data)

    try:
        data = request.data
        edt_id = _int_ou_none(data.get('emploi_du_temps_id'), 'emploi_du_temps_id', requerre=True)
        e = EmploiDuTemps.objects.filter(pk=edt_id).first()
        if e is None:
            return Response({'detail': f'Emploi du temps id={edt_id} introuvable.'},
                            status=status.HTTP_400_BAD_REQUEST)
        gel = _peut_editer(request, e)
        if gel is not None:
            return gel
        ct_id = _int_ou_none(data.get('creneau_template_id'), 'creneau_template_id', requerre=True)
        if not CreneauTemplate.objects.filter(pk=ct_id).exists():
            return Response({'detail': f'Créneau type id={ct_id} introuvable.'},
                            status=status.HTTP_400_BAD_REQUEST)
        semaine_debut = _int_ou_none(data.get('semaine_debut'), 'semaine_debut', requerre=True)
        semaine_fin = _int_ou_none(data.get('semaine_fin') or semaine_debut, 'semaine_fin', requerre=True)
        if semaine_fin < semaine_debut:
            raise ValidationError({'semaine_fin': 'La semaine de fin doit être ≥ à la semaine de début.'})
        nature = _chaine(data.get('nature', 'COURS'), 'nature').upper() or 'COURS'
        if nature not in NATURES:
            raise ValidationError({'nature': f'Nature inconnue : {nature}.'})
        for clef, modele in (('formation_id', 'formations.RefFormation'),
                             ('groupe_id', 'scolarite.Groupe')):
            if data.get(clef) not in (None, ''):
                cible = _int_ou_none(data[clef], clef)
                from django.apps import apps as _apps
                modele_objet = _apps.get_model(*modele.split('.'))
                if not modele_objet.objects.filter(pk=cible).exists():
                    return Response({'detail': f'{clef} : enregistrement introuvable (id={cible}).'},
                                    status=status.HTTP_400_BAD_REQUEST)
                data = dict(data)
                data[clef] = cible
        formateur_id = data.get('formateur_id')
        if formateur_id not in (None, ''):
            from formations.models import Formateur
            formateur = Formateur.objects.filter(pk=_int_ou_none(formateur_id, 'formateur_id')).first()
            if formateur is None:
                return Response({'detail': f'Formateur id={formateur_id} introuvable.'},
                                status=status.HTTP_400_BAD_REQUEST)
            if not _chaine(data.get('enseignant_nom'), 'enseignant_nom'):
                data = dict(data)
                data['enseignant_nom'] = f'{formateur.prenom} {formateur.nom}'.strip()
        a = AffectationCreneau(
            emploi_du_temps=e,
            creneau_template_id=ct_id,
            semaine_debut=semaine_debut,
            semaine_fin=semaine_fin,
            salle_nom=_chaine(data.get('salle_nom'), 'salle_nom'),
            formation_id=data.get('formation_id') or None,
            groupe_id=data.get('groupe_id') or None,
            enseignant_id=data.get('enseignant_id') or None,
            formateur_id=formateur_id or None,
            enseignant_nom=_chaine(data.get('enseignant_nom'), 'enseignant_nom'),
            nature=nature,
            intitule=_chaine(data.get('intitule'), 'intitule'),
            commentaire=_chaine(data.get('commentaire'), 'commentaire'),
            cree_par=request.user,
        )
        a.full_clean()
        a.save()
    except (ValidationError, ValueError) as exc:
        return _erreur_vers_statut(exc)
    avertissements = services.verifier_affectation(a)
    _journal('EDT_AFFECTATION_MODIFIEE', objet=e, acteur=request.user,
             extra={'operation': 'affectation créée', 'affectation_id': a.pk,
                    'avertissements': len(avertissements)})
    return Response({'affectation': _serialize_affectation(a),
                     'avertissements_conflits': avertissements},
                    status=status.HTTP_201_CREATED)


@api_view(['GET', 'PUT', 'PATCH', 'DELETE'])
@permission_classes([IsEdtReadOnlyOrPlanification])
def affectation_detail_api(request, pk):
    a = AffectationCreneau.objects.select_related(
        'emploi_du_temps', 'creneau_template', 'formation', 'groupe', 'formateur',
    ).filter(pk=pk).first()
    if a is None:
        return Response({'detail': 'Affectation introuvable'}, status=status.HTTP_404_NOT_FOUND)
    if request.method == 'GET':
        return Response(_serialize_affectation(a))

    gel = _peut_editer(request, a.emploi_du_temps)
    if gel is not None:
        return gel
    if request.method == 'DELETE':
        a.delete()
        _journal('EDT_AFFECTATION_MODIFIEE', objet=a.emploi_du_temps, acteur=request.user,
                 extra={'operation': 'affectation supprimée', 'affectation_id': pk})
        return Response(status=status.HTTP_204_NO_CONTENT)

    try:
        data = request.data
        for clef in ('salle_nom', 'enseignant_nom', 'intitule', 'commentaire'):
            if clef in data:
                setattr(a, clef, _chaine(data[clef], clef))
        if 'creneau_template_id' in data:
            ct = CreneauTemplate.objects.filter(pk=data['creneau_template_id']).first()
            if ct is None:
                return Response({'detail': 'Créneau type introuvable.'}, status=status.HTTP_400_BAD_REQUEST)
            a.creneau_template = ct
        for clef in ('semaine_debut', 'semaine_fin'):
            if clef in data:
                setattr(a, clef, _int_ou_none(data[clef], clef, mini=1, maxi=60))
        if 'nature' in data:
            nature = _chaine(data['nature'], 'nature').upper()
            if nature not in NATURES:
                raise ValidationError({'nature': f'Nature inconnue : {nature}.'})
            a.nature = nature
        if 'actif' in data:
            a.actif = str(data['actif']).lower() in ('1', 'true', 'yes', 'oui')
        for clef in ('formation_id', 'groupe_id', 'enseignant_id'):
            if clef in data:
                setattr(a, clef, _int_ou_none(data[clef], clef) or None)
        if 'formateur_id' in data:
            a.formateur_id = _int_ou_none(data['formateur_id'], 'formateur_id') or None
        a.full_clean()
        a.save()
    except (ValidationError, ValueError) as exc:
        return _erreur_vers_statut(exc)
    avertissements = services.verifier_affectation(a)
    _journal('EDT_AFFECTATION_MODIFIEE', objet=a.emploi_du_temps, acteur=request.user,
             extra={'operation': 'affectation modifiée', 'affectation_id': a.pk,
                    'avertissements': len(avertissements)})
    return Response({'affectation': _serialize_affectation(a),
                     'avertissements_conflits': avertissements})


@api_view(['POST'])
@permission_classes([IsEdtPlanification])
def affectation_deplacer_api(request, pk):
    """Déplacement contrôlé (P08) : refuse le dur conflit sauf forçage motivé."""
    a = AffectationCreneau.objects.select_related('emploi_du_temps', 'creneau_template').filter(pk=pk).first()
    if a is None:
        return Response({'detail': 'Affectation introuvable'}, status=status.HTTP_404_NOT_FOUND)
    gel = _peut_editer(request, a.emploi_du_temps)
    if gel is not None:
        return gel
    try:
        data = request.data
        if 'creneau_template_id' in data:
            ct = CreneauTemplate.objects.filter(pk=data['creneau_template_id']).first()
            if ct is None:
                return Response({'detail': 'Créneau cible introuvable.'}, status=status.HTTP_400_BAD_REQUEST)
            a.creneau_template = ct
        if 'semaine_debut' in data:
            a.semaine_debut = _int_ou_none(data['semaine_debut'], 'semaine_debut', mini=1, maxi=60)
        if 'semaine_fin' in data:
            a.semaine_fin = _int_ou_none(data['semaine_fin'], 'semaine_fin', mini=1, maxi=60)
        a.full_clean()
    except (ValidationError, ValueError) as exc:
        return _erreur_vers_statut(exc)

    conflits = services.verifier_affectation(a)
    forcer = str(data.get('forcer', '')).lower() in ('1', 'true', 'oui')
    motif = _chaine(data.get('motif_forçage', data.get('motif', '')), 'motif')
    if conflits and not forcer:
        return Response(
            {'detail': 'Déplacement refusé : conflits détectés.', 'conflits': conflits,
             'conseil': "Utilisez forcer=true avec un motif pour accepter et tracer le déplacement."},
            status=status.HTTP_409_CONFLICT,
        )
    if forcer and not motif:
        return Response({'detail': 'Le forçage exige un motif (traçabilité).'},
                        status=status.HTTP_400_BAD_REQUEST)
    a.save()
    _journal('EDT_AFFECTATION_MODIFIEE', objet=a.emploi_du_temps, acteur=request.user,
             extra={'operation': 'affectation déplacée', 'affectation_id': a.pk,
                    'force': forcer, 'motif': motif, 'conflits_assumes': conflits if forcer else []})
    return Response({'affectation': _serialize_affectation(a),
                     'deplace': True, 'conflits_restants': conflits})


# ---------------------------------------------------------------------------
# Conflits : lecture globale, signalement manuel, résolution
# ---------------------------------------------------------------------------


@api_view(['GET', 'POST'])
@permission_classes([IsEdtReadOnlyOrPlanification])
def conflits_api(request):
    if request.method == 'GET':
        qp = request.query_params
        conflits = ConflitCreneau.objects.select_related('emploi_du_temps', 'signale_par')
        if qp.get('emploi_du_temps_id'):
            conflits = conflits.filter(emploi_du_temps_id=qp['emploi_du_temps_id'])
        if qp.get('actif') in ('true', 'false'):
            conflits = conflits.filter(actif=qp['actif'] == 'true')
        elif qp.get('actif') is None and qp.get('tous') not in ('1', 'true'):
            conflits = conflits.filter(actif=True)
        if qp.get('type_conflit'):
            conflits = conflits.filter(type_conflit=qp['type_conflit'])
        data = [_serialize_conflit(c) for c in _limiter_pagination(request, conflits, ['-recalcule_le'])]
        return Response(data)

    try:
        data = request.data
        edt_id = _int_ou_none(data.get('emploi_du_temps_id'), 'emploi_du_temps_id', requerre=True)
        if not EmploiDuTemps.objects.filter(pk=edt_id).exists():
            return Response({'detail': f'Emploi du temps id={edt_id} introuvable.'},
                            status=status.HTTP_400_BAD_REQUEST)
        description = _chaine(data.get('description'), 'description')
        if not description:
            raise ValidationError({'description': 'Un signalement manuel doit être décrit.'})
        c = ConflitCreneau.objects.create(
            emploi_du_temps_id=edt_id,
            type_conflit='MANUEL',
            description=description,
            lignes_creneaux=data.get('lignes_creneaux', []),
            signale_par=request.user,
        )
    except (ValidationError, ValueError) as exc:
        return _erreur_vers_statut(exc)
    return Response(_serialize_conflit(c), status=status.HTTP_201_CREATED)


@api_view(['POST'])
@permission_classes([IsEdtPlanification])
def conflit_resoudre_api(request, pk):
    c = ConflitCreneau.objects.select_related('emploi_du_temps').filter(pk=pk).first()
    if c is None:
        return Response({'detail': 'Conflit introuvable'}, status=status.HTTP_404_NOT_FOUND)
    if not c.actif:
        return Response({'detail': 'Ce conflit est déjà clôturé.'}, status=status.HTTP_409_CONFLICT)
    motif = _chaine(request.data.get('motif'), 'motif') if hasattr(request, 'data') else ''
    c.actif = False
    if motif:
        c.description = f"{c.description}\nRésolution : {motif}"
    c.save(update_fields=['actif', 'description', 'recalcule_le'])
    _journal('EDT_CONFLIT_RESOLU', objet=c.emploi_du_temps, acteur=request.user,
             extra={'conflit_id': c.pk, 'motif': motif})
    return Response(_serialize_conflit(c))


# ---------------------------------------------------------------------------
# Lecture légère : EDT publiés, grille hebdo, génération, export
# ---------------------------------------------------------------------------


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def edt_publics_api(request):
    """EDT publiés (lecture authentifiée ; « publics » = visibles par tous les comptes)."""
    qp = request.query_params
    edts = EmploiDuTemps.objects.filter(
        statut__in=['VALIDE', 'PUBLIE'],
    ).select_related('annee_academique')
    if qp.get('annee_academique_id'):
        edts = edts.filter(annee_academique_id=qp['annee_academique_id'])
    if qp.get('population_type'):
        edts = edts.filter(population_type=qp['population_type'])
    if qp.get('population_id'):
        edts = edts.filter(population_id=qp['population_id'])
    data = [
        {
            'id': e.id,
            'titre': e.titre or e.population_label,
            'statut': e.statut,
            'annee_academique_id': e.annee_academique_id,
            'annee_academique': str(e.annee_academique),
            'population_type': e.population_type,
            'population_id': e.population_id,
            'population_label': e.population_label,
            'semaine_debut': e.semaine_debut,
            'semaine_fin': e.semaine_fin,
        }
        for e in edts.order_by('annee_academique', 'titre')
    ]
    return Response(data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def emploi_du_temps_grille_api(request, pk):
    """Vue hebdomadaire : créneaux occupés par jour pour une semaine donnée (P17)."""
    e = EmploiDuTemps.objects.filter(pk=pk).first()
    if e is None:
        return Response({'detail': 'Emploi du temps introuvable'}, status=status.HTTP_404_NOT_FOUND)
    semaine = request.query_params.get('semaine')
    try:
        semaine = _int_ou_none(semaine, 'semaine', mini=1, maxi=60) if semaine else None
    except ValidationError as exc:
        return _erreur_vers_statut(exc)
    if semaine is not None and not (e.semaine_debut <= semaine <= e.semaine_fin):
        return _reponse_validation(
            f'La semaine {semaine} est hors période de cet EDT (s{e.semaine_debut}–s{e.semaine_fin}).')
    return Response(services.grille_hebdomadaire(e, semaine))


@api_view(['POST'])
@permission_classes([IsEdtPlanification])
def emploi_du_temps_generer_api(request, pk):
    """Génération automatique de brouillon (P06 — glouton à contraintes)."""
    e = EmploiDuTemps.objects.filter(pk=pk).first()
    if e is None:
        return Response({'detail': 'Emploi du temps introuvable'}, status=status.HTTP_404_NOT_FOUND)
    if e.statut != 'BROUILLON':
        return Response({'detail': 'La génération ne s’applique qu’à un emploi du temps en brouillon.'},
                        status=status.HTTP_409_CONFLICT)
    remplace = str(request.data.get('remplace_existant', '')).lower() in ('1', 'true', 'oui')
    try:
        stats = services.generer_brouillon(e, remplace_existant=remplace)
    except (ValueError, ValidationError) as exc:
        return _erreur_vers_statut(exc)
    _journal('EDT_GENERATION', objet=e, acteur=request.user,
             extra={k: v for k, v in stats.items() if k != 'explications_echecs'})
    return Response(stats)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def emploi_du_temps_export_api(request, pk):
    """Export CSV institutionnel d'un EDT (P20, côté module)."""
    from .models import JOUR_CHOICES
    e = EmploiDuTemps.objects.select_related('annee_academique').filter(pk=pk).first()
    if e is None:
        return Response({'detail': 'Emploi du temps introuvable'}, status=status.HTTP_404_NOT_FOUND)
    jours = dict(JOUR_CHOICES)
    affectations = (e.affectations.filter(actif=True)
                    .select_related('creneau_template', 'groupe', 'formation')
                    .order_by('creneau_template__jour', 'creneau_template__heure_debut', 'semaine_debut'))
    reponse = HttpResponse(content_type='text/csv; charset=utf-8')
    nom = f"edt-{e.pk}-{(e.titre or e.population_label).casefold().replace(' ', '-')[:40]}.csv"
    reponse['Content-Disposition'] = f'attachment; filename="{nom}"'
    reponse.write('\ufeff')  # BOM : Excel ouvre correctement les accents (cf. contrat scolarite).
    ecrivain = csv.writer(reponse)
    ecrivain.writerow(['Jour', 'Heure début', 'Heure fin', 'Semaines', 'Nature', 'Intitulé',
                       'Enseignant', 'Groupe', 'Formation', 'Salle', 'Commentaire'])
    for aff in affectations:
        ct = aff.creneau_template
        ecrivain.writerow([
            jours.get(ct.jour, ct.jour) if ct else '',
            ct.heure_debut.strftime('%H:%M') if ct else '',
            ct.heure_fin.strftime('%H:%M') if ct else '',
            f'S{aff.semaine_debut}–S{aff.semaine_fin}',
            aff.get_nature_display(),
            aff.intitule,
            aff.enseignant_nom,
            str(aff.groupe or ''),
            str(aff.formation or ''),
            aff.salle_nom,
            aff.commentaire.replace('\n', ' '),
        ])
    return reponse


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def referentiel_enseignants_api(request):
    """Annuaire léger des encadrants planifiables (id utilisateur + libellé)."""
    from django.contrib.auth import get_user_model
    User = get_user_model()
    qs = (User.objects
          .filter(is_active=True, role__in=['ENCADRANT', 'FORMATEUR'])
          .order_by('last_name', 'first_name')[:500])
    return Response([
        {
            'id': u.pk,
            'username': u.username,
            'nom_complet': (u.get_full_name() or u.username),
            'role': u.role,
        }
        for u in qs
    ])
