from django.contrib import admin
from django.contrib import messages
from django.core.exceptions import ValidationError
from django import forms
from django.utils.translation import gettext_lazy as _
from django.db.models import Count, Exists, OuterRef, Prefetch
from django.db import IntegrityError, transaction
from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html
from datetime import timedelta

from admin_mixins import (
    AdminScopeMixin,
    AdminSidebarHiddenMixin,
    AuditLogAdminMixin,
    FormateurAdminScopeMixin,
    ModuleRelatedFilter,
    ParticipantAdminScopeMixin,
    admin_user_has_global_access,
    log_admin_audit,
)
from .models import (
    Formation, Participant, Secretariat, ModuleParticipant, ModuleFormateur,
    Formateur, QRToken, RefFormation, RefModule, RefModuleVolumeHoraire, RefSite, RefBatiment, RefSalle,
    RefCategorie, RefGrade, RefTypeSecretariat, RefVague, Module, SessionModule,
    FinanceSettings,
)
from .serializer_querysets import annotate_secretariat_counts
from presences.models import AuditLog
from presences.admin_rattrapage_badgeage import AdminRattrapageBadgeageMixin
FormationFormateur = ModuleFormateur


def _reactiver_session_et_qr(session, request=None):
    """Réouvre une séance terminée, réactive le QR et journalise l'action."""
    from .session_views import reactiver_session_et_qr

    reactiver_session_et_qr(session)
    formation = session.module.formation

    if request is not None:
        label = session.intitule or f'Séance {session.numero}'
        log_admin_audit(
            AuditLog.Action.SEANCE_START,
            request,
            formation=formation,
            extra={
                'session_id': session.id,
                'label': label,
                'action': 'reactiver_via_admin',
            },
        )


class FormationAdminScopeMixin:
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if admin_user_has_global_access(request.user):
            return qs

        role = getattr(request.user, 'role', None)
        secretariat = getattr(request.user, 'secretariat', None)

        if role == 'ENCADRANT':
            return qs.filter(modules__superviseur=request.user).distinct()
        if role in ('SECRETARIAT', 'CHEF_SECRETARIAT') and secretariat:
            return qs.filter(modules__secretariat=secretariat).distinct()
        return qs.none()


@admin.register(Secretariat)
class SecretariatAdmin(AdminScopeMixin, admin.ModelAdmin):
    admin_scope_secretariat_field = 'pk'

    def get_queryset(self, request):
        return annotate_secretariat_counts(super().get_queryset(request))

    @admin.display(description='Participants', ordering='_nb_participants')
    def nb_participants(self, obj):
        if hasattr(obj, '_nb_participants'):
            return obj._nb_participants
        return obj.participants.count()

    @admin.display(description='Modules', ordering='_nb_modules')
    def nb_modules(self, obj):
        if hasattr(obj, '_nb_modules'):
            return obj._nb_modules
        return obj.modules_secretariat.count()

    @admin.display(description='Formations', ordering='_nb_formations')
    def nb_formations(self, obj):
        if hasattr(obj, '_nb_formations'):
            return obj._nb_formations
        return obj.modules_secretariat.values('formation_id').distinct().count()
    list_display = [
        'numero', 'nom', 'type', 'responsable',
        'nb_participants', 'nb_modules', 'nb_formations',
    ]
    list_display_links = ['numero', 'nom']
    search_fields = [
        'numero', 'nom', 'description',
        'responsable__username', 'responsable__first_name', 'responsable__last_name',
    ]
    list_filter = ['type']
    autocomplete_fields = ['responsable', 'type']
    list_select_related = ['responsable', 'type']
    ordering = ['nom']
    list_per_page = 50


class ModuleParticipantInline(admin.TabularInline):
    model = ModuleParticipant
    extra = 1
    autocomplete_fields = ['participant']
    readonly_fields = ['inscrit_le']
    verbose_name = "Étudiant inscrit"
    verbose_name_plural = "Étudiants inscrits"


class ModuleFormateurInline(admin.TabularInline):
    model = ModuleFormateur
    extra = 1
    autocomplete_fields = ['formateur']
    readonly_fields = ['inscrit_le']
    verbose_name = "Formateur assigné"
    verbose_name_plural = "Formateurs assignés"


