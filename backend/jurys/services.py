"""Services du module Jurys : workflow, calcul, décisions, PV, publication.

Règles (Prompt 13) :
  - seuls les étudiants concernés (inscriptions VALIDEE de la session) sont inclus ;
  - les propositions proviennent du moteur ECTS de ``scolarite`` (lot L3),
    uniquement à partir de notes VALIDÉES et verrouillées (lot L1) ;
  - toute décision manuelle est justifiée ;
  - une session VERROUILLE ne se modifie plus librement ; la rectification
    passe par une session dédiée (type RECTIFICATION) ;
  - toutes les délibérations sont journalisées (JournalScolarite, append-only).
"""
import hashlib
import json

from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import F, Window
from django.db.models.functions import RowNumber

from scolarite.models import InscriptionAdministrative, journaliser
from scolarite.validation_services import (
    _ponderee,
    calculer_validation_etudiant,
    regle_pour,
)

from .models import DecisionJury, MembreJury, PropositionJury, SessionJury


def transition(session, user):
    """Fait avancer la session vers l'état suivant de la chaîne contrôlée."""
    suivant = SessionJury.TRANSITIONS.get(session.statut)
    if suivant is None:
        raise ValidationError('La session est déjà à son état final (PUBLIE).')

    # Garde-fous spécifiques avant transition.
    if suivant == SessionJury.Statut.PV_GENERE:
        if not DecisionJury.objects.filter(session=session).exists():
            raise ValidationError(
                "Aucune décision enregistrée : le PV exige au moins une décision."
            )
    if suivant == SessionJury.Statut.DELIBERATION:
        if not PropositionJury.objects.filter(session=session).exists():
            raise ValidationError(
                "Aucune proposition calculée : exécutez d'abord l'action CALCUL."
            )

    ancien = session.statut
    with transaction.atomic():
        session.statut = suivant
        session.save(update_fields=['statut', 'updated_at'])
        journaliser(
            'JURY_TRANSITION', objet=session, acteur=user,
            ancienne_valeur=ancien, nouvelle_valeur=suivant,
        )
    return session


def ajouter_membre(session, user_cible, fonction, user):
    """Ajoute un membre au jury (session non verrouillée) et journalise."""
    if session.verrouillee:
        raise ValidationError('Session verrouillée : les membres ne peuvent plus être modifiés.')
    membre, created = MembreJury.objects.get_or_create(
        session=session, user=user_cible,
        defaults={'fonction': fonction, 'ajoute_par': user},
    )
    if created:
        journaliser('JURY_MEMBRE', objet=session, acteur=user,
                    nouvelle_valeur=f'{user_cible} – {fonction}')
    return membre


def inscriptions_concernees(session):
    """Étudiants concernés : inscriptions VALIDEE couvrant la session."""
    qs = InscriptionAdministrative.objects.filter(
        annee_academique=session.annee_academique,
        ref_formation=session.ref_formation,
        niveau=session.niveau,
        statut=InscriptionAdministrative.Statut.VALIDEE,
    ).select_related('etudiant')
    if session.parcours_id:
        qs = qs.filter(parcours=session.parcours)
    return qs


def _empreinte(resultat):
    """SHA-256 d'un résultat moteur (reproductibilité)."""
    brut = json.dumps(resultat, sort_keys=True, default=str).encode()
    return hashlib.sha256(brut).hexdigest()


def _nettoyer_resultat(resultat):
    """Nettoie un dict résultat avant stockage JSONField : Decimal → float.

    PostgreSQL/Django n'acceptent pas les ``decimal.Decimal`` dans un
    JSONField natif ; on convertit donc récursivement les Decimals en
    ``float`` (perte de précision négligeable pour des moyennes /20).
    """
    from decimal import Decimal

    def _clean(v):
        if isinstance(v, Decimal):
            return float(v)
        if isinstance(v, list):
            return [_clean(x) for x in v]
        if isinstance(v, dict):
            return {k: _clean(val) for k, val in v.items()}
        return v

    return _clean(resultat)


