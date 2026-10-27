"""Sécurité du flux de connexion — LOT 2 (unité U6 CURP).

Trois mécanismes, tous additifs et pilotés par drapeaux
(``parametres``), livrés ÉTEINTS : drapeau fermé = comportement
strictement identique à celui d'avant (no-op).

1. **Verrouillage de compte à la connexion**
   (``flag.curp_verrouillage_connexion``) : après
   ``PolitiqueSecurite.nombre_echecs_avant_verrouillage`` échecs
   consécutifs d'authentification, le compte passe VERROUILLÉ via la
   machine à états A5 (``changer_statut``, journalisé). Le délai
   (``duree_verrouillage_minutes``) peut être levé automatiquement à
   l'échéance, ou par un administrateur via la console CURP.

2. **MFA TOTP** (``flag.curp_mfa_active`` + optionnellement
   ``flag.curp_mfa_obligatoire_sensibles``) : la connexion réussie se
   termine par un jeton d'étape court (5 min) ; l'authentification
   n'est complétée qu'après un code TOTP valide
   (``POST /api/auth/mfa/verify/``).

3. **Horodatage des connexions** (sans drapeau — correction de l'écart
   E11 d'U0) : ``User.last_login`` et
   ``CompteUtilisateur.derniere_connexion`` sont alimentés à chaque
   connexion réussie (JWT web comme mobile), et le compteur d'échecs
   est remis à zéro.

Le backend reste la seule autorité : rien de ceci n'est masqué côté
interface sans être appliqué ici.
"""
from datetime import timedelta

from django.utils import timezone

from habilitations.models import (
    AttributionRole,
    CompteUtilisateur,
    JournalHabilitation,
    PolitiqueSecurite,
)
from habilitations.services import drapeaux, totp
from habilitations.services.comptes_admin import changer_statut
from habilitations.services.journalisation import journaliser

#: Durée de validité du jeton d'étape MFA (secondes).
DUREE_JETON_MFA = totp.DUREE_JETON_ETAPSE


def compte_curp(user=None, username=None):
    """Profil CURP de l'utilisateur (``None`` si compte non gouverné)."""
    if user is not None:
        try:
            return user.profil_habilitation
        except CompteUtilisateur.DoesNotExist:
            return None
    from django.contrib.auth import get_user_model
    try:
        user = get_user_model().objects.get(username=username)
    except Exception:
        return None
    try:
        return user.profil_habilitation
    except CompteUtilisateur.DoesNotExist:
        return None


def porte_role_sensible(compte):
    """Vrai si le compte porte au moins un rôle sensible actif."""
    if compte is None:
        return False
    return compte.attributions.filter(
        statut=AttributionRole.Statut.ACTIVE, role__sensible=True,
    ).exists()


# ---------------------------------------------------------------------------
# 1. Verrouillage
# ---------------------------------------------------------------------------
def verifier_verrouillage(user=None, username=None):
    """Seconde(s) restantes de verrouillage, ou ``None`` si pas verrouillé.

    Si le délai est écoulé, applique le déverrouillage automatique A5
    (journalisé, compteur remis à zéro) avant de retourner ``None``.
    """
    if not drapeaux.verrouillage_connexion_active():
        return None
    compte = compte_curp(user=user, username=username)
    if compte is None or compte.statut != CompteUtilisateur.Statut.VERROUILLE:
        return None
    politique = PolitiqueSecurite.objet()
    duree = timedelta(minutes=politique.duree_verrouillage_minutes)
    reference = compte.date_verrouillage or (timezone.now() - duree)
    if timezone.now() >= reference + duree:
        changer_statut(
            compte, None, 'deverrouiller',
            'Déverrouillage automatique : délai de verrouillage écoulé.',
        )
        return None
    return int((reference + duree - timezone.now()).total_seconds()) + 1


