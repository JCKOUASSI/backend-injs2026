#!/usr/bin/env python3
"""Génère le manuel PDF institutionnel (A4, couverture premium, sommaire,
pagination, signets, index des profils, glossaire).

Sortie : documentation/manuel_utilisateur/pdf/MANUEL_UTILISATEUR_OFFICIEL_INJS_2026.pdf
Dépendance : reportlab (déjà exigée par le backend).
"""
from __future__ import annotations

import re
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.pdfmetrics import registerFontFamily
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate, CondPageBreak, Frame, Image, KeepTogether, NextPageTemplate,
    PageBreak, PageTemplate, Paragraph, Spacer, Table, TableStyle,
)

from socle import (
    APPLICATION, CAPTURES, DATE_GENERATION, EDITION, INSTITUTION, LISTE_PROFILS,
    META, MODULES, PALETTE, RACINE, ROLES, SECTIONS, TITRE, VERSION_DOC,
    roles_par_famille, roles_sensibles,
)
from fiches import construire_fiches
from matrice import construire_matrice
from parties_1_3 import PARTIE_I, PARTIE_II, PARTIE_III
from parties_4_7 import PARTIE_IV, PARTIE_V, PARTIE_VI, PARTIE_VII
from parties_8_12 import PARTIE_VIII, PARTIE_IX, PARTIE_X, PARTIE_XI, PARTIE_XII

SORTIE = RACINE / "pdf"
IMAGES = RACINE / "html" / "images"
FICHIER = SORTIE / "MANUEL_UTILISATEUR_OFFICIEL_INJS_2026.pdf"

LARGE_P, HAUT_P = landscape(A4)
NAVY = colors.HexColor(PALETTE["navy"])
PROFOND = colors.HexColor(PALETTE["profond"])
BLEU = colors.HexColor(PALETTE["clair"])
BLEU_PALE = colors.HexColor(PALETTE["tres_clair"])
TEXTE = colors.HexColor(PALETTE["texte"])
DOUX = colors.HexColor(PALETTE["texte_doux"])
MUET = colors.HexColor("#64748B")
BORD = colors.HexColor(PALETTE["bordure"])
BORD_DOUX = colors.HexColor("#E2E8F0")
SURFACE = colors.HexColor("#F8FAFC")
SUCCES = colors.HexColor(PALETTE["succes"])
SUCCES_FD = colors.HexColor("#ECFDF5")
ALERTE = colors.HexColor(PALETTE["alerte"])
ALERTE_FD = colors.HexColor("#FFFBEB")
DANGER = colors.HexColor(PALETTE["danger"])
DANGER_FD = colors.HexColor("#FEF2F2")

PARTIES = [PARTIE_I, PARTIE_II, PARTIE_III, PARTIE_IV, PARTIE_V, PARTIE_VI,
           PARTIE_VII, PARTIE_VIII, PARTIE_IX, PARTIE_X, PARTIE_XI, PARTIE_XII]

# ─────────────────────────────────────────────────────────── polices
def _enregistrer_polices():
    """Tente DejaVu (large couverture Unicode), retombe sur Helvetica."""
    candidats = [
        ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
         "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
         "/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf"),
    ]
    for reg, gras, ital in candidats:
        if all(Path(p).exists() for p in (reg, gras)):
            try:
                pdfmetrics.registerFont(TTFont("Corps", reg))
                pdfmetrics.registerFont(TTFont("Corps-Bold", gras))
                if Path(ital).exists():
                    pdfmetrics.registerFont(TTFont("Corps-Italic", ital))
                else:
                    pdfmetrics.registerFont(TTFont("Corps-Italic", reg))
                registerFontFamily("Corps", normal="Corps", bold="Corps-Bold",
                                   italic="Corps-Italic", boldItalic="Corps-Bold")
                return "Corps", "Corps-Bold", "Corps-Italic"
            except Exception:
                pass
    return "Helvetica", "Helvetica-Bold", "Helvetica-Oblique"


CORPS, GRAS, ITAL = _enregistrer_polices()


def _styles():
    ss = getSampleStyleSheet()
    base = dict(fontName=CORPS, textColor=TEXTE)

    s = {}
    s["corps"] = ParagraphStyle("corps", parent=ss["BodyText"], fontName=CORPS,
                                fontSize=9.6, leading=14.4, textColor=TEXTE,
                                alignment=TA_JUSTIFY, spaceAfter=6)
    s["h3"] = ParagraphStyle("h3", fontName=GRAS, fontSize=11.2, leading=15,
                             textColor=NAVY, spaceBefore=9, spaceAfter=4)
    s["h2"] = ParagraphStyle("h2", fontName=GRAS, fontSize=14.2, leading=18,
                             textColor=NAVY, spaceBefore=3, spaceAfter=7)
    s["h1partie"] = ParagraphStyle("h1partie", fontName=GRAS, fontSize=25, leading=29,
                                   textColor=colors.white, spaceAfter=2)
    s["partienum"] = ParagraphStyle("partienum", fontName=GRAS, fontSize=9, leading=11,
                                    textColor=colors.HexColor("#9EC8F0"))
    s["chapitrenum"] = ParagraphStyle("chapitrenum", fontName=GRAS, fontSize=8.5,
                                      textColor=BLEU)
    s["titrechapitre"] = ParagraphStyle("titrechapitre", fontName=GRAS, fontSize=15.5,
                                        leading=19, textColor=NAVY, spaceAfter=3)
    s["profils"] = ParagraphStyle("profils", fontName=ITAL, fontSize=7.8, leading=10,
                                  textColor=MUET, spaceAfter=6)
    s["petit"] = ParagraphStyle("petit", fontName=CORPS, fontSize=8.2, leading=11.4,
                                textColor=DOUX)
    s["legende"] = ParagraphStyle("legende", fontName=ITAL, fontSize=8.1, leading=11,
                                  textColor=DOUX, spaceBefore=3)
    s["cellule"] = ParagraphStyle("cellule", fontName=CORPS, fontSize=7.9, leading=10.4,
                                  textColor=TEXTE)
    s["celluleb"] = ParagraphStyle("celluleb", fontName=GRAS, fontSize=7.9, leading=10.4,
                                   textColor=TEXTE)
    s["entetecell"] = ParagraphStyle("entetecell", fontName=GRAS, fontSize=7.9,
                                     leading=10.4, textColor=colors.white)
    s["etape"] = ParagraphStyle("etape", fontName=CORPS, fontSize=9.3, leading=13,
                                textColor=TEXTE)
    s["exergue"] = ParagraphStyle("exergue", fontName=CORPS, fontSize=9.3, leading=13.4,
                                  textColor=TEXTE)
    s["formule"] = ParagraphStyle("formule", fontName=GRAS, fontSize=10.5, leading=15,
                                  textColor=colors.white, alignment=TA_CENTER)
    s["couvtitre"] = ParagraphStyle("couvtitre", fontName=GRAS, fontSize=38, leading=42,
                                    textColor=colors.white, spaceAfter=10)
    s["couvsous"] = ParagraphStyle("couvsous", fontName=CORPS, fontSize=15, leading=20,
                                   textColor=BLEU)
    s["couvinstit"] = ParagraphStyle("couvinstit", fontName=GRAS, fontSize=9.4, leading=13,
                                     textColor=NAVY, spaceAfter=1)
    s["couvedition"] = ParagraphStyle("couvedition", fontName=GRAS, fontSize=11,
                                      textColor=colors.white)
    s["toc1"] = ParagraphStyle("toc1", fontName=GRAS, fontSize=10.4, leading=15,
                               textColor=NAVY, spaceBefore=7)
    s["toc2"] = ParagraphStyle("toc2", fontName=CORPS, fontSize=9.1, leading=12.6,
                               textColor=DOUX, leftIndent=14)
    s["fichnom"] = ParagraphStyle("fichnom", fontName=GRAS, fontSize=19, leading=22,
                                  textColor=colors.white)
    s["fichfonction"] = ParagraphStyle("fichfonction", fontName=CORPS, fontSize=9.2,
                                       leading=12, textColor=colors.HexColor("#D6E6F7"))
    s["fichsection"] = ParagraphStyle("fichsection", fontName=GRAS, fontSize=10,
                                      leading=13, textColor=BLEU, spaceBefore=9,
                                      spaceAfter=4)
    return s


