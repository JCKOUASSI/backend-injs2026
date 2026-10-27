"""Action admin : badgeage forcé de plusieurs auditeurs (rattrapage)."""
from collections import defaultdict

from django import forms
from django.contrib import admin, messages
from django.db.models import Count, Q
from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.urls import path, reverse
from django.utils.formats import date_format
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from formations.models import Module, ModuleParticipant, Participant, SessionModule
from presences.bulk_force_auditeurs import run_rattrapage_badgeage
from presences.models import Pointage


def module_rattrapage_label(module):
    """Libellé module lisible dans les listes admin."""
    parts = []
    if module.formation_id:
        parts.append(str(module.formation))
    if module.intitule:
        parts.append(module.intitule)
    ctx = ' / '.join(p for p in (module.grade, module.groupe, module.vague) if p)
    if ctx:
        parts.append(f'[{ctx}]')
    return ' — '.join(parts) if parts else str(module)


def format_session_horaires(session):
    debut = session.heure_debut_prevue
    fin = session.heure_fin_prevue
    if debut and fin:
        return f'{debut.strftime("%H:%M")}–{fin.strftime("%H:%M")}'
    if debut:
        return f'dès {debut.strftime("%H:%M")}'
    if fin:
        return f'jusqu’à {fin.strftime("%H:%M")}'
    return '—'


def session_statut_label(session):
    if session.demarree_le and not session.terminee_le:
        return _('En cours')
    if session.terminee_le:
        return _('Terminée')
    if session.demarree_le:
        return _('Démarrée')
    return _('Planifiée')


def _groupe_match_variants(groupe):
    """Variantes de libellé groupe pour rapprocher module et participant."""
    if not groupe:
        return []
    raw = str(groupe).strip()
    upper = raw.upper()
    variants = {raw, upper}
    if upper.startswith('GROUPE '):
        num = upper.replace('GROUPE ', '').strip()
        variants.update({num, f'GROUPE {num}'})
    elif upper.isdigit():
        variants.update({upper, f'GROUPE {upper}'})
    return [v for v in variants if v]


def resolve_expected_participants(module):
    """
    Auditeurs attendus sur le module.
    1. Inscriptions ModuleParticipant (source fiable)
    2. Filtre strict Participant : tous les critères renseignés sur le module
       (groupe, grade, vague) doivent correspondre
    3. Déjà badgés sur une séance du module
    Retourne (queryset, source, hint).
    """
    qs = module_participants_qs(module)
    if qs.exists():
        return qs, 'inscriptions', ''

    filt = Participant.objects.all()
    applied = []

    if module.groupe:
        q_groupe = Q()
        for variant in _groupe_match_variants(module.groupe):
            q_groupe |= Q(groupe__iexact=variant)
        filt = filt.filter(q_groupe)
        applied.append(f'groupe={module.groupe}')

    if module.grade:
        filt = filt.filter(grade__iexact=module.grade.strip())
        applied.append(f'grade={module.grade}')

    if module.vague:
        filt = filt.filter(vague__iexact=module.vague.strip())
        applied.append(f'vague={module.vague}')

    if applied and filt.exists():
        return (
            filt.distinct().order_by('nom', 'prenom'),
            'classification',
            _('Correspondance %(fields)s — sans inscription explicite au module.') % {
                'fields': ', '.join(applied),
            },
        )

    pt_ids = Pointage.objects.filter(
        session__module=module,
        participant__isnull=False,
    ).values_list('participant_id', flat=True).distinct()
    if pt_ids:
        return (
            Participant.objects.filter(pk__in=pt_ids).order_by('nom', 'prenom'),
            'pointages',
            _("Auditeurs repérés via d'anciens badgeages sur ce module."),
        )

    nb_insc = ModuleParticipant.objects.filter(module=module).count()
    if applied:
        hint = _(
            'Aucun auditeur ne correspond au module #%(id)s « %(intitule)s » '
            'avec les critères %(fields)s (inscriptions module : %(nb)s). '
            'Le groupe « %(groupe)s » semble sans auditeurs inscrits — '
            'ajoutez-les via Admin → Modules → onglet auditeurs, '
            'ou vérifiez l\'import Excel des inscriptions.'
        ) % {
            'id': module.id,
            'intitule': module.intitule or '—',
            'fields': ', '.join(applied),
            'groupe': module.groupe or '—',
            'nb': nb_insc,
        }
    else:
        hint = _(
            'Aucun auditeur attendu pour le module #%(id)s « %(intitule)s » '
            '(%(groupe)s / %(grade)s / %(vague)s). '
            'Inscriptions module (ModuleParticipant) : %(nb)s. '
            'Ajoutez les auditeurs via Admin → Modules → onglet auditeurs.'
        ) % {
            'id': module.id,
            'intitule': module.intitule or '—',
            'groupe': module.groupe or '—',
            'grade': module.grade or '—',
            'vague': module.vague or '—',
            'nb': nb_insc,
        }
    return Participant.objects.none(), 'none', hint


