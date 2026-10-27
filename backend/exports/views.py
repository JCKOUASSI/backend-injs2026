import io
from datetime import datetime, timedelta

from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from formations.models import Formation, ModuleParticipant, ModuleFormateur, SessionModule, Formateur, Module
FormationParticipant = ModuleParticipant
FormationFormateur = ModuleFormateur
from presences.models import Pointage, AuditLog


def _calculer_duree_export(pointage):
    """
    Durée de présence pour l'export, via la règle commune ``presences.duree``
    (clamp aux heures prévues de la séance ; pointage ouvert → sortie = maintenant).
    Retourne (duree_minutes: float, duree_str, heure_entree: str, heure_sortie: str).
    """
    from presences.duree import pointage_bornes_clampees

    entree, sortie, en_cours = pointage_bornes_clampees(pointage)
    entree = timezone.localtime(entree)
    sortie = timezone.localtime(sortie)

    minutes = max(round((sortie - entree).total_seconds() / 60, 2), 0)

    h = int(minutes // 60)
    m = int(minutes % 60)
    duree_str = f"{h}h{m:02d}" if h > 0 else f"{m} min"

    heure_entree_str = entree.strftime('%H:%M')
    # Si la sortie n'est pas encore enregistrée, afficher explicitement "En cours"
    # plutôt qu'un tiret pour éviter l'ambiguïté dans les exports.
    heure_sortie_str = 'En cours' if en_cours else sortie.strftime('%H:%M')

    return minutes, duree_str, heure_entree_str, heure_sortie_str


# ──────────────────────────────────────────────
# Couleurs branding CI
# ──────────────────────────────────────────────
CI_GREEN_DARK = '#1A68AC'
CI_GREEN = '#2277C1'
CI_ORANGE = '#F5B100'
CI_LIGHT_GREEN = '#E8EFF5'
CI_LIGHT_ORANGE = '#FFF8E0'

# Modèle CPFAE — fiche de paie formateur
CI_PAIE_BLUE = '#DDEBF7'
CI_PAIE_ORANGE = '#FCE7B4'
CI_PAIE_GREEN = '#77BCE7'

_FINANCE_PAIE_HEADER_LEFT = [
    "MINISTERE D'ETAT,",
    "MINISTERE DE LA FONCTION PUBLIQUE ET DE LA MODERNISATION DE L'ADMINISTRATION",
    "DIRECTION GENERALE DE LA FONCTION PUBLIQUE",
    "DIRECTION DE LA FORMATION ET DU RENFORCEMENT DES CAPACITES",
    "CENTRE DE PERFECTIONNEMENT DES FONCTIONNAIRES ET AGENTS DE L'ETAT AMADOU GON COULIBALY",
]
_FINANCE_PAIE_HEADER_RIGHT = [
    "REPUBLIQUE DE COTE D'IVOIRE",
    "Union – Discipline – Travail",
]
_FINANCE_PAIE_NB_NOTE = (
    "NB : Le volume horaire indiqué ne tient pas compte des heures effectuées auprès "
    "des groupes 1 à 9 de la catégorie C qui seront comptabilisées à la fin de la formation."
)
_FINANCE_PAIE_CONTACTS = [
    "Pour toute information complémentaire, veuillez contacter :",
    "KEITA née SERIFOU Aicha Danielle tel 0707478812 / 0505378392",
    "Mme SIHOULOI née DJIKE Valérie tel 0707124247 / 0504422220",
]
_FINANCE_PAIE_PIED_ADRESSE = (
    "MINISTERE D'ETAT, MINISTERE DE LA FONCTION PUBLIQUE ET DE LA MODERNISATION DE L'ADMINISTRATION "
    "– DIRECTION GENERALE DE LA FONCTION PUBLIQUE – DIRECTION DE LA FORMATION ET DU RENFORCEMENT "
    "DES CAPACITES – CENTRE DE PERFECTIONNEMENT DES FONCTIONNAIRES ET AGENTS DE L'ETAT "
    "« AMADOU GON COULIBALY » Bouaké I.BP.V.20. Tel 20 21 34 08 / Abidjan : 10, Avenue ANGOUVANT "
    "– Porte 2078 Croisement des Rues du Commerce et du Grand Marché – 05 B.P.784. Tel : 27.20.25.90.13"
)
_FINANCE_PAIE_GENERIC_TITRES = {
    'FICHE DE PAIE DÉTAILLÉE',
    'ÉTAT FINANCIER FORMATEUR',
    'FICHE DE PAIE GLOBALE — FORMATEURS',
    'FICHE DE PAIE GLOBALE',
}


def _finance_paie_volume_heures(minutes):
    return int(round(float(minutes or 0) / 60))


def _finance_paie_recap_modules(recap_modules):
    """Fiche de paie : garde-fou — modules avec au moins une séance sur la période."""
    from formations.api_views import _finance_recap_par_module

    return [
        m for m in _finance_recap_par_module(recap_modules)
        if int(m.get('sessions_count') or 0) > 0
    ]


def _finance_paie_format_groupe(groupe):
    if not groupe:
        return '-'
    g = str(groupe).strip()
    upper = g.upper()
    if upper.startswith('GROUPE'):
        suffix = g[6:].strip()
        return f'Groupe {suffix}' if suffix else 'Groupe'
    return g


def _finance_paie_formateur_label(fmt):
    nom = (fmt.get('nom') or '').strip().upper()
    prenom = (fmt.get('prenom') or '').strip().upper()
    if nom and prenom:
        return f'{nom} {prenom}'
    return (nom or prenom or '-').strip()


def _finance_paie_build_title(recap_modules, export_opts, periode):
    custom = (export_opts.get('titre_document') or '').strip()
    if custom and custom.upper() not in {t.upper() for t in _FINANCE_PAIE_GENERIC_TITRES}:
        return custom.upper()

    formations = [m.get('formation_intitule') for m in (recap_modules or []) if m.get('formation_intitule')]
    formation = (formations[0] if formations else 'FORMATION').strip().upper()
    if not formation.startswith('FORMATION'):
        formation = f'FORMATION {formation}'

    year = None
    for key in ('date_fin', 'date_debut'):
        val = (periode or {}).get(key)
        if val:
            try:
                year = int(str(val)[:4])
                break
            except (TypeError, ValueError):
                pass
    if not year:
        year = datetime.now().year

    return (
        f"ETAT RECAPITULATIF DES MODULES DISPENSES RELATIF AU PROGRAMME "
        f"DE LA {formation}, SESSION {year}"
    )


def _finance_paie_parse_lines(raw, default_lines):
    """Découpe un texte multiligne ; retombe sur les valeurs par défaut si vide."""
    if raw and str(raw).strip():
        lines = [ln.strip() for ln in str(raw).splitlines() if ln.strip()]
        if lines:
            return lines
    return list(default_lines)


def _finance_paie_contacts(export_opts):
    contacts = export_opts.get('contacts')
    if contacts:
        return contacts
    return list(_FINANCE_PAIE_CONTACTS)


def _finance_paie_nb_note(export_opts):
    return (export_opts.get('mention_legale') or '').strip() or _FINANCE_PAIE_NB_NOTE


def _finance_paie_pied_titre(export_opts):
    titre = (export_opts.get('pied_page_titre') or '').strip()
    return titre or 'DOCUMENT CONFIDENTIEL'


def _finance_paie_pied_texte(export_opts):
    for key in ('pied_page_texte', 'adresse'):
        raw = (export_opts.get(key) or '').strip()
        if raw:
            return raw
    return _FINANCE_PAIE_PIED_ADRESSE


def _finance_paie_pied_de_page(export_opts):
    """Pied de page officiel : mention confidentielle + coordonnées CPFAE."""
    return _finance_paie_pied_titre(export_opts), _finance_paie_pied_texte(export_opts)


def _check_finance_export_access(request):
    user = request.user
    return bool(user and user.is_authenticated and user.role in ('FINANCE', 'DIRECTION', 'ARCHIVE'))


def _session_realized_minutes_for_formateur(formateur_id, session, now=None):
    from presences.duree import pointage_minutes_clampees

    now = now or timezone.now()
    total = 0.0
    qset = Pointage.objects.filter(
        formateur_id=formateur_id,
        session_id=session.id,
    ).select_related('session').only(
        'duree_presence_minutes', 'timestamp_entree', 'timestamp_sortie',
        'session__heure_debut_prevue', 'session__heure_fin_prevue',
    )
    for pt in qset:
        if pt.duree_presence_minutes is not None:
            total += float(pt.duree_presence_minutes)
        else:
            # Règle commune SYGEP : durée clampée au créneau de la séance.
            total += pointage_minutes_clampees(pt, now=now)
    return round(total, 1)


def _finance_formateur_summary_rows(formateur, request=None):
    """Lignes détail + totaux pour export fiche de paie (aligné sur le rapport finance API)."""
    from formations.duration_format import format_duration_minutes, minutes_to_hours_minutes
    from formations.period_filter import parse_period_from_request, periode_api_payload
    from formations.api_views import (
        _finance_secretariat_id_from_request,
        _finance_report_rows,
    )

    period = parse_period_from_request(request) if request else {
        'error': False, 'date_debut': None, 'date_fin': None, 'meta': {'preset': 'tout'},
    }
    if period.get('error'):
        period = {'error': False, 'date_debut': None, 'date_fin': None, 'meta': {'preset': 'tout'}}
    secretariat_id = _finance_secretariat_id_from_request(request) if request else None
    global_agg = {'activite_par_mois': {}, 'activite_montant_par_mois': {}, 'date_min': None, 'date_max': None}
    results = _finance_report_rows(
        [formateur],
        include_sessions=True,
        date_debut=period['date_debut'],
        date_fin=period['date_fin'],
        global_aggregates=global_agg,
        secretariat_id=secretariat_id,
    )
    finance_row = results[0] if results else {}
    sessions = finance_row.get('sessions') or []

    def _fmt_date(val):
        if not val:
            return '-'
        if hasattr(val, 'strftime'):
            return val.strftime('%d/%m/%Y')
        try:
            from datetime import date as date_cls
            return date_cls.fromisoformat(str(val)[:10]).strftime('%d/%m/%Y')
        except (ValueError, TypeError):
            return str(val)

    rows = []
    session_rows_by_key = {}
    for s in sessions:
        realized = float(s.get('duree_realisee_minutes') or 0)
        sess_row = {
            'date': _fmt_date(s.get('date_journee')),
            'session': s.get('intitule') or f"Séance {s.get('numero', '')}",
            'module': s.get('module_intitule') or s.get('module_intitule_brut') or '-',
            'formation': s.get('formation_intitule') or '-',
            'grade': s.get('grade') or '-',
            'groupe': s.get('groupe') or '-',
            'secretariat': '-',
            'duree_seance': float(s.get('duree_minutes') or 0),
            'temps_realise': realized,
            'heures_planifiees': minutes_to_hours_minutes(s.get('duree_minutes'))[0],
            'heures_realisees': minutes_to_hours_minutes(realized)[0],
            'duree_planifiee_label': format_duration_minutes(s.get('duree_minutes')),
            'duree_realisee_label': format_duration_minutes(realized),
            'montant': float(s.get('montant_realise') or 0),
            'prix_heure': s.get('prix_heure_realisee'),
        }
        rows.append(sess_row)
        session_rows_by_key[(s.get('date_journee'), s.get('numero'), s.get('session_id'))] = sess_row

    stats = finance_row.get('statistiques') or {}
    periode_info = periode_api_payload(
        period['date_debut'], period['date_fin'], period['meta'],
        global_agg.get('date_min'), global_agg.get('date_max'),
    )
    return {
        'rows': rows,
        'total_planned': float(finance_row.get('total_duree_minutes') or 0),
        'total_realized': float(finance_row.get('total_duree_realisee_minutes') or 0),
        'total_heures_planifiees': float(finance_row.get('total_duree_heures') or 0),
        'total_heures_realisees': float(finance_row.get('total_duree_realisee_heures') or 0),
        'montant_total': float(finance_row.get('montant_total_realise') or 0),
        'prix_heure': finance_row.get('prix_heure_realisee'),
        'tarifs_variables': True,
        'taux_realisation_pct': stats.get('taux_realisation_pct', 0),
        'periode': periode_info,
        'sessions_count': int(finance_row.get('sessions_count') or len(rows)),
        'modules': finance_row.get('modules') or [],
        'recap_modules': finance_row.get('recap_modules') or [],
        'sessions_by_groupe': finance_row.get('sessions_by_groupe') or [],
        'rows_grouped': _finance_sessions_grouped_export_rows(
            finance_row.get('sessions_by_groupe') or [],
            session_rows_by_key,
        ),
        'recap_formations': _finance_recap_par_formation(finance_row.get('modules') or []),
        'formateur': {
            'numerobadge': formateur.numerobadge or '',
            'nom': formateur.nom or '',
            'prenom': formateur.prenom or '',
            'email': formateur.email or '',
            'telephone': formateur.telephone or '',
            'specialite': formateur.specialite or '',
            'organisation': formateur.organisation or '',
            'grades': finance_row.get('grades') or '-',
            'groupes': finance_row.get('groupes') or '-',
            'secretariats': finance_row.get('secretariats_noms') or [
                f"{sec.nom} ({sec.numero})" for sec in formateur.secretariats.all()
            ],
            'numero_piece_identite': formateur.numero_piece_identite or '',
            'numero_compte_bancaire': formateur.numero_compte_bancaire or '',
            'observations': formateur.observations or '',
        },
    }


def _finance_groupe_header_label(grade, groupe):
    parts = []
    if grade:
        parts.append(f'Grade {grade}')
    if groupe:
        parts.append(groupe)
    return ' — '.join(parts) or 'Sans groupe'


def _finance_append_recap_modules_pdf(elements, recap_modules, afficher_montants, _p, style_info, colors, CI_GREEN_DARK, CI_LIGHT_GREEN, cm):
    """Section PDF : modules dispensés."""
    from reportlab.platypus import Table, TableStyle, Paragraph, Spacer

    if not recap_modules:
        return
    elements.append(Spacer(1, 0.1 * cm))
    elements.append(Paragraph('<b>Modules dispensés</b>', style_info))
    headers = ['Module', 'Formation', 'Grade', 'Groupe', 'Séances', 'Planifié', 'Réalisé', 'Taux %']
    if afficher_montants:
        headers.append('Montant (FCFA)')
    recap_data = [[_p(h, hdr=True) for h in headers]]
    from formations.duration_format import format_duration_minutes
    for item in recap_modules:
        row = [
            _p(item.get('module_intitule') or '-'),
            _p(item.get('formation_intitule') or '-'),
            _p(item.get('grade') or '-', center=True),
            _p(item.get('groupe') or '-', center=True),
            _p(item.get('sessions_count') or 0, center=True),
            _p(format_duration_minutes(item.get('total_duree_minutes')), center=True),
            _p(format_duration_minutes(item.get('total_duree_realisee_minutes')), center=True),
            _p(f"{item.get('taux_realisation_pct') or 0}%", center=True),
        ]
        if afficher_montants:
            row.append(_p(f"{float(item.get('montant_realise') or 0):,.0f}", center=True))
        recap_data.append(row)
    widths = [3.2, 3.2, 1.2, 1.6, 1.2, 1.6, 1.6, 1.2]
    if afficher_montants:
        widths.append(2.0)
    table = Table(recap_data, colWidths=[w * cm for w in widths])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor(CI_GREEN_DARK)),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTSIZE', (0, 0), (-1, -1), 7),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CCCCCC')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor(CI_LIGHT_GREEN)]),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    elements.append(table)
    elements.append(Spacer(1, 0.2 * cm))


def _finance_append_recap_modules_excel(ws, recap_modules, afficher_montants, row_idx, green_fill, header_font, thin_border, light_green_fill, Font, Alignment):
    """Section Excel : modules dispensés."""
    if not recap_modules:
        return row_idx
    from formations.duration_format import format_duration_minutes
    ws.merge_cells(start_row=row_idx, start_column=1, end_row=row_idx, end_column=10)
    ws.cell(row=row_idx, column=1, value='Modules dispensés').font = Font(bold=True, size=10)
    row_idx += 1
    headers = ['Module', 'Formation', 'Grade', 'Groupe', 'Séances', 'Planifié', 'Réalisé', 'Taux %']
    if afficher_montants:
        headers.append('Montant (FCFA)')
    for col, h in enumerate(headers, start=1):
        cell = ws.cell(row=row_idx, column=col, value=h)
        cell.font = header_font
        cell.fill = green_fill
        cell.border = thin_border
    row_idx += 1
    for i, item in enumerate(recap_modules, start=1):
        values = [
            item.get('module_intitule') or '-',
            item.get('formation_intitule') or '-',
            item.get('grade') or '-',
            item.get('groupe') or '-',
            item.get('sessions_count') or 0,
            format_duration_minutes(item.get('total_duree_minutes')),
            format_duration_minutes(item.get('total_duree_realisee_minutes')),
            f"{item.get('taux_realisation_pct') or 0}%",
        ]
        if afficher_montants:
            values.append(round(float(item.get('montant_realise') or 0), 2))
        for col, val in enumerate(values, start=1):
            cell = ws.cell(row=row_idx, column=col, value=val)
            cell.border = thin_border
            if i % 2 == 0:
                cell.fill = light_green_fill
        row_idx += 1
    return row_idx + 1