ST = _styles()

# ─────────────────────────────────────────────────────────── gabarits de page
class Manuel(BaseDocTemplate):
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.plan = []            # (niveau, titre, page)
        self.profils_pages = []   # (nom, page)
        self._partie = ""
        self._chapitre = ""
        self.parties_pages = {}   # page -> titre de partie (passe courante)
        marge_g, marge_d, marge_h, marge_b = 20 * mm, 18 * mm, 24 * mm, 20 * mm
        largeur, hauteur = A4

        couv = Frame(0, 0, largeur, hauteur, id="couv", showBoundary=0,
                     leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
        self.addPageTemplates([
            PageTemplate(id="couverture", frames=[couv], onPage=self._page_couverture),
            PageTemplate(id="standard", frames=[
                Frame(marge_g, marge_b, largeur - marge_g - marge_d,
                      hauteur - marge_h - marge_b, id="corps")
            ], onPage=self._page_standard),
            PageTemplate(id="pleinepage", frames=[
                Frame(marge_g, marge_b, largeur - marge_g - marge_d,
                      hauteur - marge_h - marge_b, id="corps")
            ], onPage=self._page_pleine),
            PageTemplate(id="paysage", frames=[
                Frame(12 * mm, 11 * mm, LARGE_P - 24 * mm, HAUT_P - 20 * mm, id="corps")
            ], onPage=self._page_paysage, pagesize=landscape(A4)),
        ])

    # couverture : composition graphique complète
    def _page_couverture(self, canv, doc):
        largeur, hauteur = A4
        c1, c2 = PROFOND, colors.HexColor("#12507E")
        n = 120
        for i in range(n):
            f = i / (n - 1)
            canv.setFillColor(colors.Color(c1.red + (c2.red - c1.red) * f,
                                           c1.green + (c2.green - c1.green) * f,
                                           c1.blue + (c2.blue - c1.blue) * f))
            canv.rect(0, hauteur * i / n, largeur, hauteur / n + 1, stroke=0, fill=1)
        # halos
        canv.setFillColor(colors.Color(0.29, 0.56, 0.85, alpha=0.20))
        canv.circle(largeur * 0.88, hauteur * 0.82, 118, stroke=0, fill=1)
        canv.setFillColor(colors.Color(1, 1, 1, alpha=0.055))
        canv.circle(largeur * 0.88, hauteur * 0.82, 168, stroke=0, fill=1)
        canv.setFillColor(colors.Color(0.49, 0.78, 1.0, alpha=0.13))
        canv.circle(largeur * 0.10, hauteur * 0.12, 130, stroke=0, fill=1)
        # trame diagonale discrète
        canv.setStrokeColor(colors.Color(1, 1, 1, alpha=0.04))
        canv.setLineWidth(0.8)
        for k in range(-8, 30):
            canv.line(k * 22, 0, k * 22 + hauteur, hauteur)
        # filet supérieur
        canv.setStrokeColor(colors.Color(1, 1, 1, alpha=0.22))
        canv.setLineWidth(0.7)
        canv.line(24 * mm, hauteur - 30 * mm, largeur - 24 * mm, hauteur - 30 * mm)
        canv.setFont(GRAS, 8.4)
        canv.setFillColor(colors.HexColor("#9EC8F0"))
        canv.drawString(24 * mm, hauteur - 26 * mm,
                        "INSTITUT NATIONAL DE LA JEUNESSE ET DES SPORTS D'ABIDJAN")
        canv.setFont(CORPS, 8.4)
        canv.setFillColor(colors.HexColor("#C9DEF2"))
        canv.drawRightString(largeur - 24 * mm, hauteur - 26 * mm, EDITION)
        # pastille logo
        canv.setFillColor(colors.white)
        canv.roundRect(24 * mm, hauteur - 62 * mm, 22 * mm, 22 * mm, 4 * mm,
                       stroke=0, fill=1)
        canv.setFillColor(NAVY)
        canv.setFont(GRAS, 15)
        canv.drawCentredString(35 * mm, hauteur - 51 * mm, "INJS")
        canv.setFont(CORPS, 5.4)
        canv.drawCentredString(35 * mm, hauteur - 56 * mm, "ABIDJAN")
        # bloc titre
        base_y = hauteur * 0.50
        canv.setFillColor(colors.white)
        canv.setFont(GRAS, 40)
        canv.drawString(24 * mm, base_y + 34 * mm, "Manuel")
        canv.drawString(24 * mm, base_y + 18 * mm, "utilisateur")
        canv.setFont(GRAS, 40)
        canv.setFillColor(colors.HexColor("#7EC8FF"))
        canv.drawString(24 * mm, base_y + 2 * mm, "officiel")
        # filet
        canv.setStrokeColor(colors.HexColor("#7EC8FF"))
        canv.setLineWidth(2.6)
        canv.line(24 * mm, base_y - 8 * mm, 24 * mm + 34 * mm, base_y - 8 * mm)
        # sous-titre
        canv.setFillColor(colors.HexColor("#D6E6F7"))
        canv.setFont(CORPS, 13)
        canv.drawString(24 * mm, base_y - 20 * mm, APPLICATION)
        canv.setFont(GRAS, 10.5)
        canv.setFillColor(colors.white)
        canv.drawString(24 * mm, base_y - 29 * mm, "ÉDITION 2026")
        # cartouche d'informations
        canv.setStrokeColor(colors.Color(1, 1, 1, alpha=0.22))
        canv.setLineWidth(0.6)
        canv.line(24 * mm, 62 * mm, largeur - 24 * mm, 62 * mm)
        infos = [
            ("VERSION DOCUMENTAIRE", VERSION_DOC),
            ("DATE DE GÉNÉRATION", DATE_GENERATION),
            ("PROFILS DOCUMENTÉS", str(len(LISTE_PROFILS))),
        ]
        x = 24 * mm
        for label, val in infos:
            canv.setFont(CORPS, 6.4)
            canv.setFillColor(colors.HexColor("#9EC8F0"))
            canv.drawString(x, 54 * mm, label)
            canv.setFont(GRAS, 11)
            canv.setFillColor(colors.white)
            canv.drawString(x, 46 * mm, val)
            x += 54 * mm
        canv.setFont(CORPS, 6.6)
        canv.setFillColor(colors.Color(1, 1, 1, alpha=0.55))
        canv.drawString(24 * mm, 26 * mm,
                        "Document institutionnel — diffusion interne")
        canv.drawRightString(largeur - 24 * mm, 26 * mm,
                             "Application de gestion intégrée INJS")

    def _page_paysage(self, canv, doc):
        canv.setFillColor(NAVY)
        canv.rect(0, HAUT_P - 11 * mm, LARGE_P, 11 * mm, stroke=0, fill=1)
        canv.setFillColor(colors.white)
        canv.setFont(GRAS, 6.8)
        canv.drawString(12 * mm, HAUT_P - 7.4 * mm, "MANUEL UTILISATEUR OFFICIEL")
        canv.setFont(CORPS, 6.8)
        canv.setFillColor(colors.HexColor("#B9D4EE"))
        canv.drawRightString(LARGE_P - 12 * mm, HAUT_P - 7.4 * mm,
                             "Matrice des habilitations — Édition 2026")
        canv.setStrokeColor(BORD_DOUX)
        canv.setLineWidth(0.6)
        canv.line(12 * mm, 9 * mm, LARGE_P - 12 * mm, 9 * mm)
        canv.setFont(GRAS, 8.4)
        canv.setFillColor(NAVY)
        canv.drawRightString(LARGE_P - 12 * mm, 5.5 * mm, str(doc.page))
        canv.setFont(CORPS, 6.4)
        canv.setFillColor(MUET)
        canv.drawString(12 * mm, 5.5 * mm, f"Version {VERSION_DOC}")

    def _page_pleine(self, canv, doc):
        self._decor(canv, doc, sans_numero=True)

    def _page_standard(self, canv, doc):
        self._decor(canv, doc, sans_numero=False)

    def _decor(self, canv, doc, sans_numero=False):
        largeur, hauteur = A4
        n = doc.page
        # bandeau supérieur
        canv.setFillColor(NAVY)
        canv.rect(0, hauteur - 13 * mm, largeur, 13 * mm, stroke=0, fill=1)
        canv.setFillColor(colors.white)
        canv.setFont(GRAS, 6.8)
        canv.drawString(20 * mm, hauteur - 8.6 * mm, "MANUEL UTILISATEUR OFFICIEL")
        canv.setFont(CORPS, 6.8)
        canv.setFillColor(colors.HexColor("#B9D4EE"))
        canv.drawRightString(largeur - 18 * mm, hauteur - 8.6 * mm,
                             f"{INSTITUTION.split(' d')[0]} — {EDITION}")
        # filet de pied
        canv.setStrokeColor(BORD_DOUX)
        canv.setLineWidth(0.6)
        canv.line(20 * mm, 14 * mm, largeur - 18 * mm, 14 * mm)
        canv.setFont(CORPS, 6.9)
        canv.setFillColor(MUET)
        courant = PARTIES_PAGES.get(doc.page, "")
        if not courant and PARTIES_PAGES:
            anterieures = [pg for pg in PARTIES_PAGES if pg <= doc.page]
            courant = PARTIES_PAGES[max(anterieures)] if anterieures else ""
        if courant:
            canv.drawString(20 * mm, 10 * mm, courant[:74])
        canv.setFont(GRAS, 8.4)
        canv.setFillColor(NAVY)
        canv.drawRightString(largeur - 18 * mm, 9.6 * mm, str(n))
        canv.setFont(CORPS, 6.4)
        canv.setFillColor(MUET)
        canv.drawCentredString(largeur / 2, 10 * mm, f"Version {VERSION_DOC}")

    # signets
    def afterFlowable(self, flowable):
        # un KeepTogether masque les attributs portés par son contenu : on les remonte
        if not hasattr(flowable, "_plan_titre") and hasattr(flowable, "_content"):
            for sous in reversed(flowable._content):
                if hasattr(sous, "_plan_titre"):
                    flowable._plan_titre = sous._plan_titre
                    flowable._plan_niveau = sous._plan_niveau
                    break
        if hasattr(flowable, "_plan_titre"):
            titre = flowable._plan_titre
            niveau = flowable._plan_niveau
            cle = f"plan{len(self.plan)}"
            self.canv.bookmarkPage(cle)
            self.canv.addOutlineEntry(titre[:110], cle, level=niveau, closed=niveau > 0)
            self.plan.append((niveau, titre, self.page))
            if niveau == 0:
                self._partie = titre
                self.parties_pages[self.page] = titre
            elif niveau == 1:
                self._chapitre = titre
        if hasattr(flowable, "_profil_nom"):
            cle = f"profil{len(self.profils_pages)}"
            self.canv.bookmarkPage(cle)
            self.canv.addOutlineEntry(flowable._profil_nom[:100], cle,
                                      level=1, closed=True)
            self.profils_pages.append((flowable._profil_nom, self.page))


def P(texte, style="corps"):
    """Paragraphe avec balises minimales (<b>, <i>, <font>)."""
    t = (texte.replace("&", "&amp;").replace("<b>", "\x01").replace("</b>", "\x02")
         .replace("<i>", "\x03").replace("</i>", "\x04")
         .replace("<br/>", "\x05"))
    t = t.replace("<", "&lt;").replace(">", "&gt;")
    t = (t.replace("\x01", "<b>").replace("\x02", "</b>")
         .replace("\x03", "<i>").replace("\x04", "</i>")
         .replace("\x05", "<br/>"))
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
    t = re.sub(r"`(.+?)`", r'<font face="{0}">\1</font>'.format(CORPS), t)
    return Paragraph(t, ST[style])


# ─────────────────────────────────────────────────────────── composants
def titre_partie(partie, premier=False):
    tab = Table([[P(f"PARTIE {partie['numero']}", "partienum")],
                 [P(partie["titre"], "h1partie")]],
                colWidths=[A4[0] - 38 * mm])
    tab.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), NAVY),
        ("LEFTPADDING", (0, 0), (-1, -1), 16),
        ("RIGHTPADDING", (0, 0), (-1, -1), 16),
        ("TOPPADDING", (0, 0), (-1, 0), 16),
        ("BOTTOMPADDING", (0, -1), (-1, -1), 16),
        ("TOPPADDING", (0, 1), (-1, 1), 0),
    ]))
    tab._plan_titre = f"Partie {partie['numero']} — {partie['titre']}"
    tab._plan_niveau = 0
    # une partie commence sur une page neuve, sauf si la page est déjà vierge
    avant = [] if premier else [CondPageBreak(240 * mm)]
    return avant + [tab, Spacer(1, 7 * mm)]