def module_participants_qs(module):
    """Auditeurs inscrits au module (QuerySet)."""
    return (
        Participant.objects.filter(modules_inscrits__module=module)
        .distinct()
        .order_by('nom', 'prenom')
    )


def build_module_participants(module):
    """Auditeurs attendus sur le module (liste matérialisée)."""
    return list(resolve_expected_participants(module)[0])


def _participant_attendance_dict(participant, *, in_selection=False, pointage=None):
    row = {
        'id': participant.id,
        'matricule': participant.matricule or '—',
        'nom': f'{participant.nom} {participant.prenom}'.strip(),
        'in_selection': in_selection,
    }
    if pointage:
        row['entree'] = (
            date_format(timezone.localtime(pointage.timestamp_entree), 'SHORT_DATETIME_FORMAT')
            if pointage.timestamp_entree else '—'
        )
        row['sortie'] = (
            date_format(timezone.localtime(pointage.timestamp_sortie), 'SHORT_DATETIME_FORMAT')
            if pointage.timestamp_sortie else '—'
        )
        row['statut'] = pointage.get_statut_display() if hasattr(pointage, 'get_statut_display') else pointage.statut
    return row


def build_session_rows(sessions, participant_ids, module_participants=None):
    """Prépare les lignes du tableau de sélection avec présents / absents."""
    session_ids = [s.id for s in sessions]
    selected_ids = set(participant_ids)
    module_participants = module_participants or []

    pointages_qs = Pointage.objects.filter(
        session_id__in=session_ids,
        participant_id__isnull=False,
    ).select_related('participant')
    present_by_session = defaultdict(dict)
    for pt in pointages_qs:
        present_by_session[pt.session_id][pt.participant_id] = pt

    rows = []
    for session in sessions:
        intitule = session.intitule or _('Séance %(num)s') % {'num': session.numero}
        present_map = present_by_session.get(session.id, {})
        present = []
        absent = []
        for participant in module_participants:
            in_selection = participant.id in selected_ids
            pt = present_map.get(participant.id)
            row = _participant_attendance_dict(
                participant,
                in_selection=in_selection,
                pointage=pt,
            )
            row['pre_checked'] = (in_selection or not selected_ids) and not pt
            if pt:
                present.append(row)
            else:
                absent.append(row)

        nb_selection_present = sum(1 for p in present if p['in_selection'])
        rows.append({
            'session': session,
            'session_id': session.id,
            'date_display': date_format(session.date_journee, 'DATE_FORMAT'),
            'date_iso': session.date_journee.isoformat(),
            'numero': session.numero,
            'intitule': intitule,
            'horaires': format_session_horaires(session),
            'statut': session_statut_label(session),
            'statut_key': (
                'terminee' if session.terminee_le
                else 'en_cours' if session.demarree_le
                else 'planifiee'
            ),
            'nb_total_badges': getattr(session, 'nb_pointages', 0) or 0,
            'nb_selection_badges': nb_selection_present,
            'nb_present': len(present),
            'nb_absent': len(absent),
            'nb_module_total': len(module_participants),
            'present': present,
            'absent': absent,
            'search_text': ' '.join(
                str(x).lower()
                for x in (
                    session.date_journee,
                    date_format(session.date_journee, 'DATE_FORMAT'),
                    session.numero,
                    intitule,
                    format_session_horaires(session),
                    session_statut_label(session),
                )
            ),
        })
    return rows


def resolve_modules_for_participants(participant_ids):
    if participant_ids:
        modules_qs = (
            Module.objects.filter(module_participants__participant_id__in=participant_ids)
            .distinct()
            .select_related('formation')
            .order_by('formation__formation', 'intitule')
        )
        if modules_qs.exists():
            return modules_qs
    return Module.objects.select_related('formation').order_by(
        'formation__formation', 'intitule',
    )


def resolve_selected_module(request, modules_qs):
    module_id = request.GET.get('module') or request.POST.get('module')
    if module_id:
        try:
            return modules_qs.filter(pk=int(module_id)).first() or Module.objects.select_related(
                'formation',
            ).filter(pk=int(module_id)).first()
        except (ValueError, TypeError):
            pass
    if modules_qs.count() == 1:
        return modules_qs.first()
    return None


def resolve_preset_session_id(request):
    raw = request.GET.get('session') or request.POST.get('preset_session') or ''
    try:
        return int(raw) if raw else None
    except (ValueError, TypeError):
        return None


