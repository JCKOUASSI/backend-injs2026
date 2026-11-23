"""Façade manuelle/automatique expérimentale (BENCH uniquement).

La persistance et l'UPSERT QR sont interdits hors DEBUG, année BENCHMARK
et drapeau explicite ; aucune publication automatique.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import date

from django.conf import settings
from django.db import transaction
from django.db.models import Q

from edts.moteur.calendrier_v2 import semaine_academique
from edts.moteur.occupation_v2 import OccupationHeriteeNonResolue, indexer_affectations
from edts.moteur.planification_v2 import DecisionLigne, TravailSeance, choisir_ligne


def _autoriser_bench(annee):
    if not (settings.DEBUG and getattr(settings, 'GETINJS_V2_EXPERIMENTAL_WRITE', False)
            and annee.libelle.startswith('BENCHMARK-')):
        raise PermissionError('Moteur v2 non activé : écriture réservée à une base BENCHMARK isolée.')


def _contexte(travail: TravailSeance, *, jour: date | None = None,
              exclure_cle: str | None = None):
    from edts.models import (AffectationCreneau, CreneauTemplate, DisponibiliteHoraire,
                             PeriodeAcademique)
    from formations.models import RefSalle
    from scolarite.models import AnneeAcademique, Groupe

    annee = AnneeAcademique.objects.get(pk=travail.annee_id)
    groupe = Groupe.objects.select_related('ref_formation', 'niveau').get(pk=travail.groupe_id)
    revisions = (PeriodeAcademique.objects.filter(annee_academique=annee, actif=True)
                 .select_related('revision').order_by('date_debut', 'pk'))
    # La lecture est bornée au groupe et aux portées applicables.
    revisions = revisions.filter(Q(portee='GLOBAL') |
        Q(portee='FORMATION', formation_id=groupe.ref_formation_id) |
        Q(portee='NIVEAU', niveau_id=groupe.niveau_id) |
        Q(portee='GROUPE', groupe_id=groupe.pk))
    periodes = tuple(revisions.iterator(chunk_size=256))
    creneaux = tuple(CreneauTemplate.objects.order_by('jour', 'heure_debut', 'pk'))
    salles = tuple(
        RefSalle.objects.filter(actif=True)
        .select_related('type_espace')
        .order_by('pk')
    )
    dispos = tuple(DisponibiliteHoraire.objects.filter(annee_academique=annee,
        statut='INDISPONIBLE').filter(Q(enseignant_id=travail.formateur_id) |
                                       Q(salle__in=salles)).iterator(chunk_size=256))
    # Les anciens placements sans date ne sont PAS ignorés : tant qu'une
    # plage de l'année coïncide, on ne sait pas l'évaluer sans réconciliation.
    anciennes = AffectationCreneau.objects.filter(
        emploi_du_temps__annee_academique=annee, actif=True, date_seance__isnull=True)
    if jour is not None:
        semaine = semaine_academique(annee, jour)
        anciennes = anciennes.filter(semaine_debut__lte=semaine, semaine_fin__gte=semaine)
    if anciennes.exists():
        raise OccupationHeriteeNonResolue('Plage historique active : rapprochement QR requis.')
    occupations = AffectationCreneau.objects.filter(
        emploi_du_temps__annee_academique=annee, actif=True, date_seance__isnull=False)
    if jour is not None:
        occupations = occupations.filter(date_seance=jour)
    if exclure_cle:
        occupations = occupations.exclude(cle_occurrence_v2=exclure_cle)
    index = indexer_affectations(occupations.iterator(chunk_size=256))
    return annee, groupe, periodes, creneaux, salles, dispos, index


def proposer_ligne(travail: TravailSeance, *, revision: int, graine: int = 0,
                   jour: date | None = None, exclure_cle: str | None = None,
                   politique: dict | None = None) -> DecisionLigne:
    """Même planification pour le manuel et l'automatique, sans mutation."""
    try:
        annee, groupe, periodes, creneaux, salles, dispos, index = _contexte(
            travail, jour=jour, exclure_cle=exclure_cle)
    except OccupationHeriteeNonResolue:
        return DecisionLigne('A_REVOIR', 'PLAGE_HISTORIQUE_AUDIT', travail.cle())
    except ValueError:
        return DecisionLigne('A_REVOIR', 'OCCUPATION_EXISTANTE_INCOHERENTE', travail.cle())
    if politique is None:
        from edts.moteur.contraintes import politique_souples
        politique = politique_souples()
    return choisir_ligne(travail, annee=annee, groupe=groupe, revision=revision,
        periodes=periodes, creneaux=creneaux, salles=salles, disponibilites=dispos,
        index=index, dates=[jour] if jour else None, graine=graine, politique=politique)


