"""GET-INJS APP — campagnes de génération (LOT 2), pilotage et traçabilité.

**Besoin.** Le moteur savait générer les emplois du temps d'une année
(``moteur.annee.generer_annee``), mais un appel HTTP ne laissait aucune trace :
ni périmètre demandé, ni bilan, ni anomalies, ni auteur, ni durée, ni
possibilité de rejouer ou de reprendre. Ce module ajoute la couche
**campagne** — persistante, contrôlée et publiable.

**Règles tenues.**

* une campagne ne peut pas être exécutée deux fois en parallèle
  (verrou pessimiste ``select_for_update`` + statut ``EN_COURS``) ;
* chaque exécution laisse une ligne ``ExecutionCampagne``, **y compris en cas
  d'échec** : aucune erreur n'est avalée ;
* un bilan incomplet n'est jamais présenté comme complet : les anomalies sont
  extraites du bilan réel (groupes non planifiés, séances non placées,
  conflits) ;
* la validation puis la publication restent des gestes humains explicites ;
* la publication du périmètre est **atomique** : si un EDT échoue, aucun EDT
  du lot n'est publié ;
* aucune donnée inventée : les effectifs et séances viennent du bilan du
  moteur, jamais de constantes.

Le module ne duplique ni le RBAC (``edts.permissions``) ni les validateurs
(``moteur.validation``, ``moteur.publication``) : il les appelle.
"""

from __future__ import annotations

import threading
import time

from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from edts.models import CampagneGeneration, EmploiDuTemps, ExecutionCampagne

# ── Statuts et transitions autorisées ────────────────────────────────────────
S = CampagneGeneration.Statut

TRANSITIONS = {
    S.BROUILLON: {S.VALIDATION_DONNEES},
    S.VALIDATION_DONNEES: {S.PRET, S.BROUILLON},
    S.PRET: {S.EN_COURS},
    S.EN_COURS: {S.TERMINE, S.TERMINE_AVEC_ANOMALIES, S.ECHEC},
    S.TERMINE: {S.VALIDE, S.EN_COURS},          # relance possible
    S.TERMINE_AVEC_ANOMALIES: {S.EN_COURS, S.VALIDE},
    S.ECHEC: {S.EN_COURS, S.BROUILLON},
    S.VALIDE: {S.PUBLIE},
    S.PUBLIE: set(),                             # figé : on crée une nouvelle campagne
}

STATUTS_TERMINES = (S.TERMINE, S.TERMINE_AVEC_ANOMALIES, S.ECHEC)


class TransitionRefusee(Exception):
    """Transition de statut non autorisée (message destiné à l'utilisateur)."""

    def __init__(self, motif, detail=None):
        super().__init__(motif)
        self.motif = motif
        self.detail = detail or {}


# ── Création et transitions ──────────────────────────────────────────────────

def creer_campagne(*, annee_academique_id, libelle, user=None,
                   semaines=None, perimetre=None, parametres=None):
    """Crée une campagne en ``BROUILLON`` pour une année académique.

    L'effectif importé est mesuré à la création (dénombrement réel) : il sert
    de référence pour vérifier ensuite que la génération a bien couvert la
    population annoncée.
    """
    from scolarite.models import AnneeAcademique
    from edts.moteur.annee import effectif_importe

    annee = AnneeAcademique.objects.filter(pk=annee_academique_id).first()
    if annee is None:
        raise TransitionRefusee('ANNEE_ACADEMIQUE_INTROUVABLE', {
            'explication': f"L'année académique #{annee_academique_id} est introuvable.",
        })

    semaines = sorted({int(s) for s in (semaines or [1]) if str(s).isdigit()}) or [1]
    if CampagneGeneration.objects.filter(annee_academique=annee, libelle=libelle).exists():
        raise TransitionRefusee('CAMPAGNE_DEJA_EXISTANTE', {
            'explication': (
                'Une campagne porte déjà ce libellé pour cette année académique ; '
                'utilisez un libellé distinct pour conserver un historique lisible.'
            ),
        })

    return CampagneGeneration.objects.create(
        annee_academique=annee,
        libelle=libelle,
        semaines=semaines,
        perimetre=perimetre or {},
        parametres=parametres or {},
        cree_par=user if getattr(user, 'is_authenticated', False) else None,
        statut=S.BROUILLON,
        statistiques={'effectif_importe_a_la_creation': effectif_importe(annee.pk)},
    )


