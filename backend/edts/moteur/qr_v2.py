"""Contrat transactionnel GET-INJS v2 ↔ Présences QR (phase 4).

Aucun registre legacy n'est réattribué automatiquement. Une identité v2
inconnue crée un registre BROUILLON et un instantané de cohorte **sans** faux
participant QR. Appeler depuis une transaction de placement, jamais seule
après le commit de l'affectation.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from django.db import transaction
from django.utils import timezone

from edts.models_interop import (SalleGeolocalisation, SeanceEvenement,
    SeanceHistorique, SeanceInstantaneAttendus, SeanceRegistre)

BASE_IMPORTEE = 'INSCRIPTIONS_IMPORTEES_EFFECTIF_SEUL'


class IntegrationQRBloquee(ValueError):
    """La collision d'identité ou la protection QR interdit l'UPSERT."""


@dataclass(frozen=True)
class ResultatQR:
    registre_id: int
    uuid: str
    cree: bool
    instantane_id: int
    anomalies: tuple[str, ...]


def _effectif_importe(affectation) -> int:
    from edts.models import InscriptionImportee

    if not affectation.groupe_id or not affectation.date_seance:
        raise IntegrationQRBloquee('Groupe et date réels exigés pour l’instantané QR.')
    return (InscriptionImportee.objects.filter(
        annee_academique_id=affectation.emploi_du_temps.annee_academique_id,
        groupe_id=affectation.groupe_id, statut='INSCRIT')
        .values('matricule').distinct().count())


def _instantane(registre, affectation, *, acteur=None):
    nombre = _effectif_importe(affectation)
    instantane = (SeanceInstantaneAttendus.objects.filter(
        registre=registre, date_seance=affectation.date_seance,
        base_calculee=BASE_IMPORTEE).order_by('id').first())
    if instantane:
        return instantane, nombre != instantane.effectif
    instantane = SeanceInstantaneAttendus.objects.create(
        registre=registre, date_seance=affectation.date_seance,
        base_calculee=BASE_IMPORTEE, effectif=nombre, participants=[], cree_par=acteur)
    SeanceHistorique.objects.create(
        registre=registre, action=SeanceHistorique.Action.INSTANTANE,
        acteur=acteur, details={'instantane_id': instantane.pk,
                                'effectif': nombre, 'base': BASE_IMPORTEE})
    return instantane, False


def _anomalies_salle(affectation) -> list[str]:
    if not affectation.salle_id:
        return ['QR_SALLE_ABSENTE']
    geo = SalleGeolocalisation.objects.filter(salle_id=affectation.salle_id, actif=True,
        statut_configuration=SalleGeolocalisation.StatutConfiguration.CONFIGUREE).first()
    if not geo or not geo.coordonnees_disponibles:
        return ['QR_GEOLOCALISATION_NON_CONFIGUREE']
    return []


@transaction.atomic
def assurer_occurrence(affectation, *, acteur=None) -> ResultatQR:
    """UPSERT sur clé v2, sans changer UUID/clé/affectation d'un registre legacy.

    La création et l'instantané participent à la transaction de l'appelant.
    L'absence de géolocalisation ou de rapprochement d'identités est une
    anomalie explicite, bloquante pour la publication QR, pas pour un brouillon.
    """
    if not affectation.pk or not affectation.date_seance or not affectation.groupe_id:
        raise IntegrationQRBloquee('Placement daté et groupe requis.')
    cle = affectation.cle_occurrence_v2
    if not cle or len(cle) != 64:
        raise IntegrationQRBloquee('Clé v2 absente ou mal formée.')
    registre = (SeanceRegistre.objects.select_for_update()
                .filter(affectation_id=affectation.pk).first())
    if registre is not None:
        if registre.cle_metier != cle:
            raise IntegrationQRBloquee('Registre hérité : clé différente, audit requis.')
        cree = False
    else:
        collision = (SeanceRegistre.objects.select_for_update()
                     .filter(cle_metier=cle).first())
        if collision is not None:
            # Même orphelin : pas de rattachement automatique après suppression
            # ou désactivation d'une séance QR historique.
            raise IntegrationQRBloquee('Clé QR déjà liée ou orpheline : audit requis.')
        registre = SeanceRegistre.objects.create(
            affectation=affectation, cle_metier=cle, cree_par=acteur, modifie_par=acteur)
        SeanceHistorique.objects.create(
            registre=registre, action=SeanceHistorique.Action.CREATION,
            acteur=acteur, details={'affectation_id': affectation.pk,
                                    'cle_occurrence_v2': cle})
        cree = True
    instantane, fige_change = _instantane(registre, affectation, acteur=acteur)
    anomalies = _anomalies_salle(affectation)
    # Le flux importé ne porte pas un identifiant Participant QR fiable.
    anomalies.append('QR_PARTICIPANTS_NON_RAPPROCHES' if instantane.effectif else
                     'QR_AUCUN_INSCRIT_IMPORTE')
    if fige_change:
        anomalies.append('QR_INSTANTANE_FIGE_EFFECTIF_CHANGE')
    return ResultatQR(registre.pk, str(registre.uuid), cree, instantane.pk, tuple(anomalies))


@transaction.atomic
def deplacer_brouillon(registre, *, ancienne_date: date, nouvelle_date: date,
                       acteur=None) -> ResultatQR:
    """Même affectation et UUID ; ne modifier ni pointage ni séance ouverte."""
    registre = SeanceRegistre.objects.select_for_update().get(pk=registre.pk)
    aff = registre.affectation
    if (aff is None or registre.statut != SeanceRegistre.Statut.BROUILLON
            or ancienne_date <= timezone.localdate() or aff.pointages.exists()):
        raise IntegrationQRBloquee('Séance QR ouverte, publiée, passée ou pointée : immuable.')
    if aff.date_seance != nouvelle_date:
        raise IntegrationQRBloquee('Le déplacement doit déjà être validé dans la même transaction.')
    registre.version += 1
    registre.modifie_par = acteur
    registre.save(update_fields=['version', 'modifie_par', 'updated_at'])
    SeanceHistorique.objects.create(
        registre=registre, action=SeanceHistorique.Action.MODIFICATION,
        acteur=acteur, motif='Déplacement du brouillon v2',
        details={'ancienne_date': ancienne_date.isoformat(),
                 'nouvelle_date': nouvelle_date.isoformat(), 'version': registre.version})
    return assurer_occurrence(aff, acteur=acteur)


@transaction.atomic
def lier_reprogrammation(origine, nouvelle, *, motif: str, acteur=None) -> ResultatQR:
    """Nouvelle séance et UUID, ancienne séance conservée ; aucun effacement.

    La séance d'origine doit être annulée/terminée et la nouvelle distincte ;
    une séance publiée active ou un pointage ouvert exige arbitrage humain.
    """
    if not motif.strip():
        raise IntegrationQRBloquee('Motif de reprogrammation obligatoire.')
    anciens = list(SeanceRegistre.objects.select_for_update().filter(
        pk__in=[origine.pk, nouvelle.pk]).order_by('pk'))
    if len(anciens) != 2:
        raise IntegrationQRBloquee('Deux registres distincts sont requis.')
    par_pk = {r.pk: r for r in anciens}
    ancien, nouveau = par_pk[origine.pk], par_pk[nouvelle.pk]
    if (ancien.pk == nouveau.pk or ancien.statut not in (
            SeanceRegistre.Statut.ANNULEE, SeanceRegistre.Statut.TERMINEE)
            or nouveau.statut != SeanceRegistre.Statut.BROUILLON
            or not nouveau.affectation_id or nouveau.seance_origine_id):
        raise IntegrationQRBloquee('Origine non terminale ou nouvelle séance non vierge.')
    if ancien.affectation_id == nouveau.affectation_id:
        raise IntegrationQRBloquee('Une reprogrammation exige une nouvelle affectation.')
    if (ancien.affectation is None or
            ancien.affectation.emploi_du_temps.annee_academique_id !=
            nouveau.affectation.emploi_du_temps.annee_academique_id or
            ancien.affectation.groupe_id != nouveau.affectation.groupe_id):
        raise IntegrationQRBloquee('Origine et rattrapage doivent porter la même cohorte et année.')
    nouveau.seance_origine = ancien
    nouveau.save(update_fields=['seance_origine', 'updated_at'])
    SeanceHistorique.objects.create(
        registre=nouveau, action=SeanceHistorique.Action.REPROGRAMMATION,
        acteur=acteur, motif=motif,
        details={'origine_uuid': str(ancien.uuid), 'nouvelle_uuid': str(nouveau.uuid)})
    from edts.moteur.interop_presences import emettre_evenement
    evt = emettre_evenement(nouveau, SeanceEvenement.Type.SEANCE_REPROGRAMMEE)
    evt.charge_utile['origine_uuid'] = str(ancien.uuid)
    evt.save(update_fields=['charge_utile'])
    resultat = assurer_occurrence(nouveau.affectation, acteur=acteur)
    return resultat


def anomalies_publication_v2(emploi_du_temps) -> dict[str, int]:
    """Préflight en lecture seule : un EDT v2 non réconcilié ne se publie pas.

    Les EDT hérités (sans date ni clé v2) restent sur leur parcours actuel.
    Aucune exception ``force`` n'autorise à ignorer les anomalies QR v2.
    """
    from edts.models import AffectationCreneau
    from django.db.models import Q

    anomalies: dict[str, int] = {}
    geos: dict[int | None, bool] = {}
    lignes = (AffectationCreneau.objects.filter(emploi_du_temps=emploi_du_temps, actif=True)
              .filter(Q(date_seance__isnull=False) | Q(cle_occurrence_v2__isnull=False))
              .select_related('registre_seance').iterator(chunk_size=256))
    for aff in lignes:
        def signaler(code):
            anomalies[code] = anomalies.get(code, 0) + 1

        if not aff.date_seance or not aff.cle_occurrence_v2:
            signaler('QR_V2_OCCURRENCE_INCOMPLETE')
            continue
        try:
            registre = aff.registre_seance
        except SeanceRegistre.DoesNotExist:
            registre = None
        if registre is None or registre.cle_metier != aff.cle_occurrence_v2:
            signaler('QR_V2_REGISTRE_ABSENT_OU_AMBIGU')
            continue
        instantane = SeanceInstantaneAttendus.objects.filter(
            registre=registre, date_seance=aff.date_seance).order_by('-id').first()
        if instantane is None:
            signaler('QR_V2_INSTANTANE_ABSENT')
        elif instantane.base_calculee == BASE_IMPORTEE:
            # L'effectif importé ne prouve aucune identité Participant.
            signaler('QR_V2_PARTICIPANTS_NON_RAPPROCHES')
        else:
            # Il n'existe PAS encore de processus d'attestation métier.
            # Modifier librement la chaîne base_calculee/participants ne doit
            # jamais transformer un brouillon en séance publiable.
            signaler('QR_V2_ATTESTATION_NON_PROUVEE')
        if aff.salle_id not in geos:
            geos[aff.salle_id] = not _anomalies_salle(aff)
        if not geos[aff.salle_id]:
            signaler('QR_V2_GEOLOCALISATION_INCOMPLETE')
    return anomalies
