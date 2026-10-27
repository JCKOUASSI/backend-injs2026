"""
Diagnostic du volume horaire planifié Finance (dashboard).

Reproduit la règle Finance ``_finance_module_planned_minutes`` (Σ créneaux EDT période)
séance par séance, pour expliquer les totaux affichés dans
« Volume horaire planifié par module ».

Usage :
  python manage.py diag_finance_planifie --intitule "Finances Publiques" --groupe "GROUPE 6"
  python manage.py diag_finance_planifie --module-id 2103 --preset trimestre --trimestre 2026-Q1
  python manage.py diag_finance_planifie --intitule "Finances Publiques" --top 10
"""

import calendar
from datetime import date, datetime

from django.core.management.base import BaseCommand
from django.utils import timezone

from formations.api_views import (
    _finance_module_planned_minutes,
    _finance_session_in_range,
    _finance_session_slot_minutes,
)
from formations.models import Module, SessionModule


def _resolve_period(options):
    """Même logique que le filtre période Finance (dashboard)."""
    preset = (options.get('preset') or 'tout').strip().lower()
    today = timezone.localdate()

    if preset == 'tout':
        return {
            'date_debut': None,
            'date_fin': None,
            'meta': {'label': 'Toutes les périodes'},
        }

    if preset == 'mois':
        mois = (options.get('mois') or today.strftime('%Y-%m')).strip()
        year, month = map(int, mois.split('-'))
        last_day = calendar.monthrange(year, month)[1]
        d0, d1 = date(year, month, 1), date(year, month, last_day)
        return {
            'date_debut': d0,
            'date_fin': d1,
            'meta': {'label': f'Mois de {d0.strftime("%m/%Y")}'},
        }

    if preset == 'trimestre':
        trimestre = (options.get('trimestre') or '').strip()
        if trimestre and '-Q' in trimestre.upper():
            year_s, q_s = trimestre.upper().split('-Q', 1)
            year, q = int(year_s), int(q_s)
        else:
            year = int(options.get('annee') or today.year)
            q = (today.month - 1) // 3 + 1
        start_month = (q - 1) * 3 + 1
        end_month = start_month + 2
        last_day = calendar.monthrange(year, end_month)[1]
        d0 = date(year, start_month, 1)
        d1 = date(year, end_month, last_day)
        return {
            'date_debut': d0,
            'date_fin': d1,
            'meta': {'label': f'Trimestre {q} — {year}'},
        }

    if preset == 'annee':
        year = int(options.get('annee') or today.year)
        return {
            'date_debut': date(year, 1, 1),
            'date_fin': date(year, 12, 31),
            'meta': {'label': f'Année {year}'},
        }

    if preset == 'custom':
        d0 = date.fromisoformat(options['date_debut'])
        d1 = date.fromisoformat(options['date_fin'])
        return {
            'date_debut': d0,
            'date_fin': d1,
            'meta': {'label': f'{d0} → {d1}'},
        }

    raise ValueError(f'Preset inconnu : {preset}')


def _edt_minutes(session):
    if not session.heure_debut_prevue or not session.heure_fin_prevue:
        return 0.0
    start = datetime.combine(session.date_journee, session.heure_debut_prevue)
    end = datetime.combine(session.date_journee, session.heure_fin_prevue)
    return max((end - start).total_seconds() / 60, 0.0)


def _real_minutes(session):
    if not session.demarree_le or not session.terminee_le:
        return 0.0
    return max((session.terminee_le - session.demarree_le).total_seconds() / 60, 0.0)


def _session_status(session):
    if session.demarree_le and session.terminee_le:
        return 'TERM'
    if session.demarree_le:
        return 'EN_COURS'
    return 'PLAN'


def _fmt_h(minutes):
    total = int(round(minutes))
    h, m = divmod(total, 60)
    return f'{h}h {m}min' if m else f'{h}h'