@transaction.atomic
def appliquer_ligne(travail: TravailSeance, proposition: DecisionLigne, *,
                   revision: int, graine: int = 0) -> DecisionLigne:
    """Applique une proposition BENCH, avec revalidation sous verrou du jour.

    Ne désactive ni ne supprime un placement ; une clé existante portant un
    registre est seulement reconnue si la position est inchangée.
    """
    from edts.models import (AffectationCreneau, CreneauTemplate, EmploiDuTemps,
                             PeriodeAcademique, VerrouJour)
    from formations.models import RefSalle
    from scolarite.models import AnneeAcademique, Groupe

    annee = AnneeAcademique.objects.select_for_update().get(pk=travail.annee_id)
    _autoriser_bench(annee)
    if proposition.statut != 'PLACEE' or proposition.cle != travail.cle() or not proposition.jour:
        return DecisionLigne('A_REVOIR', 'PROPOSITION_INVALIDE', travail.cle())
    semaine = semaine_academique(annee, proposition.jour)
    verrou, _ = VerrouJour.objects.get_or_create(annee_academique=annee, date=proposition.jour)
    VerrouJour.objects.select_for_update().get(pk=verrou.pk)
    groupe = Groupe.objects.select_related('ref_formation', 'niveau').get(pk=travail.groupe_id)
    if groupe.annee_academique_id != annee.pk:
        return DecisionLigne('A_REVOIR', 'PERIMETRE_INCOHERENT', travail.cle())
    existant = (AffectationCreneau.objects.select_for_update()
                .filter(cle_occurrence_v2=travail.cle()).first())
    if existant is not None:
        if (existant.date_seance == proposition.jour and existant.creneau_template_id == proposition.creneau_id
                and existant.salle_id == proposition.salle_id and existant.actif):
            from edts.moteur.qr_v2 import assurer_occurrence
            resultat_qr = assurer_occurrence(existant)
            return replace(proposition, code=('DEJA_PLACEE_QR_A_REVOIR'
                           if resultat_qr.anomalies else 'DEJA_PLACEE'))
        return DecisionLigne('A_REVOIR', 'OCCURRENCE_EXISTANTE_PROTEGEE', travail.cle())
    # Revalidation du contexte depuis la DB à l'intérieur de la transaction.
    courante = proposer_ligne(travail, revision=revision, graine=graine, jour=proposition.jour)
    if courante.statut != 'PLACEE':
        return courante
    slot = CreneauTemplate.objects.filter(pk=proposition.creneau_id).first()
    salle = (
        RefSalle.objects.filter(pk=proposition.salle_id, actif=True)
        .select_related('type_espace')
        .first()
    )
    if not slot or not salle:
        return DecisionLigne('ECHEC', 'RESSOURCE_INDISPONIBLE', travail.cle())
    from edts.moteur.calendrier_v2 import evaluer_periodes
    from edts.moteur.contraintes import compatible_salle, capacite_suffisante
    from edts.moteur.occupation_v2 import minute
    periode = PeriodeAcademique.objects.filter(
        annee_academique=annee, revision__numero=revision).select_related('revision')
    calendrier = evaluer_periodes(annee, groupe, proposition.jour,
        {'CM': 'COURS', 'TD': 'TD', 'TP': 'TP', 'EXAM': 'EVALUATION'}[travail.type_seance],
        periode.iterator(chunk_size=256), revision_numero=revision)
    debut, fin = minute(slot.heure_debut), minute(slot.heure_fin)
    if (not calendrier.autorise or slot.jour != ('LUNDI','MARDI','MERCREDI','JEUDI','VENDREDI','SAMEDI','DIMANCHE')[proposition.jour.weekday()]
            or debut != proposition.debut or fin != proposition.fin or
            fin - debut != travail.duree_minutes or
            not compatible_salle(
                salle,
                {'CM': 'COURS', 'TD': 'TD', 'TP': 'TP', 'EXAM': 'EVALUATION'}[
                    travail.type_seance
                ],
                travail.intitule,
            ) or
            not capacite_suffisante(salle, travail.effectif)):
        return DecisionLigne('ECHEC', 'PROPOSITION_EXPIREE', travail.cle())
    # La proposition annuelle est classée dans une fenêtre différente de
    # celle du recalcul sur un jour précis. Elle peut sortir du top 4 *sans*
    # être invalide : sa présence parmi les alternatives n'est donc PAS une
    # contrainte dure. Recontrôler explicitement la disponibilité du triplet
    # (enseignant, salle, plage) avant l'écriture, puis l'occupation SQL.
    from edts.models import DisponibiliteHoraire
    from edts.moteur.planification_v2 import _indisponible
    indispos = DisponibiliteHoraire.objects.filter(
        annee_academique=annee, statut='INDISPONIBLE', jour=slot.jour).filter(
        Q(enseignant_id=travail.formateur_id) | Q(salle_id=salle.pk))
    if _indisponible(indispos.iterator(chunk_size=256), travail, salle,
                    proposition.jour, debut, fin):
        return DecisionLigne('ECHEC', 'INDISPONIBILITE', travail.cle())
    # Deux demandes simultanées sont sérialisées par (année, date) ; la
    # relecture ci-dessus refuse les collisions mais la liste de candidats
    # doit être vérifiée à nouveau pour la cible demandée.
    from edts.moteur.occupation_v2 import indexer_affectations
    cibles = AffectationCreneau.objects.filter(
        emploi_du_temps__annee_academique=annee, date_seance=proposition.jour, actif=True)
    index = indexer_affectations(cibles.iterator(chunk_size=256))
    if index.conflits(proposition.jour, debut, fin, groupe_id=groupe.pk,
                      formateur_id=travail.formateur_id, salle_id=salle.pk):
        return DecisionLigne('ECHEC', 'OCCUPATION', travail.cle())
    edt, _ = EmploiDuTemps.objects.get_or_create(
        annee_academique=annee, population_type='GROUPE', population_id=groupe.pk,
        version=1, defaults={'titre': f'BENCH {groupe.pk}', 'statut': 'BROUILLON',
                             'semaine_debut': 1, 'semaine_fin': semaine})
    if edt.statut != 'BROUILLON':
        return DecisionLigne('A_REVOIR', 'EDT_NON_MODIFIABLE', travail.cle())
    if edt.semaine_fin < semaine:
        edt.semaine_fin = semaine
        edt.save(update_fields=['semaine_fin', 'updated_at'])
    affectation = AffectationCreneau.objects.create(
        emploi_du_temps=edt, creneau_template=slot,
        semaine_debut=semaine, semaine_fin=semaine,
        date_seance=proposition.jour, cle_occurrence_v2=travail.cle(),
        minute_debut=debut, minute_fin=fin, revision_calendrier=revision,
        salle=salle, salle_nom=salle.nom, formation_id=groupe.ref_formation_id,
        groupe=groupe, formateur_id=travail.formateur_id,
        ecue_id=travail.ecue_id or None,
        affectation_pedagogique_id=travail.affectation_pedagogique_id,
        nature={'CM': 'COURS', 'TD': 'TD', 'TP': 'TP', 'EXAM': 'EVALUATION'}[travail.type_seance],
        intitule='BENCHMARK — séance non publiable', actif=True)
    from edts.moteur.qr_v2 import assurer_occurrence
    resultat_qr = assurer_occurrence(affectation)
    return replace(proposition, code=('PLACEE_QR_A_REVOIR' if resultat_qr.anomalies
                                       else 'PLACEMENT_POSSIBLE'))


