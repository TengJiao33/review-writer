#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn


REQUIRED_STYLES = {
    "Review Title": {"font": "Times New Roman", "size": 18.0},
    "Review Body": {"font": "Times New Roman", "size": 12.0},
    "Review Heading 1": {"font": "Times New Roman", "size": 14.0},
    "Review Heading 2": {"font": "Times New Roman", "size": 12.0},
    "Review Heading 3": {"font": "Times New Roman", "size": 11.0},
    "Review Abstract": {"font": "Times New Roman", "size": 11.0},
    "Review Reference": {"font": "Times New Roman", "size": 10.0},
    "Review Figure Caption": {"font": "Times New Roman", "size": 10.0},
}

PARENTHESIZED_COMPLEX_RE = (
    r"(?:[A-Z][a-z]?\d*)+(?:\([A-Za-z][A-Za-z0-9]*\)\d*)+(?:[A-Z][a-z]?\d*)*"
)
CHEMICAL_TOKEN_RE = re.compile(
    rf"(?<![A-Za-z0-9])(?:{PARENTHESIZED_COMPLEX_RE}|(?:[A-Z][a-z]?\d*){{2,}})(?![A-Za-z0-9])"
)


def close(value: float | None, expected: float, tolerance: float = 0.02) -> bool:
    return value is not None and abs(value - expected) <= tolerance


def style_font_name(style) -> str | None:
    if style.font.name:
        return style.font.name
    rpr = style.element.rPr
    if rpr is not None and rpr.rFonts is not None:
        return rpr.rFonts.get(qn("w:ascii"))
    return None


def markdown_image_count(path: Path | None) -> int | None:
    if not path:
        return None
    text = path.read_text(encoding="utf-8")
    return len(re.findall(r"!\[[^\]]*\]\([^)]+\)", text))


def markdown_title(path: Path | None) -> str | None:
    if not path:
        return None
    text = path.read_text(encoding="utf-8")
    match = re.search(r"(?m)^#\s+(.+?)\s*$", text)
    return match.group(1).strip() if match else None


def unformatted_formula_tokens(document: Document) -> list[dict[str, object]]:
    issues: list[dict[str, object]] = []
    for paragraph_index, paragraph in enumerate(document.paragraphs, start=1):
        text = "".join(run.text for run in paragraph.runs)
        script_flags = [
            bool(run.font.subscript)
            for run in paragraph.runs
            for _ in run.text
        ]
        if len(script_flags) != len(text):
            continue
        for match in CHEMICAL_TOKEN_RE.finditer(text):
            token = match.group(0)
            digit_positions = [
                match.start() + offset
                for offset, char in enumerate(token)
                if char.isdigit()
            ]
            if digit_positions and any(not script_flags[position] for position in digit_positions):
                issues.append({"paragraph": paragraph_index, "token": token})
    return issues


