from django.contrib import admin
from django.contrib import messages
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponseRedirect
from django.urls import path, reverse
from django.utils.html import format_html

from admin_mixins import (
    AdminScopeMixin,
    ModuleRelatedFilter,
    admin_user_has_global_access,
    log_admin_audit,
    pointage_remettre_en_cours_guard,
)
from .models import Pointage, AuditLog, DeviceBinding, Rattrapage, _log_audit
from .rattrapage_service import (
    RattrapageError,
    annuler_rattrapage,
    generer_presence_rattrapage,
)


class TypePersonneFilter(admin.SimpleListFilter):
    title = "Type de personne"
    parameter_name = "type_personne"

    def lookups(self, request, model_admin):
        return (
            ("participant", "Participant"),
            ("formateur", "Formateur"),
            ("encadrant", "Encadrant"),
        )

    def queryset(self, request, queryset):
        value = self.value()
        if value == "participant":
            return queryset.filter(participant__isnull=False)
        if value == "formateur":
            return queryset.filter(formateur__isnull=False)
        if value == "encadrant":
            return queryset.filter(encadrant__isnull=False)
        return queryset


@admin.register(Pointage)
class PointageAdmin(AdminScopeMixin, admin.ModelAdmin):
    admin_scope_secretariat_field = 'session__module__secretariat'
    admin_scope_superviseur_field = 'session__module__superviseur'
    list_display = [
        'remettre_en_cours_action',
        'date_journee', 'personne_nom', 'personne_numero', 'type_personne_display',
        'formation_label', 'grade_label', 'groupe_label', 'vague_label',
        'module_label', 'session_label',
        'timestamp_entree', 'timestamp_sortie', 'duree_presence_minutes', 'statut_badge',
    ]
    list_display_links = ['personne_nom']
    list_filter = [
        'statut', 'date_journee', TypePersonneFilter,
        'session__module__formation',
        'session__module__grade',
        'session__module__groupe',
        'session__module__vague',
        ('session__module', ModuleRelatedFilter),
    ]
    search_fields = [
        'participant__matricule', 'participant__nom', 'participant__prenom',
        'participant__grade', 'participant__groupe', 'participant__vague',
        'formateur__numerobadge', 'formateur__nom', 'formateur__prenom',
        'encadrant__matricule', 'encadrant__first_name', 'encadrant__last_name', 'encadrant__username',
        'session__intitule', 'session__module__intitule', 'session__module__formation__formation',
        'session__module__grade', 'session__module__groupe', 'session__module__vague',
    ]
    date_hierarchy = 'date_journee'
    ordering = ['-date_journee', '-timestamp_entree']
    list_select_related = [
        'participant', 'participant__secretariat',
        'formateur',
        'encadrant',
        'session', 'session__module', 'session__module__formation',
    ]
    autocomplete_fields = ['participant', 'formateur', 'encadrant', 'session']
    list_per_page = 50
    show_full_result_count = False
    actions = ['remettre_selection_en_cours']
    fieldsets = (
        ("Personne", {
            'fields': ('participant', 'formateur', 'encadrant'),
            'description': "Un pointage concerne soit un participant, un formateur ou un encadrant.",
        }),
        ("Séance", {
            'fields': ('session', 'session_contexte', 'date_journee'),
            'description': (
                "Astuce : dans le champ « Session », vous pouvez chercher par formation, "
                "grade (ex. A4), groupe (ex. GROUPE 1) ou vague pour cibler la bonne séance."
            ),
        }),
        ("Horodatage", {
            'fields': ('timestamp_entree', 'timestamp_sortie', 'duree_presence_minutes', 'statut', 'remettre_en_cours_depuis_fiche'),
        }),
        ("Contexte technique", {
            'classes': ('collapse',),
            'fields': ('device_id', 'created_at', 'updated_at'),
        }),
    )
    readonly_fields = [
        'duree_presence_minutes',
        'remettre_en_cours_depuis_fiche',
        'session_contexte',
        'created_at',
        'updated_at',
    ]

    def _audit_cible(self, obj):
        personne = obj.personne
        if obj.participant_id:
            cible_type = 'participant'
            cible_numero = obj.participant.matricule or str(obj.pk)
        elif obj.formateur_id:
            cible_type = 'formateur'
            cible_numero = obj.formateur.numerobadge or str(obj.pk)
        elif obj.encadrant_id:
            cible_type = 'encadrant'
            cible_numero = obj.encadrant.matricule or str(obj.pk)
        else:
            cible_type = ''
            cible_numero = str(obj.pk)
        if personne:
            nom = getattr(personne, 'nom', '') or getattr(personne, 'last_name', '')
            prenom = getattr(personne, 'prenom', '') or getattr(personne, 'first_name', '')
            cible_nom = f"{nom} {prenom}".strip() or str(personne)
        else:
            cible_nom = ''
        return cible_type, cible_numero, cible_nom

    def _sync_duree_et_statut(self, obj):
        """Recalcule la durée et aligne le statut après édition admin des horodatages."""
        if not obj.timestamp_entree:
            return

        if obj.timestamp_sortie is None:
            obj.duree_presence_minutes = None
            if obj.statut not in (Pointage.Statut.FORCE_DFRC,):
                obj.statut = Pointage.Statut.EN_COURS
            return

        obj.calculer_duree()
        duree = float(obj.duree_presence_minutes or 0)
        if duree <= 0:
            if obj.statut not in (
                Pointage.Statut.FORCE_DFRC,
                Pointage.Statut.SORTIE_AUTO,
            ):
                obj.statut = Pointage.Statut.ABSENT_NON_BADGE
            return

        if obj.statut in (
            Pointage.Statut.EN_COURS,
            Pointage.Statut.ABSENT_NON_BADGE,
            Pointage.Statut.HORS_LIGNE_SUSPECT,
        ):
            obj.statut = Pointage.Statut.TERMINE

    def save_model(self, request, obj, form, change):
        horodatages_modifies = (
            not change
            or any(
                champ in getattr(form, 'changed_data', [])
                for champ in ('timestamp_entree', 'timestamp_sortie', 'session')
            )
        )
        if horodatages_modifies or obj.timestamp_sortie:
            self._sync_duree_et_statut(obj)

        super().save_model(request, obj, form, change)
        if change:
            action = AuditLog.Action.FORCE_SORTIE if obj.timestamp_sortie else AuditLog.Action.FORCE_ENTREE
            extra_action = 'edition_fiche'
        else:
            action = AuditLog.Action.FORCE_ENTREE
            extra_action = 'creation_fiche'
        cible_type, cible_numero, cible_nom = self._audit_cible(obj)
        _log_audit(
            action=action,
            request=request,
            cible_type=cible_type,
            cible_numero=cible_numero,
            cible_nom=cible_nom,
            formation=obj.session.module.formation if obj.session_id else None,
            pointage=obj,
            extra={
                'via_admin': True,
                'action': extra_action,
                'champs_modifies': getattr(form, 'changed_data', []) if change else [],
            },
        )

    def _appliquer_remettre_en_cours(self, request, pointage):
        ok, message = pointage_remettre_en_cours_guard(pointage)
        if not ok:
            return False, message

        pointage.timestamp_sortie = None
        pointage.duree_presence_minutes = None
        pointage.statut = Pointage.Statut.EN_COURS
        pointage.save(
            update_fields=['timestamp_sortie', 'duree_presence_minutes', 'statut', 'updated_at']
        )
        cible_type, cible_numero, cible_nom = self._audit_cible(pointage)
        _log_audit(
            action=AuditLog.Action.FORCE_ENTREE,
            request=request,
            cible_type=cible_type,
            cible_numero=cible_numero,
            cible_nom=cible_nom,
            formation=(pointage.session.module.formation if pointage.session_id else None),
            pointage=pointage,
            extra={'via_admin': True, 'action': 'remettre_en_cours'},
        )
        return True, cible_nom

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                '<int:pointage_id>/remettre-en-cours/',
                self.admin_site.admin_view(self.remettre_en_cours_view),
                name='presences_pointage_remettre_en_cours',
            ),
        ]
        return custom_urls + urls

    @admin.display(description="Nom")
    def personne_nom(self, obj):
        personne = obj.personne
        if not personne:
            return "—"
        nom = getattr(personne, 'nom', '')
        prenom = getattr(personne, 'prenom', '')
        return f"{nom} {prenom}".strip() or str(personne)

    @admin.display(description="Identifiant")
    def personne_numero(self, obj):
        if obj.participant_id:
            return obj.participant.matricule or "—"
        if obj.formateur_id:
            return obj.formateur.numerobadge or "—"
        if obj.encadrant_id:
            return obj.encadrant.matricule or "—"
        return "—"

    @admin.display(description="Type")
    def type_personne_display(self, obj):
        if obj.formateur_id:
            return "Formateur"
        if obj.encadrant_id:
            return "Encadrant"
        return "Participant"

    @admin.display(description="Formation", ordering='session__module__formation__formation')
    def formation_label(self, obj):
        # Lot C : les pointages de séance LMD (QR EDT) n'ont pas de session legacy.
        if not obj.session_id:
            return getattr(obj.seance_edt.formation, 'intitule', '—') if obj.seance_edt_id and obj.seance_edt.formation_id else 'Séance LMD (EDT)'
        return obj.session.module.formation

    @admin.display(description="Grade", ordering='session__module__grade')
    def grade_label(self, obj):
        if not obj.session_id:
            return "—"
        return obj.session.module.grade or "—"

    @admin.display(description="Groupe", ordering='session__module__groupe')
    def groupe_label(self, obj):
        if not obj.session_id:
            if obj.seance_edt_id and obj.seance_edt.groupe_id:
                return getattr(obj.seance_edt.groupe, 'nom', '—') or '—'
            return "—"
        return obj.session.module.groupe or "—"

    @admin.display(description="Vague", ordering='session__module__vague')
    def vague_label(self, obj):
        if not obj.session_id:
            return "—"
        return obj.session.module.vague or "—"

    @admin.display(description="Module", ordering='session__module__intitule')
    def module_label(self, obj):
        if not obj.session_id:
            if obj.seance_edt_id:
                return obj.seance_edt.intitule or str(obj.seance_edt.creneau_template)
            return "—"
        url = reverse('admin:formations_module_change', args=[obj.session.module_id])
        return format_html('<a href="{}">{}</a>', url, obj.session.module.intitule)

    @admin.display(description="Séance", ordering='session__intitule')
    def session_label(self, obj):
        if not obj.session_id:
            if obj.seance_edt_id:
                return f"Séance EDT #{obj.seance_edt_id}"
            return "—"
        label = obj.session.intitule or f"Session {obj.session.numero}"
        url = reverse('admin:formations_sessionmodule_change', args=[obj.session_id])
        return format_html('<a href="{}">{}</a>', url, label)

    @admin.display(description="Contexte de la séance")
    def session_contexte(self, obj):
        if not obj or not obj.pk or not obj.session_id:
            return "Sélectionnez une séance puis enregistrez pour voir le contexte (formation, grade, groupe, vague)."
        module = obj.session.module
        formation = module.formation.formation if module.formation_id else "—"
        rows = [
            ("Formation", formation),
            ("Module", module.intitule or "—"),
            ("Grade", module.grade or "—"),
            ("Groupe", module.groupe or "—"),
            ("Vague", module.vague or "—"),
            ("Date séance", obj.session.date_journee),
            ("Séance", obj.session.intitule or f"Session {obj.session.numero}"),
        ]
        html_rows = "".join(
            format_html(
                '<tr><th style="text-align:left;padding:2px 12px 2px 0;color:#555;">{}</th>'
                '<td style="padding:2px 0;">{}</td></tr>',
                libelle, valeur,
            )
            for libelle, valeur in rows
        )
        return format_html('<table style="border-collapse:collapse;">{}</table>', html_rows)

    @admin.display(description="Statut")
    def statut_badge(self, obj):
        colors = {
            Pointage.Statut.EN_COURS: ("#e8eef6", "#09306c"),
            Pointage.Statut.TERMINE: ("#eef6fc", "#0f4c81"),
            Pointage.Statut.FORCE_DFRC: ("#fffae8", "#9a7a00"),
            Pointage.Statut.ABSENT_NON_BADGE: ("#fdecec", "#b42318"),
            Pointage.Statut.HORS_LIGNE_SUSPECT: ("#fce8ff", "#7e22ce"),
            Pointage.Statut.SORTIE_AUTO: ("#fff1f2", "#be123c"),
        }
        bg, fg = colors.get(obj.statut, ("#f3f4f6", "#374151"))
        return format_html(
            '<span style="background:{};color:{};padding:3px 8px;border-radius:999px;font-weight:600;">{}</span>',
            bg, fg, obj.get_statut_display()
        )

    @admin.display(description="Action")
    def remettre_en_cours_action(self, obj):
        if not obj.timestamp_sortie:
            return "—"
        url = reverse('admin:presences_pointage_remettre_en_cours', args=[obj.pk])
        return format_html(
            '<a href="{}" style="font-weight:600;" onclick="return confirm(\'Confirmer la remise en cours de cet étudiant ?\')">Remettre en cours</a>',
            url,
        )

    @admin.display(description="Remise en cours")
    def remettre_en_cours_depuis_fiche(self, obj):
        if not obj or not obj.pk:
            return "Enregistrez d'abord le pointage."
        if not obj.timestamp_sortie:
            return "Ce pointage est deja en cours."
        url = reverse('admin:presences_pointage_remettre_en_cours', args=[obj.pk])
        return format_html(
            '<a class="button" href="{}" onclick="return confirm(\'Confirmer la remise en cours de cet étudiant ?\')">Remettre en cours</a>',
            url,
        )

    @admin.action(description="Remettre en cours les pointages selectionnes")
    def remettre_selection_en_cours(self, request, queryset):
        a_traiter = queryset.filter(timestamp_sortie__isnull=False).select_related(
            'session', 'session__module', 'session__module__formation',
            'participant', 'formateur', 'encadrant',
        )
        count = 0
        skipped = 0
        for pointage in a_traiter:
            ok, message = self._appliquer_remettre_en_cours(request, pointage)
            if ok:
                count += 1
            else:
                skipped += 1
                self.message_user(request, f"{self.personne_nom(pointage)} : {message}", level=messages.WARNING)

        if count == 0 and skipped == 0:
            self.message_user(
                request,
                "Aucun pointage termine selectionne.",
                level=messages.WARNING,
            )
            return

        if count:
            self.message_user(
                request,
                f"{count} pointage(s) remis en cours.",
                level=messages.SUCCESS,
            )

    def remettre_en_cours_view(self, request, pointage_id):
        pointage = self.get_object(request, pointage_id)
        if pointage is None:
            self.message_user(request, "Pointage introuvable.", level=messages.ERROR)
            return HttpResponseRedirect(reverse('admin:presences_pointage_changelist'))

        with transaction.atomic():
            ok, message = self._appliquer_remettre_en_cours(request, pointage)
            if not ok:
                self.message_user(request, message, level=messages.WARNING)
                return HttpResponseRedirect(reverse('admin:presences_pointage_changelist'))
            personne_nom = message

        self.message_user(
            request,
            f"{personne_nom} a été remis(e) en cours.",
            level=messages.SUCCESS,
        )
        return HttpResponseRedirect(reverse('admin:presences_pointage_changelist'))