def enregistrer_echec(username, meta=None):
    """Compte un échec d'authentification ; verrouille au seuil atteint.

    Ne fait rien si le drapeau est fermé, si le compte n'a pas de
    profil CURP, ou si le compte n'est pas ACTIF (seul état d'où la
    machine A5 autorise le verrouillage).
    """
    if not drapeaux.verrouillage_connexion_active():
        return
    compte = compte_curp(username=username)
    if compte is None or compte.statut != CompteUtilisateur.Statut.ACTIF:
        return
    politique = PolitiqueSecurite.objet()
    compte.echecs_consecutifs += 1
    if compte.echecs_consecutifs >= politique.nombre_echecs_avant_verrouillage:
        changer_statut(
            compte, None, 'verrouiller',
            f'Verrouillage automatique : {compte.echecs_consecutifs} échecs '
            'consécutifs d’authentification.',
            meta=meta,
        )
    else:
        compte.save(update_fields=['echecs_consecutifs'])


# ---------------------------------------------------------------------------
# 2. MFA
# ---------------------------------------------------------------------------
def etat_mfa(user):
    """``'aucun'`` | ``'etape'`` | ``'obligatoire'`` — obligation MFA."""
    if not drapeaux.mfa_active():
        return 'aucun'
    compte = compte_curp(user)
    if compte is None:
        return 'aucun'
    if compte.mfa_actif and compte.mfa_secret:
        return 'etape'
    if drapeaux.mfa_obligatoire_sensibles_active() and porte_role_sensible(compte):
        return 'obligatoire'
    return 'aucun'


def jeton_etape_mfa(user, duree_secondes=DUREE_JETON_MFA):
    """Jeton court (claim ``mfa_etape``) qui complète la connexion."""
    from rest_framework_simplejwt.tokens import AccessToken
    jeton = AccessToken()
    jeton['mfa_etape'] = True
    jeton['username'] = user.get_username()
    jeton['exp'] = int(
        (timezone.now() + timedelta(seconds=duree_secondes)).timestamp()
    )
    return str(jeton)


def verifier_etape_mfa(mfa_token):
    """Décode le jeton d'étape ; retourne le nom d'utilisateur ou ``None``."""
    from rest_framework_simplejwt.exceptions import TokenError
    from rest_framework_simplejwt.tokens import AccessToken
    if not mfa_token:
        return None
    try:
        jeton = AccessToken(mfa_token)
    except TokenError:
        return None
    if not jeton.get('mfa_etape'):
        return None
    return jeton.get('username') or None


# ---------------------------------------------------------------------------
# 3. Finalisation (connexions complètes : login direct ou après MFA)
# ---------------------------------------------------------------------------
def finaliser_connexion(user, request, device_id=''):
    """Alimente les horodatages, remet le compteur d'échecs, émet les
    tokens et le cookie refresh, journalise — réponse complète."""
    from . import views as auth_views
    from .role_groups import get_user_role, user_role_context

    maintenant = timezone.now()
    user.last_login = maintenant
    user.save(update_fields=['last_login'])
    compte = compte_curp(user)
    if compte is not None:
        compte.derniere_connexion = maintenant
        compte.echecs_consecutifs = 0
        compte.save(update_fields=['derniere_connexion', 'echecs_consecutifs'])

    user_role = get_user_role(user)
    client_ip = auth_views.get_client_ip(request)
    device_id = (device_id or '')
    auth_views.logger.info(
        'login_ok user_id=%s username=%r role=%s ip=%s device_id=%r',
        user.pk, user.username, user_role, client_ip,
        device_id[:16] + '…' if len(device_id) > 16 else device_id,
    )
    # LOT 5 (L4-03) : l'horodatage de connexion est reflété au journal
    # d'habilitation pour les comptes gouvernés (type CONNEXION prévu au
    # modèle et jamais émis jusque-là). Best effort : une panne du journal ne
    # bloque jamais la connexion (le miroir presences.AuditLog reste posé en
    # aval, la double piste est assumée et documentée).
    if compte is not None:
        try:
            journaliser(
                'CONNEXION', acteur=user, compte=compte,
                nouvelle_valeur={'canal': 'MOBILE' if device_id else 'WEB'},
                motif='Connexion réussie (émission additive LOT 5).',
                adresse_ip=client_ip,
                agent_utilisateur=(
                    request.META.get('HTTP_USER_AGENT', '')[:250]),
            )
        except Exception:  # pragma: no cover - jamais bloquant
            auth_views.logger.warning(
                'journal CONNEXION indisponible user_id=%s', user.pk,
                exc_info=True)

    from presences.models import AuditLog
    from rest_framework_simplejwt.tokens import RefreshToken

    refresh = RefreshToken.for_user(user)
    refresh['role'] = user_role
    refresh['full_name'] = user.get_full_name()
    refresh['must_change_password'] = bool(
        getattr(user, 'must_change_password', False)
    )
    auth_views._log_audit(
        action=AuditLog.Action.USER_LOGIN,
        request=request,
        cible_type='user',
        cible_numero=user.username,
        cible_nom=user.get_full_name() or user.username,
        extra={'role': user_role, 'device_id': bool(device_id)},
    )
    response = auth_views.Response({
        'access': str(refresh.access_token),
        # Conservé pour l'app mobile (stockage sécurisé applicatif) ;
        # le web utilise le cookie HttpOnly.
        'refresh': str(refresh),
        'refresh_in_cookie': True,
        'must_change_password': bool(
            getattr(user, 'must_change_password', False)
        ),
        'user': auth_views._user_payload(user),
        'role_context': user_role_context(user),
    })
    auth_views._set_refresh_cookie(response, str(refresh))
    return response