def audit(docx_path: Path, markdown_path: Path | None, render_qa: str = "not_run") -> dict:
    document = Document(docx_path)
    blockers: list[str] = []
    warnings: list[str] = []
    text = "\n".join(paragraph.text for paragraph in document.paragraphs)
    properties = document.core_properties
    expected_title = markdown_title(markdown_path)
    stale_template_titles = {"template for electronic submission to acs journals"}
    if not str(properties.title or "").strip():
        blockers.append("document title metadata is empty")
    elif str(properties.title).strip().lower() in stale_template_titles:
        blockers.append("document title metadata still contains the template title")
    elif expected_title and str(properties.title).strip() != expected_title:
        blockers.append("document title metadata does not match the Markdown title")
    if not str(properties.subject or "").strip():
        blockers.append("document subject metadata is empty")
    if str(properties.author or "").strip().lower() == "jiangzhen fu":
        blockers.append("document author metadata still contains the template author")
    if str(properties.last_modified_by or "").strip().lower() == "jiangzhen fu":
        blockers.append("document last-modified-by metadata still contains the template author")

    if "<!-- paragraph_id:" in text:
        blockers.append("editor paragraph markers are visible")
    if re.search(r"\[@P\d{3}", text):
        blockers.append("stable citation tokens are visible")
    if re.search(r"\[P\d{3}\]", text):
        blockers.append("internal paper IDs are visible")
    if re.search(r"\\(?:mathrm|mathbf|mathsf|ce)\b|_\s*\{|\^\s*\{", text):
        blockers.append("raw LaTeX commands are visible")

    for name, expected in REQUIRED_STYLES.items():
        try:
            style = document.styles[name]
        except KeyError:
            blockers.append(f"required style missing: {name}")
            continue
        if style_font_name(style) != expected["font"]:
            blockers.append(f"{name} font is not {expected['font']}")
        size = style.font.size.pt if style.font.size else None
        if not close(size, expected["size"]):
            blockers.append(f"{name} size is {size}, expected {expected['size']}")

    body = document.styles["Review Body"].paragraph_format
    if body.alignment != WD_ALIGN_PARAGRAPH.LEFT:
        blockers.append("Review Body is not left-aligned")
    if not close(float(body.line_spacing) if body.line_spacing else None, 1.5):
        blockers.append("Review Body line spacing is not 1.5")
    after = body.space_after.pt if body.space_after else 0.0
    if not close(after, 6.0):
        blockers.append("Review Body paragraph spacing after is not 6 pt")

    if len(document.sections) != 1:
        warnings.append(f"document has {len(document.sections)} sections")
    for index, section in enumerate(document.sections, start=1):
        geometry = (
            section.page_width.inches,
            section.page_height.inches,
            section.top_margin.inches,
            section.bottom_margin.inches,
            section.left_margin.inches,
            section.right_margin.inches,
        )
        expected = (8.5, 11.0, 1.0, 1.0, 1.0, 1.0)
        if any(not close(actual, wanted) for actual, wanted in zip(geometry, expected)):
            blockers.append(f"section {index} page geometry is {geometry}, expected {expected}")

    drawing_count = len(document.inline_shapes)
    expected_images = markdown_image_count(markdown_path)
    if expected_images is not None and drawing_count != expected_images:
        blockers.append(f"DOCX contains {drawing_count} images; Markdown contains {expected_images}")
    abstract_index = next(
        (
            index
            for index, paragraph in enumerate(document.paragraphs)
            if paragraph.text.strip().lower() == "abstract"
        ),
        None,
    )
    introduction_index = next(
        (
            index
            for index, paragraph in enumerate(document.paragraphs)
            if re.fullmatch(
                r"(?:\d+[.)]?\s*)?introduction",
                paragraph.text.strip(),
                re.I,
            )
        ),
        None,
    )
    if abstract_index is not None and introduction_index is not None and any(
        paragraph._p.xpath(".//w:drawing")
        for paragraph in document.paragraphs[abstract_index + 1 : introduction_index]
    ):
        blockers.append("a figure appears inside the Abstract block")

    for paragraph_index, paragraph in enumerate(document.paragraphs):
        if not paragraph._p.xpath(".//w:drawing"):
            continue
        keep_next = paragraph._p.pPr is not None and paragraph._p.pPr.keepNext is not None
        if not keep_next:
            blockers.append(f"figure paragraph {paragraph_index + 1} is not kept with its caption")
        next_paragraph = document.paragraphs[paragraph_index + 1] if paragraph_index + 1 < len(document.paragraphs) else None
        if next_paragraph is None or next_paragraph.style.name != "Review Figure Caption":
            blockers.append(f"figure paragraph {paragraph_index + 1} is not followed by a figure caption")

    for table_index, table in enumerate(document.tables, start=1):
        widths = table._tbl.tblPr.findall(qn("w:tblW"))
        if len(widths) != 1 or widths[0].get(qn("w:w")) != "9360" or widths[0].get(qn("w:type")) != "dxa":
            blockers.append(f"table {table_index} does not have exact 9360 DXA width")
        indents = table._tbl.tblPr.findall(qn("w:tblInd"))
        if len(indents) != 1 or indents[0].get(qn("w:w")) != "120":
            blockers.append(f"table {table_index} does not have 120 DXA indent")
        grid = [int(column.get(qn("w:w")) or 0) for column in table._tbl.tblGrid.findall(qn("w:gridCol"))]
        if sum(grid) != 9360:
            blockers.append(f"table {table_index} grid width sums to {sum(grid)}, expected 9360")
        for row_index, row in enumerate(table.rows, start=1):
            cell_widths = [int(cell._tc.tcPr.tcW.get(qn("w:w")) or 0) for cell in row.cells]
            if cell_widths != grid:
                blockers.append(
                    f"table {table_index} row {row_index} cell widths {cell_widths} do not match grid {grid}"
                )

    subscript_runs = 0
    superscript_runs = 0
    numbered_paragraphs = 0
    for paragraph in document.paragraphs:
        if paragraph._p.pPr is not None and paragraph._p.pPr.numPr is not None:
            numbered_paragraphs += 1
        for run in paragraph.runs:
            subscript_runs += int(bool(run.font.subscript))
            superscript_runs += int(bool(run.font.superscript))

    formula_issues = unformatted_formula_tokens(document)
    if formula_issues:
        blockers.append(
            "chemical formula digits remain at baseline: "
            + ", ".join(
                f"{item['token']} (paragraph {item['paragraph']})"
                for item in formula_issues[:10]
            )
        )
    if render_qa == "not_run":
        warnings.append("visual render QA has not been performed")
    elif render_qa == "unavailable":
        warnings.append("visual render QA was unavailable")

    reference_heading_index = next(
        (index for index, paragraph in enumerate(document.paragraphs) if paragraph.text.strip().lower() == "references"),
        None,
    )
    if reference_heading_index is None:
        blockers.append("References heading is missing")
    elif not any(
        paragraph._p.pPr is not None and paragraph._p.pPr.numPr is not None
        for paragraph in document.paragraphs[reference_heading_index + 1 :]
    ):
        blockers.append("References are not represented by real Word numbering")

    return {
        "docx_path": str(docx_path),
        "markdown_path": str(markdown_path) if markdown_path else None,
        "paragraph_count": len(document.paragraphs),
        "table_count": len(document.tables),
        "inline_image_count": drawing_count,
        "markdown_image_count": expected_images,
        "metadata": {
            "title": properties.title,
            "subject": properties.subject,
            "author": properties.author,
            "last_modified_by": properties.last_modified_by,
            "keywords": properties.keywords,
        },
        "numbered_paragraph_count": numbered_paragraphs,
        "subscript_run_count": subscript_runs,
        "superscript_run_count": superscript_runs,
        "unformatted_formula_tokens": formula_issues,
        "render_qa": render_qa,
        "blocking_issues": blockers,
        "warnings": warnings,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit review DOCX structure and academic style tokens.")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--markdown", type=Path)
    parser.add_argument("--output-json", type=Path)
    parser.add_argument("--render-qa", choices=("passed", "unavailable", "not_run"), default="not_run")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = audit(
        args.input.resolve(),
        args.markdown.resolve() if args.markdown else None,
        args.render_qa,
    )
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output_json:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 1 if report["blocking_issues"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