def _charger(campagne_id):
    campagne = CampagneGeneration.objects.filter(pk=campagne_id).first()
    if campagne is None:
        raise TransitionRefusee('CAMPAGNE_INTROUVABLE', {
            'explication': f'La campagne #{campagne_id} est introuvable.',
        })
    return campagne


def _exiger(campagne, cibles):
    if campagne.statut not in cibles:
        autorisees = sorted(TRANSITIONS.get(campagne.statut, set()))
        raise TransitionRefusee('TRANSITION_REFUSEE', {
            'explication': (
                f"L'opération n'est pas possible depuis le statut "
                f'« {campagne.get_statut_display()} ».'
            ),
            'statut_courant': campagne.statut,
            'statuts_acceptes': sorted(cibles),
            'statuts_suivants_possibles': autorisees,
        })


def valider_donnees(campagne_id, *, user=None):
    """``BROUILLON`` → ``VALIDATION_DONNEES`` : les données sont prêtes à contrôler."""
    with transaction.atomic():
        campagne = _charger(campagne_id)
        _exiger(campagne, (S.BROUILLON,))
        campagne.statut = S.VALIDATION_DONNEES
        campagne.save(update_fields=['statut', 'updated_at'])
    return campagne_en_dict(_charger(campagne_id))


def marquer_pret(campagne_id, *, user=None):
    """``VALIDATION_DONNEES`` → ``PRET`` : la campagne peut être lancée."""
    with transaction.atomic():
        campagne = _charger(campagne_id)
        if campagne.statut == S.BROUILLON:
            # Raccourci explicite : un utilisateur qui n'a rien à contrôler
            # (aucun fichier importé) peut déclarer les données prêtes.
            campagne.statut = S.VALIDATION_DONNEES
        _exiger(campagne, (S.VALIDATION_DONNEES,))
        campagne.statut = S.PRET
        campagne.save(update_fields=['statut', 'updated_at'])
    return campagne_en_dict(_charger(campagne_id))


# ── Exécution ────────────────────────────────────────────────────────────────

def demarrer_campagne(campagne_id, *, user=None, asynchrone=True):
    """Lance une exécution de la campagne.

    Verrou : la campagne et la création de l'exécution se font dans la même
    transaction avec ``select_for_update``. Deux appels simultanés ne peuvent
    donc pas créer deux exécutions : le second reçoit ``CAMPAGNE_DEJA_EN_COURS``.

    :param asynchrone: ``True`` exécute la génération dans un fil d'arrière-plan
        (utile pour 3 500 à 14 000 étudiants) ; ``False`` exécute en synchrone
        (tests et environnements sans fils d'exécution).
    """
    with transaction.atomic():
        campagne = (
            CampagneGeneration.objects.select_for_update()
            .filter(pk=campagne_id).first()
        )
        if campagne is None:
            raise TransitionRefusee('CAMPAGNE_INTROUVABLE', {})
        if campagne.statut == S.EN_COURS:
            raise TransitionRefusee('CAMPAGNE_DEJA_EN_COURS', {
                'explication': (
                    'Une exécution est déjà en cours pour cette campagne : '
                    'attendez sa fin avant de la relancer.'
                ),
            })
        _exiger(campagne, (S.PRET, S.TERMINE, S.TERMINE_AVEC_ANOMALIES, S.ECHEC))

        numero = (
            ExecutionCampagne.objects.filter(campagne=campagne)
            .aggregate(m=Max('numero'))['m'] or 0
        ) + 1
        execution = ExecutionCampagne.objects.create(
            campagne=campagne,
            numero=numero,
            statut=ExecutionCampagne.Statut.EN_COURS,
            lancee_par=user if getattr(user, 'is_authenticated', False) else None,
        )
        campagne.statut = S.EN_COURS
        campagne.demarree_le = timezone.now()
        campagne.terminee_le = None
        campagne.save(update_fields=['statut', 'demarree_le', 'terminee_le', 'updated_at'])

    if asynchrone:
        thread = threading.Thread(
            target=executer_campagne,
            args=(campagne_id, execution.pk),
            name=f'getinjs-campagne-{campagne_id}-{numero}',
            daemon=True,
        )
        thread.start()
    else:
        executer_campagne(campagne_id, execution.pk)

    return {
        'campagne_id': campagne_id,
        'execution_id': execution.pk,
        'numero': numero,
        'asynchrone': asynchrone,
    }


