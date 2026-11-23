#!/usr/bin/env python3
"""
Génère Manuel utilisateur App Statistiques.docx à partir du fichier Markdown source.

Usage:
  python scripts/generate_manuel_statistiques_docx.py
  python scripts/generate_manuel_statistiques_docx.py --check  # vérifie que le docx est à jour
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MD_PATH = ROOT / 'docs' / 'Manuel utilisateur App Statistiques.md'
DOCX_PATH = ROOT / 'docs' / 'Manuel utilisateur App Statistiques.docx'

CI_GREEN = '43A047'


def _setup_styles(doc):
    from docx.shared import Pt, RGBColor, Cm
    from docx.enum.text import WD_ALIGN_PARAGRAPH

    normal = doc.styles['Normal']
    normal.font.name = 'Calibri'
    normal.font.size = Pt(11)

    for level, size in [(1, 18), (2, 14), (3, 12)]:
        name = f'Heading {level}'
        if name in doc.styles:
            h = doc.styles[name]
            h.font.name = 'Calibri'
            h.font.size = Pt(size)
            h.font.bold = True
            h.font.color.rgb = RGBColor(0x1E, 0x29, 0x3B)
            if level == 1:
                h.font.color.rgb = RGBColor(0x43, 0xA0, 0x47)

    return WD_ALIGN_PARAGRAPH


def _add_table_from_md(doc, rows):
    from docx.shared import Pt, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement

    if not rows:
        return
    ncols = max(len(r) for r in rows)
    table = doc.add_table(rows=len(rows), cols=ncols)
    table.style = 'Table Grid'

    for ri, row in enumerate(rows):
        for ci in range(ncols):
            cell = table.rows[ri].cells[ci]
            text = row[ci] if ci < len(row) else ''
            cell.text = text.strip()
            for p in cell.paragraphs:
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER if ri == 0 else WD_ALIGN_PARAGRAPH.LEFT
                for run in p.runs:
                    run.font.size = Pt(9 if ri == 0 else 10)
                    if ri == 0:
                        run.font.bold = True
                        run.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
            if ri == 0:
                shading = OxmlElement('w:shd')
                shading.set(qn('w:fill'), CI_GREEN)
                shading.set(qn('w:val'), 'clear')
                cell._tc.get_or_add_tcPr().append(shading)

    doc.add_paragraph()


def _parse_inline(text: str) -> str:
    """Nettoie le markdown inline basique pour Word (gras conservé via runs)."""
    return text.strip()


def _add_rich_paragraph(doc, text: str, style=None, bold=False, italic=False, bullet=False):
    from docx.shared import Pt

    if bullet:
        p = doc.add_paragraph(style='List Bullet')
    else:
        p = doc.add_paragraph(style=style)

    # Découpe **gras** et *italique*
    parts = re.split(r'(\*\*[^*]+\*\*|\*[^*]+\*)', text)
    for part in parts:
        if not part:
            continue
        run = p.add_run()
        if part.startswith('**') and part.endswith('**'):
            run.text = part[2:-2]
            run.bold = True
        elif part.startswith('*') and part.endswith('*') and not part.startswith('**'):
            run.text = part[1:-1]
            run.italic = True
        else:
            run.text = part
        run.font.size = Pt(11)
        if bold:
            run.bold = True
        if italic:
            run.italic = True
    return p


def md_to_docx(md_path: Path, docx_path: Path) -> None:
    from docx import Document
    from docx.shared import Pt, Cm, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH

    text = md_path.read_text(encoding='utf-8')
    lines = text.splitlines()

    doc = Document()
    section = doc.sections[0]
    section.top_margin = Cm(2)
    section.bottom_margin = Cm(2)
    section.left_margin = Cm(2.5)
    section.right_margin = Cm(2.5)

    WD_ALIGN = _setup_styles(doc)

    # Page de garde
    title = doc.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = title.add_run('Manuel utilisateur\nApp Statistiques')
    r.bold = True
    r.font.size = Pt(22)
    r.font.color.rgb = RGBColor(0x43, 0xA0, 0x47)

    sub = doc.add_paragraph('INJS-LMD — Module Statistiques & Bilans')
    sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
    sub.runs[0].font.size = Pt(14)
    sub.runs[0].italic = True

    doc.add_paragraph()
    doc.add_page_break()

    table_rows: list[list[str]] | None = None
    in_code = False

    for line in lines:
        raw = line.rstrip()

        if raw.startswith('```'):
            in_code = not in_code
            continue
        if in_code:
            p = doc.add_paragraph(raw)
            p.runs[0].font.name = 'Courier New'
            p.runs[0].font.size = Pt(9)
            continue

        if raw.startswith('|') and '|' in raw[1:]:
            cells = [c.strip() for c in raw.strip('|').split('|')]
            if all(re.match(r'^[-:\s]+$', c) for c in cells):
                continue
            if table_rows is None:
                table_rows = []
            table_rows.append(cells)
            continue
        elif table_rows is not None:
            _add_table_from_md(doc, table_rows)
            table_rows = None

        if not raw:
            continue
        if raw == '---':
            doc.add_paragraph()
            continue

        img_match = re.match(r'^!\[(.*?)\]\((.*?)\)$', raw)
        if img_match:
            caption, rel_path = img_match.group(1), img_match.group(2).strip()
            img_path = (md_path.parent / rel_path).resolve()
            if img_path.exists():
                try:
                    doc.add_picture(str(img_path), width=Cm(16))
                    last = doc.paragraphs[-1]
                    last.alignment = WD_ALIGN_PARAGRAPH.CENTER
                except Exception as exc:
                    doc.add_paragraph(f'[Image non insérée : {rel_path} — {exc}]')
            else:
                doc.add_paragraph(f'[Capture d\'écran manquante : {rel_path}]')
            if caption:
                cap = doc.add_paragraph(caption)
                cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
                if cap.runs:
                    cap.runs[0].italic = True
                    cap.runs[0].font.size = Pt(9)
                    cap.runs[0].font.color.rgb = RGBColor(0x64, 0x74, 0x8B)
            doc.add_paragraph()
            continue

        if raw.startswith('# '):
            doc.add_heading(raw[2:].strip(), level=1)
        elif raw.startswith('## '):
            doc.add_heading(raw[3:].strip(), level=2)
        elif raw.startswith('### '):
            doc.add_heading(raw[4:].strip(), level=3)
        elif raw.startswith('> '):
            p = doc.add_paragraph(raw[2:].strip())
            p.paragraph_format.left_indent = Cm(0.5)
            for run in p.runs:
                run.italic = True
                run.font.color.rgb = RGBColor(0x64, 0x74, 0x8B)
        elif raw.startswith('- '):
            _add_rich_paragraph(doc, raw[2:], bullet=True)
        elif re.match(r'^\d+\.\s', raw):
            p = doc.add_paragraph(raw.split('. ', 1)[1], style='List Number')
            p.runs[0].font.size = Pt(11)
        elif raw.startswith('*') and raw.endswith('*') and not raw.startswith('**'):
            p = doc.add_paragraph(raw.strip('*'))
            p.runs[0].italic = True
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        else:
            _add_rich_paragraph(doc, raw)

    if table_rows:
        _add_table_from_md(doc, table_rows)

    docx_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(docx_path))
    print(f'✓ Word généré : {docx_path.relative_to(ROOT)}')


def main():
    parser = argparse.ArgumentParser(description='Génère le manuel Statistiques (.docx) depuis le .md')
    parser.add_argument('--check', action='store_true', help='Exit 1 si le docx est absent ou plus ancien que le md')
    args = parser.parse_args()

    if not MD_PATH.exists():
        print(f'Erreur : fichier source introuvable : {MD_PATH}', file=sys.stderr)
        sys.exit(1)

    if args.check:
        if not DOCX_PATH.exists():
            print('docx manquant', file=sys.stderr)
            sys.exit(1)
        if DOCX_PATH.stat().st_mtime < MD_PATH.stat().st_mtime:
            print('docx obsolète (md plus récent)', file=sys.stderr)
            sys.exit(1)
        print('docx à jour')
        sys.exit(0)

    md_to_docx(MD_PATH, DOCX_PATH)


if __name__ == '__main__':
    main()
