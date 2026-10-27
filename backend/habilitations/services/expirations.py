"""Expiration automatique et détection d'inactivité (C3 points 2 et 3).

* :func:`expirer_termes` applique la date de fin CONVENUE à la création des
  attributions temporaires, dérogations octroyées et délégations : c'est
  l'exécution d'un terme déjà approuvé, pas une décision nouvelle, donc
  automatique (sous le drapeau ``flag.curp_expiration_auto``). Une
  notification est émise à J-7, une seule fois.
* :func:`detecter_inactivite` NOTIFIE un préavis puis dépose une PROPOSITION
  de suspension en file : jamais de suspension directe et silencieuse
  (sous le drapeau ``flag.curp_suspension_inactivite``). Les comptes
  ``exempt_inactivite`` sont ignorés (congé longue durée).
"""
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from ..models import (
    AttributionRole,
    CompteUtilisateur,
    DelegationHabilitation,
    NotificationHabilitation,
    PermissionAttribuee,
    PolitiqueSecurite,
    PropositionProvisionnement,
)
from .comptes_admin import ErreurConsole, changer_statut
from .journalisation import journaliser
from .notifications import notifier, notifier_admins, responsable_du_compte
from .provisionnement.sondes import Fait
from .provisionnement.file import mettre_en_file

#: Durée de validité d'une invitation restée sans première connexion. Le
#: recueil ne chiffre pas cette durée ; la valeur par défaut est généreuse et
#: centralisée ici (aucune règle nouvelle n'est inventée côté écran).
DUREE_INVITATION_JOURS = 30


def _notifier_echeance(compte, categorie, titre, message, objet, meta=None):
    """Préavis d'échéance adressé à l'intéressé (et à son responsable)."""
    destinataires = {compte.user}
    responsable = responsable_du_compte(compte)
    if responsable is not None:
        destinataires.add(responsable)
    for destinataire in destinataires:
        notifier(destinataire, categorie, titre, message, compte=compte,
                 meta=meta or {'objet': str(objet)[:200]})


def _dans_quelques_jours(date_fin, jours, aujourd_hui):
    return date_fin == aujourd_hui + timedelta(days=jours)


@transaction.atomic
def _expirer_attribution(attribution, politique, aujourd_hui):
    notification_j = politique.echeance_notification_jours
    if (attribution.date_fin
            and attribution.notification_echeance_le is None
            and aujourd_hui < attribution.date_fin
            and (attribution.date_fin - aujourd_hui).days <= notification_j):
        _notifier_echeance(
            attribution.compte,
            NotificationHabilitation.Categorie.ECHEANCE_ATTRIBUTION,
            f"Votre rôle {attribution.role.libelle} expire le {attribution.date_fin.isoformat()}",
            f"Le rôle {attribution.role.code} prend fin à cette date ; il sera "
            "retirable automatiquement sans nouvelle décision.",
            attribution, {'role': attribution.role.code, 'date_fin': attribution.date_fin.isoformat()},
        )
        attribution.notification_echeance_le = aujourd_hui
        attribution.save(update_fields=['notification_echeance_le'])
    if attribution.date_fin and attribution.date_fin < aujourd_hui:
        attribution.statut = AttributionRole.Statut.EXPIREE
        attribution.motif_revocation = (
            f"Expiration automatique au {attribution.date_fin.isoformat()}."
        )
        attribution.save(update_fields=['statut', 'motif_revocation', 'date_modification'])
        journaliser(
            'EXPIRATION_AUTO', compte=attribution.compte, cible=attribution,
            nouvelle_valeur={'role': attribution.role.code,
                             'date_fin': attribution.date_fin.isoformat()},
            motif=attribution.motif_revocation,
        )
        return True
    return False


@transaction.atomic
def _expirer_derogation(derogation, politique, aujourd_hui):
    if not derogation.date_fin:
        return False
    if (derogation.notification_echeance_le is None
            and aujourd_hui < derogation.date_fin
            and (derogation.date_fin - aujourd_hui).days <= politique.echeance_notification_jours):
        _notifier_echeance(
            derogation.compte,
            NotificationHabilitation.Categorie.ECHEANCE_DEROGATION,
            f"Une dérogation expire le {derogation.date_fin.isoformat()}",
            f"La permission {derogation.permission.code} retrouvera son régime "
            "normal à cette date.",
            derogation, {'permission': derogation.permission.code},
        )
        derogation.notification_echeance_le = aujourd_hui
        derogation.save(update_fields=['notification_echeance_le'])
    if derogation.date_fin < aujourd_hui:
        derogation.statut = PermissionAttribuee.Statut.EXPIREE
        derogation.save(update_fields=['statut'])
        journaliser(
            'EXPIRATION_AUTO', compte=derogation.compte, cible=derogation,
            nouvelle_valeur={'permission': derogation.permission.code,
                             'sens': derogation.sens,
                             'date_fin': derogation.date_fin.isoformat()},
            motif=f"Expiration automatique de la dérogation au {derogation.date_fin.isoformat()}.",
        )
        return True
    return False