class SessionModuleInline(admin.TabularInline):
    """Séances d'un module, en lecture seule. Pour modifier, utiliser le lien."""
    model = SessionModule
    extra = 0
    can_delete = False
    show_change_link = True
    fields = (
        'date_journee', 'numero', 'intitule',
        'heure_debut_prevue', 'heure_fin_prevue',
        'etat_seance', 'demarree_le', 'terminee_le',
    )
    readonly_fields = (
        'date_journee', 'numero', 'intitule',
        'heure_debut_prevue', 'heure_fin_prevue',
        'etat_seance', 'demarree_le', 'terminee_le',
    )
    ordering = ('-date_journee', '-numero')
    verbose_name = "Séance"
    verbose_name_plural = "Séances planifiées (lecture seule — cliquer pour modifier)"

    def has_add_permission(self, request, obj=None):
        return False

    @admin.display(description='État')
    def etat_seance(self, obj):
        if obj.demarree_le and not obj.terminee_le:
            label, bg, fg = 'En cours', '#e8eef6', '#09306c'
        elif obj.terminee_le:
            label, bg, fg = 'Terminée', '#eef6fc', '#0f4c81'
        else:
            label, bg, fg = 'Planifiée', '#f3f4f6', '#374151'
        return format_html(
            '<span style="background:{};color:{};padding:2px 8px;'
            'border-radius:999px;font-weight:600;font-size:11px;">{}</span>',
            bg, fg, label,
        )


@admin.register(Formation)
class FormationAdmin(FormationAdminScopeMixin, AuditLogAdminMixin, admin.ModelAdmin):
    audit_action_create = AuditLog.Action.FORMATION_CREATE
    audit_action_update = AuditLog.Action.FORMATION_UPDATE
    audit_action_delete = AuditLog.Action.FORMATION_DELETE
    list_display = [
        'formation', 'numero_formation',
        'nb_modules_display', 'created_at', 'updated_at',
    ]
    search_fields = ['formation']
    ordering = ['formation']
    list_per_page = 50
    date_hierarchy = 'created_at'
    readonly_fields = ['created_at', 'updated_at']

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.annotate(_nb_modules=Count('modules', distinct=True))

    @admin.display(description='Nombre de modules', ordering='_nb_modules')
    def nb_modules_display(self, obj):
        if hasattr(obj, '_nb_modules'):
            return obj._nb_modules
        return obj.modules.count()


class ParticipantAdminForm(forms.ModelForm):
    class Meta:
        model = Participant
        fields = '__all__'

    def clean_matricule(self):
        from formations.participant_matricule import normalize_matricule, validate_participant_matricule

        matricule = normalize_matricule(self.cleaned_data.get('matricule'))
        linked_user = self.cleaned_data.get('user') or getattr(self.instance, 'user', None)
        try:
            return validate_participant_matricule(
                matricule,
                participant_id=self.instance.pk,
                linked_user_id=getattr(linked_user, 'pk', None),
            )
        except ValidationError as exc:
            raise forms.ValidationError(exc.messages[0]) from exc


@admin.register(Participant)
class ParticipantAdmin(
    AdminRattrapageBadgeageMixin,
    ParticipantAdminScopeMixin,
    AuditLogAdminMixin,
    admin.ModelAdmin,
):
    form = ParticipantAdminForm
    audit_action_create = AuditLog.Action.PARTICIPANT_CREATE
    audit_action_update = AuditLog.Action.PARTICIPANT_UPDATE
    audit_action_delete = AuditLog.Action.PARTICIPANT_DELETE
    actions = ['forcer_badgeage_rattrapage']
    list_display = [
        'matricule', 'nom', 'prenom', 'sexe',
        'categorie', 'grade', 'groupe', 'vague',
        'secretariat',
    ]
    list_display_links = ['matricule', 'nom']
    search_fields = [
        'matricule', 'nom', 'prenom',
        'grade', 'groupe', 'vague',
    ]
    list_filter = [
        'grade', 'groupe', 'vague', 'categorie', 'sexe', 'secretariat',
    ]
    autocomplete_fields = ['secretariat', 'user']
    list_select_related = ['secretariat']
    ordering = ['nom', 'prenom']
    list_per_page = 100
    show_full_result_count = False  # Évite le COUNT(*) lent sur gros volumes
    readonly_fields = ['created_at']
    fieldsets = (
        ("Identification", {
            'fields': (
                ('matricule', 'sexe'),
                ('nom', 'prenom'),
                ('date_naissance', 'lieu_naissance'),
            ),
        }),
        ("Coordonnées", {
            'fields': (('email', 'telephone'), 'telephone2'),
        }),
        ("Concours d'entrée", {
            'fields': (('type_concours', 'libelle_concours'),),
        }),
        ("Affectation pédagogique", {
            'fields': (
                ('categorie', 'grade', 'grade_groupe'),
                ('groupe', 'vague'),
                ('site', 'salle'),
                'secretariat',
                'motif_notoire',
            ),
        }),
        ("Compte utilisateur", {
            'classes': ('collapse',),
            'fields': ('user', 'created_at'),
        }),
    )

    def _audit_cible(self, obj):
        return ('participant', obj.matricule or str(obj.pk), f"{obj.nom} {obj.prenom}".strip())

    def save_model(self, request, obj, form, change):
        matricule_changed = change and 'matricule' in form.changed_data
        if matricule_changed:
            from formations.participant_matricule import (
                secretariat_from_matricule_for_actor,
                sync_participant_user_after_matricule_change,
            )

            secretariat = secretariat_from_matricule_for_actor(obj.matricule, request.user)
            if secretariat is not None:
                obj.secretariat = secretariat

        try:
            with transaction.atomic():
                super().save_model(request, obj, form, change)
                if matricule_changed and obj.user_id:
                    sync_participant_user_after_matricule_change(obj)
        except IntegrityError as exc:
            messages.error(
                request,
                _('Impossible d’enregistrer ce matricule : il est déjà utilisé.'),
            )
            raise ValidationError({'matricule': _('Ce matricule est déjà utilisé.')}) from exc


