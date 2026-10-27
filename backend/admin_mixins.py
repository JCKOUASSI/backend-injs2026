"""Mixins partagés pour l'admin Django SYGEP-CPFAE."""

from django.contrib import admin
from django.db.models import Q

from authentication.role_groups import get_user_roles, user_in_roles, users_with_roles
from presences.models import AuditLog, _log_audit


# Rôles avec accès admin global (pas de filtrage queryset).
_ADMIN_GLOBAL_ROLES = frozenset({
    'ADMIN', 'INJS_ADMIN', 'CHEF_INJS_ADMIN', 'DIRECTION', 'FINANCE',
})


def admin_user_has_global_access(user):
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return user_in_roles(user, _ADMIN_GLOBAL_ROLES)


class AdminSidebarHiddenMixin:
    """Masque le modèle de l'index et de la navigation (accès via inlines / liens directs)."""

    def has_module_permission(self, request):
        return False


class RelatedFieldPrefetchListFilter(admin.RelatedFieldListFilter):
    """Filtre de clé étrangère qui charge les libellés des options en une requête.

    `RelatedFieldListFilter` appelle `str()` sur chaque option du menu déroulant.
    Quand le `__str__` du modèle cible traverse une relation, cela déclenche une
    requête par option. Les sous-classes déclarent les relations à précharger.
    """

    related_select_related = ()

    def field_choices(self, field, request, model_admin):
        choice_attr = (
            field.remote_field.get_related_field().attname
            if hasattr(field.remote_field, 'get_related_field')
            else 'pk'
        )
        queryset = field.remote_field.model._default_manager.complex_filter(
            field.get_limit_choices_to()
        )
        if self.related_select_related:
            queryset = queryset.select_related(*self.related_select_related)
        ordering = self.field_admin_ordering(field, request, model_admin)
        if ordering:
            queryset = queryset.order_by(*ordering)
        return [(getattr(obj, choice_attr), str(obj)) for obj in queryset]


class ModuleRelatedFilter(RelatedFieldPrefetchListFilter):
    """Pour les filtres pointant vers Module, dont le `__str__` lit la formation."""

    related_select_related = ('formation',)


class AdminScopeMixin:
    """Restreint les querysets admin selon le rôle (aligné dashboard / API)."""

    admin_scope_secretariat_field = None
    admin_scope_superviseur_field = None
    admin_scope_formation_field = None

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if admin_user_has_global_access(request.user):
            return qs

        roles = get_user_roles(request.user)
        secretariat = getattr(request.user, 'secretariat', None)
        scope_filter = Q()

        if 'ENCADRANT' in roles and self.admin_scope_superviseur_field:
            scope_filter |= Q(**{self.admin_scope_superviseur_field: request.user})

        if roles & {'SECRETARIAT', 'CHEF_SECRETARIAT'}:
            if secretariat:
                if self.admin_scope_secretariat_field:
                    scope_filter |= Q(**{self.admin_scope_secretariat_field: secretariat})
                elif self.admin_scope_formation_field:
                    scope_filter |= Q(
                        **{f'{self.admin_scope_formation_field}__modules__secretariat': secretariat}
                    )

        if scope_filter:
            return qs.filter(scope_filter).distinct()

        if roles & {'FINANCE', 'ENCADRANT', 'AUDITEUR', 'SECRETARIAT', 'CHEF_SECRETARIAT'}:
            return qs.none()

        return qs


class ParticipantAdminScopeMixin(AdminScopeMixin):
    admin_scope_secretariat_field = 'secretariat'

    def get_queryset(self, request):
        from formations.views import _participants_grade_filter

        qs = super().get_queryset(request)
        if admin_user_has_global_access(request.user):
            return qs

        roles = get_user_roles(request.user)
        secretariat = getattr(request.user, 'secretariat', None)

        if roles & {'SECRETARIAT', 'CHEF_SECRETARIAT'} and secretariat:
            return qs.filter(secretariat=secretariat).filter(
                _participants_grade_filter(secretariat)
            )

        if 'ENCADRANT' in roles:
            return qs.none()

        return qs.none()


class FormateurAdminScopeMixin(AdminScopeMixin):
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if admin_user_has_global_access(request.user):
            return qs

        roles = get_user_roles(request.user)

        if roles & {'SECRETARIAT', 'CHEF_SECRETARIAT'}:
            return qs

        if 'ENCADRANT' in roles:
            return qs.none()

        return qs.none()