def _finance_sessions_grouped_export_rows(sessions_by_groupe, session_rows_by_key):
    """Lignes export avec en-têtes de groupe et sous-totaux."""
    from formations.duration_format import format_duration_minutes

    grouped = []
    for block in sessions_by_groupe or []:
        header = _finance_groupe_header_label(block.get('grade'), block.get('groupe'))
        grouped.append({
            'row_type': 'groupe_header',
            'label': header,
        })
        for session in block.get('sessions') or []:
            key = (
                session.get('date_journee'),
                session.get('numero'),
                session.get('session_id'),
            )
            row = session_rows_by_key.get(key)
            if row:
                grouped.append({'row_type': 'session', 'data': row})
        st = block.get('sous_total') or {}
        grouped.append({
            'row_type': 'subtotal',
            'label': f'Sous-total — {header}',
            'creneau_label': format_duration_minutes(st.get('creneau_minutes')),
            'realise_label': format_duration_minutes(st.get('realise_minutes')),
            'montant': st.get('montant'),
            'sessions_count': st.get('sessions_count'),
        })
    return grouped


def _finance_recap_par_formation(modules):
    """Synthèse par type de formation pour les exports fiche de paie."""
    recap = {}
    for mod in modules:
        label = (mod.get('formation_intitule') or '').strip() or 'Formation non renseignée'
        entry = recap.setdefault(label, {
            'formation': label,
            'prix_heure': mod.get('prix_heure_realisee'),
            'heures_realisees': 0.0,
            'montant': 0.0,
            'seances': 0,
        })
        entry['heures_realisees'] += float(mod.get('total_duree_realisee_heures') or 0)
        entry['montant'] += float(mod.get('montant_realise') or 0)
        entry['seances'] += int(mod.get('sessions_count') or 0)
        if mod.get('prix_heure_realisee') is not None:
            entry['prix_heure'] = mod.get('prix_heure_realisee')
    return sorted(recap.values(), key=lambda x: x['formation'])


def _finance_billing_mode_label():
    return 'Facturation : tarif horaire selon le type de formation (cycle)'


def _finance_strip_formateur_sensitive(formateur_dict, request):
    if not formateur_dict:
        return formateur_dict
    # FINANCE et ARCHIVE peuvent voir/exporter les données sensibles.
    if request and getattr(request.user, 'role', None) in ('FINANCE', 'ARCHIVE'):
        return formateur_dict
    out = dict(formateur_dict)
    out.pop('numero_piece_identite', None)
    out.pop('numero_compte_bancaire', None)
    return out


def _parse_bool_query(value, default=True):
    if value is None or value == '':
        return default
    return str(value).strip().lower() in ('1', 'true', 'yes', 'oui', 'on')


def _finance_export_settings():
    from formations.models import FinanceSettings
    return FinanceSettings.get_solo()


def _afficher_montants_export(request):
    settings = _finance_export_settings()
    default = bool(getattr(settings, 'afficher_montants_exports', True))
    if request is not None and request.query_params.get('afficher_montants') is not None:
        return _parse_bool_query(request.query_params.get('afficher_montants'), default)
    return default


def _finance_export_document_options(request, formateur):
    settings = _finance_export_settings()
    prefix = (settings.export_reference_prefix or 'EFI').strip() or 'EFI'
    ref_date = datetime.now().strftime('%Y%m%d')
    badge = formateur.numerobadge or str(formateur.pk)
    return {
        'afficher_montants': _afficher_montants_export(request),
        'titre_document': settings.export_titre_document or 'FICHE DE PAIE DÉTAILLÉE',
        'entete_ligne1': settings.export_entete_ligne1 or '',
        'entete_ligne2': settings.export_entete_ligne2 or '',
        'organisme': settings.export_organisme or '',
        'adresse': settings.export_adresse or '',
        'reference': f'{prefix}-{badge}-{ref_date}',
        'mention_legale': settings.export_mention_legale or '',
        'signataire_nom': settings.export_signataire_nom or '',
        'signataire_fonction': settings.export_signataire_fonction or '',
        'contacts': _finance_paie_parse_lines(settings.export_contacts, _FINANCE_PAIE_CONTACTS),
        'pied_page_titre': settings.export_pied_page_titre or '',
        'pied_page_texte': settings.export_pied_page_texte or '',
    }


def _finance_formateur_export_context(formateur, request):
    summary = _finance_formateur_summary_rows(formateur, request)
    summary['recap_modules'] = _finance_paie_recap_modules(summary.get('recap_modules'))
    options = _finance_export_document_options(request, formateur)
    summary['export'] = options
    summary['prix_label'] = 'Selon la formation'
    summary['billing_label'] = _finance_billing_mode_label()
    summary['periode_label'] = summary['periode'].get('periode_label') or 'Toutes périodes'
    summary['formateur'] = _finance_strip_formateur_sensitive(summary.get('formateur'), request)
    return summary


def _finance_export_table_headers(afficher_montants):
    headers = [
        'Date', 'Séance', 'Module', 'Formation', 'Grade', 'Groupe', 'Secrétariat',
        'Durée (min)', 'Réalisé (min)', 'Heures réalisées',
    ]
    if afficher_montants:
        headers.append('Tarif (FCFA/h)')
        headers.append('Montant (FCFA)')
    return headers


def _finance_export_table_row(row, afficher_montants):
    values = [
        row['date'],
        row['session'],
        row['module'],
        row['formation'],
        row.get('grade') or '-',
        row.get('groupe') or '-',
        row['secretariat'],
        row['duree_seance'],
        row['temps_realise'],
        row.get('heures_realisees', round(float(row.get('temps_realise') or 0) / 60, 2)),
    ]
    if afficher_montants:
        values.append(row.get('prix_heure', ''))
        values.append(row.get('montant', 0))
    return values


def _finance_synthese_document_options(request):
    settings = _finance_export_settings()
    prefix = (settings.export_reference_prefix or 'EFI').strip() or 'EFI'
    ref_date = datetime.now().strftime('%Y%m%d')
    return {
        'afficher_montants': _afficher_montants_export(request),
        'titre_document': 'FICHE DE PAIE GLOBALE — FORMATEURS',
        'entete_ligne1': settings.export_entete_ligne1 or '',
        'entete_ligne2': settings.export_entete_ligne2 or '',
        'organisme': settings.export_organisme or '',
        'adresse': settings.export_adresse or '',
        'reference': f'{prefix}-SYN-{ref_date}',
        'mention_legale': settings.export_mention_legale or '',
        'signataire_nom': settings.export_signataire_nom or '',
        'signataire_fonction': settings.export_signataire_fonction or '',
    }


def _finance_synthese_export_context(request):
    from django.db.models import Q
    from formations.period_filter import parse_period_from_request, periode_api_payload
    from formations.api_views import (
        _finance_secretariat_id_from_request,
        _finance_filter_formateur_queryset,
        _finance_report_rows,
        _finance_canonical_volume_kpis,
    )

    period = parse_period_from_request(request)
    if period.get('error'):
        return None, period.get('detail') or 'Période invalide.'

    secretariat_id = _finance_secretariat_id_from_request(request)
    queryset = Formateur.objects.prefetch_related('secretariats').order_by('nom', 'prenom')
    queryset = _finance_filter_formateur_queryset(queryset, secretariat_id)
    search = (request.query_params.get('search') or '').strip()
    if search:
        queryset = queryset.filter(
            Q(nom__icontains=search)
            | Q(prenom__icontains=search)
            | Q(specialite__icontains=search)
        )

    formateurs = list(queryset)
    global_agg = {'activite_par_mois': {}, 'date_min': None, 'date_max': None}
    rows = _finance_report_rows(
        formateurs,
        include_sessions=False,
        date_debut=period['date_debut'],
        date_fin=period['date_fin'],
        global_aggregates=global_agg,
        secretariat_id=secretariat_id,
    )
    if request.user.role != 'FINANCE':
        for row in rows:
            row.pop('numero_piece_identite', None)
            row.pop('numero_compte_bancaire', None)

    vh_totals = _finance_canonical_volume_kpis(
        date_debut=period['date_debut'],
        date_fin=period['date_fin'],
        secretariat_id=secretariat_id,
    )
    totals = {
        'sessions_count': sum(int(r.get('sessions_count') or 0) for r in rows),
        'total_planned': vh_totals['prevu_minutes'],
        'total_realized': vh_totals['realise_minutes'],
        'total_heures_realisees': vh_totals['realise_heures'],
        'montant_total': round(sum(float(r.get('montant_total_realise') or 0) for r in rows), 2),
        'formateurs_count': len(rows),
        'formateurs_actifs': sum(1 for r in rows if (r.get('sessions_count') or 0) > 0),
    }
    periode_info = periode_api_payload(
        period['date_debut'],
        period['date_fin'],
        period['meta'],
        global_agg.get('date_min'),
        global_agg.get('date_max'),
    )
    return {
        'rows': rows,
        'totals': totals,
        'export': _finance_synthese_document_options(request),
        'periode_label': periode_info.get('periode_label') or 'Toutes périodes',
    }, None


def _finance_synthese_table_headers(afficher_montants, include_sensitive=False):
    headers = [
        'N° Badge', 'Nom', 'Prénom', 'Modules dispensés', 'Grade(s)', 'Groupe(s)', 'Séances',
        'Planifié (min)', 'Réalisé (min)', 'Heures réal.', 'Taux %',
    ]
    if afficher_montants:
        headers.append('Montant (FCFA)')
    if include_sensitive:
        headers.extend(['N° pièce identité', 'N° compte bancaire'])
    return headers


def _finance_synthese_table_row(row, afficher_montants, include_sensitive=False):
    stats = row.get('statistiques') or {}
    values = [
        row.get('numerobadge') or '-',
        row.get('nom') or '',
        row.get('prenom') or '',
        row.get('modules_dispenses') or '-',
        row.get('grades') or '-',
        row.get('groupes') or '-',
        row.get('sessions_count') or 0,
        round(float(row.get('total_duree_minutes') or 0), 1),
        round(float(row.get('total_duree_realisee_minutes') or 0), 1),
        round(float(row.get('total_duree_realisee_minutes') or 0) / 60, 2),
        stats.get('taux_realisation_pct', 0),
    ]
    if afficher_montants:
        values.append(round(float(row.get('montant_total_realise') or 0), 2))
    if include_sensitive:
        values.extend([
            row.get('numero_piece_identite') or '-',
            row.get('numero_compte_bancaire') or '-',
        ])
    return values


def _formation_meta(formation):
    """
    Agrège grade / groupe / vague / superviseurs depuis les modules de la formation.
    Ces champs ont été déplacés de Formation vers Module ; cette fonction reconstruit
    une vue unifiée pour les en-têtes des exports.
    """
    modules = list(formation.modules.select_related('superviseur').all())
    grades = sorted({m.grade for m in modules if m.grade})
    groupes = sorted({m.groupe for m in modules if m.groupe})
    vagues = sorted({m.vague for m in modules if m.vague})
    superviseurs = [m.superviseur for m in modules if m.superviseur]
    # Dédoublonner tout en préservant l'ordre d'apparition
    seen, unique_superviseurs = set(), []
    for s in superviseurs:
        if s.pk not in seen:
            seen.add(s.pk)
            unique_superviseurs.append(s)
    return {
        'grade': ', '.join(grades) or '-',
        'groupe': ', '.join(groupes) or '-',
        'vague': ', '.join(vagues) or '-',
        'superviseurs': unique_superviseurs,
    }


def _check_export_access(request, formation):
    """
    Vérifie que l'utilisateur peut exporter les données de cette formation.

    - DFRC (INJS_ADMIN / CHEF_INJS_ADMIN) : accès complet.
    - DIRECTION / ARCHIVE                      : accès complet (lecture + export).
    - SECRETARIAT / CHEF_SECRETARIAT         : uniquement si au moins un module
                                               de la formation appartient au secrétariat
                                               de l'utilisateur.
    - ENCADRANT                              : uniquement si au moins un module
                                               est supervisé par cet utilisateur.
    - AUDITEUR et autres                     : accès refusé.
    """
    user = request.user
    if not user.is_authenticated:
        return False
    if user.role in ('INJS_ADMIN', 'CHEF_INJS_ADMIN', 'ADMIN', 'DIRECTION', 'ARCHIVE'):
        return True
    if user.role in ('SECRETARIAT', 'CHEF_SECRETARIAT'):
        secretariat = getattr(user, 'secretariat', None)
        if not secretariat:
            return False
        return Formation.objects.filter(
            pk=formation.pk,
            modules__secretariat=secretariat,
        ).exists()
    if user.role == 'ENCADRANT':
        return Formation.objects.filter(
            pk=formation.pk,
            modules__superviseur=user,
        ).exists()
    return False


def _check_liste_classe_export_access(request):
    from authentication.role_groups import LISTE_CLASSE_EXPORT_ROLES
    user = request.user
    return bool(user and user.is_authenticated and user.role in LISTE_CLASSE_EXPORT_ROLES)


def _liste_classe_export_context(request):
    from formations.access import participants_queryset_for_user
    from .participants_list_export import (
        build_liste_classe_groups,
        build_liste_classe_meta,
    )

    if not _check_liste_classe_export_access(request):
        return None, Response({'detail': 'Accès non autorisé.'}, status=403)

    params = request.query_params
    queryset = participants_queryset_for_user(request.user)
    blocks = build_liste_classe_groups(queryset, params)
    meta = build_liste_classe_meta(params)
    return {'blocks': blocks, 'meta': meta}, None


def _get_motif_force(pointage):
    """Retourne le motif de forçage d'un pointage depuis AuditLog, ou chaîne vide."""
    if not pointage or pointage.statut != Pointage.Statut.FORCE_DFRC:
        return ''
    log = AuditLog.objects.filter(
        pointage=pointage,
        action__in=['FORCE_ENTREE', 'FORCE_SORTIE'],
    ).order_by('-timestamp').first()
    if log:
        return log.extra.get('motif', '')
    return ''


