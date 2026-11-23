from django.contrib import admin
from django.contrib.auth.admin import GroupAdmin as BaseGroupAdmin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import Group
from django.utils.html import format_html

from admin_mixins import AuditLogAdminMixin, UserAdminScopeMixin
from presences.models import AuditLog

from .admin_badge_accounts import AdminBadgeAccountsMixin
from .admin_forms import AdminPasswordChangeForm, UserChangeForm, UserCreationForm
from .models import User
from .role_groups import GROUP_NAME_TO_ROLE, ROLE_GROUP_NAMES, ROLE_LABELS, get_user_role, get_user_roles

try:
    admin.site.unregister(Group)
except admin.sites.NotRegistered:
    pass


@admin.register(Group)
class RoleGroupAdmin(BaseGroupAdmin, admin.ModelAdmin):
    """Groupes Django ROLE_* — permissions et rôles de l'application."""

    list_display = ['name', 'role_label', 'permissions_count']
    search_fields = ['name']
    filter_horizontal = ['permissions']
    fieldsets = (
        (None, {
            'fields': ('name',),
            'description': (
                'Chaque groupe ROLE_* correspond à un rôle métier. '
                'Modifiez les permissions ci-dessous pour définir ce que ce rôle peut faire.'
            ),
        }),
        ('Permissions du rôle', {'fields': ('permissions',)}),
    )

    @admin.display(description='Rôle métier')
    def role_label(self, obj):
        role = GROUP_NAME_TO_ROLE.get(obj.name)
        if role:
            return ROLE_LABELS.get(role, role)
        return '—'

    @admin.display(description='Permissions')
    def permissions_count(self, obj):
        return obj.permissions.count()


@admin.register(User)
class UserAdmin(
    AdminBadgeAccountsMixin,
    UserAdminScopeMixin,
    AuditLogAdminMixin,
    BaseUserAdmin,
    admin.ModelAdmin,
):
    form = UserChangeForm
    add_form = UserCreationForm
    change_password_form = AdminPasswordChangeForm
    audit_action_create = AuditLog.Action.USER_CREATE
    audit_action_update = AuditLog.Action.USER_UPDATE
    audit_action_delete = AuditLog.Action.USER_DELETE

    list_display = [
        'username', 'matricule', 'last_name', 'first_name',
        'email', 'role_badge', 'grade', 'secretariat',
        'is_active', 'must_change_password',
    ]

    def get_queryset(self, request):
        # role_badge lit les groupes de chaque ligne : sans préchargement, une requête par ligne.
        return super().get_queryset(request).prefetch_related('groups')
    list_filter = [
        'groups', 'is_active', 'must_change_password',
        'secretariat', 'is_staff', 'is_superuser',
    ]
    search_fields = [
        'username', 'first_name', 'last_name', 'email',
        'matricule', 'grade', 'telephone', 'organisation',
    ]
    ordering = ['last_name', 'first_name']
    list_select_related = ['secretariat']
    list_per_page = 50
    autocomplete_fields = ['secretariat']
    filter_horizontal = ['groups', 'user_permissions']
    readonly_fields = ['role_badge']
    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        ('Informations personnelles', {'fields': ('first_name', 'last_name', 'email')}),
        (
            'Permissions',
            {
                'fields': ('is_active', 'is_staff', 'is_superuser', 'user_permissions'),
                'description': (
                    'Préférez Administration → Groupes & permissions pour modifier les droits d\'un rôle. '
                    'Les permissions individuelles ci-dessous sont réservées aux exceptions (super-utilisateur).'
                ),
            },
        ),
        ('Dates importantes', {'fields': ('last_login', 'date_joined')}),
        ('Informations supplémentaires', {
            'fields': (
                'role_badge', 'groups',
                'matricule', 'grade',
                'telephone', 'organisation',
                'secretariat', 'must_change_password',
            ),
            'description': (
                'Attribuez ici les rôles (groupes ROLE_*). '
                'Seules certaines combinaisons multi-rôles sont autorisées (ex. Secrétariat + Encadrant). '
                'Les permissions détaillées se configurent dans Administration → Groupes & permissions.'
            ),
        }),
    )
    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        ('Informations supplémentaires', {
            'fields': (
                'first_name', 'last_name', 'email',
                'groups',
                'matricule', 'grade',
                'telephone', 'organisation',
                'secretariat',
            ),
            'description': (
                'Sélectionnez un ou plusieurs groupes ROLE_* (combinaisons limitées — voir aide). '
                'Permissions du rôle : Administration → Groupes & permissions.'
            ),
        }),
    )

    def get_fieldsets(self, request, obj=None):
        fieldsets = super().get_fieldsets(request, obj)
        if request.user.is_superuser:
            return fieldsets
        result = []
        for name, opts in fieldsets:
            if name != 'Permissions':
                result.append((name, opts))
                continue
            fields = tuple(f for f in opts['fields'] if f != 'user_permissions')
            result.append((name, {**opts, 'fields': fields}))
        return result

    def formfield_for_manytomany(self, db_field, request, **kwargs):
        if db_field.name == 'groups':
            kwargs['queryset'] = Group.objects.filter(name__in=ROLE_GROUP_NAMES.values())
            kwargs['label'] = 'Rôles (groupes ROLE_*)'
            kwargs['help_text'] = (
                'Choisissez un ou plusieurs rôles. Pour modifier les droits associés à un rôle, '
                'allez dans Administration → Groupes & permissions.'
            )
        if db_field.name == 'user_permissions':
            kwargs['help_text'] = (
                'Permissions exceptionnelles pour cet utilisateur uniquement. '
                'Utilisez les flèches pour déplacer les droits autorisés vers la colonne de droite.'
            )
        return super().formfield_for_manytomany(db_field, request, **kwargs)

    def _audit_cible(self, obj):
        return (
            'user',
            obj.username,
            obj.get_full_name() or obj.username,
        )

    @admin.display(description='Rôles', ordering='role')
    def role_badge(self, obj):
        effective_roles = sorted(get_user_roles(obj)) or ([obj.role] if obj.role else [])
        colors = {
            User.Role.ADMIN: ('#fdecec', '#b42318'),
            User.Role.DIRECTION: ('#eef6fc', '#0f4c81'),
            User.Role.CHEF_INJS_ADMIN: ('#eef6fc', '#0f4c81'),
            User.Role.INJS_ADMIN: ('#eef6fc', '#0f4c81'),
            User.Role.CHEF_SECRETARIAT: ('#fffae8', '#9a7a00'),
            User.Role.SECRETARIAT: ('#fffae8', '#9a7a00'),
            User.Role.FINANCE: ('#f0f4ff', '#3949ab'),
            User.Role.ARCHIVE: ('#f5f0ff', '#6b21a8'),
            User.Role.ENCADRANT: ('#e8eef6', '#09306c'),
            User.Role.SUPERVISEUR: ('#fef6c7', '#92660e'),
            User.Role.FORMATEUR: ('#f3f4f6', '#374151'),
            User.Role.AUDITEUR: ('#f3f4f6', '#374151'),
        }
        badges = []
        for effective in effective_roles:
            bg, fg = colors.get(effective, ('#f3f4f6', '#374151'))
            label = ROLE_LABELS.get(effective, effective)
            badges.append(format_html(
                '<span style="background:{};color:{};padding:3px 8px;'
                'border-radius:999px;font-weight:600;font-size:11px;margin-right:4px;">{}</span>',
                bg, fg, label,
            ))
        return format_html(''.join(badges)) if badges else '—'
