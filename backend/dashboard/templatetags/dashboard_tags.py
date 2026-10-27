from django import template

from authentication.role_groups import get_user_role

register = template.Library()

ROLE_DFRC = ['CHEF_INJS_ADMIN', 'INJS_ADMIN']
ROLE_SECRETARIAT = ['CHEF_SECRETARIAT', 'SECRETARIAT']
ROLE_ENCADRANT = ['ENCADRANT']
ROLE_ADMIN_MUTATION = ROLE_DFRC + ROLE_SECRETARIAT


def _role_in(user, roles):
    role = get_user_role(user)
    return role in roles if role else False


@register.filter
def can_create_formation(user):
    """Vérifie si l'utilisateur peut créer une formation."""
    return _role_in(user, ROLE_ADMIN_MUTATION)


@register.filter
def can_edit_formation(user):
    """Vérifie si l'utilisateur peut modifier/supprimer une formation."""
    return _role_in(user, ROLE_ADMIN_MUTATION)


@register.filter
def can_manage_sessions(user):
    """Vérifie si l'utilisateur peut gérer les sessions (démarrer, terminer, supprimer)."""
    return _role_in(user, ROLE_ADMIN_MUTATION + ROLE_ENCADRANT)


@register.filter
def can_generate_qr(user):
    """Vérifie si l'utilisateur peut générer des QR codes."""
    return _role_in(user, ROLE_ADMIN_MUTATION)


@register.filter
def can_force_pointage(user):
    """Vérifie si l'utilisateur peut forcer un pointage."""
    return _role_in(user, ROLE_ADMIN_MUTATION + ROLE_ENCADRANT)


@register.filter
def can_assign_superviseur(user):
    """Vérifie si l'utilisateur peut assigner un superviseur."""
    return _role_in(user, ROLE_ADMIN_MUTATION)


@register.filter
def can_assign_formateur(user):
    """Vérifie si l'utilisateur peut assigner un formateur."""
    return _role_in(user, ROLE_ADMIN_MUTATION)


@register.filter
def can_remove_formateur(user):
    """Vérifie si l'utilisateur peut retirer un formateur d'une formation."""
    return _role_in(user, ROLE_ADMIN_MUTATION)


@register.filter
def can_inscrire_participant(user):
    """Vérifie si l'utilisateur peut inscrire un participant."""
    return _role_in(user, ROLE_ADMIN_MUTATION)


@register.filter
def can_remove_participant(user):
    """Vérifie si l'utilisateur peut retirer un participant d'une formation."""
    return _role_in(user, ROLE_ADMIN_MUTATION)


@register.filter
def can_manage_formation_statut(user):
    """Vérifie si l'utilisateur peut changer le statut d'une formation."""
    return _role_in(user, ROLE_ADMIN_MUTATION)


@register.filter
def can_manage_participants(user):
    """Vérifie si l'utilisateur peut gérer les participants (CRUD)."""
    return _role_in(user, ROLE_ADMIN_MUTATION + ['DIRECTION'])


@register.filter
def can_manage_formateurs(user):
    """Vérifie si l'utilisateur peut gérer les formateurs (CRUD)."""
    return _role_in(user, ROLE_ADMIN_MUTATION + ['DIRECTION'])


@register.filter
def can_manage_users(user):
    """Vérifie si l'utilisateur peut gérer les utilisateurs (CRUD)."""
    return _role_in(user, ROLE_ADMIN_MUTATION)


@register.filter
def can_import_excel(user):
    """Vérifie si l'utilisateur peut importer des données Excel."""
    return _role_in(user, ROLE_ADMIN_MUTATION)


@register.filter
def can_view_nav_participants(user):
    """Vérifie si l'utilisateur peut voir la navigation Participants."""
    return _role_in(user, ROLE_ADMIN_MUTATION + ['DIRECTION'])


@register.filter
def can_view_nav_formateurs(user):
    """Vérifie si l'utilisateur peut voir la navigation Formateurs."""
    return _role_in(user, ROLE_ADMIN_MUTATION + ['DIRECTION'])


@register.filter
def can_view_nav_users(user):
    """Vérifie si l'utilisateur peut voir la navigation Utilisateurs."""
    return _role_in(user, ROLE_ADMIN_MUTATION + ['DIRECTION'])


@register.filter
def can_view_nav_import(user):
    """Vérifie si l'utilisateur peut voir la navigation Import Excel."""
    return _role_in(user, ROLE_ADMIN_MUTATION)


@register.filter
def get_item(dictionary, key):
    """Access a dictionary item by key in templates."""
    if dictionary is None:
        return None
    return dictionary.get(key)


@register.simple_tag(takes_context=True)
def nav_item_is_current(context, item):
    """Vrai seulement si l'URL courante correspond exactement au lien (pas le groupe d'onglets)."""
    request = context.get('request')
    if not request or not item:
        return False
    from urllib.parse import urlparse

    link = item.get('link_callback') or item.get('link')
    if not link:
        return False
    return urlparse(str(link)).path == request.path