def titre_chapitre(ch, partie_num, idx):
    tab = Table([[P(f"{partie_num}.{idx}", "chapitrenum")],
                 [P(ch["titre"], "titrechapitre")]],
                colWidths=[A4[0] - 38 * mm])
    tab.setStyle(TableStyle([
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 1),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
        ("LINEBELOW", (0, 1), (-1, 1), 0.9, BLEU),
    ]))
    tab._plan_titre = ch["titre"]
    tab._plan_niveau = 1
    profils = ch.get("profils", ["tous"])
    marque = ("Profils concernés : tous" if profils == ["tous"]
              else "Profils concernés : " + ", ".join(profils))
    return [tab, P(marque, "profils")]


def encadre(type_, titre, texte):
    fond = {"information": BLEU_PALE, "attention": ALERTE_FD, "danger": DANGER_FD}
    bord = {"information": BLEU, "attention": ALERTE, "danger": DANGER}
    coul = {"information": NAVY, "attention": ALERTE, "danger": DANGER}
    icone = {"information": "i", "attention": "!", "danger": "X"}
    entete = Paragraph(
        f'<font name="{GRAS}" color="{coul[type_].hexval()}">'
        f'[{icone[type_]}] {titre}</font>', ST["petit"])
    corps = P(texte, "petit")
    t = Table([[entete], [corps]], colWidths=[A4[0] - 44 * mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), fond[type_]),
        ("LINEBEFORE", (0, 0), (0, -1), 3, bord[type_]),
        ("LEFTPADDING", (0, 0), (-1, -1), 9),
        ("RIGHTPADDING", (0, 0), (-1, -1), 9),
        ("TOPPADDING", (0, 0), (-1, 0), 7),
        ("BOTTOMPADDING", (0, -1), (-1, -1), 7),
        ("TOPPADDING", (0, 1), (-1, 1), 1),
    ]))
    return KeepTogether([Spacer(1, 2 * mm), t, Spacer(1, 3 * mm)])