@admin.register(ModuleParticipant)
class ModuleParticipantAdmin(
    AdminRattrapageBadgeageMixin,
    AdminSidebarHiddenMixin,
    AdminScopeMixin,
    admin.ModelAdmin,
):
    admin_scope_secretariat_field = 'module__secretariat'
    admin_scope_superviseur_field = 'module__superviseur'
    rattrapage_participant_id_field = 'participant_id'
    actions = ['forcer_badgeage_rattrapage']
    list_display = [
        'module', 'formation_label', 'grade_module', 'groupe_module',
        'participant', 'matricule_participant', 'inscrit_le',
    ]
    list_filter = [
        'module__formation', 'module__grade', 'module__groupe', 'module__vague',
        ('module', ModuleRelatedFilter),
    ]
    search_fields = [
        'module__intitule', 'module__formation__formation',
        'module__grade', 'module__groupe', 'module__vague',
        'participant__matricule', 'participant__nom', 'participant__prenom',
    ]
    autocomplete_fields = ['module', 'participant']
    list_select_related = ['module', 'module__formation', 'participant']
    ordering = ['-inscrit_le']
    list_per_page = 50
    date_hierarchy = 'inscrit_le'

    @admin.display(description='Formation', ordering='module__formation__formation')
    def formation_label(self, obj):
        return obj.module.formation

    @admin.display(description='Grade', ordering='module__grade')
    def grade_module(self, obj):
        return obj.module.grade or '—'

    @admin.display(description='Groupe', ordering='module__groupe')
    def groupe_module(self, obj):
        return obj.module.groupe or '—'

    @admin.display(description='Matricule', ordering='participant__matricule')
    def matricule_participant(self, obj):
        return obj.participant.matricule


