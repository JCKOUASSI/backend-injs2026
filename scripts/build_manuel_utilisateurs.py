#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Construit le manuel utilisateurs INJS-LMD2026 au format DOCX puis PDF.

Source unique : docs/manuel/ManuelUtilisateurs-INJS-LMD2026.md
Sorties      : docs/manuel/ManuelUtilisateurs-INJS-LMD2026.docx
               docs/manuel/ManuelUtilisateurs-INJS-LMD2026.pdf

Le script est idempotent : deux exécutions successives produisent les mêmes
sorties. Il ÉCHOUE BRUSQUEMENT si un contrôle bloquant n'est pas satisfait.

Usage :  python3 scripts/build_manuel_utilisateurs.py
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOSSIER = os.path.join(RACINE, "docs", "manuel")
SOURCE = os.path.join(DOSSIER, "ManuelUtilisateurs-INJS-LMD2026.md")
SORTIE_DOCX = os.path.join(DOSSIER, "ManuelUtilisateurs-INJS-LMD2026.docx")
SORTIE_PDF = os.path.join(DOSSIER, "ManuelUtilisateurs-INJS-LMD2026.pdf")

TAILLE_MIN = 200 * 1024          # 200 Ko
PAGES_MIN = 60
IMAGES_MIN = 29                  # figures insérées dans le manuel

# Aucun mot de passe ne doit apparaître dans les livrables (§8.2).
MOTIFS_SECRETS = [
    r"admin123", r"sec123", r"dfrc123", r"injs123",
    r"JckPcm@123", r"sup123",
]
# Caractères hors alphabet français (CJK notamment) : interdits.
CARACTERES_INTERDITS = re.compile(r"[　-鿿가-힯＀-￯]")


class EchecControle(Exception):
    """Un contrôle bloquant n'est pas satisfait."""


def info(message):
    print("[build] %s" % message, flush=True)


def echec(message):
    raise EchecControle(message)


def lire_source():
    if not os.path.isfile(SOURCE):
        echec("Source introuvable : %s" % SOURCE)
    with open(SOURCE, encoding="utf-8") as f:
        return f.read()


def controler_source(texte):
    """Contrôles appliqués à la source, avant toute conversion."""
    problemes = []
    images = re.findall(r"!\[[^\]]*\]\(([^)]+)\)", texte)
    for chemin in images:
        cible = os.path.normpath(os.path.join(DOSSIER, chemin))
        if not os.path.isfile(cible):
            problemes.append("image référencée introuvable : %s" % chemin)
    if not images:
        problemes.append("aucune image référencée dans la source")
    for motif in MOTIFS_SECRETS:
        if re.search(motif, texte, re.IGNORECASE):
            problemes.append("secret détecté dans la source : %r" % motif)
    if CARACTERES_INTERDITS.search(texte):
        problemes.append("caractères non français détectés dans la source")
    titres = re.findall(r"^# (.+)$", texte, re.M)
    if len(titres) < 20:
        problemes.append("structure insuffisante : %d chapitres" % len(titres))
    return problemes, images


def trouver_pandoc():
    chemin = shutil.which("pandoc")
    if not chemin:
        echec("pandoc est introuvable dans le PATH")
    return chemin


def _soffice_utilisable(chemin):
    """Vrai si le binaire existe ET s'exécute réellement.

    Un lanceur Homebrew résiduel pointe souvent vers une application
    supprimée : seul un essai d'exécution permet de le démasquer.
    """
    if not chemin or not os.path.isfile(chemin):
        return False
    reel = os.path.realpath(chemin)
    if not os.path.exists(reel):
        return False
    try:
        r = subprocess.run([chemin, "--version"], capture_output=True,
                           text=True, timeout=120)
    except Exception:                    # noqa: BLE001
        return False
    return r.returncode == 0 and "LibreOffice" in (r.stdout or "")