def tableau(entetes, lignes, largeurs=None):
    dispo = A4[0] - 38 * mm
    if largeurs is None:
        largeurs = [dispo / len(entetes)] * len(entetes)
    else:
        total = sum(largeurs)
        largeurs = [w / total * dispo for w in largeurs]
    data = [[Paragraph(e, ST["entetecell"]) for e in entetes]]
    for ligne in lignes:
        data.append([P(str(c), "cellule") for c in ligne])
    t = Table(data, colWidths=largeurs, repeatRows=1, hAlign="LEFT")
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("GRID", (0, 0), (-1, -1), 0.4, BORD_DOUX),
        ("BOX", (0, 0), (-1, -1), 0.7, BORD),
    ]
    for i in range(2, len(data), 2):
        style.append(("BACKGROUND", (0, i), (-1, i), SURFACE))
    t.setStyle(TableStyle(style))
    return t


def etapes(liste):
    data = []
    for i, e in enumerate(liste, 1):
        num = Paragraph(f'<font name="{GRAS}" color="{NAVY.hexval()}">{i}</font>',
                        ST["etape"])
        data.append([num, P(e, "etape")])
    t = Table(data, colWidths=[8 * mm, A4[0] - 46 * mm], hAlign="LEFT")
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 2),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LINEBELOW", (0, 0), (-1, -2), 0.3, BORD_DOUX),
    ]))
    return t


def figure(cap):
    chemin = IMAGES / cap["image"]
    if not chemin.exists():
        return P(f"[capture absente : {cap['image']}]", "petit")
    from PIL import Image as PILImage
    with PILImage.open(chemin) as im:
        l, h = im.size
    dispo_l = A4[0] - 38 * mm
    dispo_h = 112 * mm
    ratio = min(dispo_l / l, dispo_h / h, 1.0)
    img = Image(str(chemin), width=l * ratio, height=h * ratio)
    img.hAlign = "CENTER"
    legende = Paragraph(
        f'<font name="{GRAS}" color="{NAVY.hexval()}">{cap["titre"]}</font> — '
        f'{cap["legende"]}', ST["legende"])
    t = Table([[img], [legende]], colWidths=[A4[0] - 38 * mm])
    t.setStyle(TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("BOX", (0, 0), (0, 0), 0.5, BORD),
    ]))
    return KeepTogether([Spacer(1, 2 * mm), t, Spacer(1, 3.5 * mm)])