def sessions_for_rattrapage(module, *, date_journee=None, statut=None):
    qs = (
        SessionModule.objects.filter(module=module)
        .select_related('module', 'module__formation')
        .annotate(nb_pointages=Count('pointages', distinct=True))
        .order_by('-date_journee', 'numero')
    )
    if date_journee:
        qs = qs.filter(date_journee=date_journee)
    if statut == 'terminee':
        qs = qs.filter(terminee_le__isnull=False)
    elif statut == 'en_cours':
        qs = qs.filter(demarree_le__isnull=False, terminee_le__isnull=True)
    elif statut == 'planifiee':
        qs = qs.filter(demarree_le__isnull=True)
    return qs


class RattrapageBadgeageForm(forms.Form):
    module = forms.ModelChoiceField(
        label=_('Module'),
        queryset=Module.objects.none(),
        required=True,
        widget=forms.HiddenInput,
    )
    session = forms.ModelChoiceField(
        label=_('Séance'),
        queryset=SessionModule.objects.none(),
        required=True,
        error_messages={'required': _('Sélectionnez une séance.')},
    )
    badge_participants = forms.ModelMultipleChoiceField(
        label=_('Auditeurs à badger'),
        queryset=Participant.objects.none(),
        required=False,
        widget=forms.MultipleHiddenInput,
    )
    motif = forms.CharField(
        label=_('Motif'),
        initial='Rattrapage admin — erreur badgeage',
        max_length=500,
        widget=forms.Textarea(attrs={'rows': 2}),
    )
    with_sortie = forms.BooleanField(
        label=_('Enregistrer aussi la sortie'),
        initial=True,
        required=False,
    )
    skip_existing = forms.BooleanField(
        label=_('Ignorer les auditeurs déjà badgés sur cette séance'),
        initial=True,
        required=False,
    )
    ignore_constraints = forms.BooleanField(
        label=_('Ignorer les contraintes de chevauchement'),
        initial=True,
        required=False,
        help_text=_('Recommandé pour le rattrapage après migration ou perte de données.'),
    )

    def __init__(self, *args, module=None, participant_ids=None, **kwargs):
        super().__init__(*args, **kwargs)
        participant_ids = participant_ids or []
        if module:
            self.fields['module'].queryset = Module.objects.filter(pk=module.pk)
            self.fields['module'].initial = module.pk
            self.fields['session'].queryset = sessions_for_rattrapage(module)
            self.fields['session'].label_from_instance = self._session_label
            self.fields['badge_participants'].queryset = resolve_expected_participants(module)[0]

    def clean(self):
        cleaned = super().clean()
        module = cleaned.get('module')
        session = cleaned.get('session')
        if module and session and session.module_id != module.id:
            self.add_error('session', _('Cette séance n’appartient pas au module sélectionné.'))

        badge_participants = cleaned.get('badge_participants') or []
        if session and not badge_participants:
            raw_ids = self.data.getlist('badge_participants')
            if not raw_ids:
                self.add_error(
                    'badge_participants',
                    _('Cochez au moins un auditeur absent à badger.'),
                )
        return cleaned

    @staticmethod
    def _session_label(session):
        intitule = session.intitule or f'Séance {session.numero}'
        return (
            f'{date_format(session.date_journee, "DATE_FORMAT")} '
            f'#{session.numero} {intitule} — {format_session_horaires(session)} '
            f'({session_statut_label(session)})'
        )


