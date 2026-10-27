import os

from django.apps import AppConfig


def create_superuser_from_env():
    import logging
    from django.contrib.auth import get_user_model

    logger = logging.getLogger(__name__)

    username = os.environ.get('DJANGO_SUPERUSER_USERNAME')
    email = os.environ.get('DJANGO_SUPERUSER_EMAIL')
    password = os.environ.get('DJANGO_SUPERUSER_PASSWORD')

    missing = [
        name for name, val in [
            ('DJANGO_SUPERUSER_USERNAME', username),
            ('DJANGO_SUPERUSER_EMAIL', email),
            ('DJANGO_SUPERUSER_PASSWORD', password),
        ]
        if not val
    ]
    if missing:
        logger.warning(
            "Création du super-utilisateur ignorée (variables manquantes: %s).",
            ", ".join(missing),
        )
        return

    User = get_user_model()
    if User.objects.filter(username=username).exists():
        logger.info("Super-utilisateur '%s' existe déjà — ignoré.", username)
        return

    User.objects.create_superuser(username=username, email=email, password=password, role=User.Role.ADMIN)
    logger.info("Super-utilisateur '%s' créé avec succès.", username)


class AuthenticationConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'authentication'
    verbose_name = 'Authentification'

    def ready(self):
        from admin_mixins import patch_admin_related_widgets

        patch_admin_related_widgets()

        from django.apps import apps
        from django.contrib.auth import get_user_model
        from django.db.models.signals import post_migrate, post_save, m2m_changed

        # Après authentication : crée les groupes (souvent avant les permissions
        # des apps métier). Il faut ré‑exécuter ensure_role_groups après formations
        # / presences / … pour compléter les codenames créés plus tard (voir
        # role_groups.ensure_role_groups branche « merge »).
        post_migrate.connect(
            _on_post_migrate_finalize,
            sender=self,
            dispatch_uid='authentication_post_migrate',
        )
        for label in ('formations', 'presences', 'exports', 'dashboard'):
            try:
                app_config = apps.get_app_config(label)
            except LookupError:
                continue
            post_migrate.connect(
                _on_post_migrate_ensure_roles,
                sender=app_config,
                dispatch_uid=f'authentication_ensure_roles_{label}',
            )
        post_save.connect(_on_user_saved, sender=get_user_model(), dispatch_uid='authentication_sync_role_group')

        User = get_user_model()
        m2m_changed.connect(
            _on_user_groups_changed,
            sender=User.groups.through,
            dispatch_uid='authentication_sync_role_from_group',
        )


def _on_post_migrate_ensure_roles(sender, **kwargs):
    from .role_groups import ensure_role_groups

    ensure_role_groups()


def _on_post_migrate_finalize(sender, **kwargs):
    from .role_groups import ensure_role_groups, sync_all_users_role_groups

    ensure_role_groups()
    sync_all_users_role_groups()
    create_superuser_from_env()


def _on_user_saved(sender, instance, **kwargs):
    from .role_groups import is_bulk_role_sync, sync_user_role_group, sync_user_staff_status
    from .profile_sync import sync_user_profile_links

    if is_bulk_role_sync():
        return

    sync_user_role_group(instance)
    sync_user_staff_status(instance)
    sync_user_profile_links(instance)


def _on_user_groups_changed(sender, instance, action, **kwargs):
    """Quand les groupes changent (admin Django), resynchronise role + is_staff."""
    if action not in ('post_add', 'post_clear', 'post_remove'):
        return
    from .role_groups import is_bulk_role_sync, sync_role_from_group, sync_user_staff_status

    if is_bulk_role_sync():
        return
    if hasattr(instance, '_role_groups_cache'):
        del instance._role_groups_cache
    from .profile_sync import sync_user_profile_links

    sync_role_from_group(instance)
    sync_user_staff_status(instance)
    sync_user_profile_links(instance)