def bloc(genre, valeur):
    """Traduit un bloc de contenu en éléments ReportLab."""
    if genre == "p":
        return [P(valeur)]
    if genre == "h3":
        return [CondPageBreak(24 * mm), P(valeur, "h3")]
    if genre == "liste":
        return [P("• " + x) for x in valeur]
    if genre == "etapes":
        return [Spacer(1, 1.5 * mm), etapes(valeur), Spacer(1, 3 * mm)]
    if genre == "encadre":
        return [encadre(valeur.get("type", "information"),
                        valeur.get("titre", ""), valeur.get("texte", ""))]
    if genre == "figure":
        trouve = next((c for c in CAPTURES if c["fichier"] == valeur["image"]), None)
        cap = {"image": valeur["image"],
               "titre": valeur.get("titre", ""),
               "legende": valeur.get("legende", "")}
        if trouve:
            cap["titre"] = cap["titre"] or trouve["titre"]
            cap["legende"] = cap["legende"] or trouve["legende"]
        return [figure(cap)]
    if genre == "tableau":
        return [Spacer(1, 2 * mm), tableau(valeur["entetes"], valeur["lignes"]),
                Spacer(1, 3 * mm)]
    if genre == "formule":
        t = Table([[P(valeur, "formule")]], colWidths=[A4[0] - 44 * mm])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), NAVY),
            ("TOPPADDING", (0, 0), (-1, -1), 11),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 11),
            ("LEFTPADDING", (0, 0), (-1, -1), 10),
            ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ]))
        return [Spacer(1, 2 * mm), t, Spacer(1, 3 * mm)]
    if genre == "tableau_permissions_critiques":
        from socle import RBAC
        lignes = [[c, c.split(".")[0], c.split(".")[-1]]
                  for c in RBAC["permissions_critiques"]]
        return [Spacer(1, 2 * mm),
                tableau(["Permission", "Domaine", "Action"], lignes, [3.2, 1.4, 1.2]),
                Spacer(1, 3 * mm)]
    if genre == "tableau_modules_navigation":
        lignes = []
        for s in SECTIONS:
            apercu = ", ".join(e["libelle"] for e in s["enfants"][:3])
            if len(s["enfants"]) > 3:
                apercu += f" (+{len(s['enfants']) - 3})"
            lignes.append([s["libelle"], str(len(s["enfants"])),
                           s.get("chemin") or "—", apercu or "—"])
        return [Spacer(1, 2 * mm),
                tableau(["Module", "Écrans", "Entrée", "Écrans principaux"],
                        lignes, [1.5, 0.6, 1.4, 3.4]),
                Spacer(1, 3 * mm)]
    if genre == "tableau_modules_rbac":
        lignes = [[m["code"], m["libelle"], m["app"],
                   "sensible" if m["sensible"] else "—"] for m in MODULES]
        return [Spacer(1, 2 * mm),
                tableau(["Code", "Domaine", "Application", "Nature"],
                        lignes, [1.7, 2.8, 1.5, 0.9]),
                Spacer(1, 3 * mm)]
    if genre == "roles_par_famille":
        out = []
        for libelle, roles in roles_par_famille():
            lignes = [[r["code"], r["libelle"], f"N{r['niveau'][1]}",
                       r["perimetre"], "sensible" if r["sensible"] else "—"]
                      for r in roles]
            out.append(CondPageBreak(40 * mm))
            out.append(P(f"{libelle} — {len(roles)} rôles", "h3"))
            out.append(tableau(["Code", "Libellé", "Niv.", "Périmètre", "Sens."],
                               lignes, [1.9, 2.6, 0.5, 1.1, 0.7]))
            out.append(Spacer(1, 4 * mm))
        return out
    if genre == "glossaire":
        entrees = [
            ("Admission", "Décision par laquelle un candidat est déclaré apte à rejoindre "
                          "l'institut. Distincte de l'inscription."),
            ("Candidature", "Dossier déposé par un candidat en vue d'une admission."),
            ("Délibération", "Réunion au cours de laquelle le jury arrête les décisions."),
            ("Délégation", "Transfert temporaire et borné de droits à un autre agent."),
            ("ECUE", "Élément constitutif d'une unité d'enseignement."),
            ("ECTS", "Système européen de transfert de crédits : 30 par semestre."),
            ("Émargement", "Enregistrement de la présence des étudiants à une séance."),
            ("Habilitation", "Droit accordé à un compte, résultant d'un rôle et d'un "
                             "périmètre."),
            ("Maquette", "Document décrivant l'organisation des UE par semestre."),
            ("Périmètre", "Étendue dans laquelle un droit produit ses effets."),
            ("Permission", "Autorisation précise au format module.ressource.action."),
            ("Rôle", "Fonction exercée, porteuse d'un ensemble de permissions."),
            ("UE", "Unité d'enseignement, composée d'un ou plusieurs ECUE."),
            ("Verrouillage", "Clôture de la saisie des notes."),
        ]
        return [tableau(["Terme", "Définition"], [[a, b] for a, b in sorted(entrees)],
                        [1.2, 4.4]),
                Spacer(1, 3 * mm)]
    if genre == "problemes":
        out = []
        for pb in valeur:
            contenu = [
                P(f'<b>{pb["symptome"]}</b>', "h3"),
                P(f'<b>Cause probable.</b> {pb["cause"]}'),
                P(f'<b>Vérification.</b> {pb["verification"]}'),
                P(f'<b>Solution.</b> {pb["solution"]}'),
                P(f'<b>Contact.</b> {pb["contact"]}', "petit"),
            ]
            t = Table([[c] for c in contenu], colWidths=[A4[0] - 44 * mm])
            t.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), colors.white),
                ("LINEBEFORE", (0, 0), (0, -1), 2.5, ALERTE),
                ("LEFTPADDING", (0, 0), (-1, -1), 9),
                ("RIGHTPADDING", (0, 0), (-1, -1), 9),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                ("BOX", (0, 0), (-1, -1), 0.4, BORD_DOUX),
            ]))
            out.append(KeepTogether([t, Spacer(1, 3 * mm)]))
        return out
    return [P(f"[bloc non rendu : {genre}]", "petit")]


# ─────────────────────────────────────────────────────────── fiches
def fiche_pdf(f):
    elements = []
    entete = Table(
        [[P(f["nom"], "fichnom")],
         [P(f"{f['fonction']}", "fichfonction")],
         [P(f"{f['ecrans_visibles']} écrans · "
            f"{'Accès web' if f['web'] else 'Sans accès web'} · "
            f"Niveaux : {f['niveaux']}", "fichfonction")]],
        colWidths=[A4[0] - 38 * mm])
    entete.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), NAVY),
        ("LEFTPADDING", (0, 0), (-1, -1), 14),
        ("RIGHTPADDING", (0, 0), (-1, -1), 14),
        ("TOPPADDING", (0, 0), (-1, 0), 13),
        ("BOTTOMPADDING", (0, -1), (-1, -1), 12),
        ("TOPPADDING", (0, 1), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -2), 2),
    ]))
    entete._profil_nom = f["nom"]
    elements += [PageBreak(), entete, Spacer(1, 5 * mm)]

    elements.append(P("A. Présentation", "fichsection"))
    elements.append(P(f["description"]))
    elements.append(Spacer(1, 1.5 * mm))
    elements.append(tableau(
        ["Élément", "Valeur"],
        [["Code technique", f["code"]],
         ["Famille", f["famille"]],
         ["Applications", f["apps"]],
         ["Actions backend", f["actions"]]],
        [1.3, 4.2]))
    elements.append(Spacer(1, 4 * mm))

    elements.append(P("B. Navigation", "fichsection"))
    if f["sections"]:
        for nom_section, menus in f["sections"]:
            elements.append(P(f"<b>{nom_section}</b> ({len(menus)} écrans)", "petit"))
            elements.append(tableau(
                ["Écran", "Adresse"],
                [[m["libelle"], m["chemin"] or "—"] for m in menus],
                [2.9, 2.6]))
            elements.append(Spacer(1, 2.5 * mm))
    else:
        elements.append(P("Ce profil n'a aucun écran dans l'interface web. Ses accès "
                          "passent par les applications mobiles de badgeage."))
    elements.append(Spacer(1, 4 * mm))

    elements.append(P("C. Autorisations", "fichsection"))
    cap = "".join(f"• {c}<br/>" for c in f["capacites"]) or "Aucune capacité web."
    inter = "".join(f"• {c}<br/>" for c in f["interdits"]) or "—"
    duo = Table([[P('<font color="#059669"><b>Actions autorisées</b></font>'
                    f'<br/><font size="8">{cap}</font>', "petit"),
                  P('<font color="#DC2626"><b>Actions interdites</b></font>'
                    f'<br/><font size="8">{inter}</font>', "petit")]],
                colWidths=[(A4[0] - 42 * mm) / 2] * 2)
    duo.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, 0), SUCCES_FD),
        ("BACKGROUND", (1, 0), (1, 0), DANGER_FD),
        ("BOX", (0, 0), (0, 0), 0.5, colors.HexColor("#A7F3D0")),
        ("BOX", (1, 0), (1, 0), 0.5, colors.HexColor("#FECACA")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    elements.append(duo)
    elements.append(Spacer(1, 4 * mm))

    if f["cas"]:
        elements.append(P("D. Cas pratiques", "fichsection"))
        for titre_cas, contexte, liste_etapes in f["cas"]:
            elements.append(KeepTogether([
                P(f"<b>{titre_cas}</b>", "h3"),
                P(f"<i>{contexte}</i>", "petit"),
                etapes(liste_etapes),
                Spacer(1, 3 * mm),
            ]))

    if f["erreurs"]:
        elements.append(P("E. Erreurs fréquentes", "fichsection"))
        elements.append(tableau(["Symptôme", "Conduite à tenir"],
                                [[a, b] for a, b in f["erreurs"]], [2.2, 3.3]))
        elements.append(Spacer(1, 3 * mm))
    return elements


# ─────────────────────────────────────────────────────────── sommaire paginé
PLAN_PRECEDENT = []
PARTIES_PAGES = {}
_DERNIERES_PARTIES = {}
_DERNIERS_PROFILS = []
PROFILS_PAGES = []


def _construire_sommaire(plan):
    """Table des matières paginée, alimentée par la passe précédente."""
    if not plan:
        return P("—", "petit")
    from reportlab.platypus import Table as _T, TableStyle as _TS
    lignes = []
    for niveau, titre, page in plan:
        if niveau == 0:
            lignes.append([
                Paragraph(f'<b>{titre}</b>',
                          ParagraphStyle("s1", fontName=GRAS, fontSize=9.0, leading=10.4,
                                         textColor=NAVY)),
                Paragraph(f'<b>{page}</b>',
                          ParagraphStyle("p1", fontName=GRAS, fontSize=9.4,
                                         textColor=NAVY, alignment=2)),
            ])
        else:
            lignes.append([
                Paragraph(titre,
                          ParagraphStyle("s2", fontName=CORPS, fontSize=8.0, leading=9.6,
                                         textColor=DOUX, leftIndent=12)),
                Paragraph(str(page),
                          ParagraphStyle("p2", fontName=CORPS, fontSize=8.0,
                                         textColor=DOUX, alignment=2)),
            ])
    t = _T(lignes, colWidths=[A4[0] - 38 * mm - 16 * mm, 16 * mm])
    t.setStyle(_TS([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 1),
        ("RIGHTPADDING", (0, 0), (-1, -1), 1),
        ("TOPPADDING", (0, 0), (-1, -1), 0.2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0.2),
        ("LINEBELOW", (0, 0), (-1, -2), 0.25, colors.HexColor("#E8EEF5")),
    ]))
    return t


