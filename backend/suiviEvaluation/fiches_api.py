"""Fiches individuelles auditeur et enseignant (écrans `/.../fiche`).

Constat d'audit : les écrans « fiche étudiant » et « fiche enseignant » sont
routés et accessibles (`/auditeurs/:id/formations/:id/fiche`,
`/formateurs/:id/modules/:id/fiche`), mais leurs adresses `/suiviEvaluation/…`
ne correspondaient à **aucun montage Django** — l'application est montée sous
`/api/evaluations/` — et aucune vue ne les servait : l'écran affichait
« Erreur chargement fiche ».

Principes tenus ici :

* aucune règle pédagogique n'est réinventée : moyennes, assiduité et verdicts
  proviennent du moteur `suiviEvaluation.services` (mêmes seuils, mêmes
  pondérations que le reste de l'application) et des instantanés
  `MoyenneModule` / `DecisionPedagogique` ;
* le verdict **opérationnel** (`DecisionPedagogique`) n'est jamais présenté
  comme la décision officielle : celle-ci reste `jurys.DecisionJury`, exposée
  séparément (`decision_officielle`) via `jurys.services.decision_officielle_pour` ;
* une donnée inconnue reste `None` (affichée « — ») : elle n'est pas estimée.
"""
import io
from datetime import datetime

from django.db.models import Avg
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from formations.models import Formateur, Formation, Module, ModuleParticipant, Participant, SessionModule

from .models import DecisionPedagogique, MoyenneModule, ReponseQuestion
from .permissions import IsConsultationFiche, IsFicheExport
from .services import (
    _heures_prevues_module,
    calculer_moyenne_generale,
    resume_module_participant,
)


# ── Sérialisation ───────────────────────────────────────────────────────────

def _decimal(value):
    return None if value is None else float(value)


def _date(value):
    return value.isoformat() if value else None


def _verdict_operationnel(decision):
    """Verdict interne (`DecisionPedagogique`), étiqueté comme tel."""
    if decision is None:
        return None
    return {
        'nature': 'pedagogique',
        'decision': decision.decision,
        'decision_display': decision.get_decision_display(),
        'mention': decision.mention,
        'mention_display': decision.get_mention_display() if decision.mention else '',
        'moyenne_generale': _decimal(decision.moyenne_generale),
        'taux_presence': _decimal(decision.taux_presence),
        'generee_auto': decision.generee_auto,
        'validee_le': _date(decision.validee_le),
        'appreciation': decision.appreciation or '',
        'maj_le': _date(decision.updated_at),
    }


def _decision_officielle(participant):
    """Décision officielle du jury (`jurys.DecisionJury`) ou `None`."""
    from jurys.services import decision_officielle_pour

    decision = decision_officielle_pour(participant)
    if decision is None:
        return None
    return {
        'nature': 'officielle',
        'reference': str(decision.pk),
        'decision': decision.decision,
        'decision_display': decision.get_decision_display(),
        'mention': decision.mention,
        'credits_acquis': decision.credits_acquis,
        'moyenne_generale': _decimal(decision.moyenne_generale),
        'decide_le': _date(decision.decide_le),
        'session': str(decision.session_id),
    }


# ── Fiche auditeur ──────────────────────────────────────────────────────────

def _auditeur_et_formation(participant_pk, formation_pk):
    formation = get_object_or_404(Formation, pk=formation_pk)
    participant = get_object_or_404(Participant, pk=participant_pk)
    inscrit = ModuleParticipant.objects.filter(
        participant=participant, module__formation=formation,
    ).exists()
    if not inscrit:
        # Une fiche ne doit pas mélanger deux dossiers : un auditeur rattaché à
        # une autre formation est une erreur d'adresse, pas une fiche vide.
        raise Http404('Auditeur non inscrit à cette formation.')
    return participant, formation