class Command(BaseCommand):
    help = 'Diagnostic séance par séance du planifié Finance (dashboard).'

    def add_arguments(self, parser):
        parser.add_argument('--module-id', type=int, default=None)
        parser.add_argument('--intitule', type=str, default=None)
        parser.add_argument('--groupe', type=str, default=None)
        parser.add_argument('--secretariat', type=str, default=None, help='Nom ou numéro secrétariat')
        parser.add_argument('--top', type=int, default=None, help='Top N modules par planifié sur la période')
        parser.add_argument('--preset', type=str, default='tout')
        parser.add_argument('--trimestre', type=str, default=None, help='ex. 2026-Q1')
        parser.add_argument('--mois', type=str, default=None, help='ex. 2026-03')
        parser.add_argument('--annee', type=int, default=None)
        parser.add_argument('--date-debut', type=str, default=None, help='YYYY-MM-DD')
        parser.add_argument('--date-fin', type=str, default=None, help='YYYY-MM-DD')

    def handle(self, *args, **options):
        try:
            period = _resolve_period(options)
        except ValueError as exc:
            self.stderr.write(self.style.ERROR(str(exc)))
            return

        date_debut = period['date_debut']
        date_fin = period['date_fin']
        label = period['meta'].get('label') or 'Période'
        self.stdout.write(self.style.MIGRATE_HEADING(f'Période : {label}'))
        if date_debut and date_fin:
            self.stdout.write(f'  Intervalle : {date_debut} → {date_fin}')
        self.stdout.write('')

        modules_qs = Module.objects.select_related('formation', 'secretariat').order_by('intitule', 'groupe')
        if options['module_id']:
            modules_qs = modules_qs.filter(id=options['module_id'])
        if options['intitule']:
            modules_qs = modules_qs.filter(intitule__icontains=options['intitule'])
        if options['groupe']:
            modules_qs = modules_qs.filter(groupe__iexact=options['groupe'])
        if options['secretariat']:
            from django.db.models import Q
            sec = options['secretariat'].strip()
            modules_qs = modules_qs.filter(
                Q(secretariat__nom__icontains=sec) | Q(secretariat__numero__icontains=sec)
            )

        modules = list(modules_qs)
        if not modules:
            self.stderr.write(self.style.WARNING('Aucun module trouvé.'))
            return

        ranked = []
        for module in modules:
            sessions = list(
                SessionModule.objects.filter(module=module).order_by('date_journee', 'numero')
            )
            in_period = [
                s for s in sessions
                if _finance_session_in_range(s, date_debut, date_fin)
            ]
            planned = _finance_module_planned_minutes(
                module, sessions, date_debut=date_debut, date_fin=date_fin,
            )
            ranked.append((planned, module, sessions, in_period))

        if options['top']:
            ranked = sorted(ranked, key=lambda x: x[0], reverse=True)[: options['top']]
        else:
            ranked = sorted(ranked, key=lambda x: (x[1].intitule or '', x[1].groupe or ''))

        for planned, module, all_sessions, in_period in ranked:
            if options['top'] and planned <= 0:
                continue
            self._print_module(planned, module, all_sessions, in_period, date_debut, date_fin)

    def _print_module(self, planned, module, all_sessions, in_period, date_debut, date_fin):
        sec = ''
        if module.secretariat_id:
            sec = f'{module.secretariat.nom} ({module.secretariat.numero})'
        formation = module.formation.formation if module.formation_id else '—'
        self.stdout.write(self.style.HTTP_INFO('=' * 78))
        self.stdout.write(
            f'Module #{module.id} | {module.intitule} | {module.grade} | {module.groupe}'
        )
        self.stdout.write(f'  Formation : {formation}')
        self.stdout.write(f'  Secrétariat : {sec}')
        self.stdout.write(f'  duree_prevue_heures (fiche) : {module.duree_prevue_heures or "—"}')
        self.stdout.write(
            f'  Séances dans période : {len(in_period)} / {len(all_sessions)} totales'
        )
        self.stdout.write('')

        if not in_period:
            self.stdout.write(self.style.WARNING('  (aucune séance dans la période)'))
            self.stdout.write('')
            return

        total_edt = 0.0
        total_real = 0.0
        for session in in_period:
            fin_min = _finance_session_slot_minutes(session)
            edt_min = _edt_minutes(session)
            real_min = _real_minutes(session)
            total_edt += edt_min
            total_real += real_min
            status = _session_status(session)
            rule = 'créneau EDT (détail séance)'
            line = (
                f'  S#{session.numero:>2} {session.date_journee} [{status}] '
                f'finance={_fmt_h(fin_min):>10} ({rule})'
            )
            self.stdout.write(line)
            if session.heure_debut_prevue and session.heure_fin_prevue:
                self.stdout.write(
                    f'       EDT {session.heure_debut_prevue} → {session.heure_fin_prevue} '
                    f'= {_fmt_h(edt_min)}'
                )
            if session.demarree_le:
                fin_badge = session.terminee_le.strftime('%d/%m/%Y %H:%M') if session.terminee_le else '(ouvert)'
                self.stdout.write(
                    f'       Badge {session.demarree_le.strftime("%d/%m/%Y %H:%M")} → {fin_badge} '
                    f'= {_fmt_h(real_min)}'
                )
            if status == 'TERM' and edt_min > 0 and real_min > edt_min * 1.5:
                ratio = real_min / edt_min
                self.stdout.write(self.style.ERROR(
                    f'       ⚠ ANOMALIE : durée réelle {ratio:.1f}× le créneau EDT '
                    f'(session probablement laissée ouverte)'
                ))
            elif not session.heure_debut_prevue and not session.heure_fin_prevue:
                self.stdout.write(self.style.WARNING('       ⚠ Pas d\'horaire EDT — comptée 0 min'))

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(
            f'  TOTAL Finance planifié (Σ créneaux EDT période) : {_fmt_h(planned)} '
            f'({planned / 60:.2f} h, arrondi UI ≈ {round(planned / 60)} h)'
        ))
        self.stdout.write(f'  Σ créneaux EDT (période) : {_fmt_h(total_edt)} ({total_edt / 60:.2f} h)')
        self.stdout.write(f'  Σ durée réelle badge     : {_fmt_h(total_real)} ({total_real / 60:.2f} h)')
        if module.duree_prevue_heures:
            self.stdout.write(
                f'  Rappel fiche contractuelle : {module.duree_prevue_heures} h '
                f'(non utilisée directement par Finance)'
            )
        self.stdout.write('')