@admin.register(Module)
class ModuleAdmin(AdminScopeMixin, AuditLogAdminMixin, admin.ModelAdmin):
    admin_scope_secretariat_field = 'secretariat'
    admin_scope_superviseur_field = 'superviseur'
    audit_action_create = AuditLog.Action.FORMATION_CREATE
    audit_action_update = AuditLog.Action.FORMATION_UPDATE
    audit_action_delete = AuditLog.Action.FORMATION_DELETE
    audit_formation_field = 'formation'
    list_display = [
        'intitule', 'formation', 'grade', 'groupe', 'vague',
        'statut', 'formateur', 'secretariat', 'site',
        'date_debut', 'date_fin',
        'sessions_button', 'reactiver_derniere_seance_button',
    ]
    list_display_links = ['intitule']
    search_fields = [
        'intitule', 'formation__formation',
        'grade', 'groupe', 'vague',
        'site__nom', 'batiment', 'salle',
        'formateur__nom', 'formateur__prenom',
    ]
    list_filter = [
        'statut', 'formation', 'grade', 'groupe', 'vague',
        'site', 'secretariat',
    ]
    autocomplete_fields = ['formation', 'formateur', 'secretariat', 'site', 'superviseur']
    list_select_related = ['formation', 'formateur', 'secretariat', 'site']
    ordering = ['formation', 'ordre', 'intitule']
    list_per_page = 50
    date_hierarchy = 'date_debut'
    inlines = [SessionModuleInline, ModuleParticipantInline, ModuleFormateurInline]
    actions = ['marquer_planifie', 'marquer_en_cours', 'marquer_suspendu', 'marquer_termine']
    fieldsets = (
        ("Identification", {
            'fields': (
                ('formation', 'numero_ordre'),
                'intitule', 'ordre',
                'cycle',
            ),
        }),
        ("Classification (sert au filtrage côté pointage)", {
            'fields': (('grade', 'groupe', 'vague'),),
            'description': "Ces champs permettent de retrouver la bonne séance lors d'un pointage.",
        }),
        ("Planification", {
            'fields': (
                ('date_debut', 'date_fin'),
                'duree_prevue_heures',
                'statut',
            ),
        }),
        ("Encadrement", {
            'fields': ('formateur', 'superviseur', 'secretariat'),
        }),
        ("Localisation", {
            'fields': (('site', 'batiment', 'salle'), 'site_legacy'),
        }),
        ("Traçabilité", {
            'classes': ('collapse',),
            'fields': ('creee_par', 'created_at'),
        }),
    )
    readonly_fields = ('created_at', 'numero_ordre')

    def get_queryset(self, request):
        terminated = SessionModule.objects.filter(
            module_id=OuterRef('pk'),
            demarree_le__isnull=False,
            terminee_le__isnull=False,
        )
        qs = super().get_queryset(request)
        return qs.annotate(
            _nb_sessions=Count('sessions', distinct=True),
            _has_terminated_sessions=Exists(terminated),
        )

    def _audit_cible(self, obj):
        return ('module', str(obj.pk), obj.intitule)

    def _log_statut_bulk(self, request, queryset, nouveau_statut):
        for module in queryset.select_related('formation'):
            ancien = module.statut
            if ancien == nouveau_statut:
                continue
            log_admin_audit(
                AuditLog.Action.FORMATION_STATUT,
                request,
                formation=module.formation,
                cible_type='module',
                cible_numero=str(module.pk),
                cible_nom=module.intitule,
                extra={
                    'ancien_statut': ancien,
                    'nouveau_statut': nouveau_statut,
                    'action': 'bulk_admin',
                },
            )

    @admin.display(description='N°', ordering='ordre')
    def numero_ordre(self, obj):
        return obj.ordre if obj and obj.pk else '—'

    @admin.action(description='Marquer comme « Planifiée »')
    def marquer_planifie(self, request, queryset):
        self._log_statut_bulk(request, queryset, Module.Statut.PLANIFIEE)
        n = queryset.update(statut=Module.Statut.PLANIFIEE)
        self.message_user(request, f"{n} module(s) marqué(s) « Planifié(e)s ».")

    @admin.action(description='Marquer comme « En cours »')
    def marquer_en_cours(self, request, queryset):
        self._log_statut_bulk(request, queryset, Module.Statut.EN_COURS)
        n = queryset.update(statut=Module.Statut.EN_COURS)
        self.message_user(request, f"{n} module(s) marqué(s) « En cours ».")

    @admin.action(description='Marquer comme « Suspendue »')
    def marquer_suspendu(self, request, queryset):
        self._log_statut_bulk(request, queryset, Module.Statut.SUSPENDUE)
        n = queryset.update(statut=Module.Statut.SUSPENDUE)
        self.message_user(request, f"{n} module(s) marqué(s) « Suspendu(e)s ».")

    @admin.action(description='Marquer comme « Terminée »')
    def marquer_termine(self, request, queryset):
        self._log_statut_bulk(request, queryset, Module.Statut.TERMINEE)
        n = queryset.update(statut=Module.Statut.TERMINEE)
        self.message_user(request, f"{n} module(s) marqué(s) « Terminé(e)s ».")

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                '<path:object_id>/sessions/',
                self.admin_site.admin_view(self.sessions_module_view),
                name='formations_module_sessions',
            ),
            path(
                '<path:object_id>/reactiver-derniere-seance/',
                self.admin_site.admin_view(self.reactiver_derniere_seance_view),
                name='formations_module_reactiver_derniere_seance',
            ),
        ]
        return custom_urls + urls

    @admin.display(description='Séances', ordering='_nb_sessions')
    def sessions_button(self, obj):
        count = obj._nb_sessions if hasattr(obj, '_nb_sessions') else obj.sessions.count()
        url = reverse('admin:formations_module_sessions', args=[obj.pk])
        label = f'Voir {count} séance(s)'
        return format_html('<a class="button" href="{}">{}</a>', url, label)

    def sessions_module_view(self, request, object_id):
        module = self.get_object(request, object_id)
        if module is None:
            self.message_user(request, "Module introuvable.", level='error')
            return HttpResponseRedirect(reverse('admin:formations_module_changelist'))

        sessions = list(
            module.sessions.select_related('module')
            .order_by('-date_journee', '-numero')
        )
        sessions_rows = []
        for session in sessions:
            etat = 'Planifiée'
            if session.est_en_cours:
                etat = 'En cours'
            elif session.est_terminee:
                etat = 'Terminée'
            sessions_rows.append({
                'id': session.id,
                'date_journee': session.date_journee,
                'numero': session.numero,
                'intitule': session.intitule or f"Séance {session.numero}",
                'etat': etat,
                'demarree_le': session.demarree_le,
                'terminee_le': session.terminee_le,
                'change_url': reverse('admin:formations_sessionmodule_change', args=[session.pk]),
                'reactiver_url': (
                    reverse('admin:formations_sessionmodule_reactiver', args=[session.pk])
                    if session.demarree_le and session.terminee_le
                    else None
                ),
            })

        context = {
            **self.admin_site.each_context(request),
            'opts': self.model._meta,
            'title': f"Séances du module : {module.intitule}",
            'module_obj': module,
            'sessions_rows': sessions_rows,
            'back_url': reverse('admin:formations_module_changelist'),
        }
        return render(request, 'admin/formations/module/sessions_list.html', context)

    @admin.display(description='Réactiver séance')
    def reactiver_derniere_seance_button(self, obj):
        if hasattr(obj, '_has_terminated_sessions'):
            has_terminated = obj._has_terminated_sessions
        elif not obj.pk:
            return '-'
        else:
            has_terminated = obj.sessions.filter(
                demarree_le__isnull=False,
                terminee_le__isnull=False,
            ).exists()
        if not has_terminated:
            return '-'
        url = reverse('admin:formations_module_reactiver_derniere_seance', args=[obj.pk])
        return format_html('<a class="button" href="{}">Réactiver dernière séance</a>', url)

    def reactiver_derniere_seance_view(self, request, object_id):
        module = self.get_object(request, object_id)
        if module is None:
            self.message_user(request, "Module introuvable.", level='error')
            return HttpResponseRedirect(reverse('admin:formations_module_changelist'))

        session = module.sessions.filter(
            demarree_le__isnull=False,
            terminee_le__isnull=False,
        ).order_by('-terminee_le').first()
        if session is None:
            self.message_user(request, "Aucune séance terminée à réactiver pour ce module.", level='warning')
            return HttpResponseRedirect(reverse('admin:formations_module_changelist'))

        _reactiver_session_et_qr(session, request)
        self.message_user(
            request,
            f"Dernière séance réactivée pour le module « {module.intitule} ».",
        )
        return HttpResponseRedirect(reverse('admin:formations_module_changelist'))