def _moyenne_generale(resultat):
    """Moyenne générale = moyenne des semestres pondérée par crédits attendus."""
    paires = [
        (sem['moyenne'], sem['credits_attendus'])
        for sem in resultat.get('semestres', [])
        if sem.get('moyenne') is not None
    ]
    valeur = _ponderee(paires)
    return None if valeur is None else round(valeur, 2)


def calculer_propositions(session, user):
    """Action CALCUL : exécute le moteur pour chaque étudiant et persiste (append-only)."""
    if session.verrouillee:
        raise ValidationError('Session verrouillée : recalcul impossible.')
    if session.statut not in (
        SessionJury.Statut.PREPARATION,
        SessionJury.Statut.CONTROLE,
        SessionJury.Statut.CALCUL,
    ):
        raise ValidationError(
            "Le calcul n'est possible qu'aux états PREPARATION / CONTROLE / CALCUL."
        )

    regle = regle_pour(session.maquette)
    crees = 0
    with transaction.atomic():
        for inscription in inscriptions_concernees(session):
            resultat = calculer_validation_etudiant(inscription, session.maquette, regle)
            resultat = _nettoyer_resultat(resultat)
            PropositionJury.objects.create(
                session=session,
                inscription=inscription,
                participant=inscription.etudiant.participant,
                resultat=resultat,
                empreinte=_empreinte(resultat),
                decision_proposee=resultat['decision_proposee'],
                credits_acquis=resultat['credits_acquis'],
                calcule_par=user,
            )
            crees += 1
        journaliser('JURY_CALCUL', objet=session, acteur=user, nouvelle_valeur=str(crees))
    return crees


def enregistrer_decision(session, inscription, decision, user,
                         justification='', mention='', decision_manuelle=None):
    """Enregistre la décision officielle d'un étudiant (états DELIBERATION/DECISION).

    Une décision divergeant de la proposition du moteur est considérée
    manuelle et exige une justification.
    """
    if session.verrouillee:
        raise ValidationError('Session verrouillée : les décisions ne sont plus modifiables.')
    if session.statut not in (SessionJury.Statut.DELIBERATION, SessionJury.Statut.DECISION):
        raise ValidationError(
            "Les décisions ne se saisissent qu'aux états DELIBERATION / DECISION."
        )
    derniere = (
        PropositionJury.objects.filter(session=session, inscription=inscription)
        .order_by('-calcule_le').first()
    )
    if derniere is None:
        raise ValidationError("Calculez d'abord les propositions (action CALCUL).")

    if decision_manuelle is None:
        decision_manuelle = decision != derniere.decision_proposee
    if decision_manuelle and not (justification or '').strip():
        raise ValidationError({'justification': 'Toute décision manuelle doit être justifiée.'})

    obj, created = DecisionJury.objects.update_or_create(
        session=session, inscription=inscription,
        defaults={
            'participant': inscription.etudiant.participant,
            'decision': decision,
            'credits_acquis': derniere.credits_acquis,
            'moyenne_generale': _moyenne_generale(derniere.resultat),
            'mention': (mention or '').strip(),
            'decision_manuelle': decision_manuelle,
            'justification': (justification or '').strip(),
            'decide_par': user,
        },
    )
    journaliser(
        'JURY_DECISION', objet=obj, acteur=user,
        ancienne_valeur=derniere.decision_proposee,
        nouvelle_valeur=decision,
        commentaire=(justification or '').strip(),
        extra={'decision_manuelle': decision_manuelle},
    )
    return obj, created


def decisions_verrouillables(session):
    """Vérifie que chaque étudiant concerné dispose d'une décision avant verrouillage."""
    concernes = inscriptions_concernees(session).count()
    decidees = DecisionJury.objects.filter(session=session).count()
    if concernes != decidees:
        raise ValidationError(
            f'Décisions incomplètes : {decidees}/{concernes} étudiants décidés.'
        )


