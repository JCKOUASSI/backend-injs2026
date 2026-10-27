"""TOTP RFC 6238 — double factor d'authentification du LOT 2 (unité U6).

Implémentation locale, sans dépendance externe ni appel réseau :
HMAC-SHA1, période de 30 s, code à 6 chiffres, fenêtre de tolérance de
±1 période (horloges des appareils). Le secret (base32, 20 octets) est
stocké chiffrable plus tard dans ``CompteUtilisateur.mfa_secret`` ; la
première version le stocke en clair en base comme les autres secrets du
SI (le compte est déjà protégé par mot de passe + moindre privilège).

La vérification est strictement bornée : un code invalide ne produit
aucun effet de bord sur le compte (pas d'incrément d'échec) ; c'est le
throttlage de l'endpoint ``/api/auth/mfa/verify/`` qui borne les
tentatives, comme pour la connexion elle-même.
"""
import base64
import hashlib
import hmac
import secrets
import struct
from datetime import datetime, timezone

PERIODE = 30
CHIFFRES = 6
DUREE_JETON_ETAPSE = 300  # 5 minutes pour compléter l'étape MFA


def generer_secret(octets=20):
    """Secret TOTP aléatoire au format base32 (RFC 4648)."""
    return base64.b32encode(secrets.token_bytes(octets)).decode('ascii')


def _cle(secret_b32):
    return base64.b32decode(secret_b32, casefold=True)


def _code_pas(secret_b32, pas):
    """Code TOTP du pas temporel ``pas`` (secondes // PERIODE)."""
    digest = hmac.new(
        _cle(secret_b32), struct.pack('>Q', pas), hashlib.sha1,
    ).digest()
    index = digest[-1] & 0x0F
    return struct.unpack('>I', digest[index:index + 4])[0] % (10 ** CHIFFRES)


def _pas_actuel(maintenant=None):
    maintenant = maintenant or datetime.now(timezone.utc)
    return int(maintenant.timestamp()) // PERIODE


def code_actuel(secret_b32, maintenant=None):
    """Code en vigueur (à visée d'affichage/test, pas de vérification)."""
    return _code_pas(secret_b32, _pas_actuel(maintenant))


def verifier_code(secret_b32, code, maintenant=None, tolerance=1):
    """Vrai si ``code`` est valide dans la fenêtre ±``tolerance`` pas."""
    if not secret_b32 or code is None:
        return False
    try:
        cible = str(int(str(code).strip()))
    except (TypeError, ValueError):
        return False
    if not cible or len(cible) > CHIFFRES:
        return False
    pas = _pas_actuel(maintenant)
    return any(
        _code_pas(secret_b32, pas + decalage) == int(cible)
        for decalage in range(-tolerance, tolerance + 1)
    )


def otpauth_url(secret_b32, utilisateur, emetteur='INJS'):
    """URI d'enrôlement lisible par Google Authenticator, FreeOTP…"""
    return (
        f'otpauth://totp/{emetteur}:{utilisateur}'
        f'?secret={secret_b32}&issuer={emetteur}'
        f'&algorithm=SHA1&digits={CHIFFRES}&period={PERIODE}'
    )
