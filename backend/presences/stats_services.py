"""Lot L1 — statistiques de présence et alertes d'absence.

Taux calculés par étudiant, groupe, module et formation, à partir du statut
d'assiduité effectif (mapping du processus de badgeage). Le seuil d'alerte
réutilise ``statistiques.ConfigAlerteSeuil`` (indicateur ``taux_absence``)
sans le dupliquer. Les alertes produisent des notifications in-app
(``NotificationAbsence``).
"""
from scolarite.models import DossierEtudiant

from .models import NotificationAbsence, Pointage


def _pointages(annee=None, session=None, module=None):
    queryset = Pointage.objects.filter(participant__isnull=False).select_related(
        'participant', 'session__module__formation', 'session',
    )
    if session is not None:
        queryset = queryset.filter(session=session)
    if module is not None:
        queryset = queryset.filter(session__module=module)
    if annee is not None:
        queryset = queryset.filter(annee_academique=annee)
    return queryset


def taux_from_counts(presents, total):
    return round(presents * 100 / total, 2) if total else None


def _assiduite_presente(pointage):
    return pointage.statut_assiduite_effectif() in (
        Pointage.StatutAssiduite.PRESENT, Pointage.StatutAssiduite.RETARD,
    )


def taux_par_etudiant(annee=None, session=None, module=None):
    """Taux de présence par étudiant (assiduité effective)."""
    pointages = _pointages(annee=annee, session=session, module=module)
    par_participant = {}
    for pointage in pointages:
        entree = par_participant.setdefault(pointage.participant_id, {
            'participant_id': pointage.participant_id,
            'matricule': pointage.participant.matricule,
            'total': 0, 'presents': 0, 'absents': 0,
        })
        entree['total'] += 1
        assiduite = pointage.statut_assiduite_effectif()
        if assiduite == Pointage.StatutAssiduite.PRESENT or assiduite == Pointage.StatutAssiduite.RETARD:
            entree['presents'] += 1
        elif assiduite == Pointage.StatutAssiduite.ABSENT:
            entree['absents'] += 1
    resultats = []
    for entree in par_participant.values():
        entree['taux_presence'] = taux_from_counts(entree['presents'], entree['total'])
        resultats.append(entree)
    return sorted(resultats, key=lambda e: (e['taux_presence'] is None, e['taux_presence'] or 0))


def _taux_agrege(cle_nom, getter, annee=None):
    """Agrégation générique par groupe/module/formation."""
    pointages = _pointages(annee=annee)
    par_cle = {}
    for pointage in pointages:
        cible = getter(pointage)
        if cible is None:
            continue
        entree = par_cle.setdefault(cible.id, {
            cle_nom: getattr(cible, 'nom', None) or getattr(cible, 'intitule', None)
            or getattr(cible, 'formation', ''),
            'total': 0, 'presents': 0,
        })
        entree['total'] += 1
        if _assiduite_presente(pointage):
            entree['presents'] += 1
    for entree in par_cle.values():
        entree['taux_presence'] = taux_from_counts(entree['presents'], entree['total'])
    return list(par_cle.values())


def taux_par_groupe(annee=None):
    """Taux de présence agrégé par groupe LMD."""
    return _taux_agrege('groupe', lambda p: p.groupe_lmd, annee)


def taux_par_module(annee=None):
    """Taux de présence agrégé par module (socle)."""
    return _taux_agrege('module', lambda p: p.session.module if p.session_id else None, annee)


def taux_par_formation(annee=None):
    """Taux de présence agrégé par formation."""
    return _taux_agrege('formation', lambda p: p.session.module.formation if p.session_id else None, annee)


def _seuil_absence():
    """Lit ConfigAlerteSeuil (indicateur taux_absence) — pattern réutilisé."""
    from statistiques.models import ConfigAlerteSeuil
    config = ConfigAlerteSeuil.objects.filter(
        indicateur=ConfigAlerteSeuil.Indicateur.TAUX_ABSENCE, actif=True,
    ).first()
    if config is None:
        return None, None
    return config.seuil_avertissement, config.seuil_critique