def appliquer_proposition_automatique(travail: TravailSeance, proposition: DecisionLigne,
                                       *, revision: int, graine: int = 0) -> DecisionLigne:
    """Répare seulement une simulation devenue obsolète après un commit précédent.

    La simulation anticipe virtuellement les lignes, mais un candidat hors des
    alternatives courantes est refusé par appliquer_ligne. Reproposer depuis
    l'occupation SQL *actuelle* puis réappliquer sous ses propres verrous ;
    jamais forcer une proposition expirée, ni écraser une séance QR.
    """
    decision = appliquer_ligne(travail, proposition, revision=revision, graine=graine)
    if decision.code not in ('PROPOSITION_EXPIREE', 'OCCUPATION', 'INDISPONIBILITE'):
        return decision
    courante = proposer_ligne(travail, revision=revision, graine=graine)
    if courante.statut != 'PLACEE':
        return courante
    return appliquer_ligne(travail, courante, revision=revision, graine=graine)


@transaction.atomic
def deplacer_ligne(travail: TravailSeance, proposition: DecisionLigne, *,
                   revision: int, version_attendue=None) -> DecisionLigne:
    """Déplace uniquement un brouillon BENCH futur sans pointage.

    Le registre et son UUID restent attachés à la même affectation ; une
    séance publiée, ouverte, pointée ou passée demeure immuable.
    """
    from edts.models import AffectationCreneau, CreneauTemplate, VerrouJour
    from edts.models_interop import SeanceRegistre
    from formations.models import RefSalle
    from scolarite.models import AnneeAcademique
    from edts.moteur.occupation_v2 import minute
    from edts.moteur.planification_v2 import JOURS

    annee = AnneeAcademique.objects.select_for_update().get(pk=travail.annee_id)
    _autoriser_bench(annee)
    if proposition.statut != 'PLACEE' or proposition.cle != travail.cle() or not proposition.jour:
        return DecisionLigne('A_REVOIR', 'PROPOSITION_INVALIDE', travail.cle())
    aff = (AffectationCreneau.objects.select_for_update()
           .select_related('emploi_du_temps').filter(cle_occurrence_v2=travail.cle()).first())
    if aff is None or not aff.actif:
        return DecisionLigne('A_REVOIR', 'OCCURRENCE_INTROUVABLE', travail.cle())
    if aff.emploi_du_temps.statut != 'BROUILLON':
        return DecisionLigne('A_REVOIR', 'EDT_NON_MODIFIABLE', travail.cle())
    if (version_attendue is not None and aff.updated_at != version_attendue):
        return DecisionLigne('A_REVOIR', 'VERSION_OBSOLETE', travail.cle())
    from django.utils import timezone
    registre = SeanceRegistre.objects.select_for_update().filter(affectation=aff).first()
    if (aff.date_seance <= timezone.localdate() or
            proposition.jour <= timezone.localdate() or aff.pointages.exists() or
            (registre and (registre.cle_metier != travail.cle() or
             registre.statut != SeanceRegistre.Statut.BROUILLON))):
        return DecisionLigne('A_REVOIR', 'QR_PROTEGE', travail.cle())
    for jour in sorted({aff.date_seance, proposition.jour}):
        verrou, _ = VerrouJour.objects.get_or_create(annee_academique=annee, date=jour)
        VerrouJour.objects.select_for_update().get(pk=verrou.pk)
    # Même solveur que l'automatique, en excluant la position d'origine.
    courant = proposer_ligne(travail, revision=revision, jour=proposition.jour,
                             exclure_cle=travail.cle())
    if courant.statut != 'PLACEE' or (proposition.jour, proposition.creneau_id,
         proposition.salle_id) not in ((courant.jour, courant.creneau_id, courant.salle_id),
                                        *courant.alternatives):
        return DecisionLigne('ECHEC', 'PROPOSITION_EXPIREE', travail.cle())
    slot = CreneauTemplate.objects.filter(pk=proposition.creneau_id).first()
    salle = RefSalle.objects.filter(pk=proposition.salle_id, actif=True).first()
    if not slot or not salle or slot.jour != JOURS[proposition.jour.weekday()]:
        return DecisionLigne('ECHEC', 'RESSOURCE_INDISPONIBLE', travail.cle())
    debut, fin = minute(slot.heure_debut), minute(slot.heure_fin)
    if (debut, fin) != (proposition.debut, proposition.fin):
        return DecisionLigne('ECHEC', 'PROPOSITION_EXPIREE', travail.cle())
    semaine = semaine_academique(annee, proposition.jour)
    ancienne_date = aff.date_seance
    aff.date_seance = proposition.jour
    aff.semaine_debut = aff.semaine_fin = semaine
    aff.creneau_template = slot
    aff.salle = salle
    aff.salle_nom = salle.nom
    aff.minute_debut, aff.minute_fin = debut, fin
    aff.revision_calendrier = revision
    aff.save(update_fields=['date_seance', 'semaine_debut', 'semaine_fin',
        'creneau_template', 'salle', 'salle_nom', 'minute_debut', 'minute_fin',
        'revision_calendrier', 'updated_at'])
    from edts.moteur.qr_v2 import assurer_occurrence, deplacer_brouillon
    resultat_qr = (deplacer_brouillon(registre, ancienne_date=ancienne_date,
                                     nouvelle_date=proposition.jour)
                   if registre else assurer_occurrence(aff))
    return replace(proposition, code=('DEPLACE_QR_A_REVOIR' if resultat_qr.anomalies
                                       else 'DEPLACE'))