# ─────────────────────────────────────────────────────────── construction
def _index_profils(entrees):
    """Index alphabétique des profils avec renvoi vers leur fiche."""
    if not entrees:
        return []
    out = [PageBreak()]
    bandeau = Table([[P("INDEX", "partienum")],
                     [P("Index des profils utilisateur", "h1partie")]],
                    colWidths=[A4[0] - 38 * mm])
    bandeau.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), NAVY),
        ("LEFTPADDING", (0, 0), (-1, -1), 16),
        ("RIGHTPADDING", (0, 0), (-1, -1), 16),
        ("TOPPADDING", (0, 0), (-1, 0), 16),
        ("BOTTOMPADDING", (0, -1), (-1, -1), 16),
        ("TOPPADDING", (0, 1), (-1, 1), 0),
    ]))
    bandeau._plan_titre = "Index des profils utilisateur"
    bandeau._plan_niveau = 0
    out += [bandeau, Spacer(1, 6 * mm)]
    out.append(P("Chaque profil disposant d'une fiche renvoie à la page où elle "
                 "commence. Les profils sans accès web y figurent également.", "petit"))
    out.append(Spacer(1, 4 * mm))

    lignes = []
    for nom, page in entrees:
        lignes.append([
            P(f"<b>{nom}</b>", "celluleb"),
            P(f'<a href="#profil-{page}" color="#073763">{page}</a>', "cellule"),
        ])
    t = Table(lignes, colWidths=[(A4[0] - 38 * mm) * 0.8, (A4[0] - 38 * mm) * 0.2])
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 3.2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3.2),
        ("LINEBELOW", (0, 0), (-1, -2), 0.25, colors.HexColor("#E8EEF5")),
    ]))
    out += [t, Spacer(1, 4 * mm)]
    out.append(P("La fiche détaille la présentation du profil, son tableau de bord, "
                 "son menu, les modules accessibles, un guide en étapes, ses "
                 "autorisations, des cas pratiques et les erreurs fréquentes.", "petit"))
    return out


def _partie_matrice():
    """Partie XIV — matrice « Profil | Modules | CRUD | Export », en paysage."""
    from reportlab.platypus import NextPageTemplate

    colonnes, lignes, modules = construire_matrice()
    libelles = dict(modules)
    out = [NextPageTemplate("paysage"), PageBreak()]

    bandeau = Table([[P("PARTIE XIV", "partienum")],
                     [P("Matrice des habilitations par profil", "h1partie")]],
                    colWidths=[LARGE_P - 24 * mm])
    bandeau.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), NAVY),
        ("LEFTPADDING", (0, 0), (-1, -1), 16),
        ("RIGHTPADDING", (0, 0), (-1, -1), 16),
        ("TOPPADDING", (0, 0), (-1, 0), 13),
        ("BOTTOMPADDING", (0, -1), (-1, -1), 13),
        ("TOPPADDING", (0, 1), (-1, 1), 0),
    ]))
    bandeau._plan_titre = "Partie XIV — Matrice des habilitations par profil"
    bandeau._plan_niveau = 0
    out += [bandeau, Spacer(1, 5 * mm)]

    out.append(P(
        "Cette matrice répond à une question simple : pour chaque profil, quels "
        "modules sont atteignables et quelles opérations sont réellement "
        "autorisées. Elle est calculée à partir du référentiel d'habilitations de "
        "l'application : le niveau détenu par le profil sur un module est comparé "
        "au niveau minimal exigé par chaque verbe métier (consulter, créer, "
        "modifier, valider, supprimer, exporter).", "corps"))
    out.append(Spacer(1, 2 * mm))
    out.append(P(
        "<b>Lecture :</b> « Oui » signifie que l'opération est autorisée sur au "
        "moins une ressource du module, dans le périmètre du profil. « — » "
        "signifie qu'elle est refusée. Une opération autorisée n'est pas "
        "nécessairement possible sur <i>toutes</i> les ressources du module : le "
        "périmètre (son secrétariat, ses ECUE, son service) reste déterminant.",
        "petit"))
    out.append(Spacer(1, 5 * mm))

    # tableau condensé : 7 colonnes imposées
    entetes = ["Profil", "Modules accessibles", "Consultation", "Création",
               "Modification", "Validation", "Suppression", "Export"]
    largeurs = [30 * mm, 78 * mm, 27 * mm, 19 * mm, 23 * mm, 20 * mm,
                23 * mm, 18 * mm]
    donnees = [[P(h, "entetecell") for h in entetes]]
    for l in lignes:
        noms = ", ".join(libelles.get(m, m) for m in l["modules"]) or "—"
        if not l["web"]:
            noms = "Aucun (accès web fermé)"
        rangee = [P(f"<b>{l['profil']}</b>", "celluleb"),
                  P(noms, "cellule")]
        for c, _ in colonnes:
            v = l["cellules"].get(c)
            marque = "Oui" if isinstance(v, list) and v else "—"
            rangee.append(P(f"<b>{marque}</b>" if marque == "Oui" else marque,
                            "cellule"))
        donnees.append(rangee)

    t = Table(donnees, colWidths=largeurs, repeatRows=1)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (2, 1), (-1, -1), "CENTER"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("GRID", (0, 0), (-1, -1), 0.35, BORD_DOUX),
        ("BOX", (0, 0), (-1, -1), 0.7, BORD),
    ]
    for i in range(1, len(donnees)):
        if i % 2 == 0:
            style.append(("BACKGROUND", (0, i), (-1, i), SURFACE))
    t.setStyle(TableStyle(style))
    out += [t, Spacer(1, 4 * mm)]

    out.append(P(
        "Les deux profils FORMATEUR et AUDITEUR figurent dans la matrice pour une "
        "raison de traçabilité : leur rôle existe au catalogue et peut être "
        "attribué, mais l'accès à l'interface web leur est refusé. Ils ne "
        "disposent donc d'aucun module dans l'application. Cette absence est un "
        "choix de paramétrage, pas une erreur de saisie.", "petit"))
    out += [Spacer(1, 4 * mm)]

    # détail module par module, pour les profils les plus étendus
    out.append(P("Détail des niveaux par module", "h3"))
    out.append(P(
        "Le tableau suivant donne, pour chaque couple profil / module, le niveau "
        "détenu. Il permet de comprendre pourquoi une opération est ouverte ou "
        "fermée dans la matrice ci-dessus.", "petit"))
    out.append(Spacer(1, 3 * mm))

    # Tableau de synthèse : une colonne par module, numérotée, légende en dessous
    ent2 = ["Profil"] + [str(i) for i in range(1, len(modules) + 1)]
    data2 = [[P(h, "entetecell") for h in ent2]]
    for l in lignes:
        r = [P(f"<b>{l['profil']}</b>", "celluleb")]
        for code, _ in modules:
            if not l["web"] or code not in l["modules"]:
                r.append(P("·", "cellule"))
            else:
                r.append(P("<b>●</b>", "cellule"))
        data2.append(r)
    n = len(modules)
    larg_mod = (LARGE_P - 24 * mm - 40 * mm) / n
    t2 = Table(data2, colWidths=[40 * mm] + [larg_mod] * n, repeatRows=1)
    st2 = [
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (1, 1), (-1, -1), "CENTER"),
        ("LEFTPADDING", (0, 0), (-1, -1), 2),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("GRID", (0, 0), (-1, -1), 0.3, BORD_DOUX),
    ]
    for i in range(1, len(data2)):
        if i % 2 == 0:
            st2.append(("BACKGROUND", (0, i), (-1, i), SURFACE))
    t2.setStyle(TableStyle(st2))

    # légende numérotée sur deux colonnes, lisible
    moitie = (len(modules) + 1) // 2
    gauche = [(i + 1, libelles[m]) for i, (m, _) in enumerate(modules)][:moitie]
    droite = [(i + 1, libelles[m]) for i, (m, _) in enumerate(modules)][moitie:]
    leg_data = []
    for k in range(moitie):
        g = gauche[k]
        d_ = droite[k] if k < len(droite) else ("", "")
        leg_data.append([P(f"<b>{g[0]}</b>  {g[1]}", "cellule"),
                         P(f"<b>{d_[0]}</b>  {d_[1]}" if d_[0] != "" else "", "cellule")])
    t3 = Table(leg_data, colWidths=[(LARGE_P - 24 * mm) / 2] * 2)
    t3.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 2),
        ("TOPPADDING", (0, 0), (-1, -1), 1.2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1.2),
    ]))

    out += [t2, Spacer(1, 3 * mm), t3, Spacer(1, 2 * mm)]
    out.append(P("● module accessible au profil · · module non accessible", "legende"))


    out.append(P("● module accessible · · module non accessible", "legende"))

    out += [NextPageTemplate("standard")]
    return out