@admin.register(SessionModule)
class SessionModuleAdmin(AdminScopeMixin, AuditLogAdminMixin, admin.ModelAdmin):
    admin_scope_secretariat_field = 'module__secretariat'
    admin_scope_superviseur_field = 'module__superviseur'
    audit_action_create = AuditLog.Action.SEANCE_CREATE
    audit_action_update = None
    audit_action_delete = AuditLog.Action.SEANCE_DELETE
    audit_formation_field = 'module.formation'
    list_display = [
        'date_journee', 'numero', 'intitule', 'module_lien', 'formation',
        'grade_module', 'groupe_module', 'vague_module',
        'heure_debut_prevue', 'heure_fin_prevue',
        'demarree_le', 'terminee_le',
        'pointages_button', 'reactiver_button',
    ]
    list_filter = [
        'date_journee',
        'module__formation',
        'module__grade',
        'module__groupe',
        'module__vague',
        ('module', ModuleRelatedFilter),
    ]
    search_fields = [
        'intitule',
        'module__intitule',
        'module__formation__formation',
        'module__grade',
        'module__groupe',
        'module__vague',
    ]
    autocomplete_fields = ['module', 'demarree_par']
    list_select_related = ['module', 'module__formation']
    ordering = ['-date_journee', '-heure_debut_prevue', 'numero']
    list_per_page = 50
    date_hierarchy = 'date_journee'
    actions = ['reactiver_sessions', 'rattrapage_badgeage_seance']
    fieldsets = (
        ("Rattachement", {
            'fields': ('module',),
        }),
        ("Planification", {
            'fields': (
                ('date_journee', 'numero'),
                'intitule',
                ('heure_debut_prevue', 'heure_fin_prevue'),
                'auto_demarrage',
            ),
        }),
        ("Exécution", {
            'fields': (
                ('demarree_le', 'terminee_le'),
                'demarree_par',
            ),
        }),
    )

    @admin.display(description='Grade', ordering='module__grade')
    def grade_module(self, obj):
        return obj.module.grade or '—'

    @admin.display(description='Groupe', ordering='module__groupe')
    def groupe_module(self, obj):
        return obj.module.groupe or '—'

    @admin.display(description='Vague', ordering='module__vague')
    def vague_module(self, obj):
        return obj.module.vague or '—'

    @admin.display(description='Module', ordering='module__intitule')
    def module_lien(self, obj):
        url = reverse('admin:formations_module_change', args=[obj.module_id])
        return format_html('<a href="{}">{}</a>', url, obj.module.intitule)

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                '<path:object_id>/reactiver/',
                self.admin_site.admin_view(self.reactiver_view),
                name='formations_sessionmodule_reactiver',
            ),
        ]
        return custom_urls + urls

    @admin.display(description='Formation', ordering='module__formation__formation')
    def formation(self, obj):
        return obj.module.formation

    @admin.display(description='Pointages')
    def pointages_button(self, obj):
        try:
            url = reverse('admin:presences_pointage_changelist')
        except Exception:
            return '—'
        return format_html(
            '<a class="button" href="{}?session__id__exact={}">Voir</a>',
            url, obj.pk,
        )

    @admin.display(description='Réactiver')
    def reactiver_button(self, obj):
        if not obj.demarree_le or not obj.terminee_le:
            return '-'
        url = reverse('admin:formations_sessionmodule_reactiver', args=[obj.pk])
        return format_html('<a class="button" href="{}">Réactiver</a>', url)

    def reactiver_view(self, request, object_id):
        session = self.get_object(request, object_id)
        if session is None:
            self.message_user(request, "Séance introuvable.", level='error')
            return HttpResponseRedirect(reverse('admin:formations_sessionmodule_changelist'))

        if not session.demarree_le or not session.terminee_le:
            self.message_user(
                request,
                "Cette séance n'est pas terminée, aucune réactivation nécessaire.",
                level='warning',
            )
            return HttpResponseRedirect(reverse('admin:formations_sessionmodule_changelist'))

        self._reactiver_une_session(session, request)
        self.message_user(request, "Séance réactivée avec succès.")
        return HttpResponseRedirect(reverse('admin:formations_sessionmodule_changelist'))

    def _reactiver_une_session(self, session, request=None):
        _reactiver_session_et_qr(session, request)

    @admin.action(description='Réactiver les séances sélectionnées')
    def reactiver_sessions(self, request, queryset):
        from .session_views import reactiver_sessions_en_lot

        reactivated = 0
        skipped = 0
        to_reactivate = []

        for session in queryset.select_related('module', 'module__formation'):
            if not session.demarree_le or not session.terminee_le:
                skipped += 1
                continue
            to_reactivate.append(session)

        if to_reactivate:
            reactiver_sessions_en_lot(to_reactivate)
            reactivated = len(to_reactivate)
            if request is not None:
                for session in to_reactivate:
                    label = session.intitule or f'Séance {session.numero}'
                    log_admin_audit(
                        AuditLog.Action.SEANCE_START,
                        request,
                        formation=session.module.formation,
                        extra={
                            'session_id': session.id,
                            'label': label,
                            'action': 'reactiver_via_admin',
                        },
                    )

        if reactivated:
            self.message_user(
                request,
                f"{reactivated} séance(s) réactivée(s).",
            )
        if skipped:
            self.message_user(
                request,
                f"{skipped} séance(s) ignorée(s) (non terminées ou jamais démarrées).",
                level='warning',
            )

    @admin.action(description='Rattrapage badgeage (présents / absents)')
    def rattrapage_badgeage_seance(self, request, queryset):
        if queryset.count() != 1:
            self.message_user(
                request,
                _('Sélectionnez une seule séance.'),
                level='warning',
            )
            return None
        session = queryset.select_related('module').first()
        url = reverse('admin:formations_participant_rattrapage_badgeage')
        return HttpResponseRedirect(
            f'{url}?module={session.module_id}&session={session.id}',
        )