def _suivi_modules(participant, formation):
    module_ids = (
        ModuleParticipant.objects
        .filter(participant=participant, module__formation=formation)
        .values_list('module_id', flat=True)
    )
    modules = list(Module.objects.filter(id__in=module_ids).order_by('ordre', 'intitule'))
    instantanes = {
        mm.module_id: mm
        for mm in MoyenneModule.objects.filter(participant=participant, module_id__in=module_ids)
    }

    suivi = []
    for module in modules:
        synchro = instantanes.get(module.id)
        if synchro is not None:
            donnees = {
                'moyenne': _decimal(synchro.moyenne),
                'nb_notes': synchro.nb_notes,
                'heures_presence': _decimal(synchro.heures_presence),
                'heures_prevues': _decimal(synchro.heures_prevues),
                'taux_presence': _decimal(synchro.taux_presence),
                'source': 'instantane',
            }
        else:
            # Aucun instantané : on interroge le moteur commun, jamais une
            # formule locale.
            calcule = resume_module_participant(module, participant)
            donnees = {
                'moyenne': calcule['moyenne'],
                'nb_notes': calcule['nb_notes'],
                'heures_presence': calcule['heures_presence'],
                'heures_prevues': calcule['heures_prevues'],
                'taux_presence': calcule['taux_presence'],
                'source': 'calcule',
            }

        suivi.append({
            'id': module.id,
            'module_intitule': module.intitule,
            'nb_epreuves': donnees['nb_notes'],
            'heures_presence': donnees['heures_presence'],
            'heures_prevues': donnees['heures_prevues'],
            'taux_presence': donnees['taux_presence'],
            'moyenne_module': donnees['moyenne'],
            'source': donnees['source'],
        })
    return suivi


def _classement(participant, formation):
    """Rang de l'auditeur parmi les verdicts pédagogiques de la formation."""
    rangs = list(
        DecisionPedagogique.objects
        .filter(formation=formation, moyenne_generale__isnull=False)
        .order_by('-moyenne_generale', 'participant_id')
        .values_list('participant_id', flat=True)
    )
    if participant.id not in rangs:
        return {'rang': None, 'sur': len(rangs), 'source': 'decisions_pedagogiques'}
    return {'rang': rangs.index(participant.id) + 1, 'sur': len(rangs),
            'source': 'decisions_pedagogiques'}


def construire_fiche_auditeur(participant, formation):
    veredict = (
        DecisionPedagogique.objects
        .filter(participant=participant, formation=formation)
        .select_related('validee_par')
        .order_by('-updated_at')
        .first()
    )
    moyenne = _decimal(veredict.moyenne_generale) if veredict else calculer_moyenne_generale(
        participant, formation,
    )
    classement = _classement(participant, formation)
    return {
        'participant_id': participant.id,
        'matricule': participant.matricule,
        'participant_nom': f'{participant.nom} {participant.prenom}'.strip(),
        'formation_id': formation.id,
        'formation_libelle': formation.formation,
        'moyenne_generale': moyenne,
        'moyenne_generale_source': 'decision_pedagogique' if veredict else 'moteur_calcule',
        'classement': classement['rang'],
        'classement_sur': classement['sur'],
        'classement_source': classement['source'],
        'decision_finale_detail': _verdict_operationnel(veredict),
        'decision_officielle': _decision_officielle(participant),
        'suivi_modules': _suivi_modules(participant, formation),
    }


@api_view(['GET'])
@permission_classes([IsConsultationFiche])
def fiche_auditeur(request, participant_pk, formation_pk):
    participant, formation = _auditeur_et_formation(participant_pk, formation_pk)
    return Response(construire_fiche_auditeur(participant, formation))


@api_view(['GET'])
@permission_classes([IsFicheExport])
def exporter_fiche_auditeur(request, participant_pk, formation_pk, fmt):
    participant, formation = _auditeur_et_formation(participant_pk, formation_pk)
    fiche = construire_fiche_auditeur(participant, formation)
    nom = f'fiche_auditeur_{participant.matricule}_{formation.id}'
    entetes = ['Module', 'Épreuves', 'Heures présence', 'Heures prévues',
               'Taux présence (%)', 'Moyenne']
    lignes = [
        [m['module_intitule'], m['nb_epreuves'], m['heures_presence'],
         m['heures_prevues'], m['taux_presence'], m['moyenne_module']]
        for m in fiche['suivi_modules']
    ]
    resume = [
        ['Auditeur', fiche['participant_nom']],
        ['Matricule', fiche['matricule']],
        ['Formation', fiche['formation_libelle']],
        ['Moyenne générale', fiche['moyenne_generale']],
        ['Classement', fiche['classement'] if fiche['classement'] else '—'],
        ['Verdict pédagogique', (fiche['decision_finale_detail'] or {}).get('decision_display', '—')],
        ['Décision officielle', (fiche['decision_officielle'] or {}).get('decision_display', '—')],
    ]
    return _reponse_export(fmt, f'{nom}', 'Fiche auditeur', resume, entetes, lignes)