@transaction.atomic
def reprogrammer_ligne(origine_uuid, nouveau_travail: TravailSeance,
                       proposition: DecisionLigne, *, revision: int,
                       motif: str) -> DecisionLigne:
    """Nouvelle occurrence liée à une séance QR terminale, sans modifier l'ancienne.

    Le nouvel ordinal donne une clé distincte ; l'ancienne affectation et son
    UUID/instantané/pointages demeurent inchangés. BENCH uniquement.
    """
    from edts.models import AffectationCreneau
    from edts.models_interop import SeanceRegistre
    from edts.moteur.qr_v2 import IntegrationQRBloquee, lier_reprogrammation

    from scolarite.models import AnneeAcademique
    # Même ordre de verrous que appliquer_ligne/deplacer_ligne : année avant QR.
    annee = AnneeAcademique.objects.select_for_update().get(pk=nouveau_travail.annee_id)
    _autoriser_bench(annee)
    # affectation est nullable sur le registre historique : SELECT FOR UPDATE
    # sur un LEFT JOIN est interdit par PostgreSQL. Charger la relation après
    # verrouillage du registre, dans la même transaction.
    ancien = SeanceRegistre.objects.select_for_update().filter(uuid=origine_uuid).first()
    if (ancien is None or ancien.affectation is None or
            ancien.statut not in ('ANNULEE', 'TERMINEE') or
            not motif.strip() or
            ancien.affectation.emploi_du_temps.annee_academique_id != nouveau_travail.annee_id or
            ancien.affectation.groupe_id != nouveau_travail.groupe_id or
            ancien.cle_metier == nouveau_travail.cle()):
        return DecisionLigne('A_REVOIR', 'QR_ORIGINE_NON_REPROGRAMMABLE', nouveau_travail.cle())
    decision = appliquer_ligne(nouveau_travail, proposition, revision=revision)
    if decision.statut != 'PLACEE':
        return decision
    nouvelle_aff = AffectationCreneau.objects.get(cle_occurrence_v2=nouveau_travail.cle())
    nouveau_registre = SeanceRegistre.objects.get(affectation=nouvelle_aff)
    if nouveau_registre.pk == ancien.pk:
        raise IntegrationQRBloquee('Identité QR partagée par deux séances.')
    if nouveau_registre.seance_origine_id == ancien.pk:
        return replace(decision, code='DEJA_REPROGRAMMEE_QR_A_REVOIR')
    lier_reprogrammation(ancien, nouveau_registre, motif=motif)
    return replace(decision, code='REPROGRAMMEE_QR_A_REVOIR')