@admin.register(Formateur)
class FormateurAdmin(FormateurAdminScopeMixin, AuditLogAdminMixin, admin.ModelAdmin):
    audit_action_create = AuditLog.Action.FORMATEUR_CREATE
    audit_action_update = AuditLog.Action.FORMATEUR_UPDATE
    audit_action_delete = AuditLog.Action.FORMATEUR_DELETE
    list_display = [
        'numerobadge', 'nom', 'prenom', 'specialite',
        'email', 'telephone', 'organisation',
    ]
    list_display_links = ['numerobadge', 'nom']
    search_fields = [
        'numerobadge', 'nom', 'prenom', 'email',
        'telephone', 'specialite', 'organisation',
        'secretariats__nom', 'secretariats__numero',
    ]
    list_filter = ['organisation', 'specialite', 'secretariats']
    filter_horizontal = ['secretariats']
    autocomplete_fields = ['user']
    ordering = ['nom', 'prenom']
    list_per_page = 50
    readonly_fields = ['created_at']
    fieldsets = (
        ("Identification", {
            'fields': (
                'numerobadge',
                ('nom', 'prenom'),
            ),
            'description': "Le numéro de badge est auto-généré si laissé vide.",
        }),
        ("Coordonnées", {
            'fields': (('email', 'telephone'),),
        }),
        ("Profil professionnel", {
            'fields': ('specialite', 'organisation', 'secretariats'),
        }),
        ("Compte utilisateur", {
            'classes': ('collapse',),
            'fields': ('user', 'created_at'),
        }),
    )

    def _audit_cible(self, obj):
        return ('formateur', obj.numerobadge or str(obj.pk), f"{obj.nom} {obj.prenom}".strip())