def couverture():
    largeur, hauteur = A4
    # fond dégradé simulé par bandes
    bandes = []
    c1, c2 = PROFOND, colors.HexColor("#12507E")
    n = 90
    for i in range(n):
        f = i / (n - 1)
        col = colors.Color(c1.red + (c2.red - c1.red) * f,
                           c1.green + (c2.green - c1.green) * f,
                           c1.blue + (c2.blue - c1.blue) * f)
        bandes.append(("BACKGROUND", (0, i), (-1, i), col))
    data = [[P("INJS", "couvtitre")] for _ in range(n)]
    # on n'utilise pas de tableau de fond : on dessine dans onPage
    return []


def fond_couverture(canv, doc):
    largeur, hauteur = A4
    c1, c2 = PROFOND, colors.HexColor("#12507E")
    n = 120
    for i in range(n):
        f = i / (n - 1)
        canv.setFillColor(colors.Color(c1.red + (c2.red - c1.red) * f,
                                       c1.green + (c2.green - c1.green) * f,
                                       c1.blue + (c2.blue - c1.blue) * f))
        canv.rect(0, hauteur * i / n, largeur, hauteur / n + 1, stroke=0, fill=1)
    # halo
    canv.setFillColor(colors.Color(1, 1, 1, alpha=0.05))
    canv.circle(largeur * 0.86, hauteur * 0.8, 170, stroke=0, fill=1)
    canv.setFillColor(colors.Color(0.29, 0.56, 0.85, alpha=0.18))
    canv.circle(largeur * 0.86, hauteur * 0.8, 120, stroke=0, fill=1)


def construire():
    """Compose le document jusqu'à ce que la pagination du sommaire soit stable."""
    global PLAN_PRECEDENT, PARTIES_PAGES, _DERNIERES_PARTIES, PROFILS_PAGES
    SORTIE.mkdir(parents=True, exist_ok=True)

    PLAN_PRECEDENT = []
    precedent = None
    for tentative in range(1, 6):
        plan = _assembler(essai=True)
        if plan is None:
            break
        if precedent is not None and [(n, t, pg) for (n, t, pg) in plan] == \
                [(n, t, pg) for (n, t, pg) in precedent]:
            print(f"  sommaire stabilisé après {tentative - 1} passe(s)")
            PLAN_PRECEDENT = plan
            break
        precedent = plan
        PLAN_PRECEDENT = plan
        PROFILS_PAGES = list(_DERNIERS_PROFILS)
        PARTIES_PAGES = dict(_DERNIERES_PARTIES)
    return _assembler(essai=False)