def journaliser_etape_mfa(compte):
    """Trace de la demande d'étape MFA à la connexion (évènement sensible)."""
    if compte is None:
        return
    journaliser(
        JournalHabilitation.TypeEvenement.MFA_ETAPSE_DEMANDEE,
        compte=compte,
        motif='Étape MFA (TOTP) demandée à la connexion.',
    )


class ErreurMfa(Exception):
    """Erreur de gestion du MFA (portée par les vues vers un code HTTP)."""

    def __init__(self, message, statut=400):
        self.message = message
        self.statut = statut
        super().__init__(message)


def armer_mfa(compte):
    """Arme un secret TOTP sans l'activer. Retourne ``(secret, otpauth_url)``.

    L'activation ne se fait qu'après confirmation d'un code valide
    (``confirmer_mfa``) : un secret sans preuve de possession n'autorise
    rien.
    """
    secret = totp.generer_secret()
    compte.mfa_secret = secret
    compte.save(update_fields=['mfa_secret'])
    return secret, totp.otpauth_url(secret, compte.user.get_username())


def confirmer_mfa(compte, code, acteur):
    """Active le MFA du compte après vérification d'un code valide."""
    if not compte.mfa_secret:
        raise ErreurMfa('Aucun secret armé : lancez d’abord l’armement (setup).')
    if not totp.verifier_code(compte.mfa_secret, code):
        raise ErreurMfa('Code MFA invalide.')
    compte.mfa_actif = True
    compte.save(update_fields=['mfa_actif'])
    journaliser(
        JournalHabilitation.TypeEvenement.MFA_ACTIVE,
        acteur=acteur, compte=compte, motif='MFA (TOTP) activé.',
    )


def desactiver_mfa(compte, acteur, code=''):
    """Désactive le MFA ; le code est exigé pour une désactivation par soi-même.

    Refus (409) si le drapeau « MFA obligatoire pour rôles sensibles » est
    ouvert et que le compte porte un rôle sensible actif : on ne peut pas
    retirer la protection d'un rôle qui en dépend.
    """
    est_soi = acteur is not None and acteur.id == compte.user_id
    if est_soi and not (
        compte.mfa_secret and totp.verifier_code(compte.mfa_secret, code)
    ):
        raise ErreurMfa(
            'Code MFA requis pour désactiver votre propre MFA.')
    if drapeaux.mfa_obligatoire_sensibles_active() and porte_role_sensible(compte):
        raise ErreurMfa(
            'MFA obligatoire : ce compte porte un rôle sensible actif.',
            statut=409,
        )
    compte.mfa_actif = False
    compte.mfa_secret = ''
    compte.save(update_fields=['mfa_actif', 'mfa_secret'])
    journaliser(
        JournalHabilitation.TypeEvenement.MFA_DESACTIVE,
        acteur=acteur, compte=compte, motif='MFA (TOTP) désactivé.',
    )


def journaliser_refus_verrouille(compte, secondes_restantes):
    """Trace d'une connexion refusée sur compte verrouillé (évènement sensible)."""
    journaliser(
        JournalHabilitation.TypeEvenement.CONNEXION_REFUSEE_VERROUILLEE,
        compte=compte,
        nouvelle_valeur={'secondes_restantes': secondes_restantes},
        motif='Connexion refusée : compte verrouillé (délai non écoulé).',
    )