@admin.register(AuditLog)
class AuditLogAdmin(AdminScopeMixin, admin.ModelAdmin):
    admin_scope_secretariat_field = None

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if admin_user_has_global_access(request.user):
            return qs

        role = getattr(request.user, 'role', None)
        secretariat = getattr(request.user, 'secretariat', None)

        if role == 'ENCADRANT':
            return qs.filter(
                Q(pointage__session__module__superviseur=request.user)
                | Q(formation__modules__superviseur=request.user)
                | Q(acteur=request.user)
            ).distinct()

        if role in ('SECRETARIAT', 'CHEF_SECRETARIAT') and secretariat:
            return qs.filter(
                Q(pointage__session__module__secretariat=secretariat)
                | Q(formation__modules__secretariat=secretariat)
                | Q(acteur=request.user)
            ).distinct()

        return qs.none()
    list_display = [
        'timestamp', 'action', 'acteur_label', 'cible_type',
        'cible_numero', 'cible_nom', 'formation_titre', 'ip_address',
    ]
    list_filter = ['action', 'cible_type', 'formation', 'timestamp']
    search_fields = [
        'acteur_label', 'cible_numero', 'cible_nom',
        'formation_titre', 'ip_address', 'device_id',
        'acteur__username', 'acteur__first_name', 'acteur__last_name',
    ]
    readonly_fields = [
        'timestamp', 'action', 'acteur', 'acteur_label',
        'cible_type', 'cible_numero', 'cible_nom',
        'formation', 'formation_titre', 'pointage',
        'ip_address', 'device_id', 'extra',
    ]
    ordering = ['-timestamp']
    date_hierarchy = 'timestamp'
    list_per_page = 50
    list_select_related = ['acteur', 'formation', 'pointage']

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Rattrapage)
class RattrapageAdmin(AdminScopeMixin, admin.ModelAdmin):
    """Gestion des rattrapages inter-cohorte (auditeur suivant une séance d'une
    autre cohorte pour rattraper un cours manqué)."""

    admin_scope_secretariat_field = 'seance_rattrapage__module__secretariat'
    admin_scope_superviseur_field = 'seance_rattrapage__module__superviseur'

    list_display = [
        'participant_label', 'origine_label', 'accueil_label',
        'seance_rattrapage_label', 'statut_badge', 'presence_label', 'created_at',
    ]
    list_filter = [
        'statut',
        'seance_rattrapage__module__formation',
        'seance_rattrapage__module__grade',
        'seance_rattrapage__module__groupe',
        'seance_rattrapage__date_journee',
    ]
    search_fields = [
        'participant__matricule', 'participant__nom', 'participant__prenom',
        'participant__grade', 'participant__groupe',
        'seance_rattrapage__module__intitule',
        'seance_rattrapage__module__formation__formation',
        'motif',
    ]
    autocomplete_fields = [
        'participant', 'seance_rattrapage', 'module_origine', 'seance_manquee', 'pointage',
    ]
    list_select_related = [
        'participant',
        'seance_rattrapage', 'seance_rattrapage__module', 'seance_rattrapage__module__formation',
        'module_origine', 'module_origine__formation',
        'pointage',
    ]
    ordering = ['-created_at']
    date_hierarchy = 'created_at'
    list_per_page = 50
    readonly_fields = ['cree_par', 'created_at', 'updated_at']
    actions = ['action_generer_presence', 'action_annuler']
    fieldsets = (
        ("Étudiant", {
            'fields': ('participant',),
            'description': (
                "L'étudiant garde son groupe/grade/secrétariat d'origine : "
                "aucune inscription n'est créée sur la cohorte d'accueil."
            ),
        }),
        ("Cours manqué (origine)", {
            'fields': ('module_origine', 'seance_manquee'),
            'description': "Optionnel — pour tracer précisément ce qui est rattrapé.",
        }),
        ("Séance de rattrapage (accueil)", {
            'fields': ('seance_rattrapage',),
            'description': (
                "Séance d'une AUTRE cohorte dispensant le même cours. "
                "Recherchez par formation / grade / groupe / vague."
            ),
        }),
        ("Suivi", {
            'fields': ('statut', 'motif', 'pointage', 'cree_par', 'created_at', 'updated_at'),
        }),
    )

    @admin.display(description="Étudiant", ordering='participant__nom')
    def participant_label(self, obj):
        p = obj.participant
        cohorte = ' / '.join(x for x in (p.grade, p.groupe) if x)
        base = f"{p.nom} {p.prenom}".strip() or p.matricule
        return f"{base} ({cohorte})" if cohorte else base

    @admin.display(description="Origine")
    def origine_label(self, obj):
        if not obj.module_origine_id:
            return "—"
        m = obj.module_origine
        return ' / '.join(x for x in (m.grade, m.groupe, m.vague) if x) or m.intitule

    @admin.display(description="Accueil")
    def accueil_label(self, obj):
        m = obj.module_rattrapage
        if not m:
            return "—"
        return ' / '.join(x for x in (m.grade, m.groupe, m.vague) if x) or m.intitule

    @admin.display(description="Séance rattrapage", ordering='seance_rattrapage__date_journee')
    def seance_rattrapage_label(self, obj):
        s = obj.seance_rattrapage
        url = reverse('admin:formations_sessionmodule_change', args=[s.pk])
        label = s.intitule or f"Séance {s.numero}"
        return format_html('<a href="{}">{} — {}</a>', url, s.date_journee, label)

    @admin.display(description="Présence")
    def presence_label(self, obj):
        if not obj.pointage_id:
            return "—"
        url = reverse('admin:presences_pointage_change', args=[obj.pointage_id])
        return format_html('<a href="{}">Voir le pointage</a>', url)

    @admin.display(description="Statut")
    def statut_badge(self, obj):
        colors = {
            Rattrapage.Statut.PLANIFIE: ("#fffae8", "#9a7a00"),
            Rattrapage.Statut.EFFECTUE: ("#e8eef6", "#09306c"),
            Rattrapage.Statut.ANNULE: ("#fdecec", "#b42318"),
        }
        bg, fg = colors.get(obj.statut, ("#f3f4f6", "#374151"))
        return format_html(
            '<span style="background:{};color:{};padding:3px 8px;border-radius:999px;font-weight:600;">{}</span>',
            bg, fg, obj.get_statut_display(),
        )

    def save_model(self, request, obj, form, change):
        is_new = not change
        if is_new and obj.cree_par_id is None:
            obj.cree_par = request.user
        super().save_model(request, obj, form, change)
        if is_new:
            module = obj.module_rattrapage
            _log_audit(
                action=AuditLog.Action.RATTRAPAGE_CREATE,
                request=request,
                cible_type='participant',
                cible_numero=obj.participant.matricule or str(obj.participant.pk),
                cible_nom=f"{obj.participant.nom} {obj.participant.prenom}".strip(),
                formation=module.formation if module else None,
                extra={
                    'rattrapage_id': obj.pk,
                    'seance_rattrapage_id': obj.seance_rattrapage_id,
                    'module_origine_id': obj.module_origine_id,
                    'via_admin': True,
                },
            )

    @admin.action(description="Générer / forcer la présence (rattrapage)")
    def action_generer_presence(self, request, queryset):
        ok = 0
        for rattrapage in queryset.exclude(statut=Rattrapage.Statut.ANNULE).select_related(
            'participant', 'seance_rattrapage', 'seance_rattrapage__module',
            'seance_rattrapage__module__formation',
        ):
            try:
                generer_presence_rattrapage(rattrapage, request=request)
                ok += 1
            except RattrapageError as exc:
                self.message_user(
                    request,
                    f"{self.participant_label(rattrapage)} : {exc}",
                    level=messages.WARNING,
                )
        if ok:
            self.message_user(
                request, f"{ok} présence(s) de rattrapage générée(s).", level=messages.SUCCESS,
            )
        elif queryset:
            self.message_user(request, "Aucune présence générée.", level=messages.WARNING)

    @admin.action(description="Annuler les rattrapages sélectionnés")
    def action_annuler(self, request, queryset):
        count = 0
        for rattrapage in queryset.exclude(statut=Rattrapage.Statut.ANNULE):
            annuler_rattrapage(rattrapage, request=request)
            count += 1
        self.message_user(
            request,
            f"{count} rattrapage(s) annulé(s)." if count else "Aucun rattrapage à annuler.",
            level=messages.SUCCESS if count else messages.WARNING,
        )


