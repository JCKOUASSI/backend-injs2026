# -*- coding: utf-8 -*-
"""Rendu PDF (reportlab) d'un document Markdown restreint, charte INJS-LMD."""
import re, sys, os
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle, StyleSheet1
from reportlab.lib.enums import TA_JUSTIFY, TA_LEFT, TA_CENTER
from reportlab.platypus import (BaseDocTemplate, PageTemplate, Frame, Paragraph, Spacer,
                               Table, TableStyle, KeepTogether, PageBreak, ListFlowable,
                               ListItem, CondPageBreak, HRFlowable)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.fonts import addMapping

D = '/usr/share/fonts/truetype/dejavu/'
pdfmetrics.registerFont(TTFont('DJSans', D + 'DejaVuSans.ttf'))
pdfmetrics.registerFont(TTFont('DJSans-Bold', D + 'DejaVuSans-Bold.ttf'))
pdfmetrics.registerFont(TTFont('DJSerif', D + 'DejaVuSerif.ttf'))
pdfmetrics.registerFont(TTFont('DJSerif-Bold', D + 'DejaVuSerif-Bold.ttf'))
pdfmetrics.registerFont(TTFont('DJMono', D + 'DejaVuSansMono.ttf'))
pdfmetrics.registerFont(TTFont('DJMono-Bold', D + 'DejaVuSansMono-Bold.ttf'))
pdfmetrics.registerFontFamily('DJSans', normal='DJSans', bold='DJSans-Bold', italic='DJSans', boldItalic='DJSans-Bold')
pdfmetrics.registerFontFamily('DJSerif', normal='DJSerif', bold='DJSerif-Bold', italic='DJSerif', boldItalic='DJSerif-Bold')
pdfmetrics.registerFontFamily('DJMono', normal='DJMono', bold='DJMono-Bold', italic='DJMono', boldItalic='DJMono-Bold')

BLEU = colors.HexColor('#0D2B45')
BLEU_CLAIR = colors.HexColor('#1F4E79')
GRIS = colors.HexColor('#5A6B7B')
FILET = colors.HexColor('#C9D4E0')
FOND = colors.HexColor('#F3F6F9')
VERT = colors.HexColor('#1E6B45')
ORANGE = colors.HexColor('#8A5A12')
ROUGE = colors.HexColor('#8C2020')

S = StyleSheet1()
S.add(ParagraphStyle('Corps', fontName='DJSans', fontSize=9.1, leading=12.9,
                     alignment=TA_LEFT, textColor=colors.HexColor('#1C2430'),
                     spaceAfter=4.2))
S.add(ParagraphStyle('CorpsG', fontName='DJSans', fontSize=9.1, leading=12.9,
                     alignment=TA_LEFT, textColor=colors.HexColor('#1C2430'), spaceAfter=4.2))
S.add(ParagraphStyle('H1', fontName='DJSerif-Bold', fontSize=16.5, leading=20,
                     textColor=BLEU, spaceBefore=2, spaceAfter=8))
S.add(ParagraphStyle('H2', fontName='DJSerif-Bold', fontSize=12.2, leading=15.4,
                     textColor=BLEU_CLAIR, spaceBefore=12, spaceAfter=5))
S.add(ParagraphStyle('H3', fontName='DJSans-Bold', fontSize=10.1, leading=13,
                     textColor=BLEU, spaceBefore=9, spaceAfter=3.5))
S.add(ParagraphStyle('Puce', fontName='DJSans', fontSize=9.0, leading=12.4,
                     textColor=colors.HexColor('#1C2430'), spaceAfter=2.2))
S.add(ParagraphStyle('Code', fontName='DJMono', fontSize=7.5, leading=10.6,
                     textColor=colors.HexColor('#22303C'), spaceAfter=0, spaceBefore=0))
S.add(ParagraphStyle('Th', fontName='DJSans-Bold', fontSize=8.1, leading=10.4,
                     textColor=colors.white))
S.add(ParagraphStyle('Td', fontName='DJSans', fontSize=8.0, leading=10.4,
                     textColor=colors.HexColor('#1C2430')))
S.add(ParagraphStyle('Note', fontName='DJSans', fontSize=8.6, leading=12.0,
                     textColor=colors.HexColor('#22303C')))
S.add(ParagraphStyle('TitreDoc', fontName='DJSerif-Bold', fontSize=25, leading=30,
                     textColor=BLEU, spaceAfter=4))
