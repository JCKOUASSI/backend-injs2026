"""Visibilité des données sensibles formateur (pièce d'identité, compte bancaire)."""


def _is_own_formateur_profile(user, formateur):
    if not user or not user.is_authenticated or not formateur:
        return False
    profile = getattr(user, 'formateur_profile', None)
    if profile is not None and profile.pk == formateur.pk:
        return True
    if getattr(user, 'role', None) == 'FORMATEUR':
        badge = (getattr(user, 'matricule', None) or '').strip().lower()
        if badge and badge == (formateur.numerobadge or '').strip().lower():
            return True
    return False


def can_view_formateur_sensitive_data(user, formateur=None):
    """Finance, Archiviste (lecture) ou le formateur concerné."""
    if not user or not user.is_authenticated:
        return False
    if getattr(user, 'role', None) in ('FINANCE', 'ARCHIVE'):
        return True
    if formateur is not None:
        return _is_own_formateur_profile(user, formateur)
    return getattr(user, 'role', None) == 'FORMATEUR'


def can_edit_formateur_sensitive_data(user, formateur):
    """Finance (tous) ou le formateur sur son propre profil."""
    if not can_view_formateur_sensitive_data(user, formateur):
        return False
    if getattr(user, 'role', None) == 'FINANCE':
        return True
    return _is_own_formateur_profile(user, formateur)


def strip_formateur_sensitive_fields(data):
    if not isinstance(data, dict):
        return data
    data = dict(data)
    data.pop('numero_piece_identite', None)
    data.pop('numero_compte_bancaire', None)
    return data


def formateur_sensitive_payload(formateur):
    return {
        'numero_piece_identite': formateur.numero_piece_identite or '',
        'numero_compte_bancaire': formateur.numero_compte_bancaire or '',
    }