class AdminRattrapageBadgeageMixin:
    """Mixin admin : sélection multiple → formulaire → badgeage forcé."""

    rattrapage_participant_id_field = 'pk'

    def get_urls(self):
        urls = super().get_urls()
        info = self.model._meta.app_label, self.model._meta.model_name
        custom = [
            path(
                'rattrapage-badgeage/',
                self.admin_site.admin_view(self.rattrapage_badgeage_view),
                name=f'{info[0]}_{info[1]}_rattrapage_badgeage',
            ),
        ]
        return custom + urls

    def _rattrapage_badgeage_url(self):
        return reverse(
            f'admin:{self.model._meta.app_label}_{self.model._meta.model_name}_rattrapage_badgeage',
        )

    @admin.action(description=_('Forcer badgeage (rattrapage)'))
    def forcer_badgeage_rattrapage(self, request, queryset):
        field = self.rattrapage_participant_id_field
        ids = list(queryset.values_list(field, flat=True).distinct())
        url = self._rattrapage_badgeage_url()
        params = []
        if ids:
            params.append(f'ids={",".join(str(i) for i in ids)}')
        module_ids = list(queryset.values_list('module_id', flat=True).distinct()) if hasattr(
            queryset.model, 'module_id',
        ) else []
        if len(module_ids) == 1:
            params.append(f'module={module_ids[0]}')
        if not params:
            self.message_user(
                request,
                _('Sélectionnez des auditeurs ou ouvrez depuis une séance.'),
                level=messages.WARNING,
            )
            return None
        return HttpResponseRedirect(f'{url}?{"&".join(params)}')

    def rattrapage_badgeage_view(self, request):
        ids_raw = request.GET.get('ids') or request.POST.get('participant_ids') or ''
        try:
            participant_ids = [int(x) for x in ids_raw.split(',') if x.strip()]
        except ValueError:
            participant_ids = []

        participants = []
        if participant_ids:
            participants = list(
                Participant.objects.filter(pk__in=participant_ids).order_by('nom', 'prenom'),
            )

        inscriptions = (
            ModuleParticipant.objects.filter(participant_id__in=participant_ids)
            .select_related('module', 'module__formation', 'participant')
            .order_by('module__formation__formation', 'module__intitule', 'participant__nom')
        ) if participant_ids else []

        modules_qs = resolve_modules_for_participants(participant_ids)
        module = resolve_selected_module(request, modules_qs)
        preset_session_id = resolve_preset_session_id(request)

        filter_date = request.GET.get('date_journee') or request.POST.get('filter_date') or ''
        filter_statut = request.GET.get('statut') or request.POST.get('filter_statut') or ''

        session_rows = []
        available_dates = []
        participants_source = ''
        participants_hint = ''
        module_choices = [
            {'id': m.pk, 'label': module_rattrapage_label(m), 'selected': module and m.pk == module.pk}
            for m in modules_qs
        ]

        if module:
            available_dates = list(
                SessionModule.objects.filter(module=module)
                .values_list('date_journee', flat=True)
                .distinct()
                .order_by('-date_journee'),
            )
            parsed_date = None
            if filter_date:
                try:
                    from datetime import date
                    parsed_date = date.fromisoformat(filter_date)
                except ValueError:
                    parsed_date = None

            sessions_qs = sessions_for_rattrapage(
                module,
                date_journee=parsed_date,
                statut=filter_statut or None,
            )
            module_participants_qs_resolved, participants_source, participants_hint = (
                resolve_expected_participants(module)
            )
            module_participants = list(module_participants_qs_resolved)
            session_rows = build_session_rows(
                list(sessions_qs),
                participant_ids,
                module_participants=module_participants,
            )

        form = None
        if request.method == 'POST' and module:
            form = RattrapageBadgeageForm(
                request.POST,
                module=module,
                participant_ids=participant_ids,
            )
            if form.is_valid():
                session = form.cleaned_data['session']
                to_badge = list(form.cleaned_data['badge_participants'])
                if not to_badge:
                    to_badge = participants
                counts = run_rattrapage_badgeage(
                    to_badge,
                    session,
                    motif=form.cleaned_data['motif'],
                    request=request,
                    with_sortie=form.cleaned_data['with_sortie'],
                    skip_existing=form.cleaned_data['skip_existing'],
                    ignore_constraints=form.cleaned_data['ignore_constraints'],
                )
                msg_parts = [
                    _('%(n)s entrée(s) créée(s).') % {'n': counts['created']},
                ]
                if counts['sorties']:
                    msg_parts.append(_('%(n)s sortie(s).') % {'n': counts['sorties']})
                if counts['skipped']:
                    msg_parts.append(_('%(n)s ignoré(s) (déjà badgés).') % {'n': counts['skipped']})
                level = messages.SUCCESS if counts['created'] else messages.WARNING
                self.message_user(request, ' '.join(msg_parts), level=level)
                for err in counts['errors']:
                    self.message_user(
                        request,
                        _('%(matricule)s — %(detail)s') % err,
                        level=messages.ERROR,
                    )
                changelist_url = reverse(
                    f'admin:{self.model._meta.app_label}_{self.model._meta.model_name}_changelist',
                )
                return HttpResponseRedirect(changelist_url)
        elif module:
            form = RattrapageBadgeageForm(module=module, participant_ids=participant_ids)
            if preset_session_id:
                form.fields['session'].initial = preset_session_id

        context = {
            **self.admin_site.each_context(request),
            'title': _('Rattrapage badgeage'),
            'form': form,
            'participants': participants,
            'inscriptions': inscriptions,
            'participant_ids': ','.join(str(p.pk) for p in participants),
            'opts': self.model._meta,
            'media': form.media if form else None,
            'module': module,
            'module_choices': module_choices,
            'session_rows': session_rows,
            'available_dates': available_dates,
            'filter_date': filter_date,
            'filter_statut': filter_statut,
            'nb_participants': len(participants),
            'preset_session_id': preset_session_id,
            'participants_source': participants_source,
            'participants_hint': participants_hint,
            'module_admin_url': (
                reverse('admin:formations_module_change', args=[module.pk]) if module else ''
            ),
            'rattrapage_url': self._rattrapage_badgeage_url(),
        }
        return render(request, 'admin/presences/rattrapage_badgeage.html', context)
