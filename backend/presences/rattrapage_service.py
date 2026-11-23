"""Logique métier des rattrapages inter-cohorte.

Un rattrapage permet à un auditeur de suivre une séance dispensée à une autre
cohorte (groupe / grade / vague / secrétariat) que la sienne, sans l'inscrire
au module d'accueil (pas de ``ModuleParticipant``) afin de ne pas fausser les
effectifs attendus de cette cohorte.

La présence est matérialisée par un ``Pointage`` forcé, réutilisant
l'infrastructure de badgeage forcé existante.
"""
from django.db import transaction

from formations.models import Module, ModuleParticipant, SessionModule

from .bulk_force_auditeurs import (
    force_entree_personne,
    force_presence_auditeur,
    force_sortie_pointage,
)
from .duree import rattrapage_creneau_timestamps
from .models import AuditLog, Pointage, Rattrapage, _log_audit


class RattrapageError(Exception):
    """Erreur métier lors de la génération d'une présence de rattrapage."""


def _label_variants(value):
    """Variantes normalisées (minuscules) pour rapprocher grade/groupe."""
    if value is None:
        return set()
    raw = str(value).strip()
    if not raw:
        return set()
    variants = {raw.lower()}
    upper = raw.upper()
    if upper.startswith('GROUPE '):
        num = upper[7:].strip()
        if num:
            variants.add(num.lower())
            variants.add(f'groupe {num.lower()}')
    elif upper.isdigit():
        variants.add(f'groupe {upper.lower()}')
    return variants


def module_matches_participant_cohorte(module, participant):
    """True si grade/groupe du module correspondent à la cohorte de l'auditeur."""
    module_grade = (getattr(module, 'grade', None) or '').strip()
    module_groupe = (getattr(module, 'groupe', None) or '').strip()
    participant_grade = (getattr(participant, 'grade', None) or '').strip()
    participant_groupe = (getattr(participant, 'groupe', None) or '').strip()

    if module_grade:
        if not participant_grade or module_grade.lower() != participant_grade.lower():
            return False
    if module_groupe:
        if not participant_groupe:
            return False
        if not (_label_variants(module_groupe) & _label_variants(participant_groupe)):
            return False
    return True


def pick_origine_module(candidates, participant):
    """Choisit un module d'origine parmi les candidats (désambiguïsation cohorte)."""
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]
    filtered = [m for m in candidates if module_matches_participant_cohorte(m, participant)]
    if len(filtered) == 1:
        return filtered[0]
    return None


def participant_deja_inscrit_module(participant, module):
    """True si l'auditeur est déjà inscrit au module (rattrapage inutile)."""
    if participant is None or module is None:
        return False
    return ModuleParticipant.objects.filter(participant=participant, module=module).exists()


def infer_module_origine(participant, seance_accueil, *, module_origine=None):
    """Déduit le module d'origine (cours manqué) depuis les inscriptions."""
    if module_origine is not None:
        return module_origine
    if participant is None or seance_accueil is None or not seance_accueil.module_id:
        return None
    accueil = seance_accueil.module
    intitule = (accueil.intitule or '').strip()
    if not intitule:
        return None
    candidates = list(
        Module.objects.filter(
            module_participants__participant=participant,
            formation_id=accueil.formation_id,
            intitule__iexact=intitule,
        ).exclude(pk=accueil.pk)
    )
    return pick_origine_module(candidates, participant)


def _session_sans_presence(participant, session):
    return not Pointage.objects.filter(
        session=session,
        participant=participant,
        duree_presence_minutes__isnull=False,
    ).exists()


def infer_seance_manquee(participant, module_origine, seance_accueil, *, seance_manquee=None):
    """Déduit la séance manquée sur le module d'origine."""
    if seance_manquee is not None:
        return seance_manquee
    if participant is None or module_origine is None or seance_accueil is None:
        return None

    base_qs = SessionModule.objects.filter(module=module_origine).order_by('date_journee', 'numero')

    if seance_accueil.numero is not None:
        same_numero = base_qs.filter(numero=seance_accueil.numero).first()
        if same_numero and _session_sans_presence(participant, same_numero):
            return same_numero

    if seance_accueil.date_journee:
        before_accueil = base_qs.filter(date_journee__lte=seance_accueil.date_journee)
    else:
        before_accueil = base_qs

    for session in before_accueil:
        if _session_sans_presence(participant, session):
            return session
    return None


def reactiver_rattrapage_annule(
    rattrapage,
    *,
    motif='',
    module_origine=None,
    seance_manquee=None,
    cree_par=None,
):
    """Réouvre un rattrapage annulé (statut PLANIFIE, pointage effacé)."""
    rattrapage.statut = Rattrapage.Statut.PLANIFIE
    if motif:
        rattrapage.motif = motif
    if module_origine is not None:
        rattrapage.module_origine = module_origine
    if seance_manquee is not None:
        rattrapage.seance_manquee = seance_manquee
    if cree_par is not None:
        rattrapage.cree_par = cree_par
    rattrapage.pointage = None
    update_fields = ['statut', 'motif', 'module_origine', 'seance_manquee', 'pointage', 'updated_at']
    if cree_par is not None:
        update_fields.append('cree_par')
    rattrapage.save(update_fields=update_fields)
    return rattrapage


