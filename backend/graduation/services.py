"""Services du lot L4 — génération PDF, validation, révocation, réédition, vérification.

Le moteur PDF reportlab (pattern identique à ``jurys.pv``) garantit la
reproductibilité ; l'empreinte SHA-256 du PDF est stockée sur le Diplome
et sur chaque Reedition. Toute opération sensible est journalisée via
``scolarite.journaliser`` (JURY_* déjà utilisés, on introduit DIPLOME_*).
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

from .models import Diplome, Reedition, RegistreDiplomes


def _styles():
    base = getSampleStyleSheet()
    return {
        'titre': ParagraphStyle('DipTitre', parent=base['Title'], fontSize=18, spaceAfter=10),
        'sous_titre': ParagraphStyle('DipSousTitre', parent=base['Normal'], fontSize=11, alignment=1),
        'corps': ParagraphStyle('DipCorps', parent=base['Normal'], fontSize=10, leading=14),
        'cellule': ParagraphStyle('DipCellule', parent=base['Normal'], fontSize=9),
    }


def build_diplome_story(diplome):
    """Construit la story reportlab d'un diplôme LMD."""
    styles = _styles()
    e = diplome.etudiant
    nom_complet = e.nom_complet
    matricule = e.matricule or '—'
    parcours = diplome.parcours.code if diplome.parcours else '—'
    story = [
        Paragraph('INSTITUT NATIONAL DE LA JEUNESSE ET DES SPORTS', styles['sous_titre']),
        Paragraph('RÉPUBLIQUE DE CÔTE D\'IVOIRE', styles['sous_titre']),
        Spacer(1, 0.5 * cm),
        Paragraph('DIPLOME LMD', styles['titre']),
        Paragraph(
            f"{diplome.ref_formation} — Niveau {diplome.niveau}"
            f"{' / Parcours ' + parcours if diplome.parcours_id else ''}",
            styles['sous_titre'],
        ),
        Paragraph(f"Année académique : {diplome.annee_academique}", styles['sous_titre']),
        Spacer(1, 0.6 * cm),
        Paragraph("Le présent diplôme est délivré à :", styles['corps']),
        Paragraph(f"<b>{nom_complet}</b>", ParagraphStyle('Nom', parent=styles['corps'], fontSize=14, spaceAfter=4)),
        Paragraph(f"Matricule : {matricule}", styles['corps']),
        Spacer(1, 0.4 * cm),
    ]
    info = [
        ['Mention', diplome.mention or '—'],
        ['Crédits ECTS acquis', str(diplome.credits_acquis)],
        ['Date de validation', diplome.date_validation.strftime('%d/%m/%Y') if diplome.date_validation else '—'],
        ['N° de vérification', str(diplome.numero_unique)],
    ]
    story.append(Table(
        info, colWidths=[5 * cm, 11 * cm], hAlign='LEFT',
        style=TableStyle([
            ('GRID', (0, 0), (-1, -1), 0.4, colors.grey),
            ('BACKGROUND', (0, 0), (0, -1), colors.Color(0.93, 0.93, 0.93)),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ]),
    ))
    story.append(Spacer(1, 0.6 * cm))
    story.append(Paragraph(
        "Ce diplôme est vérifiable publiquement via le numéro unique ci-dessus. "
        "Toute altération invalide sa trace SHA-256.", styles['corps'],
    ))
    return story


def generer_pdf_diplome(diplome, user=None):
    """Génère le PDF du diplôme et le persiste avec son empreinte SHA-256.

    Une fois le diplôme VALIDATED, le PDF est gelé : utiliser ``reediter_diplome``
    pour produire une nouvelle version (Reedition append-only).
    """
    if diplome.statut == Diplome.Statut.VALIDATED and diplome.pdf_fichier:
        raise ValidationError("Le PDF d'un diplôme validé est gelé — utiliser la réédition.")
    if diplome.statut == Diplome.Statut.REVOKED:
        raise ValidationError("Aucun PDF ne peut être généré pour un diplôme révoqué.")

    sortie = BytesIO()
    doc = SimpleDocTemplate(
        sortie, pagesize=landscape(A4),
        topMargin=1.2 * cm, bottomMargin=1.2 * cm,
        leftMargin=1.5 * cm, rightMargin=1.5 * cm,
    )
    doc.build(build_diplome_story(diplome))
    contenu = sortie.getvalue()
    empreinte = hashlib.sha256(contenu).hexdigest()

    nom = f'diplome-{diplome.pk}-{timezone.now():%Y%m%d-%H%M%S}.pdf'
    diplome.pdf_fichier.save(nom, ContentFile(contenu), save=False)
    diplome.empreinte_pdf = empreinte
    diplome.save(update_fields=['pdf_fichier', 'empreinte_pdf'])
    return diplome