def trouver_soffice():
    """Renvoie le chemin de LibreOffice, ou None si l'application est absente.

    Le casque Homebrew peut laisser un lanceur résiduel qui pointe vers une
    application supprimée : on vérifie donc que le binaire s'exécute réellement
    avant de le retourner.
    """
    for nom in ("soffice", "libreoffice"):
        chemin = shutil.which(nom)
        if _soffice_utilisable(chemin):
            return chemin
    for candidat in ("/Applications/LibreOffice.app/Contents/MacOS/soffice",
                     "/opt/homebrew/bin/soffice"):
        if _soffice_utilisable(candidat):
            return candidat
    return None


STYLES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:docDefaults>
    <w:rPrDefault><w:rPr>
      <w:rFonts w:ascii="Calibri" w:hAnsi="Calibri" w:cs="Calibri"/>
      <w:sz w:val="22"/><w:lang w:val="fr-FR"/>
    </w:rPr></w:rPrDefault>
    <w:pPrDefault><w:pPr><w:spacing w:after="120" w:line="276" w:lineRule="auto"/></w:pPr></w:pPrDefault>
  </w:docDefaults>
  <w:style w:type="paragraph" w:styleId="Heading1">
    <w:name w:val="heading 1"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/>
    <w:pPr><w:keepNext/><w:spacing w:before="240" w:after="180"/>
      <w:outlineLvl w:val="0"/></w:pPr>
    <w:rPr><w:b/><w:color w:val="102A57"/><w:sz w:val="38"/></w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Heading2">
    <w:name w:val="heading 2"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/>
    <w:pPr><w:keepNext/><w:spacing w:before="260" w:after="120"/>
      <w:outlineLvl w:val="1"/></w:pPr>
    <w:rPr><w:b/><w:color w:val="1D4ED8"/><w:sz w:val="30"/></w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Heading3">
    <w:name w:val="heading 3"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/>
    <w:pPr><w:keepNext/><w:spacing w:before="200" w:after="100"/>
      <w:outlineLvl w:val="2"/></w:pPr>
    <w:rPr><w:b/><w:color w:val="334155"/><w:sz w:val="26"/></w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Caption">
    <w:name w:val="caption"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/>
    <w:pPr><w:spacing w:before="60" w:after="240"/><w:jc w:val="center"/></w:pPr>
    <w:rPr><w:i/><w:color w:val="475569"/><w:sz w:val="19"/></w:rPr>
  </w:style>