def executer_campagne(campagne_id, execution_id):
    """Exécute réellement la génération et consigne tout, y compris l'échec.

    Aucune exception n'est masquée : elle est **enregistrée** (statut ``ECHEC``
    et message technique) puis re-levée vers l'appelant quand l'exécution est
    synchrone. En asynchrone, elle est journalisée par Django.
    """
    campagne = CampagneGeneration.objects.filter(pk=campagne_id).first()
    execution = ExecutionCampagne.objects.filter(pk=execution_id).first()
    if campagne is None or execution is None:
        return None

    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    from edts.moteur.annee import generer_annee

    parametres = campagne.parametres or {}
    debut = time.monotonic()
    try:
        with CaptureQueriesContext(connection) as requetes:
            bilan = generer_annee(
                campagne.annee_academique_id,
                semaines=campagne.semaines or [1],
                persister=bool(parametres.get('persister', True)),
                remplacer=bool(parametres.get('remplacer', True)),
                inclure_maquette=bool(parametres.get('inclure_maquette', True)),
            )
        duree_ms = int((time.monotonic() - debut) * 1000)
        anomalies = extraire_anomalies(bilan)
        statut_execution, statut_campagne = _statuts_depuis_bilan(bilan, anomalies)
        statistiques = {
            'duree_ms': duree_ms,
            'requetes_sql': len(requetes.captured_queries),
            'effectif_importe': bilan.get('totaux', {}).get('etudiants_couverts'),
            'seances_placees': bilan.get('totaux', {}).get('seances_placees'),
            'seances_non_placees': bilan.get('totaux', {}).get('seances_non_placees'),
            'nb_groupes': bilan.get('totaux', {}).get('nb_groupes'),
            'nb_anomalies': len(anomalies),
        }
        with transaction.atomic():
            execution.statut = statut_execution
            execution.terminee_le = timezone.now()
            execution.duree_ms = duree_ms
            execution.bilan = bilan
            execution.anomalies = anomalies
            execution.statistiques = statistiques
            execution.save()

            campagne.statut = statut_campagne
            campagne.terminee_le = execution.terminee_le
            campagne.bilan = bilan
            campagne.anomalies = anomalies
            campagne.statistiques = statistiques
            campagne.save(update_fields=[
                'statut', 'terminee_le', 'bilan', 'anomalies', 'statistiques', 'updated_at',
            ])
        return {'statut': statut_campagne, 'bilan': bilan, 'anomalies': anomalies}

    except Exception as exc:  # noqa: BLE001 — l'échec doit être CONSIGNÉ, jamais masqué
        duree_ms = int((time.monotonic() - debut) * 1000)
        with transaction.atomic():
            execution.statut = ExecutionCampagne.Statut.ECHEC
            execution.terminee_le = timezone.now()
            execution.duree_ms = duree_ms
            execution.erreur = f'{type(exc).__name__}: {exc}'
            execution.save(update_fields=[
                'statut', 'terminee_le', 'duree_ms', 'erreur',
            ])
            campagne.statut = S.ECHEC
            campagne.terminee_le = execution.terminee_le
            campagne.statistiques = {**(campagne.statistiques or {}), 'duree_ms': duree_ms}
            campagne.save(update_fields=['statut', 'terminee_le', 'statistiques', 'updated_at'])
        raise


def _statuts_depuis_bilan(bilan, anomalies):
    """Traduit le bilan du moteur en statut d'exécution et de campagne.

    ``IMPOSSIBLE`` n'est pas un « succès avec avertissements » : c'est un échec
    de génération, consigné comme tel.
    """
    from edts.moteur.annee import ANNEE_COMPLETE, ANNEE_IMPOSSIBLE

    global_ = bilan.get('status_global')
    if global_ == ANNEE_IMPOSSIBLE:
        return ExecutionCampagne.Statut.ECHEC, S.ECHEC
    if global_ == ANNEE_COMPLETE and not anomalies:
        return ExecutionCampagne.Statut.TERMINE, S.TERMINE
    return (
        ExecutionCampagne.Statut.TERMINE_AVEC_ANOMALIES,
        S.TERMINE_AVEC_ANOMALIES,
    )