@admin.register(DeviceBinding)
class DeviceBindingAdmin(admin.ModelAdmin):
    list_display = [
        'user', 'device_id_court', 'device_info', 'is_active', 'bound_at',
    ]
    list_filter = ['is_active', 'bound_at']
    search_fields = [
        'user__username', 'user__first_name', 'user__last_name',
        'user__matricule', 'device_id', 'device_info',
    ]
    autocomplete_fields = ['user']
    list_select_related = ['user']
    ordering = ['-bound_at']
    list_per_page = 50
    date_hierarchy = 'bound_at'
    readonly_fields = ['bound_at']
    actions = ['desactiver_liaisons', 'reactiver_liaisons']

    @admin.display(description='Identifiant appareil', ordering='device_id')
    def device_id_court(self, obj):
        if not obj.device_id:
            return '—'
        return obj.device_id if len(obj.device_id) <= 24 else f"{obj.device_id[:24]}…"

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if admin_user_has_global_access(request.user):
            return qs

        role = getattr(request.user, 'role', None)
        secretariat = getattr(request.user, 'secretariat', None)
        if role in ('SECRETARIAT', 'CHEF_SECRETARIAT') and secretariat:
            return qs.filter(user__secretariat=secretariat)
        return qs.none()

    @admin.action(description='Désactiver les liaisons sélectionnées')
    def desactiver_liaisons(self, request, queryset):
        updated = 0
        for binding in queryset.select_related('user'):
            if not binding.is_active:
                continue
            binding.is_active = False
            binding.save(update_fields=['is_active'])
            log_admin_audit(
                AuditLog.Action.DEVICE_UNBIND,
                request,
                cible_type='user',
                cible_numero=binding.user.username,
                cible_nom=binding.user.get_full_name() or binding.user.username,
                extra={'device_id': binding.device_id, 'action': 'desactiver_admin'},
            )
            updated += 1
        if updated == 0:
            self.message_user(request, "Aucune liaison active selectionnee.", level=messages.WARNING)
            return
        self.message_user(
            request,
            f"{updated} liaison(s) desactivee(s).",
            level=messages.SUCCESS,
        )

    @admin.action(description='Réactiver les liaisons sélectionnées')
    def reactiver_liaisons(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(
            request,
            f"{updated} liaison(s) réactivée(s).",
            level=messages.SUCCESS,
        )