S.add(ParagraphStyle('SousTitreDoc', fontName='DJSans', fontSize=12.5, leading=17,
                     textColor=GRIS, spaceAfter=2))
S.add(ParagraphStyle('Sur', fontName='DJSans-Bold', fontSize=8.6, leading=11,
                     textColor=BLEU_CLAIR, spaceAfter=10))
S.add(ParagraphStyle('PetitCentre', fontName='DJSans', fontSize=8.0, leading=11,
                     textColor=GRIS, alignment=TA_CENTER))
S.add(ParagraphStyle('TdC', fontName='DJSans', fontSize=8.0, leading=10.4,
                     textColor=colors.HexColor('#1C2430'), alignment=TA_CENTER))

INLINE = re.compile(r'(`[^`]+`|\*\*[^*]+\*\*|\*[^*]+\*)')

def esc(t):
    return (t.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;'))

def inline(t):
    t = esc(t)
    out = []
    pos = 0
    for m in INLINE.finditer(t):
        out.append(t[pos:m.start()])
        frag = m.group(0)
        if frag.startswith('`'):
            out.append('<font name="DJMono" size="8.0" color="#8C2020">%s</font>' % frag[1:-1])
        elif frag.startswith('**'):
            out.append('<b>%s</b>' % frag[2:-2])
        else:
            out.append('<i>%s</i>' % frag[1:-1])
        pos = m.end()
    out.append(t[pos:])
    return ''.join(out)

def callout(kind, text):
    palette = {
        'cas':   ('#EAF3EC', VERT,   'CAS PRATIQUE'),
        'note':  ('#EEF2F7', BLEU_CLAIR, 'À RETENIR'),
        'alerte':('#FBF0E4', ORANGE, 'POINT DE VIGILANCE'),
        'limite':('#F8EAEA', ROUGE,  'LIMITE CONSTATÉE'),
    }[kind]
    fond, bord, label = palette
    p = Paragraph('<font name="DJSans-Bold" size="7.6" color="%s">%s</font><br/>%s'
                  % (bord.hexval().replace('0x', '#'), label, inline(text)), S['Note'])
    t = Table([[p]], colWidths=[17.0 * cm])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor(fond)),
        ('LINEBEFORE', (0, 0), (0, -1), 2.6, bord),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    return t

def table(rows):
    head = [Paragraph(inline(c), S['Th']) for c in rows[0]]
    body = [[Paragraph(inline(c), S['Td']) for c in r] for r in rows[1:]]
    n = len(rows[0])
    width = 17.0 * cm
    if n == 2:
        cols = [5.1 * cm, width - 5.1 * cm]
    elif n == 3:
        cols = [4.3 * cm, 4.0 * cm, width - 8.3 * cm]
    elif n == 4:
        cols = [3.6 * cm, 3.2 * cm, 5.2 * cm, width - 12.0 * cm]
    else:
        cols = [width / n] * n
    t = Table([head] + body, colWidths=cols, repeatRows=1)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), BLEU),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('GRID', (0, 0), (-1, -1), 0.4, FILET),
        ('LINEBELOW', (0, 0), (-1, 0), 0.6, BLEU),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, FOND]),
        ('LEFTPADDING', (0, 0), (-1, -1), 4.5),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4.5),
        ('TOPPADDING', (0, 0), (-1, -1), 3.4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3.4),
    ]))
    return t

def code(lines):
    txt = '<br/>'.join(esc(l).replace(' ', '&nbsp;') for l in lines)
    p = Paragraph(txt, S['Code'])
    t = Table([[p]], colWidths=[17.0 * cm])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#F5F7FA')),
        ('LINEBEFORE', (0, 0), (0, -1), 2.6, BLEU_CLAIR),
        ('LEFTPADDING', (0, 0), (-1, -1), 7),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
    ]))
    return t