def valider_diplome(diplome, user):
    """Passe un diplôme BROUILLON/VALIDATION_PENDING → VALIDATED.

    Vérifie les conditions de diplômation, génère le PDF, inscrit au registre
    annuel et journalise. Opération réservée à DIRECTION/DFRC (coté API).
    """
    if diplome.statut == Diplome.Statut.VALIDATED:
        raise ValidationError("Diplôme déjà validé.")
    if diplome.statut == Diplome.Statut.REVOKED:
        raise ValidationError("Diplôme révoqué — impossible de valider.")

    ok, raisons = diplome.verifier_conditions_validation()
    if not ok:
        raise ValidationError("Conditions non réunies : " + " ; ".join(raisons))

    generer_pdf_diplome(diplome, user)
    diplome.statut = Diplome.Statut.VALIDATED
    diplome.valide_par = user
    diplome.date_validation = timezone.now()
    diplome.save(update_fields=['statut', 'valide_par', 'date_validation'])

    registre, _created = RegistreDiplomes.objects.get_or_create(
        annee_academique=diplome.annee_academique,
    )
    registre.ajouter(diplome, user)

    journaliser('DIPLOME_VALIDE', objet=diplome, acteur=user,
                nouvelle_valeur=diplome.empreinte_pdf)
    return diplome


def revoquer_diplome(diplome, user, motif):
    """Révoque un diplôme VALIDATED — motif obligatoire, journalisé.

    Le PDF original reste conservé (preuve historique). Le statut passe à
    REVOKED ; aucune réédition tant que le diplôme n'est pas réhabilité via
    une nouvelle décision de jury.
    """
    motif = (motif or '').strip()
    if not motif:
        raise ValidationError({'motif': "Le motif de révocation est obligatoire."})
    if diplome.statut != Diplome.Statut.VALIDATED:
        raise ValidationError("Seul un diplôme VALIDATED peut être révoqué.")

    diplome.statut = Diplome.Statut.REVOKED
    diplome.revoque_par = user
    diplome.date_revocation = timezone.now()
    diplome.motif_revocation = motif
    diplome.save(update_fields=['statut', 'revoque_par', 'date_revocation', 'motif_revocation'])
    journaliser('DIPLOME_REVOQUE', objet=diplome, acteur=user, nouvelle_valeur=motif)
    return diplome


def reediter_diplome(diplome, user, motif):
    """Crée une Réédition (append-only) d'un diplôme VALIDATED.

    Le PDF original reste intouché ; une nouvelle Reedition est créée avec
    un nouveau PDF horodaté et hashé. À motif obligatoire.
    """
    motif = (motif or '').strip()
    if not motif:
        raise ValidationError({'motif': "Le motif de réédition est obligatoire."})
    if diplome.statut != Diplome.Statut.VALIDATED:
        raise ValidationError("Seul un diplôme VALIDATED peut être réédité.")

    reedition = Reedition(diplome=diplome, motif=motif, par=user)
    reedition.save()  # clean() valide le motif

    sortie = BytesIO()
    doc = SimpleDocTemplate(
        sortie, pagesize=landscape(A4),
        topMargin=1.2 * cm, bottomMargin=1.2 * cm,
        leftMargin=1.5 * cm, rightMargin=1.5 * cm,
    )
    doc.build(build_diplome_story(diplome))
    contenu = sortie.getvalue()
    reedition.empreinte_pdf = hashlib.sha256(contenu).hexdigest()
    nom = f'diplome-reedition-{reedition.pk}-{timezone.now():%Y%m%d-%H%M%S}.pdf'
    reedition.pdf_fichier.save(nom, ContentFile(contenu), save=True)

    journaliser('DIPLOME_REEDITE', objet=diplome, acteur=user,
                nouvelle_valeur=reedition.empreinte_pdf)
    return reedition


def verifier_par_token(token):
    """Portail public de vérification (lecture seule, aucune donnée sensible).

    Retourne un dict JSON-sérialisable limité au strict nécessaire pour qu'un
    tiers puisse authentifier le diplôme (pas de matricule interne, pas
    d'identifiants de scolarité).
    """
    try:
        diplome = Diplome.objects.select_related(
            'etudiant__participant', 'ref_formation', 'niveau', 'parcours',
            'annee_academique',
        ).get(numero_unique=token)
    except (Diplome.DoesNotExist, ValueError, Exception):
        return {
            'valide': False,
            'raison': "Aucun diplôme trouvé pour ce numéro de vérification.",
        }
    return {
        'valide': diplome.statut == Diplome.Statut.VALIDATED,
        'statut': diplome.statut,
        'statut_display': diplome.get_statut_display(),
        'nom_complet': diplome.etudiant.nom_complet,
        'formation': str(diplome.ref_formation),
        'niveau': str(diplome.niveau),
        'parcours': str(diplome.parcours) if diplome.parcours_id else None,
        'mention': diplome.mention,
        'date_validation': (
            diplome.date_validation.isoformat() if diplome.date_validation else None
        ),
        'annee_academique': str(diplome.annee_academique),
    }