@transaction.atomic
def _terminer_delegation(delegation, politique, aujourd_hui):
    if (delegation.notification_echeance_le is None
            and aujourd_hui < delegation.date_fin
            and (delegation.date_fin - aujourd_hui).days <= politique.echeance_notification_jours):
        _notifier_echeance(
            delegation.delegataire,
            NotificationHabilitation.Categorie.ECHEANCE_DELEGATION,
            f"Une délégation expire le {delegation.date_fin.isoformat()}",
            f"Les droits reçus de {delegation.delegant.user.get_username()} "
            "seront retirés à cette date.",
            delegation,
            {'delegant': delegation.delegant.user.get_username(),
             'date_fin': delegation.date_fin.isoformat()},
        )
        delegation.notification_echeance_le = aujourd_hui
        delegation.save(update_fields=['notification_echeance_le'])
    if delegation.date_fin < aujourd_hui and delegation.statut == DelegationHabilitation.Statut.ACTIVE:
        delegation.statut = DelegationHabilitation.Statut.TERMINEE
        delegation.raison_arret = f"Extinction automatique au {delegation.date_fin.isoformat()}."
        delegation.save(update_fields=['statut', 'raison_arret', 'date_modification'])
        journaliser(
            'DELEGATION_REVOQUEE', compte=delegation.delegataire, cible=delegation,
            nouvelle_valeur={'date_fin': delegation.date_fin.isoformat()},
            motif=delegation.raison_arret,
        )
        return True
    return False


def _preavis_deja_emise(compte, categorie, aujourd_hui):
    return NotificationHabilitation.objects.filter(
        compte=compte, categorie=categorie,
        date_creation__date=aujourd_hui,
    ).exists()


def _expirer_comptes(politique, aujourd_hui):
    """Invitations jamais acceptées et comptes ACTIFS arrivés à date (A5)."""
    bilan_local = {'comptes': 0, 'invitations': 0}

    # 1) Invitations expirées : INVITÉ sans première connexion au-delà de la
    # durée d'invitation. L'intéressé n'a pas accès : on alerte les admins.
    date_limite_invitation = aujourd_hui - timedelta(days=DUREE_INVITATION_JOURS)
    for compte in CompteUtilisateur.objects.filter(
        statut=CompteUtilisateur.Statut.INVITE,
    ).select_related('user'):
        date_creation = timezone.localdate(compte.date_creation)
        if date_creation > date_limite_invitation:
            continue
        try:
            changer_statut(
                compte, None, 'expirer',
                f"Invitation expirée : aucune première connexion dans les "
                f"{DUREE_INVITATION_JOURS} jours.", {},
            )
        except ErreurConsole:
            continue
        notifier_admins(
            NotificationHabilitation.Categorie.EXPIRATION_INVITATION,
            f"Invitation expirée : {compte.user.get_username()}",
            "L'invitation est arrivée à expiration sans être acceptée ; "
            "une nouvelle invitation peut être émise après vérification.",
            {'compte': compte.pk},
        )
        bilan_local['invitations'] += 1

    # 2) Comptes actifs dont la date d'expiration est atteinte (préavis J-7).
    for compte in CompteUtilisateur.objects.filter(
        statut=CompteUtilisateur.Statut.ACTIF,
        date_expiration__isnull=False,
    ).select_related('user'):
        date_exp = timezone.localdate(compte.date_expiration)
        if date_exp == aujourd_hui + timedelta(
            days=politique.echeance_notification_jours,
        ) and not _preavis_deja_emise(
            compte, NotificationHabilitation.Categorie.ECHEANCE_COMPTE, aujourd_hui,
        ):
            notifier(
                compte.user, NotificationHabilitation.Categorie.ECHEANCE_COMPTE,
                f"Votre compte expire le {date_exp.isoformat()}",
                "À cette date, l'accès sera retiré automatiquement. Une "
                "décision de prolongation doit passer par l'administration.",
                compte=compte, meta={'date_expiration': date_exp.isoformat()},
            )
        if date_exp < aujourd_hui:
            try:
                changer_statut(
                    compte, None, 'expirer',
                    f"Expiration automatique au {date_exp.isoformat()} (date d'échéance du compte).", {},
                )
            except ErreurConsole:
                # Garde S7 notamment : pas d'expiration qui fasse passer les
                # administrateurs sous le seuil sans décision humaine.
                notifier_admins(
                    NotificationHabilitation.Categorie.ALERTE_PLAFOND,
                    f"Expiration bloquée pour {compte.user.get_username()}",
                    "L'expiration automatique a été refusée par une garde de "
                    "sécurité (seuil d'administrateurs) ; une décision humaine est requise.",
                    {'compte': compte.pk},
                )
                continue
            bilan_local['comptes'] += 1
    return bilan_local