@admin.register(ModuleFormateur)
class ModuleFormateurAdmin(AdminSidebarHiddenMixin, AdminScopeMixin, admin.ModelAdmin):
    admin_scope_secretariat_field = 'module__secretariat'
    admin_scope_superviseur_field = 'module__superviseur'
    list_display = [
        'module', 'formation_label', 'grade_module', 'groupe_module',
        'formateur', 'badge_formateur', 'inscrit_le',
    ]
    list_filter = [
        'module__formation', 'module__grade', 'module__groupe',
        'module__vague', ('module', ModuleRelatedFilter),
    ]
    search_fields = [
        'module__intitule', 'module__formation__formation',
        'module__grade', 'module__groupe', 'module__vague',
        'formateur__numerobadge', 'formateur__nom', 'formateur__prenom',
    ]
    autocomplete_fields = ['module', 'formateur']
    list_select_related = ['module', 'module__formation', 'formateur']
    ordering = ['-inscrit_le']
    list_per_page = 50
    date_hierarchy = 'inscrit_le'

    @admin.display(description='Formation', ordering='module__formation__formation')
    def formation_label(self, obj):
        return obj.module.formation

    @admin.display(description='Grade', ordering='module__grade')
    def grade_module(self, obj):
        return obj.module.grade or '—'

    @admin.display(description='Groupe', ordering='module__groupe')
    def groupe_module(self, obj):
        return obj.module.groupe or '—'

    @admin.display(description='N° badge', ordering='formateur__numerobadge')
    def badge_formateur(self, obj):
        return obj.formateur.numerobadge


@admin.register(QRToken)
class QRTokenAdmin(AdminScopeMixin, admin.ModelAdmin):
    admin_scope_secretariat_field = 'session__module__secretariat'
    admin_scope_superviseur_field = 'session__module__superviseur'
    list_display = [
        'session', 'actif_badge', 'etat_validite',
        'expire_at', 'genere_par', 'created_at',
    ]
    list_filter = [
        'actif',
        'session__module__formation',
        'session__module__grade',
        'session__module__groupe',
        'session__date_journee',
    ]
    search_fields = [
        'token',
        'session__intitule',
        'session__module__intitule',
        'session__module__formation__formation',
        'session__module__grade',
        'session__module__groupe',
        'session__module__vague',
        'genere_par__username',
    ]
    autocomplete_fields = ['session', 'genere_par']
    list_select_related = ['session', 'session__module', 'session__module__formation', 'genere_par']
    ordering = ['-created_at']
    list_per_page = 50
    date_hierarchy = 'expire_at'
    readonly_fields = ['token', 'created_at']

    @admin.display(description='Actif', boolean=True, ordering='actif')
    def actif_badge(self, obj):
        return obj.actif

    @admin.display(description='Validité')
    def etat_validite(self, obj):
        if not obj.actif:
            label, bg, fg = 'Désactivé', '#fdecec', '#b42318'
        elif obj.is_expired:
            label, bg, fg = 'Expiré', '#fffae8', '#9a7a00'
        elif obj.session.est_terminee:
            label, bg, fg = 'Séance terminée', '#fffae8', '#9a7a00'
        else:
            label, bg, fg = 'Valide', '#e8eef6', '#09306c'
        return format_html(
            '<span style="background:{};color:{};padding:3px 8px;'
            'border-radius:999px;font-weight:600;font-size:11px;">{}</span>',
            bg, fg, label,
        )


@admin.register(RefTypeSecretariat)
class RefTypeSecretariatAdmin(admin.ModelAdmin):
    list_display = ['libelle', 'actif']
    search_fields = ['libelle']
    list_filter = ['actif']
    ordering = ['libelle']


@admin.register(RefVague)
class RefVagueAdmin(admin.ModelAdmin):
    list_display = ['libelle', 'ordre', 'actif']
    search_fields = ['libelle']
    list_filter = ['actif']
    ordering = ['ordre', 'libelle']


@admin.register(RefCategorie)
class RefCategorieAdmin(admin.ModelAdmin):
    list_display = ['libelle', 'actif']
    search_fields = ['libelle']
    list_filter = ['actif']
    ordering = ['libelle']


@admin.register(RefGrade)
class RefGradeAdmin(admin.ModelAdmin):
    list_display = ['libelle', 'categorie', 'actif']
    search_fields = ['libelle', 'categorie__libelle']
    list_filter = ['categorie', 'actif']
    autocomplete_fields = ['categorie']
    list_select_related = ['categorie']
    ordering = ['categorie__libelle', 'libelle']


@admin.register(RefFormation)
class RefFormationAdmin(admin.ModelAdmin):
    list_display = ['intitule', 'prix_heure_realisee', 'actif']
    search_fields = ['intitule']
    list_filter = ['actif']