def _assembler(essai=False):
    global PLAN_PRECEDENT, _DERNIERES_PARTIES, _DERNIERS_PROFILS
    doc = Manuel(str(FICHIER), pagesize=A4,
                 title=f"{TITRE} — {INSTITUTION}",
                 author=INSTITUTION, subject=APPLICATION,
                 creator="Générateur documentaire INJS", lang="fr")

    story = []
    story.append(NextPageTemplate("standard"))

    # ── COUVERTURE (dessinée sur une page dédiée)
    story.append(Spacer(1, 150 * mm))
    story.append(PageBreak())

    # ── PAGE DE TITRE
    story.append(Spacer(1, 10 * mm))
    story.append(P("RÉPUBLIQUE DE CÔTE D'IVOIRE", "couvinstit"))
    story.append(P("INSTITUT NATIONAL DE LA JEUNESSE ET DES SPORTS", "couvinstit"))
    story.append(Spacer(1, 6 * mm))
    story.append(Paragraph("Manuel utilisateur officiel",
                           ParagraphStyle("t", fontName=GRAS, fontSize=30, leading=34,
                                          textColor=NAVY)))
    story.append(Spacer(1, 3 * mm))
    story.append(P(APPLICATION, "couvsous"))
    story.append(Spacer(1, 2 * mm))
    story.append(Paragraph(EDITION, ParagraphStyle("edt", fontName=GRAS, fontSize=11,
                                                   leading=15, textColor=BLEU)))
    story.append(Spacer(1, 8 * mm))
    story.append(tableau(
        ["Élément", "Valeur"],
        [["Version documentaire", VERSION_DOC],
         ["Date de génération", DATE_GENERATION],
         ["Profils documentés", str(len(LISTE_PROFILS))],
         ["Rôles au catalogue", str(len(ROLES))],
         ["Permissions atomiques", f"{META['permissions']:,}".replace(",", " ")],
         ["Domaines fonctionnels", str(len(MODULES))],
         ["Captures d'écran", str(len(CAPTURES))]],
        [1.4, 2.2]))
    story.append(Spacer(1, 6 * mm))
    story.append(encadre("information", "Objet du document",
                         "Ce manuel décrit l'application de gestion intégrée de l'INJS "
                         "d'Abidjan telle qu'elle fonctionne à la date de génération. "
                         "Chaque écran, chaque procédure et chaque autorisation ont été "
                         "vérifiés dans le code source. Aucune fonctionnalité non "
                         "disponible n'y est présentée comme opérationnelle."))
    story.append(PageBreak())

    # ── SOMMAIRE (à remplir après coup : on réserve et on génère en 2 passes)
    sommaire_debut = len(story)
    story.append(Paragraph("Sommaire", ParagraphStyle(
        "tocs", fontName=GRAS, fontSize=22, leading=26, textColor=NAVY,
        spaceAfter=6)))
    if PLAN_PRECEDENT:
        story.append(_construire_sommaire(PLAN_PRECEDENT))
    else:
        story.append(P("Sommaire généré à la seconde passe typographique.", "petit"))
    story.append(PageBreak())

    # ── CORPS
    for _idx, partie in enumerate(PARTIES):
        elements = titre_partie(partie, premier=(_idx == 0))
        story.extend(elements)
        for i, ch in enumerate(partie["chapitres"], 1):
            story.extend(titre_chapitre(ch, partie["numero"], i))
            for b in ch["blocs"]:
                story.extend(bloc(b[0], b[1] if len(b) > 1 else None))
            story.append(Spacer(1, 6 * mm))

    # ── FICHES
    part_fiches = Table([[P("PARTIE XIII", "partienum")],
                         [P("Fiches par profil utilisateur", "h1partie")]],
                        colWidths=[A4[0] - 38 * mm])
    part_fiches.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), NAVY),
        ("LEFTPADDING", (0, 0), (-1, -1), 16),
        ("RIGHTPADDING", (0, 0), (-1, -1), 16),
        ("TOPPADDING", (0, 0), (-1, 0), 16),
        ("BOTTOMPADDING", (0, -1), (-1, -1), 16),
        ("TOPPADDING", (0, 1), (-1, 1), 0),
    ]))
    # ── INDEX DES PROFILS (après la matrice, avant les annexes)
    story.extend(_index_profils(PROFILS_PAGES))

    part_fiches._plan_titre = "Partie XIII — Fiches par profil utilisateur"
    part_fiches._plan_niveau = 0
    story += [PageBreak(), part_fiches, Spacer(1, 6 * mm)]
    story.append(P("Chaque fiche décrit une fonction telle qu'elle est réellement "
                   "outillée. Les profils sans accès web sont conservés : ils expliquent "
                   "pourquoi l'accès est refusé et quelles applications utiliser."))
    for f in construire_fiches():
        story.extend(fiche_pdf(f))

    # ── ANNEXES
    annexe = Table([[P("ANNEXES", "partienum")],
                    [P("Référentiels techniques et glossaire", "h1partie")]],
                   colWidths=[A4[0] - 38 * mm])
    annexe.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), NAVY),
        ("LEFTPADDING", (0, 0), (-1, -1), 16),
        ("RIGHTPADDING", (0, 0), (-1, -1), 16),
        ("TOPPADDING", (0, 0), (-1, 0), 16),
        ("BOTTOMPADDING", (0, -1), (-1, -1), 16),
        ("TOPPADDING", (0, 1), (-1, 1), 0),
    ]))
    # ── PARTIE XIV : MATRICE DES HABILITATIONS (paysage)
    story.extend(_partie_matrice())

    annexe._plan_titre = "Annexes — Référentiels techniques et glossaire"
    annexe._plan_niveau = 0
    story += [PageBreak(), annexe, Spacer(1, 6 * mm)]
    story.append(P("Annexe A — Chiffres clés vérifiés", "h3"))
    story.append(tableau(
        ["Élément", "Valeur", "Source"],
        [["Rôles au catalogue", str(len(ROLES)),
          "catalogue_roles.py"],
         ["Rôles sensibles", str(len(roles_sensibles())),
          "champ sensible"],
         ["Permissions atomiques", f"{META['permissions']:,}".replace(",", " "),
          "deplier_permissions()"],
         ["Domaines fonctionnels", str(len(MODULES)), "catalogue_modules.py"],
         ["Écrans de navigation", str(META["entrees_menu"]), "arborescence.js"],
         ["Profils documentés", str(len(LISTE_PROFILS)), "models.py"],
         ["Captures d'écran", str(len(CAPTURES)), "images réelles"]],
        [2.0, 1.0, 2.0]))
    story.append(Spacer(1, 5 * mm))
    story.append(P("Annexe B — Ce que ce manuel ne documente pas", "h3"))
    story += bloc("liste", [
        "Les rôles du catalogue sans compte attribué : listés en partie III, sans fiche "
        "dédiée.",
        "Les modules annoncés dans les documents de conception mais absents de "
        "l'arborescence de navigation.",
        "Les fonctionnalités de reconnaissance faciale ou de signature électronique, "
        "absentes du code.",
    ])
    story.append(encadre("information", "Principe de rédaction",
                         "Aucune fonctionnalité n'a été inventée. Lorsqu'un élément n'a "
                         "pu être vérifié, il est signalé comme tel."))
    story.append(Spacer(1, 5 * mm))
    story.append(P("Glossaire", "h3"))
    story += bloc("glossaire", None)

    # ── nettoyage : jamais de saut de page en fin de flux
    while story and isinstance(story[-1], (PageBreak, Spacer)):
        story.pop()
    while story and isinstance(story[-1], CondPageBreak):
        story.pop()

    # ── construction
    if essai:
        doc.build(story)
        _DERNIERES_PARTIES = dict(doc.parties_pages)
        _DERNIERS_PROFILS = list(doc.profils_pages)
        plan = [(n, t, p) for (n, t, p) in doc.plan]
        import os as _os
        _os.remove(doc.filename) if _os.path.exists(doc.filename) else None
        return plan

    doc.build(story)
    print(f"PDF généré : {FICHIER} ({FICHIER.stat().st_size:,} octets)")
    print(f"  pages : {doc.page}")
    print(f"  entrées de sommaire : {len(doc.plan)}")
    print(f"  fiches indexées : {len(doc.profils_pages)}")
    return FICHIER


if __name__ == "__main__":
    construire()