def parse(md):
    """Renvoie une liste de blocs (type, payload)."""
    lines = md.split('\n')
    blocks, i = [], 0
    while i < len(lines):
        ln = lines[i]
        if ln.startswith('```'):
            i += 1
            buf = []
            while i < len(lines) and not lines[i].startswith('```'):
                buf.append(lines[i]); i += 1
            i += 1
            blocks.append(('code', buf)); continue
        if ln.startswith('%%'):
            blocks.append(('break', None)); i += 1; continue
        if ln.startswith('!!'):
            blocks.append(('callout', (ln[2:].strip(), ln[3:].strip() if False else ''))); i += 1; continue
        m = re.match(r'^(cas|note|alerte|limite)::\s*(.*)$', ln)
        if m:
            blocks.append(('callout', (m.group(1), m.group(2)))); i += 1; continue
        if ln.startswith('|') and i + 1 < len(lines) and set(lines[i + 1].replace('|', '').strip()) <= set('-: '):
            rows = []
            header = [c.strip() for c in ln.strip().strip('|').split('|')]
            rows.append(header)
            i += 2
            while i < len(lines) and lines[i].startswith('|'):
                rows.append([c.strip() for c in lines[i].strip().strip('|').split('|')])
                i += 1
            blocks.append(('table', rows)); continue
        if ln.startswith('#### '):
            blocks.append(('h4', ln[5:].strip())); i += 1; continue
        if ln.startswith('### '):
            blocks.append(('h3', ln[4:].strip())); i += 1; continue
        if ln.startswith('## '):
            blocks.append(('h2', ln[3:].strip())); i += 1; continue
        if ln.startswith('# '):
            blocks.append(('h1', ln[2:].strip())); i += 1; continue
        if ln.startswith('---'):
            blocks.append(('rule', None)); i += 1; continue
        if ln.startswith('> '):
            blocks.append(('quote', ln[2:].strip())); i += 1; continue
        if re.match(r'^[0-9]+\.\s', ln):
            items = []
            while i < len(lines) and re.match(r'^[0-9]+\.\s', lines[i]):
                items.append(re.sub(r'^[0-9]+\.\s', '', lines[i])); i += 1
            blocks.append(('ol', items)); continue
        if ln.startswith('- '):
            items = []
            while i < len(lines) and lines[i].startswith('- '):
                items.append(lines[i][2:]); i += 1
            blocks.append(('ul', items)); continue
        if ln.strip() == '':
            i += 1; continue
        buf = [ln]
        i += 1
        while i < len(lines) and lines[i].strip() and not re.match(
                r'^(#|\||```|cas::|note::|alerte::|limite::|- |[0-9]+\.\s|---|> |%%)', lines[i]):
            buf.append(lines[i]); i += 1
        blocks.append(('p', ' '.join(x.strip() for x in buf)))
    return blocks

class Doc(BaseDocTemplate):
    def __init__(self, path, title, **kw):
        self.title_doc = title
        BaseDocTemplate.__init__(self, path, pagesize=A4,
                                 leftMargin=1.9 * cm, rightMargin=1.9 * cm,
                                 topMargin=1.75 * cm, bottomMargin=1.85 * cm,
                                 title=title, author='INJS-LMD 2026',
                                 subject='Documentation fonctionnelle GET INJS APP',
                                 **kw)
        frame = Frame(self.leftMargin, self.bottomMargin, self.width, self.height, id='c')
        self.addPageTemplates([PageTemplate(id='std', frames=[frame], onPage=self._deco)])

    def _deco(self, canv, doc):
        canv.saveState()
        w, h = A4
        canv.setStrokeColor(FILET); canv.setLineWidth(0.5)
        canv.line(1.9 * cm, h - 1.32 * cm, w - 1.9 * cm, h - 1.32 * cm)
        canv.setFont('DJSans', 7.3); canv.setFillColor(GRIS)
        canv.drawString(1.9 * cm, h - 1.16 * cm, 'INJS-LMD 2026  ·  Documentation fonctionnelle')
        canv.drawRightString(w - 1.9 * cm, h - 1.16 * cm, doc.title_doc)
        canv.line(1.9 * cm, 1.5 * cm, w - 1.9 * cm, 1.5 * cm)
        canv.drawString(1.9 * cm, 1.06 * cm, 'Rédigé d’après le code du dépôt backend-injs2026')
        canv.setFont('DJSans-Bold', 8.0); canv.setFillColor(BLEU)
        canv.drawRightString(w - 1.9 * cm, 1.06 * cm, 'page %d' % canv.getPageNumber())
        canv.restoreState()

