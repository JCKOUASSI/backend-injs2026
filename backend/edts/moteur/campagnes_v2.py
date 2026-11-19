"""Traitement durable par groupe de travaux V2, limité aux bases BENCH (phase 3).

Un worker supervisé invoquera ``executer_campagne_v2`` ; aucune tâche
asynchrone n'est lancée par une requête HTTP et aucun travail réel n'est
activé avant le contrat Présences QR de phase 4.
"""
from __future__ import annotations

from datetime import timedelta
from itertools import groupby, tee
from typing import Iterable
from uuid import uuid4

from django.db import transaction
from django.utils import timezone

from edts.moteur.application_v2 import _autoriser_bench, appliquer_ligne, proposer_ligne
from edts.moteur.planification_v2 import DecisionLigne, TravailSeance


def travaux_non_attestes(annee_id: int, *, groupe_ids: tuple[int, ...] = ()) -> Iterable[TravailSeance]:
    """Flux DB conservateur : jamais qualifier un volume de confirmé seul.

    Si aucune affectation n'existe pour un groupe, une ligne À_REVOIR le rend
    explicite. Les entrées fiables et leur preuve seront intégrées en phase 4
    après audit des volumes, sans utiliser la migration scolarité locale.
    """
    from scolarite.models import AffectationPedagogique, Groupe

    groupes = Groupe.objects.filter(annee_academique_id=annee_id, actif=True,
        ref_formation__perimetre='INJS').order_by('pk')
    if groupe_ids:
        groupes = groupes.filter(pk__in=groupe_ids)
    affectations = (AffectationPedagogique.objects.filter(
        annee_academique_id=annee_id, groupe__in=groupes,
        statut__in=('VALIDEE', 'PLANIFIEE'))
        .order_by('groupe_id', 'pk').iterator(chunk_size=256))
    courant = next(affectations, None)
    for groupe in groupes.iterator(chunk_size=256):
        trouve = False
        while courant is not None and courant.groupe_id == groupe.pk:
            trouve = True
            yield TravailSeance(annee_id, groupe.pk, courant.ecue_id or 0,
                courant.type_enseignement if courant.type_enseignement in ('CM','TD','TP') else 'CM',
                courant.pk, 0, 0, formateur_id=courant.enseignant_id,
                affectation_pedagogique_id=courant.pk,
                source_confirmee=False)
            courant = next(affectations, None)
        if not trouve:
            yield TravailSeance(annee_id, groupe.pk, 0, 'CM', 1, 0, 0)


def simuler_campagne_v2(travaux: Iterable[TravailSeance], *, revision: int,
                         graine: int = 0, politique: dict | None = None) -> Iterable[DecisionLigne]:
    """Dry-run sans écriture SQL ; les choix précédents occupent le plan simulé."""
    from edts.moteur.application_v2 import _contexte
    from edts.moteur.occupation_v2 import IndexOccupation, OccupationHeriteeNonResolue
    from edts.moteur.planification_v2 import choisir_ligne
    from edts.moteur.contraintes import politique_souples

    politique = politique if politique is not None else politique_souples()
    simul = IndexOccupation()
    cache_groupe = None
    cache_annee = None
    contexte = None
    for travail in travaux:
        if travail.groupe_id != cache_groupe or travail.annee_id != cache_annee:
            if cache_annee is not None and travail.annee_id != cache_annee:
                simul = IndexOccupation()  # l'index d'une année ne traverse pas l'autre
            cache_groupe = travail.groupe_id
            cache_annee = travail.annee_id
            try:
                contexte = _contexte(travail)
            except (OccupationHeriteeNonResolue, ValueError):
                contexte = None
        if contexte is None:
            yield DecisionLigne('A_REVOIR', 'OCCUPATION_OU_PLAGE_AUDIT', travail.cle())
            continue
        annee, groupe, periodes, creneaux, salles, dispos, persiste = contexte

        class OccupationsFusionnees:
            def conflits(self, jour, debut, fin, **ressources):
                return persiste.conflits(jour, debut, fin, **ressources) + simul.conflits(
                    jour, debut, fin, **ressources)

            def score_souple(self, jour, groupe_id, debut, fin, regle):
                return persiste.score_souple(jour, groupe_id, debut, fin, regle) + simul.score_souple(
                    jour, groupe_id, debut, fin, regle)

        decision = choisir_ligne(travail, annee=annee, groupe=groupe, revision=revision,
            periodes=periodes, creneaux=creneaux, salles=salles, disponibilites=dispos,
            index=OccupationsFusionnees(), graine=graine, politique=politique)
        if decision.statut == 'PLACEE':
            simul.ajouter(decision.jour, decision.debut, decision.fin,
                groupe_id=travail.groupe_id, formateur_id=travail.formateur_id,
                salle_id=decision.salle_id)
        yield decision