def expirer_termes(aujourd_hui=None):
    """Applique toutes les fins de terme et les préavis J-7. Bilan retourné."""
    politique = PolitiqueSecurite.objet()
    aujourd_hui = aujourd_hui or timezone.localdate()
    bilan = {'attributions': 0, 'derogations': 0, 'delegations': 0,
             'comptes': 0, 'invitations': 0, 'preavis': 0}

    for attribution in AttributionRole.objects.filter(
        statut=AttributionRole.Statut.ACTIVE,
    ).select_related('compte__user', 'role'):
        avant = attribution.notification_echeance_le is None and attribution.date_fin
        if _expirer_attribution(attribution, politique, aujourd_hui):
            bilan['attributions'] += 1
        elif avant and attribution.notification_echeance_le is not None:
            bilan['preavis'] += 1

    for derogation in PermissionAttribuee.objects.filter(
        statut=PermissionAttribuee.Statut.ACTIVE,
    ).select_related('compte__user', 'permission'):
        avant = derogation.notification_echeance_le is None and derogation.date_fin
        if _expirer_derogation(derogation, politique, aujourd_hui):
            bilan['derogations'] += 1
        elif avant and derogation.notification_echeance_le is not None:
            bilan['preavis'] += 1

    for delegation in DelegationHabilitation.objects.filter(
        statut__in=[DelegationHabilitation.Statut.ACTIVE,
                    DelegationHabilitation.Statut.PROPOSEE],
    ).select_related('delegant__user', 'delegataire__user'):
        avant = delegation.notification_echeance_le is None
        if _terminer_delegation(delegation, politique, aujourd_hui):
            bilan['delegations'] += 1
        elif avant and delegation.notification_echeance_le is not None:
            bilan['preavis'] += 1

    bilan.update(_expirer_comptes(politique, aujourd_hui))
    return bilan


def _derniere_activite(compte):
    # La date de création n'est pas une activité de l'usager : on s'appuie
    # sur les connexions, puis sur la date d'activation (première entrée).
    candidats = [
        compte.derniere_connexion, compte.derniere_activite,
        compte.user.last_login, compte.date_activation,
    ]
    dates = [d for d in candidats if d is not None]
    if not dates:
        return None
    # Les dates DateField sont converties pour comparaison avec localdate.
    return max(d.date() if hasattr(d, 'date') else d for d in dates)


def detecter_inactivite(aujourd_hui=None, acteur=None):
    """Préavis puis proposition de suspension pour les comptes inactifs."""
    politique = PolitiqueSecurite.objet()
    aujourd_hui = aujourd_hui or timezone.localdate()
    seuil = politique.inactivite_suspension_jours
    preavis = politique.preavis_suspension_jours
    bilan = {'preavis': 0, 'propositions': 0}

    for compte in (
        CompteUtilisateur.objects
        .filter(statut=CompteUtilisateur.Statut.ACTIF, exempt_inactivite=False)
        .select_related('user')
    ):
        derniere = _derniere_activite(compte)
        if derniere is None:
            continue
        jours_inactif = (aujourd_hui - derniere).days
        date_limite = derniere + timedelta(days=seuil)

        # 1) Fenêtre de préavis : on notifie l'agent et le responsable.
        if seuil - preavis <= jours_inactif < seuil:
            if compte.date_preavis_inactivite is None or \
                    compte.date_preavis_inactivite < (derniere + timedelta(days=seuil - preavis)):
                titre = (f"Votre compte sera suspendu le {date_limite.isoformat()} "
                         "sans nouvelle connexion")
                message = (f"Aucune activité depuis {jours_inactif} jours. Au-delà de "
                           f"{seuil} jours, une proposition de suspension sera déposée.")
                notifier(compte.user, NotificationHabilitation.Categorie.PREAVIS_SUSPENSION,
                         titre, message, compte=compte,
                         meta={'jours_inactif': jours_inactif, 'seuil': seuil})
                responsable = responsable_du_compte(compte)
                if responsable is not None:
                    notifier(responsable,
                             NotificationHabilitation.Categorie.PREAVIS_SUSPENSION,
                             f"Préavis d'inactivité : {compte.user.get_username()}",
                             message, compte=compte)
                compte.date_preavis_inactivite = aujourd_hui
                compte.save(update_fields=['date_preavis_inactivite'])
                bilan['preavis'] += 1
            continue

        # 2) Seuil franchi : mise en file humaine (pas de suspension directe).
        if jours_inactif >= seuil:
            periode = derniere.strftime('%Y-%m')
            fait = Fait(
                declencheur=PropositionProvisionnement.Declencheur.INACTIVITE,
                action=PropositionProvisionnement.Action.SUSPENDRE_COMPTE,
                source_app='habilitations', source_modele='CompteUtilisateur',
                source_objet_id=compte.pk,
                source_libelle=f"Inactivité de {compte.user.get_username()} ({jours_inactif} j)",
                proposition={
                    'motif': f"Compte inactif depuis {jours_inactif} jours (seuil : {seuil}).",
                    'transition': 'suspendre',
                },
                username_cible=compte.user.get_username(),
                version=periode,
            )
            if mettre_en_file(fait, acteur=acteur) is not None:
                bilan['propositions'] += 1
    return bilan