def extraire_anomalies(bilan):
    """Liste explicite des anomalies d'un bilan — jamais un simple « OK ».

    Une anomalie décrit : nature, groupe concerné, motif et action attendue.
    """
    anomalies = []
    for ligne in bilan.get('groupes', []):
        motif = ligne.get('motif_echec')
        non_placees = ligne.get('seances_non_placees') or 0
        conflits = ligne.get('conflits') or 0
        if motif:
            anomalies.append({
                'niveau': 'BLOQUANT',
                'nature': 'GROUPE_NON_PLANIFIE',
                'groupe_id': ligne.get('groupe_id'),
                'groupe': ligne.get('groupe'),
                'formation': ligne.get('formation'),
                'niveau_etude': ligne.get('niveau'),
                'motif': motif,
                'explication': _explication_motif(motif),
            })
        elif non_placees or conflits:
            anomalies.append({
                'niveau': 'AVERTISSEMENT',
                'nature': 'SEANCES_NON_PLACEES',
                'groupe_id': ligne.get('groupe_id'),
                'groupe': ligne.get('groupe'),
                'formation': ligne.get('formation'),
                'niveau_etude': ligne.get('niveau'),
                'seances_non_placees': non_placees,
                'conflits': conflits,
                'explication': (
                    f'{non_placees} séance(s) n’ont pas pu être placées et '
                    f'{conflits} conflit(s) subsistent : le bilan par groupe en '
                    'donne le détail.'
                ),
            })
    if bilan.get('motif_echec') and not anomalies:
        anomalies.append({
            'niveau': 'BLOQUANT',
            'nature': 'GENERATION_IMPOSSIBLE',
            'motif': bilan['motif_echec'],
            'explication': (bilan.get('detail') or {}).get('explication', ''),
        })
    return anomalies


def _explication_motif(motif):
    return {
        'AUCUN_BESOIN_PLANIFIABLE': (
            'Aucun besoin horaire calculable pour ce groupe : ni affectation '
            'pédagogique, ni maquette active ne le couvre.'
        ),
        'EDT_STATUT_NON_MODIFIABLE': (
            'L’emploi du temps de ce groupe est déjà validé ou publié : il ne '
            'peut plus être régénéré sans nouvelle version.'
        ),
        'VALIDATION_BLOQUANTE': (
            'Le plan produit viole une contrainte obligatoire : il n’est pas persisté.'
        ),
    }.get(motif, 'Motif transmis par le moteur de génération.')


# ── Validation et publication ────────────────────────────────────────────────

def valider_campagne(campagne_id, *, user=None):
    """Contrôle chaque EDT persisté puis marque la campagne ``VALIDE``.

    Refus explicite si un EDT viole une contrainte obligatoire : la campagne
    n'est jamais marquée validée sur la foi d'un simple statut.
    """
    from edts.moteur.validation import valider_emploi_du_temps

    campagne = _charger(campagne_id)
    if campagne.statut not in (S.TERMINE, S.TERMINE_AVEC_ANOMALIES):
        _exiger(campagne, (S.TERMINE, S.TERMINE_AVEC_ANOMALIES))

    edt_ids = [
        ligne['edt_id'] for ligne in (campagne.bilan or {}).get('groupes', [])
        if ligne.get('edt_id')
    ]
    if not edt_ids:
        raise TransitionRefusee('AUCUN_EDT_A_VALIDER', {
            'explication': (
                'La campagne ne contient aucun emploi du temps persisté : '
                'relancez-la avec l’option « persister » activée.'
            ),
        })

    refus = []
    rapports = []
    for edt in EmploiDuTemps.objects.filter(pk__in=edt_ids).order_by('pk'):
        rapport = valider_emploi_du_temps(edt)
        if rapport.valide:
            rapports.append(edt.pk)
        else:
            refus.append({
                'edt_id': edt.pk,
                'titre': edt.titre or edt.population_denominateur,
                'violations': getattr(rapport, 'violations', []),
            })
    if refus:
        raise TransitionRefusee('VALIDATION_BLOQUANTE', {
            'explication': (
                f'{len(refus)} emploi(s) du temps violent une contrainte '
                'obligatoire : la campagne ne peut pas être validée.'
            ),
            'edt_en_echec': refus,
        })

    maintenant = timezone.now()
    with transaction.atomic():
        EmploiDuTemps.objects.filter(pk__in=rapports).update(
            statut='VALIDE', valide_par=user if getattr(user, 'is_authenticated', False) else None,
            valide_le=maintenant, updated_at=maintenant,
        )
        campagne.statut = S.VALIDE
        campagne.save(update_fields=['statut', 'updated_at'])
    return campagne_en_dict(_charger(campagne_id))