</w:styles>
"""

DOCUMENT_VIDE = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
    '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/'
    '2006/main"><w:body><w:p/></w:body></w:document>'
)

CONTENT_TYPES = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="xml" ContentType="application/xml"/></Types>'
)


def ecrire_reference(dossier_temporaire):
    """Document de référence : styles INJS + sommaire automatique (champ TOC)."""
    chemin = os.path.join(dossier_temporaire, "reference.docx")
    with zipfile.ZipFile(chemin, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("word/styles.xml", STYLES)
        zf.writestr("word/document.xml", DOCUMENT_VIDE)
        zf.writestr("[Content_Types].xml", CONTENT_TYPES)
    return chemin


def preparer_source(texte, dossier_temporaire):
    """Prépare le Markdown : numérotation des figures et résolution des images.

    Le sommaire (champ TOC) est inséré après la page de garde, en début de corps,
    de sorte qu'il soit à jour dès l'ouverture dans Word.
    """
    base = os.path.dirname(SOURCE)

    # 1. Copie de travail avec les images rendues en chemins absolus, car Pandoc
    #    résout les chemins relatifs par rapport au répertoire d'exécution.
    travail = os.path.join(dossier_temporaire, "manuel_source.md")
    sortie = []
    for ligne in texte.split("\n"):
        m = re.match(r"^(!\[[^\]]*\]\()(.+)(\))$", ligne.strip())
        if m:
            cible = os.path.normpath(os.path.join(base, m.group(2)))
            ligne = "%s%s%s" % (m.group(1), cible, m.group(3))
        sortie.append(ligne)
    texte = "\n".join(sortie)

    # 2. Sommaire automatique : bloc inséré avant le premier chapitre.
    sommaire = (
        "\\newpage\n"
        "## Sommaire\n\n"
        "```{=openxml}\n"
        "<w:p><w:pPr><w:jc w:val=\"center\"/></w:pPr>"
        "<w:r><w:rPr><w:b/><w:sz w:val=\"32\"/><w:color w:val=\"102A57\"/></w:rPr>"
        "<w:t>Sommaire</w:t></w:r></w:p>\n"
        "```\n\n"
        "```{=openxml}\n"
        "<w:sdt><w:sdtPr><w:docPartObj>"
        "<w:docPartGallery w:val=\"Table of Contents\"/>"
        "<w:docPartUnique/></w:docPartObj></w:sdtPr><w:sdtContent>\n"
        "<w:p><w:pPr><w:pStyle w:val=\"TOCHeading\"/></w:pPr>"
        "<w:r><w:t>Sommaire</w:t></w:r></w:p>\n"
        "<w:p><w:r><w:fldChar w:fldCharType=\"begin\" w:dirty=\"true\"/></w:r>"
        "<w:r><w:instrText xml:space=\"preserve\"> TOC \\o \"1-3\" \\h \\z \\u "
        "</w:instrText></w:r>"
        "<w:r><w:fldChar w:fldCharType=\"separate\"/></w:r>"
        "<w:r><w:t>Le sommaire se met à jour à l'ouverture du document "
        "(Word : F9 pour forcer).</w:t></w:r>"
        "<w:r><w:fldChar w:fldCharType=\"end\"/></w:r></w:p>\n"
        "</w:sdtContent></w:sdt>\n"
        "```\n\n"
    )
    texte = texte.replace("\n# 1. Introduction",
                          "\n" + sommaire + "# 1. Introduction", 1)

    with open(travail, "w", encoding="utf-8") as f:
        f.write(texte)
    return travail


def construire_docx(texte, dossier_temporaire):
    pandoc = trouver_pandoc()
    reference = ecrire_reference(dossier_temporaire)
    travail = preparer_source(texte, dossier_temporaire)
    info("conversion Markdown -> DOCX (pandoc)")
    commande = [
        pandoc, travail,
        "--from", "markdown-yaml_metadata_block-raw_attribute",
        "--to", "docx",
        "--reference-doc", reference,
        "--toc", "--toc-depth=3",
        "--resource-path", dossier_temporaire + ":" + RACINE,
        "-o", SORTIE_DOCX,
    ]
    resultat = subprocess.run(commande, capture_output=True, text=True)
    if resultat.returncode != 0:
        echec("pandoc a échoué :\n%s" % (resultat.stderr or "")[:2000])
    if not os.path.isfile(SORTIE_DOCX):
        echec("DOCX non produit")
    return SORTIE_DOCX


def construire_pdf():
    """Conversion DOCX -> PDF.

    Deux voies, dans cet ordre :
      1. LibreOffice (conversion de référence, fidèle au DOCX) ;
      2. repli ReportLab si l'application LibreOffice est absente de la machine.
    """
    soffice = trouver_soffice()
    if soffice:
        info("conversion DOCX -> PDF (LibreOffice)")
        # le PDF précédent est retiré : sinon LibreOffice peut laisser
        # l'ancien fichier en place et l'échec passerait inaperçu.
        if os.path.isfile(SORTIE_PDF):
            os.remove(SORTIE_PDF)
        try:
            r = subprocess.run(
                [soffice, "--headless", "--convert-to", "pdf",
                 "--outdir", DOSSIER, SORTIE_DOCX],
                capture_output=True, text=True, timeout=900,
            )
            if r.returncode != 0:
                info("LibreOffice a échoué (code %d) — repli ReportLab"
                     % r.returncode)
        except Exception as e:                      # noqa: BLE001
            info("LibreOffice a échoué (%s) — repli ReportLab" % e)
        if (os.path.isfile(SORTIE_PDF)
                and os.path.getsize(SORTIE_PDF) > 0):
            return "LibreOffice"
        info("LibreOffice n'a rien produit — repli ReportLab")
    else:
        info("LibreOffice absent de la machine — repli ReportLab")

    # LibreOffice peut laisser un fichier vide : on le retire pour que le
    # repli ReportLab puisse écrire un PDF valide à la même adresse.
    if os.path.isfile(SORTIE_PDF) and os.path.getsize(SORTIE_PDF) == 0:
        os.remove(SORTIE_PDF)

    construire_pdf_reportlab()
    return "ReportLab (repli)"


def echapper(texte):
    return (texte.replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;"))


def ancre(titre):
    return re.sub(r"[^A-Za-z0-9]+", "-", titre).strip("-")


def _position_insertion_sommaire(story):
    """Le sommaire est placé avant le premier titre de niveau 1 du corps."""
    for index, element in enumerate(story):
        style = getattr(element, "style", None)
        if style is not None and getattr(style, "name", "") == "H1":
            return index
    return len(story)


def _enrichir(txt):
    """Markdown inline -> balises ReportLab (code, puis gras, puis italique)."""
    txt = re.sub(r"`([^`]+)`", r'<font face="Courier">\1</font>', txt)
    txt = txt.replace("&", "&amp;")
    txt = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", txt)
    txt = re.sub(r"(?<![\w*])\*([^*\n]+)\*(?![\w*])", r"<i>\1</i>", txt)
    return txt


def _normaliser_glyphes(texte):
    """Remplace les caractères absents de la police du PDF.

    La source emploie l'U+2011 (trait d'union insécable) dans « sous‑menus ».
    ReportLab ne dispose pas de ce glyphe : il dessine un carré noir à la place,
    ce qui casse la lecture. Le caractère est remplacé à la lecture du texte par
    un trait d'union ASCII ; le fichier Markdown n'est pas modifié.
    """
    return texte.replace("\u2011", "-")


def _desequilibre(ligne):
    """Vrai si la ligne laisse un marqueur inline ouvert.

    Soit un gras « ** » non fermé, soit une italique « * » non fermée : les
    deux cas laissent un marqueur littéral dans le PDF si la ligne suivante
    n'est pas rattachée.
    """
    return (ligne.count("*") % 2 == 1) or (ligne.count("**") % 2 == 1)


def _fusionner_continuations(lignes):
    """Rapproche une ligne de continuation de la précédente si celle-ci laisse
    un marqueur ** ou * ouvert.
    Le générateur analyse le document ligne à ligne : un formatage qui traverse
    un retour à la ligne (ex. « … et **statut de » suivi de « validation**. »,
    ou une légende « *Figure 12 — … » fermée sur la ligne suivante) formerait
    deux moitiés non appariées et laisserait le marqueur littéral dans le PDF.
    Les lignes sont donc réunies avant analyse pour que _enrichir() forme la
    paire. Seules les lignes réellement orphelines sont fusionnées : la source
    Markdown n'est pas modifiée, et les blocs (titres, tableaux, images, listes)
    ne sont jamais absorbés.
    """
    sortie = []
    for ligne in lignes:
        precedent = sortie[-1] if sortie else None
        if (precedent is not None
                and not precedent.strip().startswith("|")
                and _desequilibre(precedent)):
            suite = ligne.lstrip()
            if (suite
                    and not suite.startswith("|")
                    and not suite.startswith("#")
                    and not suite.startswith("!")
                    and not re.match(r"^\d+\.\s+", suite)
                    and not re.match(r"^[-*+]\s+", suite)
                    and not re.fullmatch(r"[-=_]{3,}", suite)):
                sortie[-1] = precedent + " " + suite
                continue
        sortie.append(ligne)
    return sortie


def construire_pdf_reportlab():
    """Produit le PDF directement depuis la source Markdown (ReportLab)."""
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import (BaseDocTemplate, Frame, Image, KeepTogether,
                                    NextPageTemplate, PageBreak, PageTemplate,
                                    Paragraph, Spacer, Table, TableStyle)

    bleu = colors.HexColor("#102A57")
    bleu_clair = colors.HexColor("#1D4ED8")
    gris = colors.HexColor("#475569")

    texte = _normaliser_glyphes(lire_source())
    base = os.path.dirname(SOURCE)

    bs = getSampleStyleSheet()
    S_titre = ParagraphStyle("Titre", parent=bs["Title"], fontSize=24,
                             textColor=bleu, leading=30, spaceAfter=14,
                             alignment=TA_CENTER)
    S_sous = ParagraphStyle("Sous", parent=bs["Normal"], fontSize=13,
                            textColor=bleu_clair, leading=19, spaceAfter=10,
                            alignment=TA_CENTER)
    S_h1 = ParagraphStyle("H1", parent=bs["Heading1"], fontSize=16,
                          textColor=bleu, spaceBefore=4, spaceAfter=10,
                          leading=20, keepWithNext=True)
    S_h2 = ParagraphStyle("H2", parent=bs["Heading2"], fontSize=11.5,
                          textColor=bleu_clair, spaceBefore=11, spaceAfter=5,
                          leading=15, keepWithNext=True)
    S_h3 = ParagraphStyle("H3", parent=bs["Heading3"], fontSize=10,
                          textColor=colors.HexColor("#334155"), spaceBefore=8,
                          spaceAfter=4, leading=13, keepWithNext=True)
    S_corps = ParagraphStyle("Corps", parent=bs["BodyText"], fontSize=9,
                             leading=13.5, spaceAfter=6)
    S_liste = ParagraphStyle("Liste", parent=S_corps, leftIndent=14,
                             bulletIndent=3, spaceAfter=3)
    S_legende = ParagraphStyle("Legende", parent=S_corps, fontSize=8,
                               textColor=gris, alignment=TA_CENTER,
                               spaceAfter=12, leading=10.5)
    S_cell = ParagraphStyle("Cell", parent=S_corps, fontSize=7.5, leading=9.5,
                            spaceAfter=0)
    S_ent = ParagraphStyle("Ent", parent=S_cell, textColor=colors.white,
                           fontName="Helvetica-Bold")
    S_som = ParagraphStyle("Som", parent=S_corps, fontSize=9.5, leading=15,
                           spaceAfter=2)

    def pager(canevas, doc):
        if doc.page <= 1:
            return
        canevas.saveState()
        canevas.setFont("Helvetica", 7.5)
        canevas.setFillColor(gris)
        canevas.drawString(2 * cm, A4[1] - 1.3 * cm,
                           "Manuel Utilisateurs INJS-LMD2026 — CONFIDENTIEL")
        canevas.drawRightString(A4[0] - 2 * cm, 1.4 * cm,
                                "Page %d" % doc.page)
        canevas.drawString(2 * cm, 1.4 * cm, "Usage interne")
        canevas.setStrokeColor(colors.HexColor("#CBD5E1"))
        canevas.line(2 * cm, A4[1] - 1.55 * cm, A4[0] - 2 * cm,
                     A4[1] - 1.55 * cm)
        canevas.restoreState()

    doc = BaseDocTemplate(
        SORTIE_PDF, pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm,
        topMargin=2 * cm, bottomMargin=1.8 * cm,
        title="Manuel Utilisateurs INJS-LMD2026",
        author="Documentation technique INJS-LMD",
        subject="Manuel utilisateurs — confidentiel, usage interne")
    cadre = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height,
                  id="normal")

    story, titres, tampon = [], [], []

    doc.addPageTemplates([
        PageTemplate(id="couverture", frames=[cadre]),
        PageTemplate(id="standard", frames=[cadre], onPage=pager),
    ])

    def vider_tableau():
        if not tampon:
            return
        donnees = [[Paragraph(_enrichir(c), S_ent) for c in tampon[0]]]
        for ligne in tampon[1:]:
            donnees.append([Paragraph(_enrichir(c), S_cell) for c in ligne])
        nb = max(len(d) for d in donnees)
        for d in donnees:
            while len(d) < nb:
                d.append(Paragraph("", S_cell))
        t = Table(donnees, colWidths=[doc.width / nb] * nb, repeatRows=1)
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), bleu),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#CBD5E1")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1),
             [colors.white, colors.HexColor("#F1F5F9")]),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        story.append(Spacer(1, 4))
        story.append(t)
        story.append(Spacer(1, 10))
        del tampon[:]

    def analyser_tableau(ligne):
        cells = [c.strip() for c in ligne.strip().strip("|").split("|")]
        if cells and all(re.fullmatch(r":?-{2,}:?", c) for c in cells if c):
            return
        tampon.append(cells)

    couverture = False
    lignes = _fusionner_continuations(texte.split("\n"))
    i = 0
    while i < len(lignes):
        ligne = lignes[i]
        i += 1
        brut = ligne.strip()
        # le marqueur de citation Markdown n'est pas interprété par le
        # générateur : il serait affiché littéralement en tête de paragraphe.
        brut = re.sub(r"^>\s?", "", brut)

        if brut.startswith("|") and brut.endswith("|"):
            vider_tableau()
            # la première ligne du tableau est déjà son contenu : elle doit
            # être transmise, sinon l'en-tête est perdu et la première ligne
            # de données prend sa place.
            analyser_tableau(brut)
            while i < len(lignes) and lignes[i].strip().startswith("|"):
                analyser_tableau(lignes[i])
                i += 1
            vider_tableau()
            continue

        m = re.match(r"^!\[([^\]]*)\]\((.+)\)\s*$", brut)
        if m:
            cible = os.path.normpath(os.path.join(base, m.group(2)))
            alt = m.group(1)
            if os.path.isfile(cible):
                largeur = doc.width
                hauteur = largeur * 0.62
                try:
                    from PIL import Image as PILImage
                    with PILImage.open(cible) as im:
                        w, h = im.size
                    hauteur = largeur * (h / float(w))
                except Exception:                  # noqa: BLE001
                    pass
                hauteur = min(hauteur, 9.5 * cm)
                story.append(KeepTogether([
                    Image(cible, width=largeur, height=hauteur),
                    Paragraph(echapper(alt), S_legende)]))
            else:
                story.append(Paragraph("Image manquante : %s"
                                       % echapper(alt), S_legende))
            continue

        if brut.startswith("# "):
            titre = brut[2:].strip()
            if not couverture:
                couverture = True
                story.append(Spacer(1, 4.5 * cm))
                story.append(Paragraph("INSTITUT NATIONAL DE LA JEUNESSE "
                                       "ET DES SPORTS", S_sous))
                story.append(Paragraph(echapper(titre), S_titre))
                story.append(Paragraph("Manuel Utilisateurs — version 1.0",
                                       S_sous))
                story.append(Spacer(1, 1.2 * cm))
                story.append(Paragraph(
                    "<b>CONFIDENTIEL — document d'usage interne.</b>"
                    "<br/><br/>Ce manuel décrit le fonctionnement de "
                    "l'application INJS-LMD. Il ne contient aucune donnee "
                    "personnelle reelle, aucun mot de passe et aucun secret "
                    "technique.<br/><br/>Diffusion soumise a autorisation de "
                    "la Direction.", S_corps))
                story.append(Spacer(1, 1.5 * cm))
                story.append(Paragraph("Marcory \u2014 Abidjan, Cote d'Ivoire"
                                       "<br/>Document produit a partir de "
                                       "l'application reelle", S_sous))
                story.append(NextPageTemplate("standard"))
                story.append(PageBreak())
                continue
            titres.append((1, titre))
            story.append(Paragraph('<a name="%s"/>' % ancre(titre)
                                   + echapper(titre), S_h1))
            continue

        mh = re.match(r"^(#{2,4})\s+(.*)$", brut)
        if mh:
            niveau = len(mh.group(1))
            titres.append((niveau, mh.group(2).strip()))
            style = S_h1 if niveau == 2 else (S_h2 if niveau == 3 else S_h3)
            story.append(Paragraph('<a name="%s"/>' % ancre(mh.group(2).strip())
                                   + _enrichir(mh.group(2).strip()), style))
            continue

        if not brut:
            vider_tableau()
            continue

        if set(brut) <= set("-"):
            vider_tableau()
            story.append(Spacer(1, 6))
            continue

        if brut.startswith("*Figure") or brut.startswith("*Tableau"):
            vider_tableau()
            story.append(Paragraph(_enrichir(brut.strip("*")), S_legende))
            continue

        vider_tableau()
        mo = re.match(r"^(\d+)\.\s+(.*)$", brut)
        if mo:
            story.append(Paragraph(_enrichir(mo.group(2)), S_liste,
                                   bulletText="%s." % mo.group(1)))
            continue
        if re.match(r"^[-*+]\s+", brut):
            story.append(Paragraph(_enrichir(re.sub(r"^[-*+]\s+", "", brut)),
                                   S_liste, bulletText="•"))
            continue
        story.append(Paragraph(_enrichir(brut), S_corps))

    vider_tableau()

    if titres:
        entrees = []
        for niveau, titre in titres:
            if niveau == 1:
                entrees.append('<link href="#%s" color="#102A57"><b>%s</b>'
                               '</link>' % (ancre(titre), echapper(titre)))
            elif niveau == 2 and entrees:
                entrees.append('<link href="#%s" color="#1D4ED8">%s</link>'
                               % (ancre(titre), echapper(titre)))
        if entrees:
            bloc = [PageBreak(), Paragraph("Sommaire", S_h1), Spacer(1, 12)]
            bloc += [Paragraph(e, S_som) for e in entrees]
            position = _position_insertion_sommaire(story)
            for element in reversed(bloc):
                story.insert(position, element)

    doc.build(story)
    if not os.path.isfile(SORTIE_PDF):
        echec("PDF non produit par le repli ReportLab")

# --------------------------------------------------------------------------
# 4. Contrôles bloquants sur les fichiers produits
# --------------------------------------------------------------------------

def compter_pages_pdf(chemin):
    """Nombre de pages sans dépendance externe."""
    with open(chemin, "rb") as f:
        donnees = f.read()
    correspondances = re.findall(rb"/Type\s*/Page[^s]", donnees)
    if correspondances:
        return len(correspondances)
    for motif in (rb"/Count\s+(\d+)",):
        valeurs = [int(v) for v in re.findall(motif, donnees)]
        if valeurs:
            return max(valeurs)
    return 0


def compter_images_docx(chemin):
    with zipfile.ZipFile(chemin) as zf:
        return len([n for n in zf.namelist()
                    if n.startswith("word/media/")])


def controler_textes_produits(chemins):
    """Aucun secret, aucun caractère non français dans les livrables."""
    problemes = []
    for chemin in chemins:
        nom = os.path.basename(chemin)
        if not os.path.isfile(chemin):
            problemes.append("%s : fichier absent" % nom)
            continue
        taille = os.path.getsize(chemin)
        if taille < TAILLE_MIN:
            problemes.append("%s : trop léger (%d octets < %d)"
                             % (nom, taille, TAILLE_MIN))
        if chemin.endswith(".docx"):
            with zipfile.ZipFile(chemin) as zf:
                contenu = b"".join(
                    zf.read(n) for n in zf.namelist()
                    if n.endswith(".xml") and "document" in n)
            contenu = contenu.decode("utf-8", "ignore")
        else:
            with open(chemin, "rb") as f:
                contenu = f.read().decode("latin-1", "ignore")
        for motif in MOTIFS_SECRETS:
            if re.search(motif, contenu, re.IGNORECASE):
                problemes.append("%s : secret détecté (%r)" % (nom, motif))
    return problemes


def controler(texte, images):
    """Exécute tous les contrôles et renvoie un rapport."""
    infos, problemes = [], []
    # le compte doit correspondre au nombre de chapitres (titres «# N. »)
    # et non au titre du document, numéroté à part.
    nb_chapitres = len(re.findall(r"^# \d+\. ", texte, re.M))
    nb_figures = len(re.findall(r"^\*Figure \d+ ", texte, re.M))
    infos.append(("Source", "%d chapitres, %d figures légendées"
                  % (nb_chapitres, nb_figures)))

    problemes_source = controler_source(texte)[0]
    problemes += problemes_source
    infos.append(("Images référencées présentes sur disque",
                  "oui (%d)" % len(images) if not problemes_source
                  else "NON (%d problèmes)" % len(problezes_source)))

    if not os.path.isfile(SORTIE_DOCX):
        echec("DOCX absent : %s" % SORTIE_DOCX)
    if not os.path.isfile(SORTIE_PDF):
        echec("PDF absent : %s" % SORTIE_PDF)

    taille_docx = os.path.getsize(SORTIE_DOCX)
    taille_pdf = os.path.getsize(SORTIE_PDF)
    nb_images = compter_images_docx(SORTIE_DOCX)
    nb_pages = compter_pages_pdf(SORTIE_PDF)

    infos.append(("DOCX", "%s — %d images, %.0f Ko"
                  % (os.path.basename(SORTIE_DOCX), nb_images, taille_docx / 1024)))
    infos.append(("PDF", "%s — %d pages, %.0f Ko"
                  % (os.path.basename(SORTIE_PDF), nb_pages, taille_pdf / 1024)))

    if nb_images < IMAGES_MIN:
        problemes.append("DOCX : %d images < %d attendues"
                         % (nb_images, IMAGES_MIN))
    if nb_pages < PAGES_MIN:
        problemes.append("PDF : %d pages < %d attendues" % (nb_pages, PAGES_MIN))
    if taille_docx < TAILLE_MIN:
        problemes.append("DOCX trop léger : %d octets" % taille_docx)
    if taille_pdf < TAILLE_MIN:
        problemes.append("PDF trop léger : %d octets" % taille_pdf)

    problemes += controler_textes_produits([SORTIE_DOCX, SORTIE_PDF])
    return infos, problemes


# --------------------------------------------------------------------------
# 5. Programme principal
# --------------------------------------------------------------------------

def principal():
    try:
        texte = lire_source()
        problemes, images = controler_source(texte)
        if problemes:
            info("SOURCE — anomalies détectées :")
            for p in problemes:
                info("   - %s" % p)
            echec("La source ne satisfait pas les contrôles : build interrompu.")

        with tempfile.TemporaryDirectory(prefix="manuel_") as temporaire:
            construire_docx(texte, temporaire)
        construire_pdf()

        infos, problemes = controler(texte, images)
        info("--- Contrôles ---")
        for libelle, valeur in infos:
            info("  %-45s %s" % (libelle, valeur))
        if problemes:
            info("RÉSULTAT : ÉCHEC")
            for p in problemes:
                info("   - %s" % p)
            return 1
        info("RÉSULTAT : SUCCÈS — tous les contrôles sont satisfaits.")
        return 0

    except EchecControle as e:
        info("ÉCHEC BLOQUANT : %s" % e)
        return 2


if __name__ == "__main__":
    sys.exit(principal())