def alertes_absence(annee=None):
    """Alertes d'absence par étudiant selon les seuils ConfigAlerteSeuil.

    Retourne la liste des alertes : {etudiant, taux_presence, taux_absence,
    niveau (AVERTISSEMENT/CRITIQUE)} pour les étudiants sous les seuils.
    """
    avertissement, critique = _seuil_absence()
    if avertissement is None and critique is None:
        return []
    alertes = []
    for entree in taux_par_etudiant(annee):
        if entree['taux_presence'] is None:
            continue
        taux_absence = round(100 - entree['taux_presence'], 2)
        niveau = None
        if critique is not None and taux_absence >= critique:
            niveau = 'CRITIQUE'
        elif avertissement is not None and taux_absence >= avertissement:
            niveau = 'AVERTISSEMENT'
        if niveau:
            alertes.append({
                'participant_id': entree['participant_id'],
                'matricule': entree['matricule'],
                'taux_presence': entree['taux_presence'],
                'taux_absence': taux_absence,
                'niveau': niveau,
            })
    return alertes


def notifier_absences_seance(affectation, date, participant_ids, utilisateur=None):
    """Lot C+ — après clôture d'une séance LMD, alerter Direction/Secrétariat
    pour les étudiants dont le cumul d'absences franchit un seuil
    ConfigAlerteSeuil. Idempotent : la contrainte d'unicité
    (destinataire, étudiant, séance, niveau) interdit le doublon."""
    if not participant_ids:
        return 0
    avertissement, critique = _seuil_absence()
    if avertissement is None and critique is None:
        return 0
    from authentication.models import User
    from scolarite.models import DossierEtudiant

    destinataires = list(User.objects.filter(
        role__in=('DIRECTION', 'SECRETARIAT', 'CHEF_SECRETARIAT')))
    if not destinataires:
        return 0
    annee = affectation.emploi_du_temps.annee_academique
    # Taux calculés uniquement pour les absents du jour (pas d'agrégation
    # globale : la clôture d'une séance ne doit pas scanner toute l'année).
    par_participant = {pid: {'total': 0, 'presents': 0} for pid in set(participant_ids)}
    for pointage in _pointages(annee=annee).filter(participant_id__in=par_participant):
        entree = par_participant[pointage.participant_id]
        entree['total'] += 1
        if _assiduite_presente(pointage):
            entree['presents'] += 1
    intitule = getattr(affectation, 'intitule', '') or str(affectation)
    creees = 0
    for pid, entree in par_participant.items():
        taux_presence = taux_from_counts(entree['presents'], entree['total'])
        if taux_presence is None:
            continue
        taux_absence = round(100 - taux_presence, 2)
        niveau = None
        if critique is not None and taux_absence >= critique:
            niveau = 'CRITIQUE'
        elif avertissement is not None and taux_absence >= avertissement:
            niveau = 'AVERTISSEMENT'
        if niveau is None:
            continue
        participant = next(
            (pt.participant for pt in
             Pointage.objects.filter(participant_id=pid).select_related('participant')[:1]), None)
        matricule = getattr(participant, 'matricule', f'#{pid}')
        dossier = DossierEtudiant.objects.filter(participant_id=pid).first()
        message = (
            f"Absences {niveau.lower()} : {matricule} — taux de présence "
            f"{taux_presence} % (séance LMD « {intitule} » du {date})"
        )
        for destinataire in destinataires:
            _, creee = NotificationAbsence.objects.get_or_create(
                destinataire=destinataire, etudiant=dossier, seance_edt=affectation,
                niveau=niveau,
                defaults={'auteur': utilisateur, 'message': message},
            )
            creees += int(creee)
    return creees


def notifier_absences(annee, utilisateur=None):
    """Génère les notifications in-app d'absence (Direction / Secrétariat)."""
    from authentication.models import User
    from scolarite.models import JournalScolarite, journaliser

    notification_creees = 0
    destinataires = User.objects.filter(role__in=('DIRECTION', 'SECRETARIAT', 'CHEF_SECRETARIAT'))
    alertes = alertes_absence(annee)
    for alerte in alertes:
        dossier = DossierEtudiant.objects.filter(
            participant_id=alerte['participant_id'],
        ).first()
        for destinataire in destinataires:
            NotificationAbsence.objects.create(
                destinataire=destinataire,
                auteur=utilisateur,
                etudiant=dossier,
                message=(
                    f"Absences {alerte['niveau'].lower()} : {alerte['matricule']} — "
                    f"taux de présence {alerte['taux_presence']} %"
                ),
                niveau=alerte['niveau'],
            )
            notification_creees += 1
    journaliser(
        JournalScolarite.Action.EVENEMENT_SCOLARITE,
        objet=annee,
        acteur=utilisateur,
        nouvelle_valeur=str(notification_creees),
        commentaire='Notifications d’absence générées',
    )
    return notification_creees