def build(md_path, pdf_path):
    md = open(md_path, encoding='utf-8').read()
    meta = {}
    body = md
    if md.startswith('---\n'):
        end = md.find('\n---\n', 4)
        head = md[4:end]
        for line in head.split('\n'):
            if ':' in line:
                k, v = line.split(':', 1)
                meta[k.strip()] = v.strip()
        body = md[end + 5:]
    doc = Doc(pdf_path, meta.get('header', meta.get('titre', '')))
    story = []
    # Couverture
    story.append(Spacer(1, 1.1 * cm))
    story.append(Paragraph(meta.get('surtitre', ''), S['Sur']))
    story.append(HRFlowable(width='100%', thickness=2.2, color=BLEU, spaceAfter=14))
    story.append(Paragraph(meta['titre'], S['TitreDoc']))
    story.append(Paragraph(meta['soustitre'], S['SousTitreDoc']))
    story.append(Spacer(1, 0.55 * cm))
    info = [
        ['Objet', meta['objet']],
        ['Public', meta.get('public', 'Direction, secrétariat, DFRC, encadrants')],
        ['Périmètre', meta.get('perimetre', 'Dépôt backend-injs2026, branche de travail')],
        ['Date', meta['date']],
    ]
    t = Table([[Paragraph('<b>%s</b>' % k, S['Td']), Paragraph(inline(v), S['Td'])] for k, v in info],
              colWidths=[3.4 * cm, 13.6 * cm])
    t.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BACKGROUND', (0, 0), (0, -1), FOND),
        ('GRID', (0, 0), (-1, -1), 0.4, FILET),
        ('LEFTPADDING', (0, 0), (-1, -1), 5), ('RIGHTPADDING', (0, 0), (-1, -1), 5),
        ('TOPPADDING', (0, 0), (-1, -1), 4), ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(t)
    if meta.get('resume'):
        story.append(Spacer(1, 0.35 * cm))
        story.append(Paragraph(meta['resume'], S['Corps']))
    # Sommaire (manuel, fourni dans le front matter) — sur la page de garde.
    if meta.get('sommaire'):
        story.append(Spacer(1, 0.25 * cm))
        story.append(Paragraph('Sommaire', S['H2']))
        for line in meta['sommaire'].split(';'):
            line = line.strip()
            if line:
                story.append(Paragraph('•&nbsp;&nbsp;' + inline(line), S['Puce']))
    story.append(PageBreak())
    for kind, payload in parse(body):
        if kind == 'h1':
            story.append(CondPageBreak(3.0 * cm))
            story.append(Paragraph(inline(payload), S['H1']))
            story.append(HRFlowable(width='100%', thickness=1.0, color=BLEU, spaceAfter=7))
        elif kind == 'h2':
            story.append(CondPageBreak(2.4 * cm))
            story.append(Paragraph(inline(payload), S['H2']))
        elif kind == 'h3':
            story.append(KeepTogether([Paragraph(inline(payload), S['H3'])]))
        elif kind == 'h4':
            story.append(Paragraph('<b>%s</b>' % inline(payload), S['Corps']))
        elif kind == 'p':
            story.append(Paragraph(inline(payload), S['Corps']))
        elif kind == 'ul':
            story.append(ListFlowable(
                [ListItem(Paragraph(inline(x), S['Puce']), leftIndent=13, value='•') for x in payload],
                bulletType='bullet', start='•', leftIndent=13, bulletFontName='DJSans', bulletFontSize=8))
            story.append(Spacer(1, 3))
        elif kind == 'ol':
            for k, x in enumerate(payload, 1):
                story.append(Paragraph('<font name="DJSans-Bold" color="#0D2B45">%d.</font>&nbsp;&nbsp;%s'
                                       % (k, inline(x)), S['Puce']))
            story.append(Spacer(1, 3))
        elif kind == 'quote':
            story.append(Paragraph('<i>%s</i>' % inline(payload), S['CorpsG']))
        elif kind == 'code':
            story.append(Spacer(1, 2)); story.append(code(payload)); story.append(Spacer(1, 6))
        elif kind == 'table':
            story.append(Spacer(1, 2))
            story.append(table(payload))
            story.append(Spacer(1, 7))
        elif kind == 'callout':
            k, txt = payload
            story.append(Spacer(1, 2)); story.append(callout(k, txt)); story.append(Spacer(1, 7))
        elif kind == 'rule':
            story.append(HRFlowable(width='100%', thickness=0.6, color=FILET, spaceBefore=5, spaceAfter=5))
        elif kind == 'break':
            story.append(PageBreak())
    doc.build(story)
    print('OK', pdf_path, os.path.getsize(pdf_path), 'octets')

if __name__ == '__main__':
    build(sys.argv[1], sys.argv[2])