def _audit_rattrapage(action, rattrapage, request=None, extra=None):
    participant = rattrapage.participant
    module = rattrapage.module_rattrapage
    _log_audit(
        action=action,
        request=request,
        cible_type='participant',
        cible_numero=getattr(participant, 'matricule', '') or str(participant.pk),
        cible_nom=f"{participant.nom} {participant.prenom}".strip(),
        formation=module.formation if module else None,
        pointage=rattrapage.pointage,
        extra={
            'rattrapage_id': rattrapage.pk,
            'seance_rattrapage_id': rattrapage.seance_rattrapage_id,
            'module_origine_id': rattrapage.module_origine_id,
            'seance_manquee_id': rattrapage.seance_manquee_id,
            'motif': rattrapage.motif,
            **(extra or {}),
        },
    )


def lier_rattrapage_au_badge(participant, seance, pointage, *, request=None):
    """Associe un badge naturel au rattrapage planifié sur cette séance."""
    rattrapage = (
        Rattrapage.objects
        .filter(
            participant=participant,
            seance_rattrapage=seance,
            statut=Rattrapage.Statut.PLANIFIE,
        )
        .first()
    )
    if rattrapage is None:
        return None

    rattrapage.pointage = pointage
    rattrapage.statut = Rattrapage.Statut.EFFECTUE
    rattrapage.save(update_fields=['pointage', 'statut', 'updated_at'])
    _audit_rattrapage(
        AuditLog.Action.RATTRAPAGE_PRESENCE,
        rattrapage,
        request=request,
        extra={'via_badge': True, 'pointage_created': True},
    )
    return rattrapage


def generer_presence_rattrapage(rattrapage, *, request=None, with_sortie=True, motif=None):
    """Force la présence de l'auditeur sur la séance de rattrapage et la lie.

    Idempotent : si un pointage existe déjà pour (séance, auditeur), il est
    réutilisé. Passe le rattrapage au statut ``EFFECTUE``.
    """
    seance = rattrapage.seance_rattrapage
    participant = rattrapage.participant
    if seance is None or participant is None:
        raise RattrapageError("Rattrapage incomplet : séance ou auditeur manquant.")

    formation = seance.module.formation
    motif_final = motif or rattrapage.motif or 'Rattrapage inter-cohorte'
    seance_date = seance.date_journee

    with transaction.atomic():
        pointage = (
            Pointage.objects.filter(session=seance, participant=participant)
            .order_by('-timestamp_entree')
            .first()
        )
        created = False
        if pointage is None:
            if with_sortie:
                pointage, err = force_presence_auditeur(
                    formation,
                    seance,
                    participant,
                    seance_date,
                    motif_final,
                    request=request,
                    ignore_constraints=True,
                )
            else:
                ts_entree, _ = rattrapage_creneau_timestamps(seance)
                pointage, err = force_entree_personne(
                    formation,
                    seance,
                    participant,
                    'participant',
                    seance_date,
                    motif_final,
                    request=request,
                    timestamp_entree=ts_entree,
                    ignore_constraints=True,
                )
            if err:
                raise RattrapageError(err)
            created = True
        elif with_sortie and not pointage.timestamp_sortie:
            _, err = force_sortie_pointage(
                formation,
                pointage,
                seance,
                participant,
                'participant',
                motif_final,
                request=request,
                creneau_complet=True,
            )
            if err:
                raise RattrapageError(err)

        rattrapage.pointage = pointage
        rattrapage.statut = Rattrapage.Statut.EFFECTUE
        rattrapage.save(update_fields=['pointage', 'statut', 'updated_at'])
        _audit_rattrapage(
            AuditLog.Action.RATTRAPAGE_PRESENCE,
            rattrapage,
            request=request,
            extra={'pointage_created': created},
        )

    return pointage


def annuler_rattrapage(rattrapage, *, request=None, supprimer_pointage=False):
    """Annule un rattrapage. Optionnellement supprime le pointage généré."""
    with transaction.atomic():
        pointage = rattrapage.pointage
        if supprimer_pointage and pointage is not None:
            rattrapage.pointage = None
            rattrapage.save(update_fields=['pointage', 'updated_at'])
            pointage.delete()
        rattrapage.statut = Rattrapage.Statut.ANNULE
        rattrapage.save(update_fields=['statut', 'updated_at'])
        _audit_rattrapage(
            AuditLog.Action.RATTRAPAGE_CANCEL,
            rattrapage,
            request=request,
            extra={'pointage_supprime': supprimer_pointage},
        )
    return rattrapage