# ── Fiche enseignant ────────────────────────────────────────────────────────

def _module_et_formateur(formateur_pk, module_pk):
    formateur = get_object_or_404(Formateur, pk=formateur_pk)
    module = get_object_or_404(Module.objects.select_related('formation'), pk=module_pk)
    if module.formateur_id != formateur.id:
        raise Http404("Ce module n'est pas affecté à cet enseignant.")
    return formateur, module


def _heures_realisees(module, maintenant=None):
    """Heures réellement tenues sur le module, d'après les séances.

    Une séance terminée compte sa durée réelle ; une séance démarrée mais non
    clôturée compte sa durée **prévue** (on ne crédite pas un temps non
    constaté). Les séances non démarrées ne comptent pas.
    """
    maintenant = maintenant or timezone.now()
    total = 0.0
    for session in SessionModule.objects.filter(module=module, demarree_le__isnull=False):
        if session.terminee_le and session.demarree_le:
            total += (session.terminee_le - session.demarree_le).total_seconds() / 3600
        elif session.heure_debut_prevue and session.heure_fin_prevue:
            debut = datetime.combine(session.date_journee, session.heure_debut_prevue)
            fin = datetime.combine(session.date_journee, session.heure_fin_prevue)
            if fin > debut:
                total += (fin - debut).total_seconds() / 3600
    return round(total, 2)


def _satisfaction(module):
    """Moyenne des notes 1–5 des questionnaires rattachés au module."""
    agregat = (
        ReponseQuestion.objects
        .filter(soumission__questionnaire__module=module, note__isnull=False)
        .aggregate(moyenne=Avg('note'))
    )
    if agregat['moyenne'] is None:
        return None, 0
    reponses = ReponseQuestion.objects.filter(
        soumission__questionnaire__module=module, note__isnull=False,
    ).count()
    return round(float(agregat['moyenne']), 2), reponses


def construire_fiche_formateur(formateur, module):
    heures_prevues = _decimal(_heures_prevues_module(module))
    if heures_prevues is None:
        heures_prevues = _decimal(module.duree_prevue_heures)
    heures_effectuees = _heures_realisees(module)
    taux = (
        MoyenneModule.objects
        .filter(module=module, taux_presence__isnull=False)
        .aggregate(moyenne=Avg('taux_presence'))
    )['moyenne']
    satisfaction, nb_notes = _satisfaction(module)
    return {
        'formateur_id': formateur.id,
        'formateur_nom': f'{formateur.nom} {formateur.prenom}'.strip(),
        'module_id': module.id,
        'module_intitule': module.intitule,
        'formation_libelle': module.formation.formation if module.formation_id else '',
        'heures_prevues': heures_prevues,
        'heures_effectuees': heures_effectuees,
        'taux_presence': _decimal(taux),
        'satisfaction_auditeurs': satisfaction,
        'satisfaction_reponses': nb_notes,
        'appreciation_pedagogique': '',
        'appreciation_source': None,
    }


@api_view(['GET'])
@permission_classes([IsConsultationFiche])
def fiche_formateur(request, formateur_pk, module_pk):
    formateur, module = _module_et_formateur(formateur_pk, module_pk)
    return Response(construire_fiche_formateur(formateur, module))


@api_view(['GET'])
@permission_classes([IsFicheExport])
def exporter_fiche_formateur(request, formateur_pk, module_pk, fmt):
    formateur, module = _module_et_formateur(formateur_pk, module_pk)
    fiche = construire_fiche_formateur(formateur, module)
    resume = [
        ['Enseignant', fiche['formateur_nom']],
        ['Module', fiche['module_intitule']],
        ['Formation', fiche['formation_libelle']],
        ['Heures prévues', fiche['heures_prevues']],
        ['Heures effectuées', fiche['heures_effectuees']],
        ['Taux de présence (%)', fiche['taux_presence']],
        ['Satisfaction (note /5)', fiche['satisfaction_auditeurs']],
        ['Appréciation pédagogique', fiche['appreciation_pedagogique'] or '—'],
    ]
    nom = f'fiche_enseignant_{formateur.id}_{module.id}'
    return _reponse_export(fmt, nom, 'Fiche enseignant', resume, [], [])