class UserAdminScopeMixin:
    """Limite la liste users aux rôles subordonnés (+ secrétariat si applicable)."""

    def get_queryset(self, request):
        from authentication.permissions import get_creatable_roles

        qs = super().get_queryset(request)
        if admin_user_has_global_access(request.user):
            return qs

        roles = get_user_roles(request.user)
        subordinates = set()
        for role in roles:
            subordinates.update(get_creatable_roles(role))
        if not subordinates:
            return qs.none()

        qs = users_with_roles(subordinates)
        if roles & {'SECRETARIAT', 'CHEF_SECRETARIAT'} and request.user.secretariat_id:
            qs = qs.filter(secretariat=request.user.secretariat)
        return qs


class AuditLogAdminMixin:
    """Mixin à ajouter à tout ModelAdmin pour tracer les actions dans l'AuditLog."""

    audit_action_create = None
    audit_action_update = None
    audit_action_delete = None
    audit_formation_field = None

    def _audit_cible(self, obj):
        return ('', str(obj.pk), str(obj))

    def _audit_formation(self, obj):
        if not self.audit_formation_field:
            return None
        related = obj
        for part in self.audit_formation_field.split('.'):
            related = getattr(related, part, None)
            if related is None:
                return None
        return related

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        action = self.audit_action_update if change else self.audit_action_create
        if action:
            cible_type, cible_numero, cible_nom = self._audit_cible(obj)
            extra = {'via_admin': True}
            if change and form and hasattr(form, 'changed_data'):
                extra['champs_modifies'] = form.changed_data
            _log_audit(
                action=action,
                request=request,
                cible_type=cible_type,
                cible_numero=cible_numero,
                cible_nom=cible_nom,
                formation=self._audit_formation(obj),
                extra=extra,
            )

    def delete_model(self, request, obj):
        if self.audit_action_delete:
            cible_type, cible_numero, cible_nom = self._audit_cible(obj)
            _log_audit(
                action=self.audit_action_delete,
                request=request,
                cible_type=cible_type,
                cible_numero=cible_numero,
                cible_nom=cible_nom,
                formation=self._audit_formation(obj),
                extra={'via_admin': True},
            )
        super().delete_model(request, obj)


def log_admin_audit(action, request, *, cible_type='', cible_numero='', cible_nom='',
                    formation=None, pointage=None, extra=None):
    """Raccourci pour journaliser une action admin hors save_model."""
    _log_audit(
        action=action,
        request=request,
        cible_type=cible_type,
        cible_numero=cible_numero,
        cible_nom=cible_nom,
        formation=formation,
        pointage=pointage,
        extra={'via_admin': True, **(extra or {})},
    )


def pointage_remettre_en_cours_guard(pointage):
    """Vérifie qu'un pointage peut être remis en cours depuis l'admin."""
    from presences.models import Pointage

    if not pointage.timestamp_sortie:
        return False, "Ce pointage est déjà en cours."

    if pointage.session.est_terminee:
        return False, "La séance est terminée ; remise en cours impossible."

    filt = {
        'date_journee': pointage.date_journee,
        'timestamp_sortie__isnull': True,
    }
    if pointage.participant_id:
        filt['participant_id'] = pointage.participant_id
    elif pointage.formateur_id:
        filt['formateur_id'] = pointage.formateur_id
    elif pointage.encadrant_id:
        filt['encadrant_id'] = pointage.encadrant_id
    else:
        return False, "Aucune personne liée à ce pointage."

    if Pointage.objects.filter(**filt).exclude(pk=pointage.pk).exists():
        return False, (
            "Un autre pointage en cours existe déjà pour cette personne aujourd'hui."
        )

    return True, ""


def patch_admin_related_widgets():
    """Désactive les boutons « + Ajouter » / supprimer sur les champs FK/M2M admin."""
    from django.contrib.admin.widgets import RelatedFieldWidgetWrapper

    if getattr(RelatedFieldWidgetWrapper, '_cpfae_no_add_patch', False):
        return

    _original_init = RelatedFieldWidgetWrapper.__init__

    def __init__(
        self,
        widget,
        rel,
        admin_site,
        can_add_related=None,
        can_change_related=False,
        can_delete_related=False,
        can_view_related=False,
    ):
        _original_init(
            self,
            widget,
            rel,
            admin_site,
            can_add_related=False,
            can_change_related=can_change_related,
            can_delete_related=False,
            can_view_related=can_view_related,
        )

    RelatedFieldWidgetWrapper.__init__ = __init__
    RelatedFieldWidgetWrapper._cpfae_no_add_patch = True
