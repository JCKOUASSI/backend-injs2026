from formations.models import Formation, Participant, Formateur
from django.contrib.auth import get_user_model

from authentication.role_groups import ALLOWED_WEB_ROLES, get_user_role, user_in_roles

User = get_user_model()


def sidebar_counts(request):
    """Inject sidebar badge counts for authenticated staff users."""
    if not hasattr(request, 'user') or not request.user.is_authenticated:
        return {}
    if not user_in_roles(request.user, ALLOWED_WEB_ROLES):
        return {}

    role = get_user_role(request.user)
    if role == 'ENCADRANT':
        nb_formations = Formation.objects.filter(
            modules__superviseur=request.user
        ).distinct().count()
    else:
        nb_formations = Formation.objects.count()

    counts = {'sidebar_formations_count': nb_formations}

    if role in ('CHEF_INJS_ADMIN', 'INJS_ADMIN', 'CHEF_SECRETARIAT', 'SECRETARIAT', 'DIRECTION'):
        counts['sidebar_participants_count'] = Participant.objects.count()
        counts['sidebar_formateurs_count'] = Formateur.objects.count()
        counts['sidebar_users_count'] = User.objects.count()

    return counts