def notifier_publication(session):
    """Publication : notification in-app à la Direction (pattern existant).

    Best-effort : la publication ne doit pas échouer pour une notification.
    """
    from authentication.models import User
    from .models import NotificationJury

    try:
        decisions = DecisionJury.objects.filter(session=session).count()
        for dest in User.objects.filter(role=User.Role.DIRECTION, is_active=True):
            NotificationJury.objects.create(
                destinataire=dest,
                session=session,
                message=(
                    f'Jury publié : {session} — {decisions} décision(s) officielle(s).'
                ),
            )
    except Exception:  # noqa: BLE001
        pass


def publier(session, user):
    """Transition finale VERROUILLE → PUBLIE : notifie la Direction."""
    from .models import PVJury
    if session.statut != SessionJury.Statut.VERROUILLE:
        raise ValidationError('Seule une session verrouillée peut être publiée.')
    if not PVJury.objects.filter(session=session).exists():
        raise ValidationError('Aucun PV généré : la publication exige un PV.')
    session = transition(session, user)
    journaliser('JURY_PUBLICATION', objet=session, acteur=user)
    notifier_publication(session)
    return session


# ── Exposition API (lot « Délibérations ») ─────────────────────────────────
# Ces fonctions ne reproduisent AUCUNE règle métier : elles exposent les
# contrôles déjà présents ci-dessus et les agrégats des modèles canoniques
# (SessionJury / PropositionJury / DecisionJury). Aucune nouvelle source de
# vérité, aucun second moteur.


class Gravite(models.TextChoices):
    """Gravité d'une anomalie."""
    BLOQUANTE = 'BLOQUANTE', 'Bloquante'
    AVERTISSEMENT = 'AVERTISSEMENT', 'Avertissement'


def _derniere_propositions(session):
    """Dernier calcul par inscription (Propositions append-only).

    La fonction fenêtre garde le même contrat que ``DISTINCT ON`` PostgreSQL,
    tout en restant exécutable sur SQLite pour le sandbox et les tests locaux.
    """
    return (
        PropositionJury.objects
        .filter(session=session)
        .annotate(
            _rang_calcul=Window(
                expression=RowNumber(),
                partition_by=[F('inscription_id')],
                order_by=[F('calcule_le').desc(), F('pk').desc()],
            ),
        )
        .filter(_rang_calcul=1)
    )


def analyser_deliberation(session):
    """Anomalies RÉELLEMENT contrôlées, dérivées des garde-fous existants.

    Rien n'est inventé : chaque anomalie correspond à un contrôle déjà exercé
    par le workflow — ``transition`` exige une proposition avant DELIBERATION,
    ``decisions_verrouillables`` exige la complétude des décisions,
    ``DecisionJury.clean`` exige une justification pour toute décision manuelle.
    """
    anomalies = []
    concernes_ids = set(inscriptions_concernees(session).values_list('id', flat=True))

    # 1. Population indéterminée.
    if not concernes_ids:
        anomalies.append({
            'code': 'POPULATION_VIDE',
            'gravite': Gravite.BLOQUANTE,
            'message': (
                'Aucune inscription administrative validée ne couvre cette '
                'session : la population à délibérer est indéterminée.'
            ),
            'participant_id': None,
            'bloquante': True,
        })

    proposees = set(_derniere_propositions(session).values_list('inscription_id', flat=True))
    # 2. Aucune proposition : garde-fou de `transition` vers DELIBERATION.
    if not proposees:
        anomalies.append({
            'code': 'PROPOSITIONS_ABSENTES',
            'gravite': Gravite.BLOQUANTE,
            'message': (
                "Aucune proposition calculée : exécutez l'action « calcul » "
                'avant d\'examiner les résultats.'
            ),
            'participant_id': None,
            'bloquante': True,
        })

    # 3. Inscription sans proposition du moteur.
    for inscription_id in sorted(concernes_ids - proposees):
        anomalies.append({
            'code': 'PROPOSITION_MANQUANTE',
            'gravite': Gravite.BLOQUANTE,
            'message': 'Aucune proposition du moteur pour cette inscription.',
            'participant_id': inscription_id,
            'bloquante': True,
        })

    decidees = set(
        DecisionJury.objects.filter(session=session).values_list('inscription_id', flat=True)
    )
    # 4. Décision absente — même contrôle que `decisions_verrouillables`.
    for inscription_id in sorted(concernes_ids - decidees):
        anomalies.append({
            'code': 'DECISION_ABSENTE',
            'gravite': Gravite.BLOQUANTE,
            'message': (
                'Aucune décision de jury enregistrée : la session ne pourra '
                'pas être verrouillée.'
            ),
            'participant_id': inscription_id,
            'bloquante': True,
        })

    # 5. Décision divergente du calcul sans justification (DecisionJury.clean).
    for obj in DecisionJury.objects.filter(session=session, decision_manuelle=True):
        if not (obj.justification or '').strip():
            anomalies.append({
                'code': 'JUSTIFICATION_ABSENTE',
                'gravite': Gravite.BLOQUANTE,
                'message': 'Décision manuelle sans justification : motif obligatoire.',
                'participant_id': obj.inscription_id,
                'bloquante': True,
            })

    # 6. Décision hors périmètre de la session (avertissement, non bloquant).
    for obj in DecisionJury.objects.filter(session=session).exclude(
        inscription_id__in=concernes_ids,
    ):
        anomalies.append({
            'code': 'DECISION_HORS_PERIMETRE',
            'gravite': Gravite.AVERTISSEMENT,
            'message': 'Décision rattachée à une inscription hors périmètre.',
            'participant_id': obj.inscription_id,
            'bloquante': False,
        })

    return anomalies