def publier_campagne(campagne_id, *, user=None, motif=''):
    """Publie **atomiquement** tous les EDT validés de la campagne.

    Un seul échec annule l'ensemble : on ne laisse jamais un semestre à moitié
    publié. L'historique de la campagne conserve l'empreinte de la publication.
    """
    from edts.moteur.publication import publier_emploi_du_temps

    campagne = _charger(campagne_id)
    _exiger(campagne, (S.VALIDE,))

    edt_ids = [
        ligne['edt_id'] for ligne in (campagne.bilan or {}).get('groupes', [])
        if ligne.get('edt_id')
    ]
    if not edt_ids:
        raise TransitionRefusee('AUCUN_EDT_A_PUBLIER', {})

    resultats = []
    try:
        with transaction.atomic():
            for edt_id in edt_ids:
                resultat = publier_emploi_du_temps(edt_id, user=user)
                resultats.append({'edt_id': edt_id, **resultat})
                if not resultat.get('publie'):
                    # Rollback volontaire : publication atomique du périmètre.
                    raise TransitionRefusee('PUBLICATION_INCOMPLETE', {
                        'explication': (
                            'Un emploi du temps du périmètre n’a pas pu être publié ; '
                            'aucun EDT du lot n’a été publié.'
                        ),
                        'echec': resultats[-1],
                    })
            campagne.statut = S.PUBLIE
            campagne.parametres = {
                **(campagne.parametres or {}),
                'publication': {
                    'publie_le': timezone.now().isoformat(),
                    'publie_par': getattr(user, 'username', None),
                    'motif': motif,
                    'nb_edt': len(resultats),
                },
            }
            campagne.save(update_fields=['statut', 'parametres', 'updated_at'])
    except TransitionRefusee:
        raise
    except Exception as exc:  # noqa: BLE001 — traduit en refus explicite
        raise TransitionRefusee('PUBLICATION_ECHOUEE', {
            'explication': f'La publication a échoué : {exc}',
        }) from exc
    return {**campagne_en_dict(_charger(campagne_id)), 'publications': resultats}


# ── Lecture ──────────────────────────────────────────────────────────────────

def campagne_en_dict(campagne):
    """Représentation stable de la campagne pour l'API et l'interface."""
    execution = campagne.executions.order_by('-numero').first()
    return {
        'id': campagne.pk,
        'libelle': campagne.libelle,
        'annee_academique_id': campagne.annee_academique_id,
        'annee_academique': campagne.annee_academique.libelle,
        'statut': campagne.statut,
        'statut_libelle': campagne.get_statut_display(),
        'semaines': campagne.semaines,
        'perimetre': campagne.perimetre,
        'parametres': campagne.parametres,
        'cree_par': getattr(campagne.cree_par, 'username', None),
        'created_at': campagne.created_at,
        'demarree_le': campagne.demarree_le,
        'terminee_le': campagne.terminee_le,
        'statistiques': campagne.statistiques,
        'anomalies': campagne.anomalies,
        'totaux': (campagne.bilan or {}).get('totaux', {}),
        'status_global': (campagne.bilan or {}).get('status_global'),
        'execution_courante': {
            'id': execution.pk,
            'numero': execution.numero,
            'statut': execution.statut,
            'duree_ms': execution.duree_ms,
            'erreur': execution.erreur,
        } if execution else None,
        'transitions_possibles': sorted(TRANSITIONS.get(campagne.statut, set())),
    }


def resultat_campagne(campagne_id):
    """Bilan détaillé par groupe + anomalies + historique d'exécutions."""
    campagne = _charger(campagne_id)
    return {
        'campagne': campagne_en_dict(campagne),
        'groupes': (campagne.bilan or {}).get('groupes', []),
        'anomalies': campagne.anomalies,
        'totaux': (campagne.bilan or {}).get('totaux', {}),
        'sources': (campagne.bilan or {}).get('sources', {}),
        'executions': [
            {
                'id': e.pk,
                'numero': e.numero,
                'statut': e.statut,
                'demarree_le': e.demarree_le,
                'terminee_le': e.terminee_le,
                'duree_ms': e.duree_ms,
                'statistiques': e.statistiques,
                'erreur': e.erreur,
            }
            for e in campagne.executions.order_by('-numero')
        ],
    }


def statut_campagne(campagne_id):
    """État compact pour l'interrogation périodique (progression)."""
    campagne = _charger(campagne_id)
    execution = campagne.executions.order_by('-numero').first()
    return {
        'id': campagne.pk,
        'statut': campagne.statut,
        'statut_libelle': campagne.get_statut_display(),
        'en_cours': campagne.statut == S.EN_COURS,
        'demarree_le': campagne.demarree_le,
        'terminee_le': campagne.terminee_le,
        'duree_ms': execution.duree_ms if execution else None,
        'totaux': (campagne.bilan or {}).get('totaux', {}),
        'status_global': (campagne.bilan or {}).get('status_global'),
        'nb_anomalies': len(campagne.anomalies or []),
        'erreur': execution.erreur if execution else '',
    }
