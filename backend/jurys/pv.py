"""Génération du PV de jury (PDF reportlab) — pattern notes_fiche_export.py.

Le PV est généré depuis les décisions officielles (DecisionJury) d'une session
dont les propositions sont verrouillées par le workflow ; le fichier est
persisté avec son empreinte SHA-256.
"""
import hashlib
from io import BytesIO

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from scolarite.models import journaliser

from .models import DecisionJury, PVJury, SessionJury


def _styles():
    base = getSampleStyleSheet()
    return {
        'titre': ParagraphStyle(
            'PVTitre', parent=base['Title'], fontSize=15, spaceAfter=8,
        ),
        'sous_titre': ParagraphStyle(
            'PVSousTitre', parent=base['Normal'], fontSize=10, alignment=1,
        ),
        'cellule': ParagraphStyle('PVCellule', parent=base['Normal'], fontSize=9),
    }


def build_pv_story(session):
    """Construit la story reportlab du PV (décisions officielles de la session)."""
    styles = _styles()
    story = [
        Paragraph('INSTITUT NATIONAL DE LA JEUNESSE ET DES SPORTS', styles['sous_titre']),
        Paragraph(f'PROCÈS-VERBAL DE JURY — {session.get_type_session_display()}',
                  styles['titre']),
        Paragraph(
            f"{session.ref_formation} / {session.niveau}"
            f"{' / ' + session.parcours.code if session.parcours else ''}"
            f" — {session.annee_academique}",
            styles['sous_titre'],
        ),
        Spacer(1, 0.4 * cm),
    ]

    membres = [
        [m.get_fonction_display(), str(m.user)]
        for m in session.membres.select_related('user').order_by('fonction')
    ]
    if membres:
        story.append(Table(
            membres, colWidths=[4 * cm, 12 * cm], hAlign='LEFT',
            style=TableStyle([
                ('GRID', (0, 0), (-1, -1), 0.4, colors.grey),
                ('BACKGROUND', (0, 0), (0, -1), colors.Color(0.93, 0.93, 0.93)),
                ('FONTSIZE', (0, 0), (-1, -1), 9),
            ]),
        ))
        story.append(Spacer(1, 0.4 * cm))

    lignes = [[
        'Matricule', 'Étudiant', 'Décision', 'Crédits', 'Moyenne', 'Mention',
    ]]
    for d in (
        DecisionJury.objects.filter(session=session)
        .select_related('participant').order_by('participant__nom', 'participant__prenom')
    ):
        lignes.append([
            d.participant.matricule or '',
            f'{d.participant.nom} {d.participant.prenom}'.strip(),
            d.get_decision_display(),
            str(d.credits_acquis),
            str(d.moyenne_generale) if d.moyenne_generale is not None else '—',
            d.mention or '',
        ])

    table = Table(
        lignes, colWidths=[2.6 * cm, 7.5 * cm, 4.2 * cm, 1.7 * cm, 2.1 * cm, 2.9 * cm],
        repeatRows=1,
    )
    table.setStyle(TableStyle([
        ('GRID', (0, 0), (-1, -1), 0.4, colors.grey),
        ('BACKGROUND', (0, 0), (-1, 0), colors.Color(0.85, 0.89, 0.95)),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('ALIGN', (3, 1), (4, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    story.append(table)
    return story


def generer_pv(session, user):
    """Génère (ou régénère) le PV de la session et le persiste avec son hash.

    Généré depuis les données verrouillées par le workflow (décisions
    officielles) ; journalisé via JournalScolarite.
    """
    from django.core.exceptions import ValidationError

    if session.verrouillee:
        raise ValidationError('Session verrouillée : le PV ne peut plus être régénéré librement.')
    if session.statut != SessionJury.Statut.DECISION:
        raise ValidationError("Le PV se génère à l'état DECISION (après la délibération).")
    if not DecisionJury.objects.filter(session=session).exists():
        raise ValidationError('Aucune décision enregistrée : impossible de générer le PV.')

    sortie = BytesIO()
    doc = SimpleDocTemplate(
        sortie, pagesize=landscape(A4),
        topMargin=1.2 * cm, bottomMargin=1.2 * cm,
        leftMargin=1.2 * cm, rightMargin=1.2 * cm,
    )
    doc.build(build_pv_story(session))
    contenu = sortie.getvalue()
    empreinte = hashlib.sha256(contenu).hexdigest()

    nom = f'pv-jury-{session.pk}-{timezone.now():%Y%m%d-%H%M%S}.pdf'
    pv, _created = PVJury.objects.update_or_create(
        session=session,
        defaults={'sha256': empreinte, 'genere_par': user},
    )
    pv.fichier.save(nom, ContentFile(contenu), save=True)
    journaliser('JURY_PV_GENERE', objet=session, acteur=user, nouvelle_valeur=empreinte)
    return pv