def _get_formation_data(pk, module_pk=None):
    """Récupère les données de présence pour export (multi-jours, multi-sessions, participants + formateurs).

    Si module_pk est fourni, filtre les données sur ce seul module.
    """
    formation = Formation.objects.get(pk=pk)

    if module_pk is not None:
        participant_filter = {'module_id': module_pk}
        pointage_filter = {'session__module_id': module_pk}
    else:
        participant_filter = {'module__formation': formation}
        pointage_filter = {'session__module__formation': formation}

    attendus_participants = ModuleParticipant.objects.filter(
        **participant_filter
    ).select_related('participant').order_by('participant__nom', 'participant__prenom').distinct()
    attendus_formateurs = ModuleFormateur.objects.filter(
        **participant_filter
    ).select_related('formateur').order_by('formateur__nom', 'formateur__prenom').distinct()

    all_pointages = Pointage.objects.filter(**pointage_filter).order_by(
        'date_journee', 'timestamp_entree'
    )

    from collections import defaultdict
    part_sessions = defaultdict(list)
    fmt_sessions = defaultdict(list)
    dates_set = set()
    for pt in all_pointages:
        if pt.formateur_id:
            fmt_sessions[(pt.formateur_id, pt.date_journee)].append(pt)
        else:
            part_sessions[(pt.participant_id, pt.date_journee)].append(pt)
        dates_set.add(pt.date_journee)

    dates = sorted(dates_set)
    if not dates:
        dates = [datetime.now().date()]

    # Construire la liste unifiée de personnes attendues
    # IMPORTANT: les formateurs doivent apparaître avant les auditeurs dans les exports.
    personnes = []
    for insc in attendus_formateurs:
        personnes.append(('Formateur', insc.formateur, fmt_sessions))
    for insc in attendus_participants:
        personnes.append(('Étudiant', insc.participant, part_sessions))

    rows = []
    total_present_count = 0
    total_row_count = 0

    for jour in dates:
        for role, p, idx in personnes:
            sessions = idx.get((p.id, jour), [])
            total_row_count += 1

            if sessions:
                nb_sessions = len(sessions)

                if nb_sessions == 1:
                    # Session unique — une seule ligne
                    s = sessions[0]
                    duree_min, duree_str, h_entree, h_sortie = _calculer_duree_export(s)
                    if duree_min == 0:
                        rows.append({
                            'date': jour.strftime('%d/%m/%Y'),
                            'role': role,
                            'matricule': getattr(p, 'matricule', None) or getattr(p, 'numero', ''),
                            'nom': p.nom,
                            'prenom': p.prenom,
                            'organisation': getattr(p, 'organisation', '') or '-',
                            'heure_entree': '-',
                            'heure_sortie': '-',
                            'duree_minutes': '-',
                            'statut': 'Absent',
                            'motif': _get_motif_force(s),
                            'is_detail': False,
                        })
                    else:
                        total_present_count += 1
                        rows.append({
                            'date': jour.strftime('%d/%m/%Y'),
                            'role': role,
                            'matricule': getattr(p, 'matricule', None) or getattr(p, 'numero', ''),
                            'nom': p.nom,
                            'prenom': p.prenom,
                            'organisation': getattr(p, 'organisation', '') or '-',
                            'heure_entree': h_entree,
                            'heure_sortie': h_sortie,
                            'duree_minutes': duree_str,
                            'statut': 'En cours' if not s.timestamp_sortie else 'Présent',
                            'motif': _get_motif_force(s),
                            'is_detail': False,
                        })
                else:
                    # Plusieurs sessions — une ligne par session + ligne récap
                    total_duree = 0
                    all_done = True
                    _matricule_p = getattr(p, 'matricule', None) or getattr(p, 'numero', '')
                    for i, s in enumerate(sessions, 1):
                        duree_min, duree_str, h_entree, h_sortie = _calculer_duree_export(s)
                        total_duree += duree_min
                        if not s.timestamp_sortie:
                            all_done = False
                        rows.append({
                            'date': jour.strftime('%d/%m/%Y') if i == 1 else '',
                            'role': role if i == 1 else '',
                            'matricule': _matricule_p if i == 1 else '',
                            'nom': p.nom if i == 1 else '',
                            'prenom': p.prenom if i == 1 else '',
                            'organisation': getattr(p, 'organisation', '') or '-',
                            'heure_entree': h_entree,
                            'heure_sortie': h_sortie,
                            'duree_minutes': duree_str if duree_min > 0 else '-',
                            'statut': f'Session {i}/{nb_sessions}',
                            'motif': _get_motif_force(s),
                            'is_detail': True,
                        })
                    # Ligne récap total
                    if total_duree == 0:
                        rows.append({
                            'date': '',
                            'role': '',
                            'matricule': '',
                            'nom': f'↳ TOTAL {p.nom} {p.prenom}',
                            'prenom': '',
                            'organisation': '',
                            'heure_entree': '',
                            'heure_sortie': '',
                            'duree_minutes': '-',
                            'statut': f'Absent ({nb_sessions} sessions)',
                            'motif': '',
                            'is_detail': False,
                            'is_recap': True,
                        })
                    else:
                        total_present_count += 1
                        statut_recap = 'Présent' if all_done else 'En cours'
                        th = int(total_duree // 60)
                        tm = int(total_duree % 60)
                        total_str = f"{th}h{tm:02d}" if th > 0 else f"{tm} min"
                        rows.append({
                            'date': '',
                            'role': '',
                            'matricule': '',
                            'nom': f'↳ TOTAL {p.nom} {p.prenom}',
                            'prenom': '',
                            'organisation': '',
                            'heure_entree': '',
                            'heure_sortie': '',
                            'duree_minutes': total_str,
                            'statut': f'{statut_recap} ({nb_sessions} sessions)',
                            'motif': '',
                            'is_detail': False,
                            'is_recap': True,
                        })
            else:
                rows.append({
                    'date': jour.strftime('%d/%m/%Y'),
                    'role': role,
                    'matricule': getattr(p, 'matricule', None) or getattr(p, 'numero', ''),
                    'nom': p.nom,
                    'prenom': p.prenom,
                    'organisation': getattr(p, 'organisation', '') or '-',
                    'heure_entree': '-',
                    'heure_sortie': '-',
                    'duree_minutes': '-',
                    'statut': 'Absent',
                    'motif': '',
                    'is_detail': False,
                })

    nb_total = total_row_count
    nb_presents = total_present_count
    taux = round(nb_presents / nb_total * 100, 1) if nb_total > 0 else 0
    stats = {
        'nb_total': nb_total,
        'nb_presents': nb_presents,
        'nb_absents': nb_total - nb_presents,
        'taux': taux,
        'nb_jours': len(dates),
        'nb_participants': attendus_participants.count(),
        'nb_formateurs': attendus_formateurs.count(),
    }
    return formation, rows, stats


# ──────────────────────────────────────────────
# EXPORT PDF
# ──────────────────────────────────────────────

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def export_pdf(request, pk):
    """Export PDF du rapport de présence d'une formation."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.units import cm
    from reportlab.lib.enums import TA_CENTER, TA_LEFT
    from reportlab.platypus import (
        SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer,
    )
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

    formation = get_object_or_404(Formation, pk=pk)
    if not _check_export_access(request, formation):
        return Response(
            {'detail': 'Accès non autorisé à cette formation.'},
            status=403,
        )

    meta = _formation_meta(formation)
    _, rows, stats = _get_formation_data(pk)

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=landscape(A4),
        leftMargin=1.5 * cm, rightMargin=1.5 * cm,
        topMargin=1.5 * cm, bottomMargin=1.5 * cm,
    )
    styles = getSampleStyleSheet()

    # Styles personnalisés
    style_ministry = ParagraphStyle(
        'Ministry', parent=styles['Normal'],
        fontSize=8, textColor=colors.HexColor('#555555'),
        alignment=TA_CENTER, spaceAfter=2,
    )
    style_title = ParagraphStyle(
        'CustomTitle', parent=styles['Title'],
        fontSize=16, textColor=colors.HexColor(CI_GREEN_DARK),
        alignment=TA_CENTER, spaceAfter=4,
    )
    style_subtitle = ParagraphStyle(
        'Subtitle', parent=styles['Normal'],
        fontSize=10, textColor=colors.HexColor('#444444'),
        alignment=TA_CENTER, spaceAfter=2,
    )
    style_stats = ParagraphStyle(
        'Stats', parent=styles['Normal'],
        fontSize=10, textColor=colors.HexColor(CI_GREEN_DARK),
        spaceAfter=2,
    )

    elements = []

    # En-tête ministère
    elements.append(Paragraph(
        "RÉPUBLIQUE DE CÔTE D'IVOIRE", style_ministry
    ))
    elements.append(Paragraph(
        "Ministère de la Fonction Publique et de la Modernisation de l'Administration",
        style_ministry,
    ))
    elements.append(Paragraph(
        "Direction de la Formation et du Renforcement des Compétences (DFRC)",
        style_ministry,
    ))
    elements.append(Spacer(1, 0.4 * cm))

    # Titre formation
    elements.append(Paragraph(
        f"Rapport de présence", style_title,
    ))
    elements.append(Paragraph(
        f"<b>{formation.formation}</b>", style_subtitle,
    ))

    elements.append(Paragraph(
        f"Grade : {meta['grade']} &nbsp;|&nbsp; "
        f"Groupe : {meta['groupe']} &nbsp;|&nbsp; "
        f"Vague : {meta['vague']}",
        style_subtitle,
    ))
    for sup in meta['superviseurs']:
        elements.append(Paragraph(
            f"Superviseur : {sup.get_full_name()}",
            style_subtitle,
        ))
    # Tableau des sessions superviseur (par journée)
    all_sf = SessionModule.objects.filter(module__formation=formation).order_by('date_journee', 'numero')
    if all_sf.exists():
        elements.append(Spacer(1, 0.3 * cm))
        elements.append(Paragraph("<b>Sessions superviseur</b>", style_stats))
        sf_header = ['Date', 'Session', 'Démarrée à', 'Terminée à', 'Durée (min)']
        sf_data = [sf_header]
        for sf in all_sf:
            duree = sf.duree_minutes
            sf_data.append([
                sf.date_journee.strftime('%d/%m/%Y'),
                f'Session {sf.numero}',
                sf.demarree_le.strftime('%H:%M') if sf.demarree_le else '-',
                sf.terminee_le.strftime('%H:%M') if sf.terminee_le else 'En cours',
                str(duree) if duree else '-',
            ])
        sf_col_widths = [3 * cm, 3 * cm, 3 * cm, 3 * cm, 3 * cm]
        sf_table = Table(sf_data, colWidths=sf_col_widths)
        sf_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor(CI_ORANGE)),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CCCCCC')),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor(CI_LIGHT_ORANGE)]),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
        ]))
        elements.append(sf_table)
    elements.append(Spacer(1, 0.5 * cm))

    # Styles cellules tableau (Paragraph → word wrap automatique)
    cell_normal = ParagraphStyle(
        'CellNormal', parent=styles['Normal'],
        fontSize=8, leading=10,
    )
    cell_center = ParagraphStyle(
        'CellCenter', parent=styles['Normal'],
        fontSize=8, leading=10, alignment=TA_CENTER,
    )
    cell_header = ParagraphStyle(
        'CellHeader', parent=styles['Normal'],
        fontSize=9, leading=11, alignment=TA_CENTER,
        textColor=colors.white, fontName='Helvetica-Bold',
    )

    def _p(text, center=False, hdr=False):
        s = cell_header if hdr else (cell_center if center else cell_normal)
        return Paragraph(str(text), s)

    # Tableau
    header = ['Date', 'Rôle', "N° d'inscription", 'Nom', 'Prénom', 'Entrée', 'Sortie', 'Durée (min)', 'Statut', 'Motif (forçage)']
    data = [[_p(h, hdr=True) for h in header]]
    for r in rows:
        data.append([
            _p(r['date'], center=True),
            _p(r['role'], center=True),
            _p(r['matricule'], center=True),
            _p(r['nom']),
            _p(r['prenom']),
            _p(r['heure_entree'], center=True),
            _p(r['heure_sortie'], center=True),
            _p(r['duree_minutes'], center=True),
            _p(r['statut'], center=True),
            _p(r.get('motif', '') or ''),
        ])

    # Largeurs : total 26.7 cm (A4 paysage 29.7 cm − 3 cm marges)
    col_widths = [2.2 * cm, 2.2 * cm, 3.4 * cm, 4.2 * cm, 4.2 * cm, 1.8 * cm, 1.8 * cm, 2.1 * cm, 2.1 * cm, 2.7 * cm]
    table = Table(data, repeatRows=1, colWidths=col_widths)
    base_style = [
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor(CI_GREEN_DARK)),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 9),
        ('FONTSIZE', (0, 1), (-1, -1), 8),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CCCCCC')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1),
         [colors.white, colors.HexColor(CI_LIGHT_GREEN)]),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
    ]
    # Style detail session rows (light orange) and recap rows (orange bold)
    for i, r in enumerate(rows):
        row_idx = i + 1  # +1 for header row
        if r.get('is_detail'):
            base_style.append(('BACKGROUND', (0, row_idx), (-1, row_idx), colors.HexColor(CI_LIGHT_ORANGE)))
            base_style.append(('FONTNAME', (0, row_idx), (-1, row_idx), 'Helvetica-Oblique'))
        elif r.get('is_recap'):
            base_style.append(('BACKGROUND', (0, row_idx), (-1, row_idx), colors.HexColor(CI_LIGHT_ORANGE)))
            base_style.append(('FONTNAME', (0, row_idx), (-1, row_idx), 'Helvetica-Bold'))
            base_style.append(('TEXTCOLOR', (0, row_idx), (-1, row_idx), colors.HexColor(CI_ORANGE)))
        if r.get('motif'):
            base_style.append(('TEXTCOLOR', (9, row_idx), (9, row_idx), colors.HexColor(CI_ORANGE)))
            base_style.append(('FONTNAME', (9, row_idx), (9, row_idx), 'Helvetica-Oblique'))
    table.setStyle(TableStyle(base_style))
    elements.append(table)
    elements.append(Spacer(1, 0.5 * cm))

    # Statistiques
    elements.append(Paragraph(
        f"<b>Résumé :</b> {stats.get('nb_participants', '-')} participants, "
        f"{stats.get('nb_formateurs', 0)} formateur(s) &nbsp;|&nbsp; "
        f"{stats.get('nb_jours', 1)} jour(s) &nbsp;|&nbsp; "
        f"Présences : {stats['nb_presents']}/{stats['nb_total']} &nbsp;|&nbsp; "
        f"Taux global : <b>{stats['taux']}%</b>",
        style_stats,
    ))
    elements.append(Spacer(1, 0.3 * cm))
    elements.append(Paragraph(
        f"<i>Exporté le {datetime.now().strftime('%d/%m/%Y à %H:%M')}</i>",
        ParagraphStyle('Footer', parent=styles['Normal'], fontSize=7,
                       textColor=colors.HexColor('#999999')),
    ))

    doc.build(elements)
    buffer.seek(0)

    filename = f"rapport_presence_{formation.id}.pdf"
    response = HttpResponse(buffer, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


# ──────────────────────────────────────────────
# EXPORT EXCEL
# ──────────────────────────────────────────────

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def export_excel(request, pk):
    """Export Excel du rapport de présence d'une formation."""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

    formation = get_object_or_404(Formation, pk=pk)
    if not _check_export_access(request, formation):
        return Response(
            {'detail': 'Accès non autorisé à cette formation.'},
            status=403,
        )

    meta = _formation_meta(formation)
    _, rows, stats = _get_formation_data(pk)

    wb = Workbook()
    ws = wb.active
    ws.title = "Présences"

    # Couleurs branding
    green_fill = PatternFill(start_color='1A68AC', end_color='1A68AC', fill_type='solid')
    orange_fill = PatternFill(start_color='F5B100', end_color='F5B100', fill_type='solid')
    light_green_fill = PatternFill(start_color='E8EFF5', end_color='E8EFF5', fill_type='solid')
    light_orange_fill = PatternFill(start_color='FFF8E0', end_color='FFF8E0', fill_type='solid')
    header_font = Font(bold=True, color='FFFFFF', size=10)
    thin_border = Border(
        left=Side(style='thin', color='CCCCCC'),
        right=Side(style='thin', color='CCCCCC'),
        top=Side(style='thin', color='CCCCCC'),
        bottom=Side(style='thin', color='CCCCCC'),
    )

    # En-tête ministère
    ws.merge_cells('A1:J1')
    ws['A1'] = "RÉPUBLIQUE DE CÔTE D'IVOIRE — Ministère de la Fonction Publique"
    ws['A1'].font = Font(size=9, color='555555')
    ws['A1'].alignment = Alignment(horizontal='center')

    ws.merge_cells('A2:J2')
    ws['A2'] = "Direction de la Formation et du Renforcement des Compétences (DFRC)"
    ws['A2'].font = Font(size=9, color='555555')
    ws['A2'].alignment = Alignment(horizontal='center')

    # Titre formation
    ws.merge_cells('A3:J3')
    ws['A3'] = f"Rapport de présence — {formation.formation}"
    ws['A3'].font = Font(bold=True, size=14, color='1A68AC')
    ws['A3'].alignment = Alignment(horizontal='center')

    ws.merge_cells('A4:J4')
    ws['A4'] = f"Grade : {meta['grade']} | Groupe : {meta['groupe']} | Vague : {meta['vague']}"
    ws['A4'].font = Font(size=10, color='444444')
    ws['A4'].alignment = Alignment(horizontal='center')

    next_row = 5
    for sup in meta['superviseurs']:
        ws.merge_cells(start_row=next_row, start_column=1, end_row=next_row, end_column=10)
        ws.cell(row=next_row, column=1, value=f"Superviseur : {sup.get_full_name()}")
        ws.cell(row=next_row, column=1).font = Font(size=10, color='444444')
        ws.cell(row=next_row, column=1).alignment = Alignment(horizontal='center')
        next_row += 1

    # Tableau des sessions superviseur
    all_sf = SessionModule.objects.filter(module__formation=formation).order_by('date_journee', 'numero')
    if all_sf.exists():
        ws.merge_cells(start_row=next_row, start_column=1, end_row=next_row, end_column=5)
        ws.cell(row=next_row, column=1, value="Sessions superviseur")
        ws.cell(row=next_row, column=1).font = Font(bold=True, size=10, color='F5B100')
        next_row += 1
        sf_headers = ['Date', 'Session', 'Démarrée à', 'Terminée à', 'Durée (min)']
        for col, h in enumerate(sf_headers, 1):
            cell = ws.cell(row=next_row, column=col, value=h)
            cell.font = Font(bold=True, color='FFFFFF', size=9)
            cell.fill = orange_fill
            cell.alignment = Alignment(horizontal='center')
            cell.border = thin_border
        next_row += 1
        for sf in all_sf:
            duree = sf.duree_minutes
            sf_vals = [
                sf.date_journee.strftime('%d/%m/%Y'),
                f'Session {sf.numero}',
                sf.demarree_le.strftime('%H:%M') if sf.demarree_le else '-',
                sf.terminee_le.strftime('%H:%M') if sf.terminee_le else 'En cours',
                str(duree) if duree else '-',
            ]
            for col, val in enumerate(sf_vals, 1):
                cell = ws.cell(row=next_row, column=col, value=val)
                cell.border = thin_border
                cell.alignment = Alignment(horizontal='center')
                if not sf.terminee_le:
                    cell.font = Font(bold=True, color='F5B100')
                else:
                    cell.fill = light_orange_fill
            next_row += 1
        next_row += 1

    data_start_row = next_row

    # En-têtes colonnes
    headers = ['Date', 'Rôle', "N° d'inscription", 'Nom', 'Prénom', 'Organisation', 'Entrée', 'Sortie', 'Durée (min)', 'Statut', 'Motif (forçage)']
    for col, h in enumerate(headers, 1):
        cell = ws.cell(row=data_start_row, column=col, value=h)
        cell.font = header_font
        cell.fill = green_fill
        cell.alignment = Alignment(horizontal='center', vertical='center')
        cell.border = thin_border

    # Données
    for i, r in enumerate(rows):
        row_num = data_start_row + 1 + i
        values = [
            r['date'], r['role'], r.get('numero', r.get('matricule', '')), r['nom'], r['prenom'], r['organisation'],
            r['heure_entree'], r['heure_sortie'], r['duree_minutes'], r['statut'], r.get('motif', '') or '',
        ]
        is_detail = r.get('is_detail', False)
        is_recap = r.get('is_recap', False)

        for col, val in enumerate(values, 1):
            cell = ws.cell(row=row_num, column=col, value=val)
            cell.border = thin_border
            cell.alignment = Alignment(vertical='center')
            if col >= 7:
                cell.alignment = Alignment(horizontal='center', vertical='center')

            # Session detail rows: light orange + italic
            if is_detail:
                cell.fill = light_orange_fill
                cell.font = Font(italic=True, size=10)
            # Recap rows: light orange + bold orange
            elif is_recap:
                cell.fill = light_orange_fill
                cell.font = Font(bold=True, color='F5B100', size=10)
            # Normal rows: alternating colors
            elif i % 2 == 1:
                cell.fill = light_green_fill

        # Colorer le statut (sauf detail/recap déjà stylés)
        if not is_detail and not is_recap:
            statut_cell = ws.cell(row=row_num, column=10)
            if r['statut'] == 'Absent':
                statut_cell.font = Font(color='C62828', bold=True)
            elif 'En cours' in r['statut']:
                statut_cell.font = Font(color='F5B100', bold=True)
            else:
                statut_cell.font = Font(color='1A68AC', bold=True)
            if r.get('motif'):
                ws.cell(row=row_num, column=11).font = Font(color='F5B100', italic=True, size=10)

    # Ligne résumé
    summary_row = data_start_row + 1 + len(rows) + 1
    ws.merge_cells(start_row=summary_row, start_column=1, end_row=summary_row, end_column=6)
    ws.cell(row=summary_row, column=1, value="RÉSUMÉ").font = Font(bold=True, size=10)

    labels = [
        (7, f"Jours: {stats.get('nb_jours', 1)}"),
        (8, f"Présents: {stats['nb_presents']}"),
        (9, f"Absents: {stats['nb_absents']}"),
        (10, f"Taux: {stats['taux']}%"),
    ]
    for col, val in labels:
        cell = ws.cell(row=summary_row, column=col, value=val)
        cell.font = Font(bold=True, size=10, color='FFFFFF')
        cell.fill = orange_fill
        cell.alignment = Alignment(horizontal='center')
        cell.border = thin_border

    # Date d'export
    footer_row = summary_row + 1
    ws.merge_cells(start_row=footer_row, start_column=1, end_row=footer_row, end_column=11)
    ws.cell(row=footer_row, column=1,
            value=f"Exporté le {datetime.now().strftime('%d/%m/%Y à %H:%M')}").font = Font(
        size=8, color='999999', italic=True)

    # Largeur colonnes
    col_widths = {'A': 12, 'B': 12, 'C': 10, 'D': 16, 'E': 16, 'F': 18, 'G': 10, 'H': 10, 'I': 12, 'J': 14, 'K': 28}
    for letter, width in col_widths.items():
        ws.column_dimensions[letter].width = width

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    filename = f"rapport_presence_{formation.id}.xlsx"
    response = HttpResponse(
        buffer,
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


# ──────────────────────────────────────────────
# MODULE-BASED EXPORTS (toutes séances d'un module)
# ──────────────────────────────────────────────

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def export_pdf_module(request, module_pk):
    """Export PDF du rapport de présence d'un module (toutes ses séances)."""
    from formations.models import Module
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.units import cm
    from reportlab.lib.enums import TA_CENTER, TA_LEFT
    from reportlab.platypus import (
        SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer,
    )
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

    module = get_object_or_404(Module.objects.select_related('formation', 'superviseur'), pk=module_pk)
    formation = module.formation

    if not _check_export_access(request, formation):
        return Response(
            {'detail': 'Accès non autorisé à ce module.'},
            status=403,
        )

    meta = {
        'grade': module.grade or '-',
        'groupe': module.groupe or '-',
        'vague': module.vague or '-',
        'superviseurs': [module.superviseur] if module.superviseur else [],
    }
    _, rows, stats = _get_formation_data(formation.pk, module_pk=module_pk)
    all_sf = SessionModule.objects.filter(module=module).order_by('date_journee', 'numero')

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=landscape(A4),
        leftMargin=1.5 * cm, rightMargin=1.5 * cm,
        topMargin=1.5 * cm, bottomMargin=1.5 * cm,
    )
    styles = getSampleStyleSheet()

    style_ministry = ParagraphStyle(
        'Ministry_m', parent=styles['Normal'],
        fontSize=8, textColor=colors.HexColor('#555555'),
        alignment=TA_CENTER, spaceAfter=2,
    )
    style_title = ParagraphStyle(
        'CustomTitle_m', parent=styles['Title'],
        fontSize=16, textColor=colors.HexColor(CI_GREEN_DARK),
        alignment=TA_CENTER, spaceAfter=4,
    )
    style_subtitle = ParagraphStyle(
        'Subtitle_m', parent=styles['Normal'],
        fontSize=10, textColor=colors.HexColor('#444444'),
        alignment=TA_CENTER, spaceAfter=2,
    )
    style_stats = ParagraphStyle(
        'Stats_m', parent=styles['Normal'],
        fontSize=10, textColor=colors.HexColor(CI_GREEN_DARK),
        spaceAfter=2,
    )

    elements = []
    elements.append(Paragraph("RÉPUBLIQUE DE CÔTE D'IVOIRE", style_ministry))
    elements.append(Paragraph(
        "Ministère de la Fonction Publique et de la Modernisation de l'Administration",
        style_ministry,
    ))
    elements.append(Paragraph(
        "Direction de la Formation et du Renforcement des Compétences (DFRC)",
        style_ministry,
    ))
    elements.append(Spacer(1, 0.4 * cm))

    elements.append(Paragraph("Rapport de présence — Module", style_title))
    elements.append(Paragraph(f"<b>{module.intitule}</b>", style_subtitle))
    elements.append(Paragraph(f"Formation : {formation.formation}", style_subtitle))
    elements.append(Paragraph(
        f"Grade : {meta['grade']} &nbsp;|&nbsp; "
        f"Groupe : {meta['groupe']} &nbsp;|&nbsp; "
        f"Vague : {meta['vague']}",
        style_subtitle,
    ))
    for sup in meta['superviseurs']:
        elements.append(Paragraph(f"Encadrant : {sup.get_full_name()}", style_subtitle))

    if all_sf.exists():
        elements.append(Spacer(1, 0.3 * cm))
        elements.append(Paragraph("<b>Séances du module</b>", style_stats))
        sf_header = ['Date', 'Séance', 'Démarrée à', 'Terminée à', 'Durée (min)']
        sf_data = [sf_header]
        for sf in all_sf:
            duree = sf.duree_minutes
            sf_data.append([
                sf.date_journee.strftime('%d/%m/%Y'),
                sf.intitule or f'Séance {sf.numero}',
                sf.demarree_le.strftime('%H:%M') if sf.demarree_le else '-',
                sf.terminee_le.strftime('%H:%M') if sf.terminee_le else 'En cours',
                str(duree) if duree else '-',
            ])
        sf_col_widths = [3 * cm, 5 * cm, 3 * cm, 3 * cm, 3 * cm]
        sf_table = Table(sf_data, colWidths=sf_col_widths)
        sf_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor(CI_ORANGE)),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CCCCCC')),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor(CI_LIGHT_ORANGE)]),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
        ]))
        elements.append(sf_table)
    elements.append(Spacer(1, 0.5 * cm))

    cell_normal = ParagraphStyle('CellNormalM', parent=styles['Normal'], fontSize=8, leading=10)
    cell_center = ParagraphStyle('CellCenterM', parent=styles['Normal'], fontSize=8, leading=10, alignment=TA_CENTER)
    cell_header = ParagraphStyle(
        'CellHeaderM', parent=styles['Normal'],
        fontSize=9, leading=11, alignment=TA_CENTER,
        textColor=colors.white, fontName='Helvetica-Bold',
    )

    def _p(text, center=False, hdr=False):
        s = cell_header if hdr else (cell_center if center else cell_normal)
        return Paragraph(str(text), s)

    header = ['Date', 'Rôle', "N° d'inscription", 'Nom', 'Prénom', 'Entrée', 'Sortie', 'Durée (min)', 'Statut', 'Motif (forçage)']
    data = [[_p(h, hdr=True) for h in header]]
    for r in rows:
        data.append([
            _p(r['date'], center=True),
            _p(r['role'], center=True),
            _p(r['matricule'], center=True),
            _p(r['nom']),
            _p(r['prenom']),
            _p(r['heure_entree'], center=True),
            _p(r['heure_sortie'], center=True),
            _p(r['duree_minutes'], center=True),
            _p(r['statut'], center=True),
            _p(r.get('motif', '') or ''),
        ])

    col_widths = [2.2 * cm, 2.2 * cm, 3.4 * cm, 4.2 * cm, 4.2 * cm, 1.8 * cm, 1.8 * cm, 2.1 * cm, 2.1 * cm, 2.7 * cm]
    table = Table(data, repeatRows=1, colWidths=col_widths)
    base_style = [
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor(CI_GREEN_DARK)),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 9),
        ('FONTSIZE', (0, 1), (-1, -1), 8),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CCCCCC')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor(CI_LIGHT_GREEN)]),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
    ]
    for i, r in enumerate(rows):
        row_idx = i + 1
        if r.get('is_detail'):
            base_style.append(('BACKGROUND', (0, row_idx), (-1, row_idx), colors.HexColor(CI_LIGHT_ORANGE)))
            base_style.append(('FONTNAME', (0, row_idx), (-1, row_idx), 'Helvetica-Oblique'))
        elif r.get('is_recap'):
            base_style.append(('BACKGROUND', (0, row_idx), (-1, row_idx), colors.HexColor(CI_LIGHT_ORANGE)))
            base_style.append(('FONTNAME', (0, row_idx), (-1, row_idx), 'Helvetica-Bold'))
            base_style.append(('TEXTCOLOR', (0, row_idx), (-1, row_idx), colors.HexColor(CI_ORANGE)))
        if r.get('motif'):
            base_style.append(('TEXTCOLOR', (9, row_idx), (9, row_idx), colors.HexColor(CI_ORANGE)))
            base_style.append(('FONTNAME', (9, row_idx), (9, row_idx), 'Helvetica-Oblique'))
    table.setStyle(TableStyle(base_style))
    elements.append(table)
    elements.append(Spacer(1, 0.5 * cm))

    elements.append(Paragraph(
        f"<b>Résumé :</b> {stats.get('nb_participants', '-')} étudiant(s), "
        f"{stats.get('nb_formateurs', 0)} formateur(s) &nbsp;|&nbsp; "
        f"{stats.get('nb_jours', 1)} jour(s) &nbsp;|&nbsp; "
        f"Présences : {stats['nb_presents']}/{stats['nb_total']} &nbsp;|&nbsp; "
        f"Taux global : <b>{stats['taux']}%</b>",
        style_stats,
    ))
    elements.append(Spacer(1, 0.3 * cm))
    elements.append(Paragraph(
        f"<i>Exporté le {datetime.now().strftime('%d/%m/%Y à %H:%M')}</i>",
        ParagraphStyle('FooterM', parent=styles['Normal'], fontSize=7,
                       textColor=colors.HexColor('#999999')),
    ))

    doc.build(elements)
    buffer.seek(0)

    filename = f"rapport_module_{module.pk}.pdf"
    response = HttpResponse(buffer, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def export_excel_module(request, module_pk):
    """Export Excel du rapport de présence d'un module (toutes ses séances)."""
    from formations.models import Module
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

    module = get_object_or_404(Module.objects.select_related('formation', 'superviseur'), pk=module_pk)
    formation = module.formation

    if not _check_export_access(request, formation):
        return Response(
            {'detail': 'Accès non autorisé à ce module.'},
            status=403,
        )

    meta = {
        'grade': module.grade or '-',
        'groupe': module.groupe or '-',
        'vague': module.vague or '-',
        'superviseurs': [module.superviseur] if module.superviseur else [],
    }
    _, rows, stats = _get_formation_data(formation.pk, module_pk=module_pk)
    all_sf = SessionModule.objects.filter(module=module).order_by('date_journee', 'numero')

    wb = Workbook()
    ws = wb.active
    ws.title = "Présences"

    green_fill = PatternFill(start_color='1A68AC', end_color='1A68AC', fill_type='solid')
    orange_fill = PatternFill(start_color='F5B100', end_color='F5B100', fill_type='solid')
    light_green_fill = PatternFill(start_color='E8EFF5', end_color='E8EFF5', fill_type='solid')
    light_orange_fill = PatternFill(start_color='FFF8E0', end_color='FFF8E0', fill_type='solid')
    header_font = Font(bold=True, color='FFFFFF', size=10)
    thin_border = Border(
        left=Side(style='thin', color='CCCCCC'),
        right=Side(style='thin', color='CCCCCC'),
        top=Side(style='thin', color='CCCCCC'),
        bottom=Side(style='thin', color='CCCCCC'),
    )

    ws.merge_cells('A1:J1')
    ws['A1'] = "RÉPUBLIQUE DE CÔTE D'IVOIRE — Ministère de la Fonction Publique"
    ws['A1'].font = Font(size=9, color='555555')
    ws['A1'].alignment = Alignment(horizontal='center')

    ws.merge_cells('A2:J2')
    ws['A2'] = "Direction de la Formation et du Renforcement des Compétences (DFRC)"
    ws['A2'].font = Font(size=9, color='555555')
    ws['A2'].alignment = Alignment(horizontal='center')

    ws.merge_cells('A3:J3')
    ws['A3'] = f"Rapport de présence — Module : {module.intitule}"
    ws['A3'].font = Font(bold=True, size=14, color='1A68AC')
    ws['A3'].alignment = Alignment(horizontal='center')

    ws.merge_cells('A4:J4')
    ws['A4'] = f"Formation : {formation.formation}"
    ws['A4'].font = Font(size=11, color='1A68AC')
    ws['A4'].alignment = Alignment(horizontal='center')

    ws.merge_cells('A5:J5')
    ws['A5'] = f"Grade : {meta['grade']} | Groupe : {meta['groupe']} | Vague : {meta['vague']}"
    ws['A5'].font = Font(size=10, color='444444')
    ws['A5'].alignment = Alignment(horizontal='center')

    next_row = 6
    for sup in meta['superviseurs']:
        ws.merge_cells(start_row=next_row, start_column=1, end_row=next_row, end_column=10)
        ws.cell(row=next_row, column=1, value=f"Encadrant : {sup.get_full_name()}")
        ws.cell(row=next_row, column=1).font = Font(size=10, color='444444')
        ws.cell(row=next_row, column=1).alignment = Alignment(horizontal='center')
        next_row += 1

    if all_sf.exists():
        ws.merge_cells(start_row=next_row, start_column=1, end_row=next_row, end_column=5)
        ws.cell(row=next_row, column=1, value="Séances du module")
        ws.cell(row=next_row, column=1).font = Font(bold=True, size=10, color='F5B100')
        next_row += 1
        sf_headers = ['Date', 'Séance', 'Démarrée à', 'Terminée à', 'Durée (min)']
        for col, h in enumerate(sf_headers, 1):
            cell = ws.cell(row=next_row, column=col, value=h)
            cell.font = Font(bold=True, color='FFFFFF', size=9)
            cell.fill = orange_fill
            cell.alignment = Alignment(horizontal='center')
            cell.border = thin_border
        next_row += 1
        for sf in all_sf:
            duree = sf.duree_minutes
            sf_vals = [
                sf.date_journee.strftime('%d/%m/%Y'),
                sf.intitule or f'Séance {sf.numero}',
                sf.demarree_le.strftime('%H:%M') if sf.demarree_le else '-',
                sf.terminee_le.strftime('%H:%M') if sf.terminee_le else 'En cours',
                str(duree) if duree else '-',
            ]
            for col, val in enumerate(sf_vals, 1):
                cell = ws.cell(row=next_row, column=col, value=val)
                cell.border = thin_border
                cell.alignment = Alignment(horizontal='center')
                if not sf.terminee_le:
                    cell.font = Font(bold=True, color='F5B100')
                else:
                    cell.fill = light_orange_fill
            next_row += 1
        next_row += 1

    data_start_row = next_row

    headers = ['Date', 'Rôle', "N° d'inscription", 'Nom', 'Prénom', 'Organisation', 'Entrée', 'Sortie', 'Durée (min)', 'Statut', 'Motif (forçage)']
    for col, h in enumerate(headers, 1):
        cell = ws.cell(row=data_start_row, column=col, value=h)
        cell.font = header_font
        cell.fill = green_fill
        cell.alignment = Alignment(horizontal='center', vertical='center')
        cell.border = thin_border

    for i, r in enumerate(rows):
        row_num = data_start_row + 1 + i
        values = [
            r['date'], r['role'], r.get('numero', r.get('matricule', '')), r['nom'], r['prenom'], r['organisation'],
            r['heure_entree'], r['heure_sortie'], r['duree_minutes'], r['statut'], r.get('motif', '') or '',
        ]
        is_detail = r.get('is_detail', False)
        is_recap = r.get('is_recap', False)

        for col, val in enumerate(values, 1):
            cell = ws.cell(row=row_num, column=col, value=val)
            cell.border = thin_border
            cell.alignment = Alignment(vertical='center')
            if col >= 7:
                cell.alignment = Alignment(horizontal='center', vertical='center')
            if is_detail:
                cell.fill = light_orange_fill
                cell.font = Font(italic=True, size=10)
            elif is_recap:
                cell.fill = light_orange_fill
                cell.font = Font(bold=True, color='F5B100', size=10)
            elif i % 2 == 1:
                cell.fill = light_green_fill

        if not is_detail and not is_recap:
            statut_cell = ws.cell(row=row_num, column=10)
            if r['statut'] == 'Absent':
                statut_cell.font = Font(color='C62828', bold=True)
            elif 'En cours' in r['statut']:
                statut_cell.font = Font(color='F5B100', bold=True)
            else:
                statut_cell.font = Font(color='1A68AC', bold=True)
            if r.get('motif'):
                ws.cell(row=row_num, column=11).font = Font(color='F5B100', italic=True, size=10)

    summary_row = data_start_row + 1 + len(rows) + 1
    ws.merge_cells(start_row=summary_row, start_column=1, end_row=summary_row, end_column=6)
    ws.cell(row=summary_row, column=1, value="RÉSUMÉ").font = Font(bold=True, size=10)

    labels = [
        (7, f"Jours: {stats.get('nb_jours', 1)}"),
        (8, f"Présents: {stats['nb_presents']}"),
        (9, f"Absents: {stats['nb_absents']}"),
        (10, f"Taux: {stats['taux']}%"),
    ]
    for col, val in labels:
        cell = ws.cell(row=summary_row, column=col, value=val)
        cell.font = Font(bold=True, size=10, color='FFFFFF')
        cell.fill = orange_fill
        cell.alignment = Alignment(horizontal='center')
        cell.border = thin_border

    footer_row = summary_row + 1
    ws.merge_cells(start_row=footer_row, start_column=1, end_row=footer_row, end_column=11)
    ws.cell(row=footer_row, column=1,
            value=f"Exporté le {datetime.now().strftime('%d/%m/%Y à %H:%M')}").font = Font(
        size=8, color='999999', italic=True)

    col_widths = {'A': 12, 'B': 12, 'C': 10, 'D': 16, 'E': 16, 'F': 18, 'G': 10, 'H': 10, 'I': 12, 'J': 14, 'K': 28}
    for letter, width in col_widths.items():
        ws.column_dimensions[letter].width = width

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    filename = f"rapport_module_{module.pk}.xlsx"
    response = HttpResponse(
        buffer,
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


# ──────────────────────────────────────────────
# SESSION-BASED EXPORTS
# ──────────────────────────────────────────────

def _get_session_data(session_pk):
    """Récupère les données de présence pour export d'une session spécifique."""
    session = SessionModule.objects.select_related('module__formation').get(pk=session_pk)
    formation = session.module.formation

    # Récupérer tous les pointages pour cette session
    all_pointages = Pointage.objects.filter(
        session=session,
    ).order_by('timestamp_entree')

    # Participants attendus
    attendus_participants = ModuleParticipant.objects.filter(
        module=session.module
    ).select_related('participant').order_by('participant__nom', 'participant__prenom').distinct()

    # Formateurs attendus = formateur principal + formateurs assignés au module
    _module = session.module
    attendus_formateurs_list = []
    seen_formateur_ids = set()

    formateur_du_module = _module.formateur if _module and _module.formateur else None
    if formateur_du_module:
        attendus_formateurs_list.append(formateur_du_module)
        seen_formateur_ids.add(formateur_du_module.id)

    formateurs_assignes = ModuleFormateur.objects.filter(
        module=session.module
    ).select_related('formateur').order_by('formateur__nom', 'formateur__prenom').distinct()
    for insc in formateurs_assignes:
        if insc.formateur_id and insc.formateur_id not in seen_formateur_ids:
            attendus_formateurs_list.append(insc.formateur)
            seen_formateur_ids.add(insc.formateur_id)

    from collections import defaultdict
    part_sessions = defaultdict(list)
    fmt_sessions = defaultdict(list)

    for pt in all_pointages:
        if pt.formateur_id:
            fmt_sessions[pt.formateur_id].append(pt)
        else:
            part_sessions[pt.participant_id].append(pt)

    # Construire la liste unifiée de personnes attendues
    # IMPORTANT: le formateur doit apparaître avant les auditeurs dans les exports.
    personnes = []
    for fmt in attendus_formateurs_list:
        personnes.append(('Formateur', fmt, fmt_sessions))
    for insc in attendus_participants:
        personnes.append(('Étudiant', insc.participant, part_sessions))

    rows = []
    total_present_count = 0
    total_row_count = 0

    for role, p, idx in personnes:
        sessions = idx.get(p.id, [])
        total_row_count += 1

        if sessions:
            nb_sessions = len(sessions)

            if nb_sessions == 1:
                s = sessions[0]
                duree_min, duree_str, h_entree, h_sortie = _calculer_duree_export(s)
                if duree_min == 0:
                    rows.append({
                        'date': session.date_journee.strftime('%d/%m/%Y'),
                        'role': role,
                        'matricule': getattr(p, 'matricule', None) or getattr(p, 'numero', ''),
                        'nom': p.nom,
                        'prenom': p.prenom,
                        'organisation': getattr(p, 'organisation', '') or '-',
                        'heure_entree': '-',
                        'heure_sortie': '-',
                        'duree_minutes': '-',
                        'statut': 'Absent',
                        'motif': _get_motif_force(s),
                        'is_detail': False,
                    })
                else:
                    total_present_count += 1
                    rows.append({
                        'date': session.date_journee.strftime('%d/%m/%Y'),
                        'role': role,
                        'matricule': getattr(p, 'matricule', None) or getattr(p, 'numero', ''),
                        'nom': p.nom,
                        'prenom': p.prenom,
                        'organisation': getattr(p, 'organisation', '') or '-',
                        'heure_entree': h_entree,
                        'heure_sortie': h_sortie,
                        'duree_minutes': duree_str,
                        'statut': 'En cours' if not s.timestamp_sortie else 'Présent',
                        'motif': _get_motif_force(s),
                        'is_detail': False,
                    })
            else:
                total_duree = 0
                all_done = True
                _matricule_p2 = getattr(p, 'matricule', None) or getattr(p, 'numero', '')
                for i, s in enumerate(sessions, 1):
                    duree_min, duree_str, h_entree, h_sortie = _calculer_duree_export(s)
                    total_duree += duree_min
                    if not s.timestamp_sortie:
                        all_done = False
                    rows.append({
                        'date': session.date_journee.strftime('%d/%m/%Y'),
                        'role': role,
                        'matricule': _matricule_p2,
                        'nom': p.nom,
                        'prenom': p.prenom,
                        'organisation': getattr(p, 'organisation', '') or '-',
                        'heure_entree': h_entree,
                        'heure_sortie': h_sortie,
                        'duree_minutes': duree_str if duree_min > 0 else '-',
                        'statut': f'Session {i}/{nb_sessions}',
                        'motif': _get_motif_force(s),
                        'is_detail': True,
                    })
                if total_duree == 0:
                    rows.append({
                        'date': '',
                        'role': '',
                        'matricule': '',
                        'nom': f'↳ TOTAL {p.nom} {p.prenom}',
                        'prenom': '',
                        'organisation': '',
                        'heure_entree': '',
                        'heure_sortie': '',
                        'duree_minutes': '-',
                        'statut': f'Absent ({nb_sessions} sessions)',
                        'motif': '',
                        'is_detail': False,
                        'is_recap': True,
                    })
                else:
                    total_present_count += 1
                    statut_recap = 'Présent' if all_done else 'En cours'
                    th = int(total_duree // 60)
                    tm = int(total_duree % 60)
                    total_str = f"{th}h{tm:02d}" if th > 0 else f"{tm} min"
                    rows.append({
                        'date': '',
                        'role': '',
                        'matricule': '',
                        'nom': f'↳ TOTAL {p.nom} {p.prenom}',
                        'prenom': '',
                        'organisation': '',
                        'heure_entree': '',
                        'heure_sortie': '',
                        'duree_minutes': total_str,
                        'statut': f'{statut_recap} ({nb_sessions} sessions)',
                        'motif': '',
                        'is_detail': False,
                        'is_recap': True,
                    })
        else:
            rows.append({
                'date': session.date_journee.strftime('%d/%m/%Y'),
                'role': role,
                'matricule': getattr(p, 'matricule', None) or getattr(p, 'numero', ''),
                'nom': p.nom,
                'prenom': p.prenom,
                'organisation': getattr(p, 'organisation', '') or '-',
                'heure_entree': '-',
                'heure_sortie': '-',
                'duree_minutes': '-',
                'statut': 'Absent',
                'motif': '',
                'is_detail': False,
            })

    nb_total = total_row_count
    nb_presents = total_present_count
    taux = round(nb_presents / nb_total * 100, 1) if nb_total > 0 else 0
    stats = {
        'nb_total': nb_total,
        'nb_presents': nb_presents,
        'nb_absents': nb_total - nb_presents,
        'taux': taux,
        'nb_jours': 1,
        'nb_participants': attendus_participants.count(),
        'nb_formateurs': len(attendus_formateurs_list),
    }
    return session, formation, rows, stats


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def export_pdf_session(request, session_pk):
    """Export PDF du rapport de présence d'une session de formation."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.units import cm
    from reportlab.lib.enums import TA_CENTER, TA_LEFT
    from reportlab.platypus import (
        SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer,
    )
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

    session = get_object_or_404(SessionModule.objects.select_related('module__formation'), pk=session_pk)
    formation = session.module.formation
    if not _check_export_access(request, formation):
        return Response(
            {'detail': 'Accès non autorisé à cette formation.'},
            status=403,
        )

    _, _, rows, stats = _get_session_data(session_pk)

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=landscape(A4),
        leftMargin=1.5 * cm, rightMargin=1.5 * cm,
        topMargin=1.5 * cm, bottomMargin=1.5 * cm,
    )
    styles = getSampleStyleSheet()

    style_ministry = ParagraphStyle(
        'Ministry', parent=styles['Normal'],
        fontSize=8, textColor=colors.HexColor('#555555'),
        alignment=TA_CENTER, spaceAfter=2,
    )
    style_title = ParagraphStyle(
        'CustomTitle', parent=styles['Title'],
        fontSize=16, textColor=colors.HexColor(CI_GREEN_DARK),
        alignment=TA_CENTER, spaceAfter=4,
    )
    style_subtitle = ParagraphStyle(
        'Subtitle', parent=styles['Normal'],
        fontSize=10, textColor=colors.HexColor('#444444'),
        alignment=TA_CENTER, spaceAfter=2,
    )
    style_stats = ParagraphStyle(
        'Stats', parent=styles['Normal'],
        fontSize=10, textColor=colors.HexColor(CI_GREEN_DARK),
        spaceAfter=2,
    )

    elements = []

    # En-tête ministère
    elements.append(Paragraph(
        "RÉPUBLIQUE DE CÔTE D'IVOIRE", style_ministry
    ))
    elements.append(Paragraph(
        "Ministère de la Fonction Publique et de la Modernisation de l'Administration",
        style_ministry,
    ))
    elements.append(Paragraph(
        "Direction de la Formation et du Renforcement des Compétences (DFRC)",
        style_ministry,
    ))
    elements.append(Spacer(1, 0.4 * cm))

    # Titre session
    session_label = session.intitule or f"Session {session.numero}"
    elements.append(Paragraph(
        f"Rapport de présence — Session", style_title,
    ))
    elements.append(Paragraph(
        f"<b>{formation.formation}</b>", style_subtitle,
    ))
    elements.append(Paragraph(
        f"{session.date_journee.strftime('%d/%m/%Y')} — {session_label}",
        style_subtitle,
    ))

    _mod = session.module if session.module else None
    _s_site = (_mod.site     if _mod and _mod.site     else '') or ''
    _s_bat  = (_mod.batiment if _mod and _mod.batiment else '') or ''
    _s_sal  = (_mod.salle    if _mod and _mod.salle    else '') or ''
    _mod_lbl = (_mod.intitule if _mod else '') or ''
    _mod_grade = (_mod.grade if _mod and _mod.grade else '') or ''
    _mod_groupe = (_mod.groupe if _mod and _mod.groupe else '') or ''
    _heure_debut = session.heure_debut_prevue.strftime('%H:%M') if session.heure_debut_prevue else '-'
    _heure_fin = session.heure_fin_prevue.strftime('%H:%M') if session.heure_fin_prevue else '-'
    _date_seance = session.date_journee.strftime('%d/%m/%Y')
    # Infos session
    if _mod_lbl or _mod_grade or _mod_groupe:
        elements.append(Paragraph(
            f"Module : <b>{_mod_lbl or '-'}</b> &nbsp;|&nbsp; "
            f"Grade : <b>{_mod_grade or '-'}</b> &nbsp;|&nbsp; "
            f"Groupe : <b>{_mod_groupe or '-'}</b>",
            style_subtitle,
        ))
    elements.append(Paragraph(
        f"Date séance : {_date_seance} &nbsp;|&nbsp; Heures séance : {_heure_debut} - {_heure_fin}",
        style_subtitle,
    ))
    elements.append(Paragraph(
        f"Site : {_s_site or '-'} | Bât. : {_s_bat or '-'} | Salle : {_s_sal or '-'} &nbsp;|&nbsp; "
        f"Début prévu : {_heure_debut} &nbsp;|&nbsp; "
        f"Fin prévue : {_heure_fin}",
        style_subtitle,
    ))
    if session.demarree_le:
        elements.append(Paragraph(
            f"Démarrée à : {session.demarree_le.strftime('%H:%M')} &nbsp;|&nbsp; "
            f"Terminée à : {session.terminee_le.strftime('%H:%M') if session.terminee_le else 'En cours'}",
            style_subtitle,
        ))

    elements.append(Spacer(1, 0.5 * cm))

    # Styles cellules tableau (Paragraph → word wrap automatique)
    cell_normal = ParagraphStyle(
        'CellNormal2', parent=styles['Normal'],
        fontSize=8, leading=10,
    )
    cell_center = ParagraphStyle(
        'CellCenter2', parent=styles['Normal'],
        fontSize=8, leading=10, alignment=TA_CENTER,
    )
    cell_header = ParagraphStyle(
        'CellHeader2', parent=styles['Normal'],
        fontSize=9, leading=11, alignment=TA_CENTER,
        textColor=colors.white, fontName='Helvetica-Bold',
    )

    def _p(text, center=False, hdr=False):
        s = cell_header if hdr else (cell_center if center else cell_normal)
        return Paragraph(str(text), s)

    # Tableau
    header = ['Date', 'Rôle', "N° d'inscription", 'Nom', 'Prénom', 'Entrée', 'Sortie', 'Durée (min)', 'Statut', 'Motif (forçage)']
    data = [[_p(h, hdr=True) for h in header]]
    for r in rows:
        data.append([
            _p(r['date'], center=True),
            _p(r['role'], center=True),
            _p(r['matricule'], center=True),
            _p(r['nom']),
            _p(r['prenom']),
            _p(r['heure_entree'], center=True),
            _p(r['heure_sortie'], center=True),
            _p(r['duree_minutes'], center=True),
            _p(r['statut'], center=True),
            _p(r.get('motif', '') or ''),
        ])

    # Largeurs : total 26.7 cm (A4 paysage 29.7 cm − 3 cm marges)
    col_widths = [2.2 * cm, 2.2 * cm, 3.4 * cm, 4.2 * cm, 4.2 * cm, 1.8 * cm, 1.8 * cm, 2.1 * cm, 2.1 * cm, 2.7 * cm]
    table = Table(data, repeatRows=1, colWidths=col_widths)
    base_style = [
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor(CI_GREEN_DARK)),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 9),
        ('FONTSIZE', (0, 1), (-1, -1), 8),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CCCCCC')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1),
         [colors.white, colors.HexColor(CI_LIGHT_GREEN)]),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
    ]
    for i, r in enumerate(rows):
        row_idx = i + 1
        if r.get('is_detail'):
            base_style.append(('BACKGROUND', (0, row_idx), (-1, row_idx), colors.HexColor(CI_LIGHT_ORANGE)))
            base_style.append(('FONTNAME', (0, row_idx), (-1, row_idx), 'Helvetica-Oblique'))
        elif r.get('is_recap'):
            base_style.append(('BACKGROUND', (0, row_idx), (-1, row_idx), colors.HexColor(CI_LIGHT_ORANGE)))
            base_style.append(('FONTNAME', (0, row_idx), (-1, row_idx), 'Helvetica-Bold'))
            base_style.append(('TEXTCOLOR', (0, row_idx), (-1, row_idx), colors.HexColor(CI_ORANGE)))
        if r.get('motif'):
            base_style.append(('TEXTCOLOR', (9, row_idx), (9, row_idx), colors.HexColor(CI_ORANGE)))
            base_style.append(('FONTNAME', (9, row_idx), (9, row_idx), 'Helvetica-Oblique'))
    table.setStyle(TableStyle(base_style))
    elements.append(table)
    elements.append(Spacer(1, 0.5 * cm))

    # Statistiques
    elements.append(Paragraph(
        f"<b>Résumé :</b> {stats.get('nb_participants', '-')} participants, "
        f"{stats.get('nb_formateurs', 0)} formateur(s) &nbsp;|&nbsp; "
        f"Présences : {stats['nb_presents']}/{stats['nb_total']} &nbsp;|&nbsp; "
        f"Taux : <b>{stats['taux']}%</b>",
        style_stats,
    ))
    elements.append(Spacer(1, 0.3 * cm))
    elements.append(Paragraph(
        f"<i>Exporté le {datetime.now().strftime('%d/%m/%Y à %H:%M')}</i>",
        ParagraphStyle('Footer', parent=styles['Normal'], fontSize=7,
                       textColor=colors.HexColor('#999999')),
    ))

    doc.build(elements)
    buffer.seek(0)

    filename = f"rapport_session_{session.id}.pdf"
    response = HttpResponse(buffer, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def export_excel_session(request, session_pk):
    """Export Excel du rapport de présence d'une session de formation."""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

    session = get_object_or_404(SessionModule.objects.select_related('module__formation'), pk=session_pk)
    formation = session.module.formation
    if not _check_export_access(request, formation):
        return Response(
            {'detail': 'Accès non autorisé à cette formation.'},
            status=403,
        )

    _, _, rows, stats = _get_session_data(session_pk)

    wb = Workbook()
    ws = wb.active
    ws.title = "Présences"

    green_fill = PatternFill(start_color='1A68AC', end_color='1A68AC', fill_type='solid')
    orange_fill = PatternFill(start_color='F5B100', end_color='F5B100', fill_type='solid')
    light_green_fill = PatternFill(start_color='E8EFF5', end_color='E8EFF5', fill_type='solid')
    light_orange_fill = PatternFill(start_color='FFF8E0', end_color='FFF8E0', fill_type='solid')
    header_font = Font(bold=True, color='FFFFFF', size=10)
    thin_border = Border(
        left=Side(style='thin', color='CCCCCC'),
        right=Side(style='thin', color='CCCCCC'),
        top=Side(style='thin', color='CCCCCC'),
        bottom=Side(style='thin', color='CCCCCC'),
    )

    # En-tête ministère
    ws.merge_cells('A1:J1')
    ws['A1'] = "RÉPUBLIQUE DE CÔTE D'IVOIRE — Ministère de la Fonction Publique"
    ws['A1'].font = Font(size=9, color='555555')
    ws['A1'].alignment = Alignment(horizontal='center')

    ws.merge_cells('A2:J2')
    ws['A2'] = "Direction de la Formation et du Renforcement des Compétences (DFRC)"
    ws['A2'].font = Font(size=9, color='555555')
    ws['A2'].alignment = Alignment(horizontal='center')

    # Titre session
    session_label = session.intitule or f"Session {session.numero}"
    ws.merge_cells('A3:J3')
    ws['A3'] = f"Rapport de présence — Session"
    ws['A3'].font = Font(bold=True, size=14, color='1A68AC')
    ws['A3'].alignment = Alignment(horizontal='center')

    ws.merge_cells('A4:J4')
    ws['A4'] = f"{formation.formation}"
    ws['A4'].font = Font(bold=True, size=12, color='1A68AC')
    ws['A4'].alignment = Alignment(horizontal='center')

    ws.merge_cells('A5:J5')
    ws['A5'] = f"{session.date_journee.strftime('%d/%m/%Y')} — {session_label}"
    ws['A5'].font = Font(size=10, color='444444')
    ws['A5'].alignment = Alignment(horizontal='center')

    # Infos session
    ws.merge_cells('A6:J6')
    heure_debut = session.heure_debut_prevue.strftime('%H:%M') if session.heure_debut_prevue else '-'
    heure_fin = session.heure_fin_prevue.strftime('%H:%M') if session.heure_fin_prevue else '-'
    _sm = session.module if session.module else None
    _xs = (
        (_sm.site.nom if getattr(_sm, 'site', None) else getattr(_sm, 'site_legacy', ''))
        if _sm else ''
    ) or ''
    _xb = (_sm.batiment if _sm and _sm.batiment else '') or ''
    _xl = (_sm.salle    if _sm and _sm.salle    else '') or ''
    _xml = (_sm.intitule if _sm else '') or ''
    _xgrade = (_sm.grade if _sm and _sm.grade else '') or ''
    _xgroupe = (_sm.groupe if _sm and _sm.groupe else '') or ''
    if _xml or _xgrade or _xgroupe:
        ws.merge_cells('A6:J6')
        ws['A6'] = f"Module : {_xml or '-'} | Grade : {_xgrade or '-'} | Groupe : {_xgroupe or '-'}"
        ws['A6'].font = Font(bold=True, size=10, color='1A68AC')
        ws['A6'].alignment = Alignment(horizontal='center')
        ws.merge_cells('A7:J7')
        ws['A7'] = (
            f"Date séance : {session.date_journee.strftime('%d/%m/%Y')} | "
            f"Heures séance : {heure_debut} - {heure_fin} | "
            f"Site : {_xs or '-'} | Bât. : {_xb or '-'} | Salle : {_xl or '-'}"
        )
        ws['A7'].font = Font(size=10, color='444444')
        ws['A7'].alignment = Alignment(horizontal='center')
        data_start_row = 9
    else:
        ws['A6'] = (
            f"Date séance : {session.date_journee.strftime('%d/%m/%Y')} | "
            f"Heures séance : {heure_debut} - {heure_fin} | "
            f"Site : {_xs or '-'} | Bât. : {_xb or '-'} | Salle : {_xl or '-'}"
        )
        ws['A6'].font = Font(size=10, color='444444')
        ws['A6'].alignment = Alignment(horizontal='center')
        data_start_row = 8

    # En-têtes colonnes
    headers = ['Date', 'Rôle', "N° d'inscription", 'Nom', 'Prénom', 'Organisation', 'Entrée', 'Sortie', 'Durée (min)', 'Statut', 'Motif (forçage)']
    for col, h in enumerate(headers, 1):
        cell = ws.cell(row=data_start_row, column=col, value=h)
        cell.font = header_font
        cell.fill = green_fill
        cell.alignment = Alignment(horizontal='center', vertical='center')
        cell.border = thin_border

    # Données
    for i, r in enumerate(rows):
        row_num = data_start_row + 1 + i
        values = [
            r['date'], r['role'], r['matricule'], r['nom'], r['prenom'], r['organisation'],
            r['heure_entree'], r['heure_sortie'], r['duree_minutes'], r['statut'], r.get('motif', '') or '',
        ]
        is_detail = r.get('is_detail', False)
        is_recap = r.get('is_recap', False)

        for col, val in enumerate(values, 1):
            cell = ws.cell(row=row_num, column=col, value=val)
            cell.border = thin_border
            cell.alignment = Alignment(vertical='center')
            if col >= 7:
                cell.alignment = Alignment(horizontal='center', vertical='center')

            if is_detail:
                cell.fill = light_orange_fill
                cell.font = Font(italic=True, size=10)
            elif is_recap:
                cell.fill = light_orange_fill
                cell.font = Font(bold=True, color='F5B100', size=10)
            elif i % 2 == 1:
                cell.fill = light_green_fill

        if not is_detail and not is_recap:
            statut_cell = ws.cell(row=row_num, column=10)
            if r['statut'] == 'Absent':
                statut_cell.font = Font(color='C62828', bold=True)
            elif 'En cours' in r['statut']:
                statut_cell.font = Font(color='F5B100', bold=True)
            else:
                statut_cell.font = Font(color='1A68AC', bold=True)
            if r.get('motif'):
                ws.cell(row=row_num, column=11).font = Font(color='F5B100', italic=True, size=10)

    # Ligne résumé
    summary_row = data_start_row + 1 + len(rows) + 1
    ws.merge_cells(start_row=summary_row, start_column=1, end_row=summary_row, end_column=6)
    ws.cell(row=summary_row, column=1, value="RÉSUMÉ").font = Font(bold=True, size=10)

    labels = [
        (7, f"Présents: {stats['nb_presents']}"),
        (8, f"Absents: {stats['nb_absents']}"),
        (9, f"Taux: {stats['taux']}%"),
        (10, f"Participants: {stats['nb_participants']}"),
    ]
    for col, val in labels:
        cell = ws.cell(row=summary_row, column=col, value=val)
        cell.font = Font(bold=True, size=10, color='FFFFFF')
        cell.fill = orange_fill
        cell.alignment = Alignment(horizontal='center')
        cell.border = thin_border

    # Date d'export
    footer_row = summary_row + 1
    ws.merge_cells(start_row=footer_row, start_column=1, end_row=footer_row, end_column=11)
    ws.cell(row=footer_row, column=1,
            value=f"Exporté le {datetime.now().strftime('%d/%m/%Y à %H:%M')}").font = Font(
        size=8, color='999999', italic=True)

    # Largeur colonnes
    col_widths = {'A': 12, 'B': 12, 'C': 10, 'D': 16, 'E': 16, 'F': 18, 'G': 10, 'H': 10, 'I': 12, 'J': 14, 'K': 28}
    for letter, width in col_widths.items():
        ws.column_dimensions[letter].width = width

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    filename = f"rapport_session_{session.id}.xlsx"
    response = HttpResponse(
        buffer,
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def export_finance_formateur_pdf(request, formateur_pk):
    """Export PDF — état récapitulatif des modules dispensés (modèle CPFAE)."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.utils import simpleSplit

    if not _check_finance_export_access(request):
        return Response({'detail': 'Accès réservé à la direction et à la finance.'}, status=403)

    formateur = get_object_or_404(Formateur.objects.prefetch_related('secretariats'), pk=formateur_pk)
    ctx = _finance_formateur_export_context(formateur, request)
    export_opts = ctx['export']
    fmt = ctx.get('formateur') or {}
    recap_modules = ctx.get('recap_modules') or []
    periode = ctx.get('periode') or {}

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        leftMargin=1.8 * cm, rightMargin=1.8 * cm,
        topMargin=1.2 * cm, bottomMargin=2.8 * cm,
    )
    styles = getSampleStyleSheet()
    dash = '—' * 32

    style_hdr_left = ParagraphStyle(
        'PaieHdrL', parent=styles['Normal'],
        fontSize=7.5, leading=10, alignment=TA_LEFT,
    )
    style_hdr_right = ParagraphStyle(
        'PaieHdrR', parent=styles['Normal'],
        fontSize=8.5, leading=11, alignment=TA_RIGHT,
    )
    style_title = ParagraphStyle(
        'PaieTitle', parent=styles['Normal'],
        fontSize=10, leading=13, alignment=TA_CENTER,
        fontName='Helvetica-Bold', spaceAfter=8, spaceBefore=6,
    )
    style_body = ParagraphStyle(
        'PaieBody', parent=styles['Normal'],
        fontSize=9, leading=12, alignment=TA_LEFT,
    )
    style_body_center = ParagraphStyle(
        'PaieBodyC', parent=styles['Normal'],
        fontSize=9, leading=12, alignment=TA_CENTER,
    )
    style_small = ParagraphStyle(
        'PaieSmall', parent=styles['Normal'],
        fontSize=7, leading=9, alignment=TA_LEFT, textColor=colors.HexColor('#333333'),
    )
    style_confidentiel = ParagraphStyle(
        'PaieConf', parent=styles['Normal'],
        fontSize=9, leading=12, alignment=TA_LEFT, fontName='Helvetica-Bold',
        spaceBefore=10,
    )

    def _esc(text):
        return str(text or '').replace('&', '&amp;')

    def _cell(text, *, bold=False, center=False, size=9):
        content = _esc(text)
        if bold:
            content = f'<b>{content}</b>'
        style = style_body_center if center else style_body
        if size != 9:
            style = ParagraphStyle(
                f'PaieCell{size}', parent=style,
                fontSize=size, leading=size + 2,
            )
        return Paragraph(content, style)

    elements = []

    left_hdr = '<br/>'.join([
        _esc(_FINANCE_PAIE_HEADER_LEFT[0]),
        dash,
        _esc(_FINANCE_PAIE_HEADER_LEFT[1]),
        _esc(_FINANCE_PAIE_HEADER_LEFT[2]),
        dash,
        _esc(_FINANCE_PAIE_HEADER_LEFT[3]),
        _esc(_FINANCE_PAIE_HEADER_LEFT[4]),
    ])
    right_hdr = '<br/>'.join([
        f'<b>{_esc(_FINANCE_PAIE_HEADER_RIGHT[0])}</b>',
        f'<i>{_esc(_FINANCE_PAIE_HEADER_RIGHT[1])}</i>',
        dash,
    ])
    header_table = Table(
        [[Paragraph(left_hdr, style_hdr_left), Paragraph(right_hdr, style_hdr_right)]],
        colWidths=[10.5 * cm, 6.5 * cm],
    )
    header_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))
    elements.append(header_table)
    elements.append(Spacer(1, 0.35 * cm))

    titre = _finance_paie_build_title(recap_modules, export_opts, periode)
    elements.append(Paragraph(f'<u>{_esc(titre)}</u>', style_title))
    elements.append(Spacer(1, 0.25 * cm))

    col_widths = [0.9 * cm, 6.0 * cm, 2.6 * cm, 2.4 * cm, 2.0 * cm, 2.0 * cm]
    table_data = []
    formateur_label = _finance_paie_formateur_label(fmt)
    table_data.append([_cell(formateur_label, bold=True), '', '', '', '', ''])

    table_data.append([
        _cell('N°', bold=True, center=True),
        _cell('MODULES', bold=True, center=True),
        _cell('CATEGORIE/GRADE', bold=True, center=True),
        _cell('GROUPES', bold=True, center=True),
        _cell('VOLUME RÉALISÉ', bold=True, center=True),
        _cell('VOLUME PLANIFIÉ', bold=True, center=True),
    ])

    total_realise = 0
    total_planifie = 0
    for idx, item in enumerate(recap_modules, start=1):
        heures_realise = _finance_paie_volume_heures(item.get('total_duree_realisee_minutes'))
        heures_planifie = _finance_paie_volume_heures(item.get('total_creneau_periode_minutes'))
        total_realise += heures_realise
        total_planifie += heures_planifie
        table_data.append([
            _cell(idx, center=True),
            _cell((item.get('module_intitule') or '-').upper()),
            _cell(item.get('grade') or '-', center=True),
            _cell(_finance_paie_format_groupe(item.get('groupe')), center=True),
            _cell(heures_realise, center=True),
            _cell(heures_planifie, center=True),
        ])

    if not recap_modules:
        table_data.append([
            _cell('—', center=True),
            _cell('Aucun module sur la période'),
            _cell('—', center=True),
            _cell('—', center=True),
            _cell(0, center=True),
            _cell(0, center=True),
        ])

    table_data.append([
        _cell('TOTAL VOLUME HORAIRE', bold=True, center=True),
        '', '', '',
        _cell(total_realise, bold=True, center=True),
        _cell(total_planifie, bold=True, center=True),
    ])

    main_table = Table(table_data, colWidths=col_widths)
    n_rows = len(table_data)
    main_style = [
        ('GRID', (0, 0), (-1, -1), 0.75, colors.black),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('SPAN', (0, 0), (-1, 0)),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor(CI_PAIE_BLUE)),
        ('BACKGROUND', (0, 1), (-1, 1), colors.HexColor(CI_PAIE_ORANGE)),
        ('BACKGROUND', (0, n_rows - 1), (-1, n_rows - 1), colors.HexColor(CI_PAIE_GREEN)),
        ('SPAN', (0, n_rows - 1), (3, n_rows - 1)),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('ALIGN', (1, 2), (1, n_rows - 2), 'LEFT'),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
    ]
    main_table.setStyle(TableStyle(main_style))
    elements.append(main_table)
    elements.append(Spacer(1, 0.5 * cm))

    # ── Bloc identité & observations (fiche complète) ──
    identite_lignes = []
    if fmt.get('specialite'):
        identite_lignes.append(f"<b>Spécialité :</b> {_esc(fmt.get('specialite'))}")
    if fmt.get('organisation'):
        identite_lignes.append(f"<b>Organisation :</b> {_esc(fmt.get('organisation'))}")
    if fmt.get('email'):
        identite_lignes.append(f"<b>E-mail :</b> {_esc(fmt.get('email'))}")
    if fmt.get('telephone'):
        identite_lignes.append(f"<b>Téléphone :</b> {_esc(fmt.get('telephone'))}")
    if fmt.get('numero_piece_identite'):
        identite_lignes.append(f"<b>N° pièce d'identité :</b> {_esc(fmt.get('numero_piece_identite'))}")
    if fmt.get('numero_compte_bancaire'):
        identite_lignes.append(f"<b>N° compte bancaire (RIB) :</b> {_esc(fmt.get('numero_compte_bancaire'))}")
    if identite_lignes:
        elements.append(Paragraph('<u>IDENTITÉ</u>', style_confidentiel))
        for ligne in identite_lignes:
            elements.append(Paragraph(ligne, style_body))
        elements.append(Spacer(1, 0.4 * cm))

    observations_txt = (fmt.get('observations') or '').strip()
    if observations_txt:
        elements.append(Paragraph('<u>OBSERVATIONS</u>', style_confidentiel))
        for para in observations_txt.split('\n'):
            elements.append(Paragraph(_esc(para) or '&nbsp;', style_body))
        elements.append(Spacer(1, 0.5 * cm))

    for line in _finance_paie_contacts(export_opts):
        elements.append(Paragraph(_esc(line), style_body))
    elements.append(Spacer(1, 0.6 * cm))

    pied_titre, pied_adresse = _finance_paie_pied_de_page(export_opts)
    page_w, page_h = A4
    left_m = 1.8 * cm
    right_m = 1.8 * cm
    usable_w = page_w - left_m - right_m

    def _draw_footer(canvas, doc):
        canvas.saveState()
        y_base = 1.0 * cm
        # Adresse (petite police, multiligne)
        canvas.setFont('Helvetica', 7)
        canvas.setFillColor(colors.HexColor('#333333'))
        addr_lines = simpleSplit(pied_adresse, 'Helvetica', 7, usable_w)
        line_h = 9
        for i, line in enumerate(reversed(addr_lines)):
            canvas.drawString(left_m, y_base + i * line_h, line)
        y_titre = y_base + len(addr_lines) * line_h + 3
        # Titre confidentiel (gras)
        canvas.setFont('Helvetica-Bold', 9)
        canvas.setFillColor(colors.black)
        canvas.drawString(left_m, y_titre, pied_titre)
        canvas.restoreState()

    doc.build(elements, onFirstPage=_draw_footer, onLaterPages=_draw_footer)
    buffer.seek(0)
    filename = f"fiche_paie_{formateur.numerobadge or formateur.pk}.pdf"
    response = HttpResponse(buffer, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def export_finance_formateur_excel(request, formateur_pk):
    """Export Excel — état récapitulatif des modules dispensés (modèle CPFAE)."""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

    if not _check_finance_export_access(request):
        return Response({'detail': 'Accès réservé à la direction et à la finance.'}, status=403)

    formateur = get_object_or_404(Formateur.objects.prefetch_related('secretariats'), pk=formateur_pk)
    ctx = _finance_formateur_export_context(formateur, request)
    export_opts = ctx['export']
    fmt = ctx.get('formateur') or {}
    recap_modules = ctx.get('recap_modules') or []
    periode = ctx.get('periode') or {}
    last_col = 6

    wb = Workbook()
    ws = wb.active
    ws.title = "Modules dispensés"

    blue_fill = PatternFill(start_color='DDEBF7', end_color='DDEBF7', fill_type='solid')
    orange_fill = PatternFill(start_color='FCE7B4', end_color='FCE7B4', fill_type='solid')
    green_fill = PatternFill(start_color='77BCE7', end_color='77BCE7', fill_type='solid')
    black_border = Border(
        left=Side(style='thin', color='000000'),
        right=Side(style='thin', color='000000'),
        top=Side(style='thin', color='000000'),
        bottom=Side(style='thin', color='000000'),
    )
    dash = '—' * 28
    row_idx = 1

    left_lines = [
        _FINANCE_PAIE_HEADER_LEFT[0], dash,
        _FINANCE_PAIE_HEADER_LEFT[1], _FINANCE_PAIE_HEADER_LEFT[2], dash,
        _FINANCE_PAIE_HEADER_LEFT[3], _FINANCE_PAIE_HEADER_LEFT[4],
    ]
    right_lines = [
        _FINANCE_PAIE_HEADER_RIGHT[0], _FINANCE_PAIE_HEADER_RIGHT[1], dash,
    ]
    max_hdr = max(len(left_lines), len(right_lines))
    for i in range(max_hdr):
        left_val = left_lines[i] if i < len(left_lines) else ''
        right_val = right_lines[i] if i < len(right_lines) else ''
        ws.merge_cells(start_row=row_idx, start_column=1, end_row=row_idx, end_column=3)
        ws.merge_cells(start_row=row_idx, start_column=4, end_row=row_idx, end_column=5)
        c_left = ws.cell(row=row_idx, column=1, value=left_val)
        c_left.font = Font(size=8)
        c_left.alignment = Alignment(horizontal='left', wrap_text=True)
        c_right = ws.cell(row=row_idx, column=4, value=right_val)
        c_right.font = Font(size=9, bold=(i == 0))
        c_right.alignment = Alignment(horizontal='right', wrap_text=True)
        row_idx += 1

    row_idx += 1
    titre = _finance_paie_build_title(recap_modules, export_opts, periode)
    ws.merge_cells(start_row=row_idx, start_column=1, end_row=row_idx, end_column=last_col)
    title_cell = ws.cell(row=row_idx, column=1, value=titre)
    title_cell.font = Font(bold=True, size=10, underline='single')
    title_cell.alignment = Alignment(horizontal='center', wrap_text=True)
    row_idx += 2

    formateur_label = _finance_paie_formateur_label(fmt)
    ws.merge_cells(start_row=row_idx, start_column=1, end_row=row_idx, end_column=last_col)
    name_cell = ws.cell(row=row_idx, column=1, value=formateur_label)
    name_cell.font = Font(bold=True, size=10)
    name_cell.fill = blue_fill
    name_cell.border = black_border
    name_cell.alignment = Alignment(horizontal='left')
    row_idx += 1

    headers = ['N°', 'MODULES', 'CATEGORIE/GRADE', 'GROUPES', 'VOLUME RÉALISÉ', 'VOLUME PLANIFIÉ']
    for col, h in enumerate(headers, start=1):
        cell = ws.cell(row=row_idx, column=col, value=h)
        cell.font = Font(bold=True, size=9)
        cell.fill = orange_fill
        cell.border = black_border
        cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
    row_idx += 1

    total_realise = 0
    total_planifie = 0
    if recap_modules:
        for idx, item in enumerate(recap_modules, start=1):
            heures_realise = _finance_paie_volume_heures(item.get('total_duree_realisee_minutes'))
            heures_planifie = _finance_paie_volume_heures(item.get('total_creneau_periode_minutes'))
            total_realise += heures_realise
            total_planifie += heures_planifie
            values = [
                idx,
                (item.get('module_intitule') or '-').upper(),
                item.get('grade') or '-',
                _finance_paie_format_groupe(item.get('groupe')),
                heures_realise,
                heures_planifie,
            ]
            for col, val in enumerate(values, start=1):
                cell = ws.cell(row=row_idx, column=col, value=val)
                cell.border = black_border
                cell.alignment = Alignment(
                    horizontal='left' if col == 2 else 'center',
                    vertical='center',
                    wrap_text=True,
                )
            row_idx += 1
    else:
        for col, val in enumerate(['—', 'Aucun module sur la période', '—', '—', 0, 0], start=1):
            cell = ws.cell(row=row_idx, column=col, value=val)
            cell.border = black_border
        row_idx += 1

    ws.merge_cells(start_row=row_idx, start_column=1, end_row=row_idx, end_column=4)
    total_label = ws.cell(row=row_idx, column=1, value='TOTAL VOLUME HORAIRE')
    total_label.font = Font(bold=True, size=9)
    total_label.fill = green_fill
    total_label.border = black_border
    total_label.alignment = Alignment(horizontal='center')
    total_realise_cell = ws.cell(row=row_idx, column=5, value=total_realise)
    total_realise_cell.font = Font(bold=True, size=9)
    total_realise_cell.fill = green_fill
    total_realise_cell.border = black_border
    total_realise_cell.alignment = Alignment(horizontal='center')
    total_planifie_cell = ws.cell(row=row_idx, column=6, value=total_planifie)
    total_planifie_cell.font = Font(bold=True, size=9)
    total_planifie_cell.fill = green_fill
    total_planifie_cell.border = black_border
    total_planifie_cell.alignment = Alignment(horizontal='center')
    row_idx += 2

    # ── Bloc identité & observations (fiche complète) ──
    identite_pairs = []
    if fmt.get('specialite'):
        identite_pairs.append(('Spécialité', fmt.get('specialite')))
    if fmt.get('organisation'):
        identite_pairs.append(('Organisation', fmt.get('organisation')))
    if fmt.get('email'):
        identite_pairs.append(('E-mail', fmt.get('email')))
    if fmt.get('telephone'):
        identite_pairs.append(('Téléphone', fmt.get('telephone')))
    if fmt.get('numero_piece_identite'):
        identite_pairs.append(("N° pièce d'identité", fmt.get('numero_piece_identite')))
    if fmt.get('numero_compte_bancaire'):
        identite_pairs.append(('N° compte bancaire (RIB)', fmt.get('numero_compte_bancaire')))
    if identite_pairs:
        ws.merge_cells(start_row=row_idx, start_column=1, end_row=row_idx, end_column=last_col)
        hdr = ws.cell(row=row_idx, column=1, value='IDENTITÉ')
        hdr.font = Font(bold=True, size=10)
        row_idx += 1
        for label, value in identite_pairs:
            lbl = ws.cell(row=row_idx, column=1, value=label)
            lbl.font = Font(bold=True, size=9)
            ws.merge_cells(start_row=row_idx, start_column=2, end_row=row_idx, end_column=last_col)
            ws.cell(row=row_idx, column=2, value=str(value)).font = Font(size=9)
            row_idx += 1
        row_idx += 1

    observations_txt = (fmt.get('observations') or '').strip()
    if observations_txt:
        ws.merge_cells(start_row=row_idx, start_column=1, end_row=row_idx, end_column=last_col)
        obs_hdr = ws.cell(row=row_idx, column=1, value='OBSERVATIONS')
        obs_hdr.font = Font(bold=True, size=10)
        row_idx += 1
        ws.merge_cells(start_row=row_idx, start_column=1, end_row=row_idx, end_column=last_col)
        obs_cell = ws.cell(row=row_idx, column=1, value=observations_txt)
        obs_cell.font = Font(size=9)
        obs_cell.alignment = Alignment(wrap_text=True, vertical='top', horizontal='left')
        row_idx += 2

    for text in _finance_paie_contacts(export_opts):
        ws.merge_cells(start_row=row_idx, start_column=1, end_row=row_idx, end_column=last_col)
        cell = ws.cell(row=row_idx, column=1, value=text)
        cell.font = Font(size=9)
        cell.alignment = Alignment(wrap_text=True, horizontal='left')
        row_idx += 1

    row_idx += 1
    pied_titre, pied_adresse = _finance_paie_pied_de_page(export_opts)
    ws.merge_cells(start_row=row_idx, start_column=1, end_row=row_idx, end_column=last_col)
    pied_title_cell = ws.cell(row=row_idx, column=1, value=pied_titre)
    pied_title_cell.font = Font(bold=True, size=9)
    pied_title_cell.alignment = Alignment(horizontal='left')
    row_idx += 1
    ws.merge_cells(start_row=row_idx, start_column=1, end_row=row_idx, end_column=last_col)
    pied_addr_cell = ws.cell(row=row_idx, column=1, value=pied_adresse)
    pied_addr_cell.font = Font(size=7)
    pied_addr_cell.alignment = Alignment(wrap_text=True, horizontal='left')
    row_idx += 1

    ws.column_dimensions['A'].width = 5
    ws.column_dimensions['B'].width = 38
    ws.column_dimensions['C'].width = 16
    ws.column_dimensions['D'].width = 14
    ws.column_dimensions['E'].width = 14
    ws.column_dimensions['F'].width = 14

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    filename = f"fiche_paie_{formateur.numerobadge or formateur.pk}.xlsx"
    response = HttpResponse(
        buffer,
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def export_finance_synthese_pdf(request):
    """Export PDF consolidé : synthèse finance de tous les formateurs (période / filtres)."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.units import cm
    from reportlab.lib.enums import TA_CENTER, TA_RIGHT
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

    if not _check_finance_export_access(request):
        return Response({'detail': 'Accès réservé à la direction et à la finance.'}, status=403)

    ctx, err = _finance_synthese_export_context(request)
    if err:
        return Response({'detail': err}, status=400)

    rows = ctx['rows']
    totals = ctx['totals']
    export_opts = ctx['export']
    afficher_montants = export_opts['afficher_montants']
    include_sensitive = request.user.role == 'FINANCE'

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=landscape(A4),
        leftMargin=0.8 * cm, rightMargin=0.8 * cm,
        topMargin=1.0 * cm, bottomMargin=1.0 * cm,
    )
    styles = getSampleStyleSheet()
    style_title = ParagraphStyle(
        'FinSynTitle', parent=styles['Title'],
        fontSize=14, textColor=colors.HexColor(CI_GREEN_DARK),
        alignment=TA_CENTER, spaceAfter=3,
    )
    style_sub = ParagraphStyle(
        'FinSynSub', parent=styles['Normal'],
        fontSize=9, textColor=colors.HexColor('#444444'),
        alignment=TA_CENTER, spaceAfter=2,
    )
    style_stats = ParagraphStyle(
        'FinSynStats', parent=styles['Normal'],
        fontSize=9, textColor=colors.HexColor(CI_GREEN_DARK), spaceAfter=6,
    )
    cell_normal = ParagraphStyle('FinSynCell', parent=styles['Normal'], fontSize=7, leading=9)
    cell_center = ParagraphStyle('FinSynCellC', parent=styles['Normal'], fontSize=7, leading=9, alignment=TA_CENTER)
    cell_header = ParagraphStyle(
        'FinSynHdr', parent=styles['Normal'],
        fontSize=8, leading=10, alignment=TA_CENTER,
        textColor=colors.white, fontName='Helvetica-Bold',
    )

    def _p(text, center=False, hdr=False):
        s = cell_header if hdr else (cell_center if center else cell_normal)
        return Paragraph(str(text).replace('&', '&amp;'), s)

    elements = []
    for line in (export_opts.get('entete_ligne1'), export_opts.get('entete_ligne2'), export_opts.get('organisme')):
        if line:
            elements.append(Paragraph(line, style_sub))
    if export_opts.get('adresse'):
        elements.append(Paragraph(export_opts['adresse'].replace('\n', '<br/>'), style_sub))
    elements.append(Spacer(1, 0.15 * cm))
    elements.append(Paragraph(export_opts.get('titre_document') or 'FICHE DE PAIE GLOBALE', style_title))
    elements.append(Paragraph(f"Réf. : <b>{export_opts.get('reference', '-')}</b>", style_sub))
    elements.append(Paragraph(f"Période : <b>{ctx['periode_label']}</b>", style_sub))
    elements.append(Paragraph(
        'Facturation : tarif horaire selon le type de formation (cycle) pour chaque module.',
        style_sub,
    ))
    elements.append(Spacer(1, 0.15 * cm))

    stats_parts = [
        f"Formateurs : <b>{totals['formateurs_count']}</b> ({totals['formateurs_actifs']} actifs)",
        f"Séances : <b>{totals['sessions_count']}</b>",
        f"Réalisé : <b>{totals['total_realized']}</b> min ({totals['total_heures_realisees']} h)",
    ]
    if afficher_montants:
        stats_parts.append(f"Total à verser : <b>{totals['montant_total']:,.0f}</b> FCFA")
    elements.append(Paragraph(' &nbsp;|&nbsp; '.join(stats_parts), style_stats))

    headers = _finance_synthese_table_headers(afficher_montants, include_sensitive)
    data = [[_p(h, hdr=True) for h in headers]]
    for row in rows:
        vals = _finance_synthese_table_row(row, afficher_montants, include_sensitive)
        data.append([_p(v, center=(i >= 6)) for i, v in enumerate(vals)])
    total_vals = ['TOTAL', '', '', '', '', '', totals['sessions_count'], totals['total_planned'],
                  totals['total_realized'], totals['total_heures_realisees'], '']
    if afficher_montants:
        total_vals.append(totals['montant_total'])
    if include_sensitive:
        total_vals.extend(['', ''])
    data.append([_p(v, center=(i >= 6)) for i, v in enumerate(total_vals)])

    col_count = len(headers)
    base_w = [1.4, 1.8, 1.8, 2.2, 1.2, 1.6, 1.0, 1.3, 1.3, 1.2, 1.0]
    if afficher_montants:
        base_w.append(1.6)
    if include_sensitive:
        base_w.extend([1.8, 1.8])
    while len(base_w) < col_count:
        base_w.append(1.5)
    col_widths = [w * cm for w in base_w[:col_count]]

    table = Table(data, repeatRows=1, colWidths=col_widths)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor(CI_GREEN_DARK)),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 7),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CCCCCC')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -2), [colors.white, colors.HexColor(CI_LIGHT_GREEN)]),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor(CI_LIGHT_ORANGE)),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
    ]))
    elements.append(table)
    elements.append(Spacer(1, 0.3 * cm))

    if export_opts.get('signataire_nom') or export_opts.get('signataire_fonction'):
        sig_style = ParagraphStyle(
            'FinSynSig', parent=styles['Normal'], fontSize=9,
            alignment=TA_RIGHT, textColor=colors.HexColor('#333333'),
        )
        sig_lines = []
        if export_opts.get('signataire_fonction'):
            sig_lines.append(export_opts['signataire_fonction'])
        if export_opts.get('signataire_nom'):
            sig_lines.append(f"<b>{export_opts['signataire_nom']}</b>")
        elements.append(Paragraph('<br/>'.join(sig_lines), sig_style))

    foot = f"Exporté le {datetime.now().strftime('%d/%m/%Y à %H:%M')}"
    if export_opts.get('mention_legale'):
        foot += f"<br/>{export_opts['mention_legale']}"
    elements.append(Paragraph(
        foot,
        ParagraphStyle('FinSynFoot', parent=styles['Normal'], fontSize=7, textColor=colors.HexColor('#999999')),
    ))

    doc.build(elements)
    buffer.seek(0)
    response = HttpResponse(buffer, content_type='application/pdf')
    response['Content-Disposition'] = 'attachment; filename="fiche_paie_globale.pdf"'
    return response


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def export_finance_synthese_excel(request):
    """Export Excel consolidé : synthèse finance de tous les formateurs."""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter

    if not _check_finance_export_access(request):
        return Response({'detail': 'Accès réservé à la direction et à la finance.'}, status=403)

    ctx, err = _finance_synthese_export_context(request)
    if err:
        return Response({'detail': err}, status=400)

    rows = ctx['rows']
    totals = ctx['totals']
    export_opts = ctx['export']
    afficher_montants = export_opts['afficher_montants']
    include_sensitive = request.user.role == 'FINANCE'
    headers = _finance_synthese_table_headers(afficher_montants, include_sensitive)
    last_col = len(headers)

    wb = Workbook()
    ws = wb.active
    ws.title = 'Synthèse formateurs'

    green_fill = PatternFill(start_color='1A68AC', end_color='1A68AC', fill_type='solid')
    light_green_fill = PatternFill(start_color='E8EFF5', end_color='E8EFF5', fill_type='solid')
    orange_fill = PatternFill(start_color='F5B100', end_color='F5B100', fill_type='solid')
    total_fill = PatternFill(start_color='FFF8E0', end_color='FFF8E0', fill_type='solid')
    header_font = Font(bold=True, color='FFFFFF', size=10)
    thin_border = Border(
        left=Side(style='thin', color='CCCCCC'),
        right=Side(style='thin', color='CCCCCC'),
        top=Side(style='thin', color='CCCCCC'),
        bottom=Side(style='thin', color='CCCCCC'),
    )

    row_idx = 1
    for line in (export_opts.get('entete_ligne1'), export_opts.get('entete_ligne2'), export_opts.get('organisme')):
        if line:
            ws.merge_cells(start_row=row_idx, start_column=1, end_row=row_idx, end_column=last_col)
            ws.cell(row=row_idx, column=1, value=line).alignment = Alignment(horizontal='center')
            row_idx += 1
    row_idx += 1
    ws.merge_cells(start_row=row_idx, start_column=1, end_row=row_idx, end_column=last_col)
    ws.cell(row=row_idx, column=1, value=export_opts.get('titre_document'))
    ws.cell(row=row_idx, column=1).font = Font(bold=True, size=13, color='1A68AC')
    ws.cell(row=row_idx, column=1).alignment = Alignment(horizontal='center')
    row_idx += 1
    ws.merge_cells(start_row=row_idx, start_column=1, end_row=row_idx, end_column=last_col)
    ws.cell(row=row_idx, column=1, value=f"Réf. {export_opts.get('reference')} — Période : {ctx['periode_label']}")
    ws.cell(row=row_idx, column=1).alignment = Alignment(horizontal='center')
    row_idx += 2

    synth = [
        ('Formateurs', totals['formateurs_count']),
        ('Actifs', totals['formateurs_actifs']),
        ('Séances', totals['sessions_count']),
        ('Réalisé (min)', totals['total_realized']),
        ('Heures réalisées', totals['total_heures_realisees']),
    ]
    if afficher_montants:
        synth.append(('Total à verser (FCFA)', totals['montant_total']))
    for col, (label, val) in enumerate(synth, start=1):
        ws.cell(row=row_idx, column=col, value=label).fill = orange_fill
        ws.cell(row=row_idx, column=col).font = Font(bold=True, color='FFFFFF', size=9)
        ws.cell(row=row_idx + 1, column=col, value=val).fill = orange_fill
        ws.cell(row=row_idx + 1, column=col).font = Font(bold=True, color='FFFFFF', size=9)
        ws.cell(row=row_idx, column=col).alignment = Alignment(horizontal='center')
        ws.cell(row=row_idx + 1, column=col).alignment = Alignment(horizontal='center')
    row_idx += 4

    start_row = row_idx
    for idx, h in enumerate(headers, 1):
        cell = ws.cell(row=start_row, column=idx, value=h)
        cell.font = header_font
        cell.fill = green_fill
        cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
        cell.border = thin_border

    for i, row in enumerate(rows, start=1):
        row_num = start_row + i
        values = _finance_synthese_table_row(row, afficher_montants, include_sensitive)
        for col, val in enumerate(values, start=1):
            cell = ws.cell(row=row_num, column=col, value=val)
            cell.border = thin_border
            if col >= 7:
                cell.alignment = Alignment(horizontal='center', vertical='center')
            if i % 2 == 0:
                cell.fill = light_green_fill

    total_row = start_row + len(rows) + 1
    total_values = _finance_synthese_table_row(
        {
            'numerobadge': 'TOTAL', 'nom': '', 'prenom': '', 'modules_dispenses': '',
            'grades': '', 'groupes': '',
            'sessions_count': totals['sessions_count'],
            'total_duree_minutes': totals['total_planned'],
            'total_duree_realisee_minutes': totals['total_realized'],
            'montant_total_realise': totals['montant_total'],
            'statistiques': {},
        },
        afficher_montants,
        include_sensitive,
    )
    total_values[0] = 'TOTAL'
    for col, val in enumerate(total_values, start=1):
        cell = ws.cell(row=total_row, column=col, value=val)
        cell.border = thin_border
        cell.fill = total_fill
        cell.font = Font(bold=True)
        if col >= 7:
            cell.alignment = Alignment(horizontal='center')

    col_widths = [12, 14, 14, 32, 10, 14, 8, 12, 12, 12, 8]
    if afficher_montants:
        col_widths.append(14)
    if include_sensitive:
        col_widths.extend([16, 16])
    for idx, width in enumerate(col_widths, start=1):
        ws.column_dimensions[get_column_letter(idx)].width = width

    footer_row = total_row + 2
    ws.merge_cells(start_row=footer_row, start_column=1, end_row=footer_row, end_column=last_col)
    foot = f"Exporté le {datetime.now().strftime('%d/%m/%Y à %H:%M')}"
    if export_opts.get('mention_legale'):
        foot += f" — {export_opts['mention_legale']}"
    ws.cell(row=footer_row, column=1, value=foot)
    ws.cell(row=footer_row, column=1).font = Font(size=8, color='999999', italic=True)
    ws.cell(row=footer_row, column=1).alignment = Alignment(horizontal='right', wrap_text=True)

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    response = HttpResponse(
        buffer,
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    response['Content-Disposition'] = 'attachment; filename="fiche_paie_globale.xlsx"'
    return response


def _finance_encadrants_export_context(request):
    from formations.period_filter import parse_period_from_request, periode_api_payload
    from formations.api_views import _finance_secretariat_id_from_request
    from formations.finance_encadrants import finance_encadrants_report
    from formations.duration_format import format_duration_minutes

    period = parse_period_from_request(request)
    if period.get('error'):
        return None, period.get('detail') or 'Période invalide.'

    secretariat_id = _finance_secretariat_id_from_request(request)
    report = finance_encadrants_report(
        date_debut=period['date_debut'],
        date_fin=period['date_fin'],
        secretariat_id=secretariat_id,
    )
    settings = _finance_export_settings()
    prefix = (settings.export_reference_prefix or 'EFI').strip() or 'EFI'
    ref_date = datetime.now().strftime('%Y%m%d')
    export_opts = {
        'titre_document': 'LISTE DES ENCADRANTS — VOLUMES HORAIRES',
        'entete_ligne1': settings.export_entete_ligne1 or '',
        'entete_ligne2': settings.export_entete_ligne2 or '',
        'organisme': settings.export_organisme or '',
        'adresse': settings.export_adresse or '',
        'reference': f'{prefix}-ENC-{ref_date}',
        'mention_legale': settings.export_mention_legale or '',
        'signataire_nom': settings.export_signataire_nom or '',
        'signataire_fonction': settings.export_signataire_fonction or '',
    }
    periode_label = periode_api_payload(
        period['date_debut'], period['date_fin'], period['meta'], None, None,
    ).get('periode_label') or 'Toutes périodes'

    flat_rows = []
    for block in report['encadrants']:
        for ligne in block['lignes']:
            flat_rows.append({
                'encadrant': block['encadrant_label'] or block['encadrant_username'],
                'groupe': ligne['groupe'],
                'grade': ligne['grade'],
                'module': ligne['module_intitule'],
                'formation': ligne['formation_intitule'],
                'planned_minutes': ligne['planned_minutes'],
                'realized_minutes': ligne['realized_minutes'],
                'planned_label': format_duration_minutes(ligne['planned_minutes']),
                'realized_label': format_duration_minutes(ligne['realized_minutes']),
                'is_subtotal': False,
                'is_header': False,
            })
        flat_rows.append({
            'encadrant': block['encadrant_label'] or block['encadrant_username'],
            'groupe': 'Sous-total',
            'grade': '',
            'module': '',
            'formation': '',
            'planned_minutes': block['sous_total']['planned_minutes'],
            'realized_minutes': block['sous_total']['realized_minutes'],
            'planned_label': format_duration_minutes(block['sous_total']['planned_minutes']),
            'realized_label': format_duration_minutes(block['sous_total']['realized_minutes']),
            'is_subtotal': True,
            'is_header': False,
        })

    totals = report['totaux']
    totals['planned_label'] = format_duration_minutes(totals['planned_minutes'])
    totals['realized_label'] = format_duration_minutes(totals['realized_minutes'])

    return {
        'rows': flat_rows,
        'encadrants': report['encadrants'],
        'totals': totals,
        'export': export_opts,
        'periode_label': periode_label,
    }, None


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def export_finance_encadrants_pdf(request):
    """Export PDF : liste encadrants (groupe, volume planifié, volume réalisé)."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.units import cm
    from reportlab.lib.enums import TA_CENTER, TA_RIGHT
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

    if not _check_finance_export_access(request):
        return Response({'detail': 'Accès réservé à la direction et à la finance.'}, status=403)

    ctx, err = _finance_encadrants_export_context(request)
    if err:
        return Response({'detail': err}, status=400)

    export_opts = ctx['export']
    totals = ctx['totals']

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=landscape(A4),
        leftMargin=0.8 * cm, rightMargin=0.8 * cm,
        topMargin=1.0 * cm, bottomMargin=1.0 * cm,
    )
    styles = getSampleStyleSheet()
    style_title = ParagraphStyle(
        'EncTitle', parent=styles['Title'],
        fontSize=14, textColor=colors.HexColor(CI_GREEN_DARK),
        alignment=TA_CENTER, spaceAfter=3,
    )
    style_sub = ParagraphStyle(
        'EncSub', parent=styles['Normal'],
        fontSize=9, textColor=colors.HexColor('#444444'),
        alignment=TA_CENTER, spaceAfter=2,
    )
    cell_normal = ParagraphStyle('EncCell', parent=styles['Normal'], fontSize=8, leading=10)
    cell_header = ParagraphStyle(
        'EncHdr', parent=styles['Normal'],
        fontSize=9, leading=11, alignment=TA_CENTER,
        textColor=colors.white, fontName='Helvetica-Bold',
    )

    def _p(text, hdr=False):
        s = cell_header if hdr else cell_normal
        return Paragraph(str(text).replace('&', '&amp;'), s)

    elements = []
    for line in (export_opts.get('entete_ligne1'), export_opts.get('entete_ligne2'), export_opts.get('organisme')):
        if line:
            elements.append(Paragraph(line, style_sub))
    elements.append(Spacer(1, 0.15 * cm))
    elements.append(Paragraph(export_opts.get('titre_document'), style_title))
    elements.append(Paragraph(f"Réf. : <b>{export_opts.get('reference', '-')}</b>", style_sub))
    elements.append(Paragraph(f"Période : <b>{ctx['periode_label']}</b>", style_sub))
    elements.append(Spacer(1, 0.2 * cm))

    headers = ['Encadrant', 'Groupe', 'Grade', 'Module', 'Planifié', 'Réalisé']
    data = [[_p(h, hdr=True) for h in headers]]
    for row in ctx['rows']:
        data.append([
            _p(row['encadrant']),
            _p(row['groupe']),
            _p(row['grade'] or '—'),
            _p(row['module'] or '—'),
            _p(row['planned_label']),
            _p(row['realized_label']),
        ])
    data.append([
        _p('TOTAL'),
        _p(''),
        _p(''),
        _p(f"{totals['encadrants_count']} encadrant(s)"),
        _p(totals['planned_label']),
        _p(totals['realized_label']),
    ])

    col_widths = [3.5 * cm, 2.5 * cm, 1.5 * cm, 5.5 * cm, 2.2 * cm, 2.2 * cm]
    table = Table(data, repeatRows=1, colWidths=col_widths)
    row_styles = [
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor(CI_GREEN_DARK)),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CCCCCC')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor(CI_LIGHT_ORANGE)),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
    ]
    for i, row in enumerate(ctx['rows'], start=1):
        if row.get('is_subtotal'):
            row_styles.append(('BACKGROUND', (0, i), (-1, i), colors.HexColor('#E3F2FD')))
            row_styles.append(('FONTNAME', (0, i), (-1, i), 'Helvetica-Bold'))
    table.setStyle(TableStyle(row_styles))
    elements.append(table)

    foot = f"Exporté le {datetime.now().strftime('%d/%m/%Y à %H:%M')}"
    elements.append(Spacer(1, 0.3 * cm))
    elements.append(Paragraph(
        foot,
        ParagraphStyle('EncFoot', parent=styles['Normal'], fontSize=7, textColor=colors.HexColor('#999999')),
    ))

    doc.build(elements)
    buffer.seek(0)
    response = HttpResponse(buffer, content_type='application/pdf')
    response['Content-Disposition'] = 'attachment; filename="liste_encadrants.pdf"'
    return response


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def export_finance_encadrants_excel(request):
    """Export Excel : liste encadrants (groupe, volume planifié, volume réalisé)."""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter

    if not _check_finance_export_access(request):
        return Response({'detail': 'Accès réservé à la direction et à la finance.'}, status=403)

    ctx, err = _finance_encadrants_export_context(request)
    if err:
        return Response({'detail': err}, status=400)

    export_opts = ctx['export']
    totals = ctx['totals']
    headers = ['Encadrant', 'Groupe', 'Grade', 'Module', 'Formation', 'Planifié', 'Réalisé']
    last_col = len(headers)

    wb = Workbook()
    ws = wb.active
    ws.title = 'Encadrants'

    green_fill = PatternFill(start_color='1A68AC', end_color='1A68AC', fill_type='solid')
    subtotal_fill = PatternFill(start_color='E3F2FD', end_color='E3F2FD', fill_type='solid')
    total_fill = PatternFill(start_color='FFF8E0', end_color='FFF8E0', fill_type='solid')
    header_font = Font(bold=True, color='FFFFFF', size=10)
    thin_border = Border(
        left=Side(style='thin', color='CCCCCC'),
        right=Side(style='thin', color='CCCCCC'),
        top=Side(style='thin', color='CCCCCC'),
        bottom=Side(style='thin', color='CCCCCC'),
    )

    row_idx = 1
    for line in (export_opts.get('entete_ligne1'), export_opts.get('entete_ligne2'), export_opts.get('organisme')):
        if line:
            ws.merge_cells(start_row=row_idx, start_column=1, end_row=row_idx, end_column=last_col)
            ws.cell(row=row_idx, column=1, value=line).alignment = Alignment(horizontal='center')
            row_idx += 1
    row_idx += 1
    ws.merge_cells(start_row=row_idx, start_column=1, end_row=row_idx, end_column=last_col)
    ws.cell(row=row_idx, column=1, value=export_opts.get('titre_document'))
    ws.cell(row=row_idx, column=1).font = Font(bold=True, size=13, color='1A68AC')
    ws.cell(row=row_idx, column=1).alignment = Alignment(horizontal='center')
    row_idx += 1
    ws.merge_cells(start_row=row_idx, start_column=1, end_row=row_idx, end_column=last_col)
    ws.cell(row=row_idx, column=1, value=f"Période : {ctx['periode_label']}")
    ws.cell(row=row_idx, column=1).alignment = Alignment(horizontal='center')
    row_idx += 2

    for col, h in enumerate(headers, start=1):
        cell = ws.cell(row=row_idx, column=col, value=h)
        cell.fill = green_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal='center', vertical='center')
        cell.border = thin_border
    row_idx += 1

    for row in ctx['rows']:
        values = [
            row['encadrant'],
            row['groupe'],
            row['grade'] or '—',
            row['module'] or '—',
            row['formation'] or '—',
            row['planned_label'],
            row['realized_label'],
        ]
        for col, val in enumerate(values, start=1):
            cell = ws.cell(row=row_idx, column=col, value=val)
            cell.border = thin_border
            if row.get('is_subtotal'):
                cell.fill = subtotal_fill
                cell.font = Font(bold=True)
        row_idx += 1

    total_values = [
        'TOTAL', '', '', f"{totals['encadrants_count']} encadrant(s)", '',
        totals['planned_label'], totals['realized_label'],
    ]
    for col, val in enumerate(total_values, start=1):
        cell = ws.cell(row=row_idx, column=col, value=val)
        cell.border = thin_border
        cell.fill = total_fill
        cell.font = Font(bold=True)
    row_idx += 2
    ws.merge_cells(start_row=row_idx, start_column=1, end_row=row_idx, end_column=last_col)
    ws.cell(row=row_idx, column=1, value=f"Exporté le {datetime.now().strftime('%d/%m/%Y à %H:%M')}")
    ws.cell(row=row_idx, column=1).font = Font(size=8, color='999999', italic=True)
    ws.cell(row=row_idx, column=1).alignment = Alignment(horizontal='right')

    col_widths = [22, 14, 8, 24, 22, 12, 12]
    for idx, width in enumerate(col_widths, start=1):
        ws.column_dimensions[get_column_letter(idx)].width = width

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    response = HttpResponse(
        buffer,
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    response['Content-Disposition'] = 'attachment; filename="liste_encadrants.xlsx"'
    return response


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def export_liste_classe_pdf(request):
    """Export PDF : liste de classe auditeurs (par groupe)."""
    from .participants_list_export import export_liste_classe_pdf, liste_classe_filename

    ctx, err = _liste_classe_export_context(request)
    if err:
        return err

    try:
        buffer = export_liste_classe_pdf(ctx['blocks'], ctx['meta'])
    except RuntimeError as exc:
        return Response({'detail': str(exc)}, status=503)

    filename = liste_classe_filename(ctx['blocks'], 'pdf')
    response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def export_liste_classe_excel(request):
    """Export Excel : liste de classe auditeurs (une feuille par groupe)."""
    from .participants_list_export import export_liste_classe_excel, liste_classe_filename

    ctx, err = _liste_classe_export_context(request)
    if err:
        return err

    try:
        buffer = export_liste_classe_excel(ctx['blocks'], ctx['meta'])
    except RuntimeError as exc:
        return Response({'detail': str(exc)}, status=503)

    filename = liste_classe_filename(ctx['blocks'], 'xlsx')
    response = HttpResponse(
        buffer.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response