def executer_campagne_v2(execution_id: int, *, travaux: Iterable[TravailSeance] | None = None,
                          revision: int, graine: int = 0,
                          max_groupes: int | None = None) -> dict:
    """Checkpoint atomique par groupe, reprise par (execution, cle_travail).

    Une écriture n'est permise que sous DEBUG + flag + année BENCHMARK ; les
    périodes et les volumes confirmés sont toujours vérifiés par ligne.
    ``max_groupes`` sert uniquement à simuler une interruption contrôlée.
    """
    from edts.models import ExecutionCampagne, ExecutionLigne

    identifiant_worker = uuid4().hex
    with transaction.atomic():
        execution = (ExecutionCampagne.objects.select_for_update()
                     .select_related('campagne__annee_academique').get(pk=execution_id))
        annee = execution.campagne.annee_academique
        _autoriser_bench(annee)
        maintenant = timezone.now()
        if execution.lease_jusqua and execution.lease_jusqua > maintenant and execution.worker_id:
            raise RuntimeError('Exécution déjà détenue par un worker actif.')
        if execution.statut not in ('EN_COURS', 'ECHEC'):
            raise ValueError('Exécution non reprenable dans ce statut.')
        execution.worker_id = identifiant_worker
        execution.heartbeat_le = maintenant
        execution.lease_jusqua = maintenant + timedelta(minutes=5)
        execution.statut = 'EN_COURS'
        execution.save(update_fields=['worker_id', 'heartbeat_le', 'lease_jusqua', 'statut'])
    source = travaux if travaux is not None else travaux_non_attestes(annee.pk)
    from edts.moteur.contraintes import politique_souples
    politique = politique_souples()  # une seule lecture par exécution
    groupes_traites = 0
    dernier_groupe = -1
    try:
        for gid, lignes in groupby(source, key=lambda x: x.groupe_id):
            if gid <= dernier_groupe:
                raise ValueError('Les travaux doivent être triés par groupe croissant.')
            dernier_groupe = gid
            with transaction.atomic():
                execution = ExecutionCampagne.objects.select_for_update().get(pk=execution_id)
                if execution.worker_id != identifiant_worker:
                    raise RuntimeError('Lease détenu par un autre worker.')
                deja = set(ExecutionLigne.objects.filter(execution=execution, groupe_id=gid)
                           .values_list('cle_travail', flat=True))
                resultats = []
                # tee n'accumule qu'une ligne en décalage : le simulateur lit
                # le groupe en flux et met à jour son occupation incrémentale.
                def nouveaux_travaux():
                    for t in lignes:
                        if t.annee_id != annee.pk or t.groupe_id != gid:
                            raise ValueError('Travail hors périmètre de l’exécution.')
                        if t.cle() not in deja:
                            yield t

                disponibles, simulation = tee(nouveaux_travaux())
                for travail, proposition in zip(disponibles, simuler_campagne_v2(
                        simulation, revision=revision, graine=graine, politique=politique)):
                    decision = (appliquer_ligne(travail, proposition, revision=revision, graine=graine)
                                if proposition.statut == 'PLACEE' else proposition)
                    if decision.code == 'DEJA_PLACEE':
                        decision = DecisionLigne('PLACEE', 'DEJA_PLACEE', travail.cle(),
                            jour=decision.jour, creneau_id=decision.creneau_id,
                            salle_id=decision.salle_id, score_souple=decision.score_souple)
                    resultats.append(ExecutionLigne(
                        execution=execution, cle_travail=travail.cle(), groupe_id=gid,
                        ecue_id=travail.ecue_id or None, type_seance=travail.type_seance,
                        cle_occurrence_v2=travail.cle() if decision.statut == 'PLACEE' else None,
                        date_candidate=decision.jour, statut=decision.statut,
                        code_contrainte=decision.code, score_souple=decision.score_souple,
                        version_calendrier=revision))
                    deja.add(travail.cle())
                ExecutionLigne.objects.bulk_create(resultats, batch_size=256)
                execution.lignes_lues += len(resultats)
                execution.lignes_traitees += len(resultats)
                execution.lignes_placees += sum(l.statut == 'PLACEE' for l in resultats)
                execution.lignes_a_revoir += sum(l.statut == 'A_REVOIR' for l in resultats)
                execution.lignes_echec += sum(l.statut == 'ECHEC' for l in resultats)
                execution.version_calendrier = revision
                execution.heartbeat_le = timezone.now()
                execution.lease_jusqua = execution.heartbeat_le + timedelta(minutes=5)
                execution.save(update_fields=['lignes_lues','lignes_traitees','lignes_placees',
                    'lignes_a_revoir','lignes_echec','version_calendrier',
                    'heartbeat_le','lease_jusqua'])
            groupes_traites += 1
            if max_groupes is not None and groupes_traites >= max_groupes:
                # Simulation d'arrêt : le prochain appel peut reprendre.
                with transaction.atomic():
                    ExecutionCampagne.objects.filter(pk=execution_id, worker_id=identifiant_worker).update(
                        lease_jusqua=timezone.now(), worker_id='')
                return {'etat': 'INTERROMPU', 'groupes_traites': groupes_traites}
        with transaction.atomic():
            execution = ExecutionCampagne.objects.select_for_update().get(pk=execution_id)
            if execution.worker_id != identifiant_worker:
                raise RuntimeError('Lease expiré pendant le calcul.')
            execution.statut = ('TERMINE_AVEC_ANOMALIES'
                if (not execution.lignes_traitees or execution.lignes_echec
                    or execution.lignes_a_revoir) else 'TERMINE')
            execution.terminee_le = timezone.now()
            if not execution.lignes_traitees:
                execution.anomalies = [{'code': 'AUCUN_GROUPE_INJS',
                    'explication': 'Aucune ligne à planifier dans le périmètre.'}]
            execution.statistiques = {'moteur_v2': True, 'graine': graine,
                'non_publiable_sans_qr': True,
                'score_souple_total': sum(ExecutionLigne.objects.filter(
                    execution=execution, statut='PLACEE').values_list('score_souple', flat=True))}
            execution.worker_id = ''
            execution.lease_jusqua = None
            execution.save(update_fields=['statut', 'terminee_le', 'statistiques',
                                          'anomalies', 'worker_id', 'lease_jusqua'])
        return {'etat': execution.statut, 'groupes_traites': groupes_traites,
                'lignes_placees': execution.lignes_placees,
                'lignes_a_revoir': execution.lignes_a_revoir,
                'lignes_echec': execution.lignes_echec}
    except Exception:
        with transaction.atomic():
            ExecutionCampagne.objects.filter(pk=execution_id, worker_id=identifiant_worker).update(
                worker_id='', lease_jusqua=timezone.now())
        raise