class RefModuleVolumeHoraireInline(admin.TabularInline):
    model = RefModuleVolumeHoraire
    extra = 1
    autocomplete_fields = ['formation', 'categorie']


@admin.register(RefModule)
class RefModuleAdmin(admin.ModelAdmin):
    list_display = ['intitule', 'formations_display', 'volume_horaire', 'volumes_par_categorie_display', 'actif']
    search_fields = ['intitule', 'formations__intitule']
    list_filter = ['actif', 'formations']
    filter_horizontal = ['formations']
    ordering = ['intitule']
    inlines = [RefModuleVolumeHoraireInline]

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related(
            'formations',
            Prefetch(
                'volumes_horaires',
                queryset=RefModuleVolumeHoraire.objects.select_related('formation', 'categorie'),
            ),
        )

    @admin.display(description='Formations')
    def formations_display(self, obj):
        labels = sorted(formation.intitule for formation in obj.formations.all())
        return ', '.join(labels) if labels else '—'

    @admin.display(description='Volumes (formation × cat.)')
    def volumes_par_categorie_display(self, obj):
        volumes = list(obj.volumes_horaires.all())
        if not volumes:
            return '—'
        return ', '.join([
            f"{v.formation.intitule[:20]}…/{v.categorie.libelle}: {v.volume_horaire}h"
            if len(v.formation.intitule) > 20
            else f"{v.formation.intitule}/{v.categorie.libelle}: {v.volume_horaire}h"
            for v in volumes
        ])


class RefBatimentInline(admin.TabularInline):
    model = RefBatiment
    extra = 1


class RefSalleInline(admin.TabularInline):
    model = RefSalle
    extra = 1


@admin.register(RefSite)
class RefSiteAdmin(admin.ModelAdmin):
    list_display = ['nom', 'actif', 'geofence_latitude', 'geofence_longitude', 'geofence_rayon_m']
    search_fields = ['nom']
    list_filter = ['actif']
    fields = [
        'nom', 'actif',
        'geofence_latitude', 'geofence_longitude', 'geofence_rayon_m',
    ]
    inlines = [RefBatimentInline, RefSalleInline]


@admin.register(RefBatiment)
class RefBatimentAdmin(AdminSidebarHiddenMixin, admin.ModelAdmin):
    list_display = ['nom', 'site', 'actif']
    search_fields = ['nom', 'site__nom']
    list_filter = ['site', 'actif']
    autocomplete_fields = ['site']
    list_select_related = ['site']
    ordering = ['site__nom', 'nom']


@admin.register(RefSalle)
class RefSalleAdmin(AdminSidebarHiddenMixin, admin.ModelAdmin):
    list_display = ['nom', 'site', 'batiment', 'type_lieu', 'capacite', 'actif']
    search_fields = ['nom', 'site__nom', 'batiment__nom']
    list_filter = ['site', 'batiment', 'actif']
    autocomplete_fields = ['site', 'batiment']
    list_select_related = ['site', 'batiment']
    ordering = ['site__nom', 'batiment__nom', 'nom']


@admin.register(RefModuleVolumeHoraire)
class RefModuleVolumeHoraireAdmin(admin.ModelAdmin):
    list_display = ['module', 'formation', 'categorie', 'volume_horaire']
    search_fields = ['module__intitule', 'formation__intitule', 'categorie__libelle']
    list_filter = ['formation', 'categorie']
    autocomplete_fields = ['module', 'formation', 'categorie']
    list_select_related = ['module', 'formation', 'categorie']
    ordering = ['module__intitule', 'formation__intitule', 'categorie__libelle']


@admin.register(FinanceSettings)
class FinanceSettingsAdmin(admin.ModelAdmin):
    list_display = ['prix_heure_realisee', 'afficher_montants_exports', 'updated_at', 'updated_by']
    readonly_fields = ['updated_at']
    autocomplete_fields = ['updated_by']
    fieldsets = (
        (_("Tarification"), {
            'fields': ('prix_heure_realisee', 'afficher_montants_exports'),
        }),
        (_("Mise en page des exports"), {
            'fields': (
                'export_titre_document',
                ('export_entete_ligne1', 'export_entete_ligne2'),
                'export_organisme',
                'export_adresse',
                'export_reference_prefix',
                'export_mention_legale',
                ('export_signataire_nom', 'export_signataire_fonction'),
                'export_contacts',
                ('export_pied_page_titre', 'export_pied_page_texte'),
            ),
        }),
        (_("Traçabilité"), {
            'classes': ('collapse',),
            'fields': ('updated_at', 'updated_by'),
        }),
    )

    def has_add_permission(self, request):
        return not FinanceSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)


from formations.admin_diagnostic import attach_volume_diagnostic_admin_urls

attach_volume_diagnostic_admin_urls()