def decision_officielle_pour(participant, *, session=None):
    """Décision officielle INJS-LMD d'un participant : `DecisionJury` ou `None`.

    SOURCE UNIQUE DE VÉRITÉ. Les écrans de consultation (fiche 360°, exports,
    dashboards) doivent passer par ici : le verdict opérationnel
    `suiviEvaluation.DecisionPedagogique` n'est PAS une autorité académique et
    ne doit jamais être présenté comme telle.

    `session` restreint la recherche à une session de jury donnée ; sinon la
    décision la plus récente est retenue.
    """
    qs = DecisionJury.objects.filter(participant=participant)
    if session is not None:
        return qs.filter(session=session).order_by('-session__created_at').first()
    return qs.order_by('-session__created_at').first()


def statistiques_deliberation(session):
    """Agrégats calculés à la demande depuis les modèles canoniques.

    Aucune colonne dénormalisée : tout provient de ``Count`` /
    ``values().annotate()`` sur SessionJury / DecisionJury /
    PropositionJury — pas de boucle Python sur les participants.
    """
    participants = inscriptions_concernees(session).count()

    # Répartition des décisions : une seule requête agrégée.
    repartition = {
        row['decision']: row['total']
        for row in DecisionJury.objects.filter(session=session)
        .values('decision')
        .annotate(total=models.Count('id'))
    }
    admis = repartition.get(DecisionJury.Decision.ADMIS, 0) + repartition.get(
        DecisionJury.Decision.ADMIS_AVEC_RESERVES, 0,
    )
    ajournes = repartition.get(DecisionJury.Decision.AJOURNE, 0)
    exclusions = repartition.get(DecisionJury.Decision.EXCLUSION, 0)
    autres = sum(repartition.values()) - admis - ajournes - exclusions

    decidees = DecisionJury.objects.filter(session=session).count()
    propositions = _derniere_propositions(session).count()
    anomalies = analyser_deliberation(session)

    return {
        'session_id': session.pk,
        'statut': session.statut,
        'verrouillee': session.verrouillee,
        'participants': participants,
        'admis': admis,
        'ajournes': ajournes,
        'exclus': exclusions,
        'autres_decisions': autres,
        'decisions': {
            'enregistrees': decidees,
            'completes': decidees >= participants,
            'manquantes': max(participants - decidees, 0),
        },
        'propositions': propositions,
        'repartition': repartition,
        'anomalies': {
            'total': len(anomalies),
            'bloquantes': sum(1 for a in anomalies if a['bloquante']),
        },
    }