# ── Exports PDF / XLSX ──────────────────────────────────────────────────────

def _valeur(value):
    if value is None or value == '':
        return '—'
    if isinstance(value, float):
        return f'{value:.2f}'.rstrip('0').rstrip('.').replace('.', ',')
    return str(value)


def _reponse_export(fmt, nom, titre, resume, entetes, lignes):
    fmt = (fmt or '').lower()
    if fmt not in ('pdf', 'xlsx'):
        raise Http404('Format d’export inconnu (pdf ou xlsx).')
    if fmt == 'pdf':
        contenu = _pdf(titre, resume, entetes, lignes)
        type_mime = 'application/pdf'
    else:
        contenu = _xlsx(titre, resume, entetes, lignes)
        type_mime = ('application/vnd.openxmlformats-officedocument'
                     '.spreadsheetml.sheet')
    reponse = HttpResponse(contenu, content_type=type_mime)
    reponse['Content-Disposition'] = f'attachment; filename="{nom}.{fmt}"'
    return reponse


def _pdf(titre, resume, entetes, lignes):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    tampon = io.BytesIO()
    doc = SimpleDocTemplate(
        tampon, pagesize=A4, title=titre,
        leftMargin=1.6 * cm, rightMargin=1.6 * cm, topMargin=1.5 * cm, bottomMargin=1.5 * cm,
    )
    styles = getSampleStyleSheet()
    flux = [
        Paragraph("INSTITUT NATIONAL DE LA JEUNESSE ET DES SPORTS (INJS)", styles['Title']),
        Paragraph(titre, styles['Heading2']),
        Paragraph(
            'Édité le ' + timezone.localtime().strftime('%d/%m/%Y à %H:%M'),
            styles['Normal'],
        ),
        Spacer(1, 0.5 * cm),
    ]
    if resume:
        tableau = Table([[Paragraph(f'<b>{_valeur(k)}</b>', styles['Normal']),
                          Paragraph(_valeur(v), styles['Normal'])] for k, v in resume],
                        colWidths=[5.5 * cm, 12 * cm])
        tableau.setStyle(TableStyle([
            ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#B0BEC5')),
            ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#ECEFF1')),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        flux += [tableau, Spacer(1, 0.6 * cm)]
    if entetes and lignes:
        donnees = [[Paragraph(f'<b>{e}</b>', styles['Normal']) for e in entetes]]
        donnees += [[Paragraph(_valeur(c), styles['Normal']) for c in ligne] for ligne in lignes]
        tableau = Table(donnees, repeatRows=1)
        tableau.setStyle(TableStyle([
            ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#B0BEC5')),
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#E8EFF5')),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        flux.append(tableau)
    doc.build(flux)
    return tampon.getvalue()


def _xlsx(titre, resume, entetes, lignes):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill

    classeur = Workbook()
    feuille = classeur.active
    feuille.title = 'Fiche'
    feuille['A1'] = titre
    feuille['A1'].font = Font(bold=True, size=14)
    ligne = 3
    for cle, valeur in resume:
        feuille.cell(row=ligne, column=1, value=str(cle)).font = Font(bold=True)
        feuille.cell(row=ligne, column=2, value=_valeur(valeur))
        ligne += 1
    if entetes and lignes:
        ligne += 1
        for colonne, entete in enumerate(entetes, start=1):
            cellule = feuille.cell(row=ligne, column=colonne, value=entete)
            cellule.font = Font(bold=True)
            cellule.fill = PatternFill('solid', fgColor='E8EFF5')
        for decalage, contenu in enumerate(lignes, start=1):
            for colonne, valeur in enumerate(contenu, start=1):
                feuille.cell(row=ligne + decalage, column=colonne,
                             value=valeur if isinstance(valeur, (int, float)) else _valeur(valeur))
    for colonne in ('A', 'B', 'C', 'D', 'E', 'F'):
        feuille.column_dimensions[colonne].width = 28
    tampon = io.BytesIO()
    classeur.save(tampon)
    return tampon.getvalue()
