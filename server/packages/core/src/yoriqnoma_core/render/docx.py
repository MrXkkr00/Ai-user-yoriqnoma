"""DOCX (TZ FR-R4): headings, numbered steps, images (15 cm) with captions, TOC field, tables."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt

from yoriqnoma_schemas import Manual


def _toc(document: Any) -> None:
    paragraph = document.add_paragraph()
    run = paragraph.add_run()
    begin = OxmlElement("w:fldChar")
    begin.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = 'TOC \\o "1-2" \\h \\z \\u'
    separate = OxmlElement("w:fldChar")
    separate.set(qn("w:fldCharType"), "separate")
    text = OxmlElement("w:t")
    text.text = "Mundarijani yangilash uchun: o'ng tugma → «Maydonni yangilash» (F9)."
    end = OxmlElement("w:fldChar")
    end.set(qn("w:fldCharType"), "end")
    for el in (begin, instr, separate, text, end):
        run._r.append(el)


def _table(document: Any, headers: list[str], rows: list[list[str]]) -> None:
    table = document.add_table(rows=1, cols=len(headers))
    table.style = "Table Grid"
    for cell, text in zip(table.rows[0].cells, headers, strict=True):
        cell.text = text
        for r in cell.paragraphs[0].runs:
            r.bold = True
    for row in rows:
        cells = table.add_row().cells
        for cell, text in zip(cells, row, strict=True):
            cell.text = text


def build_docx(manual: Manual, ctx: dict[str, Any], out: Path) -> Path:
    document = Document()
    style = document.styles["Normal"]
    style.font.name = "Calibri"
    style.font.size = Pt(11)
    document.add_heading(f"{manual.project}: foydalanuvchi yo'riqnomasi", level=0)
    document.add_paragraph(f"Rol: «{manual.role_label}». Bu rolni {manual.role_granted_by} beradi.")
    document.add_paragraph(
        f"Qamrov: {manual.coverage.percent.get('total', 0)}%. Model: {', '.join(manual.models)}."
    )
    document.add_heading("Mundarija", level=1)
    _toc(document)
    figure = 0
    for section in ctx["sections"]:
        document.add_page_break()  # type: ignore[no-untyped-call]
        document.add_heading(section["title"], level=1)
        document.add_paragraph(section["intro"])
        if section["stage"] == "reference":
            _table(
                document,
                ["Sahifa", "Manzil", "Nima uchun"],
                [[r.page_title, r.path, r.purpose] for r in ctx["reference"]],
            )
        if section["stage"] == "faq":
            for item in ctx["faq"]:
                p = document.add_paragraph()
                p.add_run(item.q).bold = True
                document.add_paragraph(item.a)
        for article in section["articles"]:
            title = article["title"] + (" (tekshirilsin)" if article["needs_review"] else "")
            document.add_heading(title, level=2)
            document.add_paragraph(article["purpose"])
            for step in article["steps"]:
                document.add_paragraph(step["text"], style="List Number")
                img = step.get("img")
                if img and Path(img["path"]).is_file():
                    figure += 1
                    document.add_picture(str(img["path"]), width=Cm(15))
                    cap = document.add_paragraph(
                        f"{figure}-rasm. {article['title']}, {step['n']}-qadam"
                    )
                    cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
                    cap.runs[0].italic = True
            if article["statuses"]:
                _table(
                    document,
                    ["Status", "Ma'nosi", "Nima qilasiz"],
                    [
                        [r["status"], r["meaning"], r["what_you_can_do"]]
                        for r in article["statuses"]
                    ],
                )
            for note in article["notes"]:
                document.add_paragraph(note, style="Intense Quote")
    out.parent.mkdir(parents=True, exist_ok=True)
    document.save(str(out))
    return out
