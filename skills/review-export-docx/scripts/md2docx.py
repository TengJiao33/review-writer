#!/usr/bin/env python3
"""
md2docx.py -- Convert a Markdown file to DOCX using review_template.docx styles.

Inline support:
  **bold**  *italic*  ***bold-italic***  `code`
  ^superscript^       alnum_subscript_   $math$  $$display math$$
  [@citation]  ->  [citation key]

Section-aware styling (auto-detected from headings OR bold-only paragraphs):
  Abstract / Keywords / Acknowledgments / References / Supporting Information

Font specification (explicitly applied to every run):
  H1 title      : Times New Roman 18 pt  (xiao-er)
  Author line   : Times New Roman 12 pt  (xiao-si)
  Affiliation   : Times New Roman 10.5 pt (wu-hao)
  H2 heading    : Times New Roman 14 pt  (si-hao)  bold
  H3 heading    : Times New Roman 12 pt  bold italic
  Body / Abstract / Keywords : Times New Roman 12 pt
  Captions / References      : Times New Roman 10.5 pt

Usage:
    python3 scripts/md2docx.py --input review.md --output review.docx
"""
from __future__ import annotations

import argparse
import re
from copy import deepcopy  # noqa: F401
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from docx import Document
from docx.enum.style import WD_STYLE_TYPE
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement, parse_xml  # noqa: F401
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

try:
    from PIL import Image as PILImage
except ImportError:
    PILImage = None

try:
    from latex2word import LatexToWordElement
    _LATEX_OK = True
except ImportError:
    _LATEX_OK = False

# ---------------------------------------------------------------------------
# Template style name map
# ---------------------------------------------------------------------------

_S: Dict[str, str] = {
    "title":        "Review Title",
    "author":       "Review Author",
    "address":      "Review Affiliation",
    "email":        "Review Affiliation",
    "abstract":     "Review Abstract",
    "keywords":     "Review Keywords",
    "body":         "Review Body",
    "h1":           "Review Heading 1",
    "h2":           "Review Heading 2",
    "h3":           "Review Heading 3",
    "figure":       "Review Figure Caption",
    "table_title":  "Review Table Caption",
    "table_body":   "Review Table Body",
    "chart":        "Review Figure Caption",
    "scheme":       "Review Figure Caption",
    "references":   "Review Reference",
    "acks":         "Review Body",
    "supporting":   "Review Body",
    "footnote":     "Review Reference",
}

# ---------------------------------------------------------------------------
# Font spec -- every run gets an explicit font name + size
# ---------------------------------------------------------------------------

_FONT_SPEC: Dict[str, Dict] = {
    "title":        {"font": "Times New Roman", "size": 18, "bold": True},
    "author":       {"font": "Times New Roman", "size": 12},
    "address":      {"font": "Times New Roman", "size": 10.5},
    "email":        {"font": "Times New Roman", "size": 10.5},
    "abstract":     {"font": "Times New Roman", "size": 11},
    "keywords":     {"font": "Times New Roman", "size": 11},
    "body":         {"font": "Times New Roman", "size": 12},
    "h1":           {"font": "Times New Roman", "size": 14,  "bold": True},
    "h2":           {"font": "Times New Roman", "size": 12,  "bold": True},
    "h3":           {"font": "Times New Roman", "size": 11,  "bold": True, "italic": True},
    "h4":           {"font": "Times New Roman", "size": 11,  "italic": True},
    "figure":       {"font": "Times New Roman", "size": 10.5},
    "table_title":  {"font": "Times New Roman", "size": 12},
    "table_body":   {"font": "Times New Roman", "size": 10.5},
    "scheme":       {"font": "Times New Roman", "size": 10.5},
    "chart":        {"font": "Times New Roman", "size": 10.5},
    "references":   {"font": "Times New Roman", "size": 10.5},
    "acks":         {"font": "Times New Roman", "size": 12},
    "supporting":   {"font": "Times New Roman", "size": 12},
    "footnote":     {"font": "Times New Roman", "size": 10.5},
}

# Heading level -> (para_style_key, font_spec_key)
_HEADING_FORMAT: Dict[int, Tuple[str, str]] = {
    1: ("title", "title"),
    2: ("h1",  "h1"),
    3: ("h2",  "h2"),
    4: ("h3",  "h3"),
    5: ("body",  "body"),
    6: ("body",  "body"),
}

_SECTION_CONTEXT: Dict[str, str] = {
    "abstract":               "abstract",
    "keywords":               "keywords",
    "key words":              "keywords",
    "acknowledgments":        "acks",
    "acknowledgements":       "acks",
    "supporting information": "supporting",
    "references":             "references",
    "reference":              "references",
}

_CAPTION_PATTERNS: List[Tuple[re.Pattern, str]] = [
    (re.compile(r"^(figure|fig\.)\s*\d+", re.I), "figure"),
    (re.compile(r"^table\s*\d+",            re.I), "table_title"),
    (re.compile(r"^scheme\s*\d+",           re.I), "scheme"),
    (re.compile(r"^chart\s*\d+",            re.I), "chart"),
]


def _usable_page_width_inches(doc: Document) -> float:
    section = doc.sections[0]
    width_emu = section.page_width - section.left_margin - section.right_margin
    # 914400 EMUs per inch. Keep a conservative upper bound for journal templates.
    return max(1.0, min(6.2, width_emu / 914400))


def _bounded_figure_size(path: Path, max_width: float, max_height: float = 5.9) -> Tuple[float, Optional[float]]:
    """Bound figure height so Word can keep its caption on the same page."""
    if PILImage is None:
        return max_width, None
    try:
        with PILImage.open(path) as image:
            width_px, height_px = image.size
    except Exception:
        return max_width, None
    if width_px <= 0 or height_px <= 0:
        return max_width, None
    ratio = width_px / height_px
    width = min(max_width, max_height * ratio)
    return width, width / ratio


def _figure_bounds_for_caption(caption_key: str, page_width: float) -> Tuple[float, float]:
    """Use a compact displayed block for reaction schemes."""
    if caption_key == "scheme":
        return min(page_width, 5.25), 3.6
    return page_width, 5.9


def _set_style_font(style, font_name: str, size: float, bold: bool = False, italic: bool = False) -> None:
    style.font.name = font_name
    style.font.size = Pt(size)
    style.font.bold = bold
    style.font.italic = italic
    rpr = style.element.get_or_add_rPr()
    rfonts = rpr.rFonts
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.insert(0, rfonts)
    for attr in ("ascii", "hAnsi", "eastAsia", "cs"):
        rfonts.set(qn(f"w:{attr}"), font_name)


def _ensure_style(doc: Document, name: str):
    try:
        return doc.styles[name]
    except KeyError:
        return doc.styles.add_style(name, WD_STYLE_TYPE.PARAGRAPH)


def _set_outline_level(style, level: int | None) -> None:
    ppr = style.element.get_or_add_pPr()
    existing = ppr.find(qn("w:outlineLvl"))
    if existing is not None:
        ppr.remove(existing)
    if level is not None:
        outline = OxmlElement("w:outlineLvl")
        outline.set(qn("w:val"), str(level))
        ppr.append(outline)


def _configure_style(
    doc: Document,
    name: str,
    *,
    size: float,
    bold: bool = False,
    italic: bool = False,
    alignment=WD_ALIGN_PARAGRAPH.LEFT,
    before: float = 0,
    after: float = 0,
    line_spacing: float = 1.0,
    keep_with_next: bool = False,
    outline_level: int | None = None,
):
    style = _ensure_style(doc, name)
    _set_style_font(style, "Times New Roman", size, bold=bold, italic=italic)
    paragraph = style.paragraph_format
    paragraph.alignment = alignment
    paragraph.space_before = Pt(before)
    paragraph.space_after = Pt(after)
    paragraph.line_spacing = line_spacing
    paragraph.keep_with_next = keep_with_next
    paragraph.widow_control = True
    _set_outline_level(style, outline_level)
    return style


def _configure_academic_document(doc: Document) -> None:
    section = doc.sections[0]
    section.page_width = Inches(8.5)
    section.page_height = Inches(11)
    section.top_margin = Inches(1)
    section.bottom_margin = Inches(1)
    section.left_margin = Inches(1)
    section.right_margin = Inches(1)
    section.header_distance = Inches(0.49)
    section.footer_distance = Inches(0.49)

    _configure_style(
        doc, _S["title"], size=18, bold=True, alignment=WD_ALIGN_PARAGRAPH.CENTER,
        before=0, after=12, line_spacing=1.15,
    )
    _configure_style(
        doc, _S["author"], size=11.5, alignment=WD_ALIGN_PARAGRAPH.CENTER,
        before=0, after=3, line_spacing=1.0,
    )
    _configure_style(
        doc, _S["address"], size=10, italic=True, alignment=WD_ALIGN_PARAGRAPH.CENTER,
        before=0, after=3, line_spacing=1.0,
    )
    _configure_style(
        doc, _S["abstract"], size=11, alignment=WD_ALIGN_PARAGRAPH.JUSTIFY,
        before=0, after=6, line_spacing=1.15,
    )
    _configure_style(
        doc, _S["keywords"], size=11, alignment=WD_ALIGN_PARAGRAPH.LEFT,
        before=0, after=8, line_spacing=1.15,
    )
    _configure_style(
        doc, _S["body"], size=12, alignment=WD_ALIGN_PARAGRAPH.LEFT,
        before=0, after=6, line_spacing=1.5,
    )
    _configure_style(
        doc, _S["h1"], size=14, bold=True, before=12, after=6,
        line_spacing=1.0, keep_with_next=True, outline_level=0,
    )
    _configure_style(
        doc, _S["h2"], size=12, bold=True, before=10, after=4,
        line_spacing=1.0, keep_with_next=True, outline_level=1,
    )
    _configure_style(
        doc, _S["h3"], size=11, bold=True, italic=True, before=8, after=3,
        line_spacing=1.0, keep_with_next=True, outline_level=2,
    )
    _configure_style(
        doc, _S["figure"], size=10, alignment=WD_ALIGN_PARAGRAPH.CENTER,
        before=0, after=8, line_spacing=1.0,
    )
    _configure_style(
        doc, _S["table_title"], size=10, bold=True, alignment=WD_ALIGN_PARAGRAPH.LEFT,
        before=6, after=4, line_spacing=1.0, keep_with_next=True,
    )
    _configure_style(
        doc, _S["table_body"], size=9.5, alignment=WD_ALIGN_PARAGRAPH.LEFT,
        before=0, after=0, line_spacing=1.0,
    )
    _configure_style(
        doc, _S["references"], size=10, alignment=WD_ALIGN_PARAGRAPH.LEFT,
        before=0, after=3, line_spacing=1.0,
    )

    normal = doc.styles["Normal"]
    _set_style_font(normal, "Times New Roman", 12)
    normal.paragraph_format.space_after = Pt(6)
    normal.paragraph_format.line_spacing = 1.5


def _append_page_number(paragraph) -> None:
    paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    run = paragraph.add_run()
    begin = OxmlElement("w:fldChar")
    begin.set(qn("w:fldCharType"), "begin")
    instruction = OxmlElement("w:instrText")
    instruction.set(qn("xml:space"), "preserve")
    instruction.text = " PAGE "
    separate = OxmlElement("w:fldChar")
    separate.set(qn("w:fldCharType"), "separate")
    text = OxmlElement("w:t")
    text.text = "1"
    end = OxmlElement("w:fldChar")
    end.set(qn("w:fldCharType"), "end")
    for element in (begin, instruction, separate, text, end):
        run._r.append(element)
    run.font.name = "Times New Roman"
    run.font.size = Pt(9)


def _configure_footer(doc: Document) -> None:
    for section in doc.sections:
        footer = section.footer
        paragraph = footer.paragraphs[0]
        for run in list(paragraph.runs):
            paragraph._p.remove(run._r)
        _append_page_number(paragraph)

_UNICODE_SUPERSCRIPT_MAP: Dict[str, str] = {
    "⁰": "0",
    "¹": "1",
    "²": "2",
    "³": "3",
    "⁴": "4",
    "⁵": "5",
    "⁶": "6",
    "⁷": "7",
    "⁸": "8",
    "⁹": "9",
    "⁺": "+",
    "⁻": "-",
    "⁼": "=",
    "⁽": "(",
    "⁾": ")",
}

_UNICODE_SUBSCRIPT_MAP: Dict[str, str] = {
    "₀": "0",
    "₁": "1",
    "₂": "2",
    "₃": "3",
    "₄": "4",
    "₅": "5",
    "₆": "6",
    "₇": "7",
    "₈": "8",
    "₉": "9",
    "₊": "+",
    "₋": "-",
    "₌": "=",
    "₍": "(",
    "₎": ")",
}

# ---------------------------------------------------------------------------
# Run dataclass
# ---------------------------------------------------------------------------

@dataclass
class Run:
    text:        str  = ""
    bold:        bool = False
    italic:      bool = False
    code:        bool = False
    superscript: bool = False
    subscript:   bool = False
    math:        str  = ""

# ---------------------------------------------------------------------------
# Inline parser
# ---------------------------------------------------------------------------

_INLINE_RE = re.compile(
    r"(\$\$[\s\S]*?\$\$"
    r"|\$[^$\n]+?\$"
    r"|\*\*\*(?:\S[^*\n]*?\S|\S)\*\*\*"
    r"|\*\*(?:\S[^*\n]*?\S|\S)\*\*"
    r"|\^[^\^\s\n]+?\^"
    r"|_[^_\s\n]+_"
    r"|\*(?:\S[^*\n]*?\S|\S)\*"
    r"|__(?:\S[^_\n]*?\S|\S)__"
    r"|_(?:\S[^_\n]*?\S|\S)_"
    r"|`[^`\n]+`"
    r"|\[@([^\]]+)\]"
    r"|\[([^\]]*)\]\([^\)]*\)"
    r")"
)


def _parse_nested(inner: str, bold: bool = False, italic: bool = False) -> List[Run]:
    runs = parse_inline(inner)
    for r in runs:
        if bold:
            r.bold = True
        if italic:
            r.italic = True
    return runs


def parse_inline(raw: str) -> List[Run]:
    runs: List[Run] = []
    pos = 0
    for m in _INLINE_RE.finditer(raw):
        if m.start() > pos:
            runs.append(Run(text=raw[pos:m.start()]))
        token = m.group(0)
        char_before = raw[m.start() - 1] if m.start() > 0 else ""

        if token.startswith("$$"):
            runs.append(Run(math=token[2:-2].strip()))
        elif token.startswith("$"):
            runs.append(Run(math=token[1:-1].strip()))
        elif token.startswith("***"):
            runs.extend(_parse_nested(token[3:-3], bold=True, italic=True))
        elif token.startswith("**"):
            runs.extend(_parse_nested(token[2:-2], bold=True))
        elif token.startswith("^") and token.endswith("^"):
            runs.append(Run(text=token[1:-1], superscript=True))
        elif token.startswith("_") and token.endswith("_") and " " not in token[1:-1]:
            if char_before.isalnum():
                runs.append(Run(text=token[1:-1], subscript=True))
            else:
                runs.append(Run(text=token[1:-1], italic=True))
        elif token.startswith("*"):
            runs.extend(_parse_nested(token[1:-1], italic=True))
        elif token.startswith("__"):
            runs.extend(_parse_nested(token[2:-2], bold=True))
        elif token.startswith("_"):
            runs.extend(_parse_nested(token[1:-1], italic=True))
        elif token.startswith("`"):
            runs.append(Run(text=token[1:-1], code=True))
        elif token.startswith("[@"):
            cite_key = m.group(1) or token[2:-1]
            runs.append(Run(text=f"[{cite_key}]"))
        elif token.startswith("["):
            display = m.group(2)
            runs.append(Run(text=display if display is not None else token))
        else:
            runs.append(Run(text=token))
        pos = m.end()

    if pos < len(raw):
        runs.append(Run(text=raw[pos:]))
    return runs or [Run(text=raw)]


# ---------------------------------------------------------------------------
# Font + run application
# ---------------------------------------------------------------------------

def _apply_math(para, latex: str) -> None:
    if _LATEX_OK:
        try:
            LatexToWordElement(latex).add_latex_to_paragraph(para)
            return
        except Exception:
            pass
    expression = latex.strip()
    chemical = re.fullmatch(r"\\ce\{(.+)\}", expression)
    if chemical:
        expression = chemical.group(1)
    expression = re.sub(r"\\(?:mathrm|text)\{([^{}]*)\}", r"\1", expression)
    pattern = re.compile(r"([_^])(?:\{([^{}]+)\}|([A-Za-z0-9+\-=]+))")
    position = 0
    for match in pattern.finditer(expression):
        if match.start() > position:
            run = para.add_run(expression[position:match.start()])
            _set_word_run_font(run, "Times New Roman", 12)
        run = para.add_run(match.group(2) or match.group(3) or "")
        _set_word_run_font(run, "Times New Roman", 12)
        run.font.subscript = match.group(1) == "_"
        run.font.superscript = match.group(1) == "^"
        position = match.end()
    if position < len(expression):
        run = para.add_run(expression[position:])
        _set_word_run_font(run, "Times New Roman", 12)


def _split_script_segments(text: str) -> List[Tuple[str, str]]:
    segments: List[Tuple[str, str]] = []
    mode = "normal"
    current = ""

    def looks_like_ascii_subscript(index: int) -> bool:
        if index < 0 or index >= len(text):
            return False
        char = text[index]
        if not char.isdigit() or index == 0:
            return False
        prev = text[index - 1]
        if prev in "-–—/[ ":
            return False
        if prev.isalpha():
            return True
        if prev in ")]}" and index >= 2 and text[index - 2].isalpha():
            return True
        return False

    def flush() -> None:
        nonlocal current
        if current:
            segments.append((mode, current))
            current = ""

    for idx, char in enumerate(text):
        if char in _UNICODE_SUPERSCRIPT_MAP:
            char_mode = "superscript"
            rendered = _UNICODE_SUPERSCRIPT_MAP[char]
        elif char in _UNICODE_SUBSCRIPT_MAP:
            char_mode = "subscript"
            rendered = _UNICODE_SUBSCRIPT_MAP[char]
        elif looks_like_ascii_subscript(idx):
            char_mode = "subscript"
            rendered = char
        else:
            char_mode = "normal"
            rendered = char
        if char_mode != mode:
            flush()
            mode = char_mode
        current += rendered
    flush()
    return segments or [("normal", text)]


def _split_script_segments_v2(text: str) -> List[Tuple[str, str]]:
    """Apply explicit Unicode scripts and conservative chemistry-aware defaults.

    Explicit Markdown `_sub_` and `^super^` is handled before this function.
    Automatic conversion is intentionally limited to multi-element formulae,
    sp2/sp3 hybridization, SN1/SN2 notation, and hapticity labels such as
    eta1/eta3 (written with the Greek eta character) so years and ordinary
    alphanumeric labels stay intact.
    """
    segments: List[Tuple[str, str]] = []

    def append(mode: str, value: str) -> None:
        if not value:
            return
        if segments and segments[-1][0] == mode:
            segments[-1] = (mode, segments[-1][1] + value)
        else:
            segments.append((mode, value))

    def append_unicode(value: str) -> None:
        for char in value:
            if char in _UNICODE_SUPERSCRIPT_MAP:
                append("superscript", _UNICODE_SUPERSCRIPT_MAP[char])
            elif char in _UNICODE_SUBSCRIPT_MAP:
                append("subscript", _UNICODE_SUBSCRIPT_MAP[char])
            else:
                append("normal", char)

    parenthesized_complex = (
        r"(?:[A-Z][a-z]?\d*)+(?:\([A-Za-z][A-Za-z0-9]*\)\d*)+"
        r"(?:[A-Z][a-z]?\d*)*"
    )
    token_re = re.compile(
        rf"(?<![A-Za-z0-9])(?:η[1-9]|sp[23]|SN[12]|{parenthesized_complex}|"
        rf"(?:[A-Z][a-z]?\d*){{2,}})(?![A-Za-z0-9])"
    )
    position = 0
    for match in token_re.finditer(text):
        append_unicode(text[position:match.start()])
        token = match.group(0)
        if re.fullmatch(r"η[1-9]", token):
            append("normal", "η")
            append("superscript", token[-1])
        elif re.fullmatch(r"sp[23]", token):
            append("normal", "sp")
            append("superscript", token[-1])
        elif re.fullmatch(r"SN[12]", token):
            append("normal", "S")
            append("subscript", token[1:])
        elif re.fullmatch(parenthesized_complex, token):
            for piece in re.finditer(r"\d+|[^\d]+", token):
                append("subscript" if piece.group(0).isdigit() else "normal", piece.group(0))
        else:
            for piece in re.finditer(r"[A-Z][a-z]?|\d+", token):
                append("subscript" if piece.group(0).isdigit() else "normal", piece.group(0))
        position = match.end()
    append_unicode(text[position:])
    return segments or [("normal", text)]


def _set_word_run_font(run, font_name: str, size_pt: float) -> None:
    run.font.name = font_name
    run.font.size = Pt(size_pt)
    rpr = run._element.get_or_add_rPr()
    rfonts = rpr.rFonts
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.insert(0, rfonts)
    for attr in ("ascii", "hAnsi", "eastAsia", "cs"):
        rfonts.set(qn(f"w:{attr}"), font_name)


def apply_runs(
    para,
    runs: List[Run],
    spec_key: str = "body",
    force_bold: bool = False,
    force_italic: bool = False,
) -> None:
    spec        = _FONT_SPEC.get(spec_key, _FONT_SPEC["body"])
    font_name   = spec["font"]
    size_pt     = spec["size"]
    spec_bold   = spec.get("bold", False)
    spec_italic = spec.get("italic", False)

    for r in runs:
        if r.math:
            _apply_math(para, r.math)
            continue
        segments = [("normal", r.text)] if r.code else _split_script_segments_v2(r.text)
        for segment_mode, segment_text in segments:
            if not segment_text:
                continue
            wr = para.add_run(segment_text)
            if r.code:
                _set_word_run_font(wr, "Courier New", 9)
            else:
                _set_word_run_font(wr, font_name, size_pt)
            wr.bold = (spec_bold or force_bold or r.bold) or None
            wr.italic = (spec_italic or force_italic or r.italic) or None
            if r.superscript or segment_mode == "superscript":
                wr.font.superscript = True
            if r.subscript or segment_mode == "subscript":
                wr.font.subscript = True


# ---------------------------------------------------------------------------
# Paragraph factory
# ---------------------------------------------------------------------------

def _para(
    doc: Document,
    style_key: str,
    spec_key: str,
    inline_text: str = "",
    force_bold: bool = False,
    force_italic: bool = False,
):
    p = doc.add_paragraph(style=_S.get(style_key, _S["body"]))
    if inline_text:
        apply_runs(p, parse_inline(inline_text),
                   spec_key=spec_key,
                   force_bold=force_bold,
                   force_italic=force_italic)
    return p


def _next_numbering_id(numbering, tag: str, attribute: str) -> int:
    values = []
    for element in numbering.findall(qn(tag)):
        raw = element.get(qn(attribute))
        if raw and raw.isdigit():
            values.append(int(raw))
    return max(values, default=0) + 1


def _create_numbering_definition(doc: Document, ordered: bool, reference: bool = False) -> int:
    numbering = doc.part.numbering_part.element
    abstract_id = _next_numbering_id(numbering, "w:abstractNum", "w:abstractNumId")
    abstract = OxmlElement("w:abstractNum")
    abstract.set(qn("w:abstractNumId"), str(abstract_id))
    multi = OxmlElement("w:multiLevelType")
    multi.set(qn("w:val"), "multilevel")
    abstract.append(multi)
    for level in range(3):
        lvl = OxmlElement("w:lvl")
        lvl.set(qn("w:ilvl"), str(level))
        start = OxmlElement("w:start")
        start.set(qn("w:val"), "1")
        num_fmt = OxmlElement("w:numFmt")
        num_fmt.set(qn("w:val"), "decimal" if ordered else "bullet")
        lvl_text = OxmlElement("w:lvlText")
        lvl_text.set(qn("w:val"), f"%{level + 1}." if ordered else "•")
        suffix = OxmlElement("w:suff")
        suffix.set(qn("w:val"), "tab")
        justification = OxmlElement("w:lvlJc")
        justification.set(qn("w:val"), "left")
        ppr = OxmlElement("w:pPr")
        tabs = OxmlElement("w:tabs")
        tab = OxmlElement("w:tab")
        tab.set(qn("w:val"), "num")
        left = (720 if reference else 540) + level * 360
        hanging = 360 if reference else 270
        tab.set(qn("w:pos"), str(left))
        tabs.append(tab)
        indentation = OxmlElement("w:ind")
        indentation.set(qn("w:left"), str(left))
        indentation.set(qn("w:hanging"), str(hanging))
        ppr.extend([tabs, indentation])
        lvl.extend([start, num_fmt, lvl_text, suffix, justification, ppr])
        abstract.append(lvl)
    numbering.append(abstract)

    num_id = _next_numbering_id(numbering, "w:num", "w:numId")
    num = OxmlElement("w:num")
    num.set(qn("w:numId"), str(num_id))
    abstract_ref = OxmlElement("w:abstractNumId")
    abstract_ref.set(qn("w:val"), str(abstract_id))
    num.append(abstract_ref)
    if ordered:
        for level in range(3):
            override = OxmlElement("w:lvlOverride")
            override.set(qn("w:ilvl"), str(level))
            start_override = OxmlElement("w:startOverride")
            start_override.set(qn("w:val"), "1")
            override.append(start_override)
            num.append(override)
    numbering.append(num)
    return num_id


def _apply_numbering(paragraph, num_id: int, level: int = 0) -> None:
    ppr = paragraph._p.get_or_add_pPr()
    num_pr = ppr.find(qn("w:numPr"))
    if num_pr is None:
        num_pr = OxmlElement("w:numPr")
        ppr.append(num_pr)
    ilvl = OxmlElement("w:ilvl")
    ilvl.set(qn("w:val"), str(max(0, min(level, 2))))
    num_id_el = OxmlElement("w:numId")
    num_id_el.set(qn("w:val"), str(num_id))
    num_pr.extend([ilvl, num_id_el])


# ---------------------------------------------------------------------------
# Table builder
# ---------------------------------------------------------------------------

def _set_cell_borders(
    cell,
    *,
    top: bool = False,
    bottom: bool = False,
) -> None:
    """Apply a white three-line-table border treatment."""
    tc = cell._tc
    tcPr = tc.get_or_add_tcPr()
    borders = tcPr.first_child_found_in("w:tcBorders")
    if borders is None:
        borders = OxmlElement("w:tcBorders")
        tcPr.append(borders)
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        for existing in list(borders.findall(qn(f"w:{edge}"))):
            borders.remove(existing)
        elem = OxmlElement(f"w:{edge}")
        enabled = (edge == "top" and top) or (edge == "bottom" and bottom)
        elem.set(qn("w:val"), "single" if enabled else "nil")
        elem.set(qn("w:sz"), "8" if enabled else "0")
        elem.set(qn("w:space"), "0")
        elem.set(qn("w:color"), "000000")
        borders.append(elem)


def _set_cell_margins(cell, top: int = 80, start: int = 120, bottom: int = 80, end: int = 120) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    margins = tc_pr.first_child_found_in("w:tcMar")
    if margins is None:
        margins = OxmlElement("w:tcMar")
        tc_pr.append(margins)
    for edge, value in (("top", top), ("start", start), ("bottom", bottom), ("end", end)):
        element = margins.find(qn(f"w:{edge}"))
        if element is None:
            element = OxmlElement(f"w:{edge}")
            margins.append(element)
        element.set(qn("w:w"), str(value))
        element.set(qn("w:type"), "dxa")


def _add_table_single(doc: Document, header: List[str], rows: List[List[str]]) -> None:
    ncols = max(len(header), max((len(r) for r in rows), default=1))
    table = doc.add_table(rows=1 + len(rows), cols=ncols)
    table.autofit = False
    table.alignment = WD_TABLE_ALIGNMENT.LEFT
    content_rows = [header] + rows
    weights = []
    for index in range(ncols):
        longest = max((len(str(row[index])) if index < len(row) else 0 for row in content_rows), default=1)
        weights.append(max(8, min(longest, 50)))
    total_weight = sum(weights) or ncols
    widths = [max(0.8, 6.5 * weight / total_weight) for weight in weights]
    scale = 6.5 / sum(widths)
    widths = [width * scale for width in widths]
    dxa_widths = [int(round(width * 1440)) for width in widths]
    dxa_widths[-1] += 9360 - sum(dxa_widths)

    table_pr = table._tbl.tblPr
    for tag in ("w:tblW", "w:tblInd", "w:tblLayout"):
        for existing in list(table_pr.findall(qn(tag))):
            table_pr.remove(existing)
    table_width = OxmlElement("w:tblW")
    table_width.set(qn("w:w"), "9360")
    table_width.set(qn("w:type"), "dxa")
    table_indent = OxmlElement("w:tblInd")
    table_indent.set(qn("w:w"), "120")
    table_indent.set(qn("w:type"), "dxa")
    layout = OxmlElement("w:tblLayout")
    layout.set(qn("w:type"), "fixed")
    table_pr.extend([table_width, table_indent, layout])
    grid_columns = table._tbl.tblGrid.findall(qn("w:gridCol"))
    for index, grid_column in enumerate(grid_columns[:ncols]):
        grid_column.set(qn("w:w"), str(dxa_widths[index]))
    for j, h in enumerate(header):
        cell = table.cell(0, j)
        cell.width = Inches(widths[j])
        cell._tc.get_or_add_tcPr().get_or_add_tcW().set(qn("w:w"), str(dxa_widths[j]))
        cell._tc.get_or_add_tcPr().get_or_add_tcW().set(qn("w:type"), "dxa")
        cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
        cell.text = ""
        cell.paragraphs[0].style = doc.styles[_S["table_body"]]
        apply_runs(cell.paragraphs[0], parse_inline(h),
                   spec_key="table_body", force_bold=True)
        _set_cell_borders(cell, top=True, bottom=True)
        _set_cell_margins(cell)
    for i, row in enumerate(rows):
        for j in range(ncols):
            cell = table.cell(i + 1, j)
            cell.width = Inches(widths[j])
            cell._tc.get_or_add_tcPr().get_or_add_tcW().set(qn("w:w"), str(dxa_widths[j]))
            cell._tc.get_or_add_tcPr().get_or_add_tcW().set(qn("w:type"), "dxa")
            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            cell.text = ""
            cell.paragraphs[0].style = doc.styles[_S["table_body"]]
            apply_runs(cell.paragraphs[0],
                       parse_inline(row[j] if j < len(row) else ""),
                       spec_key="table_body")
            _set_cell_borders(cell, bottom=i == len(rows) - 1)
            _set_cell_margins(cell)


def _add_table(doc: Document, header: List[str], rows: List[List[str]]) -> None:
    """Add a readable table, splitting overly wide comparison grids.

    A method table with seven or eight narrow columns is technically inside
    the page but practically unreadable.  Repeat the identifying first column
    and split the remaining fields into compact continuation tables instead of
    shrinking words into vertical fragments.
    """
    ncols = max(len(header), max((len(row) for row in rows), default=1))
    if ncols <= 6:
        _add_table_single(doc, header, rows)
        return
    padded_header = header + [""] * (ncols - len(header))
    padded_rows = [row + [""] * (ncols - len(row)) for row in rows]
    for chunk_index, start in enumerate(range(1, ncols, 4)):
        indices = [0] + list(range(start, min(start + 4, ncols)))
        if chunk_index:
            _para(doc, "table_title", "table_title", "Table continued", force_bold=True)
        _add_table_single(
            doc,
            [padded_header[index] for index in indices],
            [[row[index] for index in indices] for row in padded_rows],
        )


# ---------------------------------------------------------------------------
# Block tokenizer
# ---------------------------------------------------------------------------

@dataclass
class Block:
    kind:     str
    level:    int             = 0
    text:     str             = ""
    ordered:  bool            = False
    list_number: int          = 0
    depth:    int             = 0
    code:     str             = ""
    language: str             = ""
    header:   List[str]       = field(default_factory=list)
    rows:     List[List[str]] = field(default_factory=list)
    alt:      str             = ""
    path:     str             = ""
    latex:    str             = ""
    lines:    List[str]       = field(default_factory=list)


_HEADING_RE    = re.compile(r"^(#{1,6})\s+(.*)")
_EMBEDDED_HEADING_PREFIX_RE = re.compile(r"^#{1,6}\s+")
_NUMBERED_SECTION_HEADING_RE = re.compile(r"^\d+(?:\.\d+)*\.\s+\S")
_HTML_ANCHOR_RE = re.compile(r"^<a\s+id=[\"']ref-\d+[\"']\s*>\s*</a>\s*$", re.I)
_HTML_COMMENT_START_RE = re.compile(r"^\s*<!--")
_UL_RE         = re.compile(r"^(\s*)[-*+]\s+(.*)")
_OL_RE         = re.compile(r"^(\s*)(\d+)[.)]\s+(.*)")
_FENCE_RE      = re.compile(r"^```(\w*)\s*$")
_MATH_FENCE_RE = re.compile(r"^\$\$\s*$")
_IMG_RE        = re.compile(r"^!\[([^\]]*)\]\(([^)]+)\)\s*$")
_TABLE_ROW_RE  = re.compile(r"^\|.+")
_HR_RE         = re.compile(r"^(?:-{3,}|_{3,}|\*{3,})\s*$")
_REF_ENTRY_RE  = re.compile(r"^\[?\d+\]?[.)\s]|\[@[^\]]+\]:")
_AFFIL_START   = re.compile(r"^\^[0-9,]+\^")
_INDENTED_RE   = re.compile(r"^(?: {4,}|\t+)(.*)$")


def _is_continuation(line: str) -> bool:
    if not line.strip():
        return False
    if _REF_ENTRY_RE.match(line):
        return False
    if _AFFIL_START.match(line):
        return False
    if _HTML_COMMENT_START_RE.match(line):
        return False
    for pat in (_HEADING_RE, _FENCE_RE, _TABLE_ROW_RE,
                _UL_RE, _OL_RE, _HR_RE, _IMG_RE):
        if pat.match(line):
            return False
    return True


def tokenize(md_text: str) -> List[Block]:
    lines = md_text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    blocks: List[Block] = []
    i, n = 0, len(lines)

    while i < n:
        line = lines[i]

        # YAML front matter
        if i == 0 and line.strip() == "---":
            i += 1
            while i < n and lines[i].strip() != "---":
                i += 1
            i += 1
            continue

        # Editor-only HTML comments never belong in the exported manuscript.
        if _HTML_COMMENT_START_RE.match(line):
            while i < n:
                current = lines[i]
                i += 1
                if "-->" in current:
                    break
            continue

        # Fenced code block
        m = _FENCE_RE.match(line)
        if m:
            lang = m.group(1)
            code_lines: List[str] = []
            i += 1
            while i < n and not lines[i].startswith("```"):
                code_lines.append(lines[i])
                i += 1
            i += 1
            blocks.append(Block(kind="code_block", language=lang,
                                code="\n".join(code_lines)))
            continue

        # Display math fence
        if _MATH_FENCE_RE.match(line):
            math_lines: List[str] = []
            i += 1
            while i < n and not _MATH_FENCE_RE.match(lines[i]):
                math_lines.append(lines[i])
                i += 1
            i += 1
            blocks.append(Block(kind="math_block", latex="\n".join(math_lines)))
            continue

        if _HTML_ANCHOR_RE.match(line.strip()):
            i += 1
            continue

        # ATX heading
        m = _HEADING_RE.match(line)
        if m:
            heading_text = m.group(2).strip()
            while _EMBEDDED_HEADING_PREFIX_RE.match(heading_text):
                heading_text = _EMBEDDED_HEADING_PREFIX_RE.sub("", heading_text, count=1).strip()
            blocks.append(Block(kind="heading", level=len(m.group(1)),
                                text=heading_text))
            i += 1
            continue

        # Horizontal rule
        if _HR_RE.match(line):
            blocks.append(Block(kind="hr"))
            i += 1
            continue

        # Standalone image
        m = _IMG_RE.match(line)
        if m:
            blocks.append(Block(kind="image", alt=m.group(1), path=m.group(2)))
            i += 1
            continue

        # Indented text block: preserve one source line -> one logical block line.
        m = _INDENTED_RE.match(line)
        if m and not _TABLE_ROW_RE.match(line):
            block_lines: List[str] = [m.group(1).rstrip()]
            i += 1
            while i < n:
                next_match = _INDENTED_RE.match(lines[i])
                if not next_match or not next_match.group(1).strip():
                    break
                block_lines.append(next_match.group(1).rstrip())
                i += 1
            blocks.append(Block(kind="indented_block", lines=block_lines))
            continue

        # Reference definition  [@key]: text...
        ref_m = re.match(r"^\[@([^\]]+)\]:\s*(.+)$", line)
        if ref_m:
            blocks.append(Block(kind="ref_def", text=ref_m.group(2).strip()))
            i += 1
            continue

        # Pipe table
        if _TABLE_ROW_RE.match(line):
            raw_rows: List[List[str]] = []
            while i < n and _TABLE_ROW_RE.match(lines[i]):
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                raw_rows.append(cells)
                i += 1
            data = [r for r in raw_rows
                    if not all(re.match(r"^[-: ]+$", c) for c in r)]
            if data:
                blocks.append(Block(kind="table", header=data[0], rows=data[1:]))
            continue

        # Ordered list item
        m = _OL_RE.match(line)
        if m:
            blocks.append(Block(kind="list_item", ordered=True,
                                list_number=int(m.group(2)),
                                depth=len(m.group(1)) // 2, text=m.group(3)))
            i += 1
            continue

        # Unordered list item
        m = _UL_RE.match(line)
        if m:
            blocks.append(Block(kind="list_item", ordered=False,
                                depth=len(m.group(1)) // 2, text=m.group(2)))
            i += 1
            continue

        # Blank line
        if not line.strip():
            i += 1
            continue

        # Paragraph
        para_lines = [line]
        i += 1
        while i < n and _is_continuation(lines[i]):
            para_lines.append(lines[i].rstrip())
            i += 1
        blocks.append(Block(kind="paragraph",
                            text=" ".join(l.rstrip() for l in para_lines)))

    return blocks


# ---------------------------------------------------------------------------
# Context helpers
# ---------------------------------------------------------------------------

def _plain_text(raw: str) -> str:
    t = re.sub(r"\*+|__?", "", raw)
    t = re.sub(r"\[@[^\]]+\]", "", t)
    t = re.sub(r"\^[^\^]+\^", "", t)
    t = re.sub(r"`[^`]+`", "", t)
    t = re.sub(r"\[[^\]]*\]\([^\)]*\)", "", t)
    return t.strip()


def _section_ctx(text: str) -> Optional[str]:
    return _SECTION_CONTEXT.get(text.strip().lower())


def _caption_style(raw_text: str) -> Optional[str]:
    plain = _plain_text(raw_text)
    for pat, key in _CAPTION_PATTERNS:
        if pat.match(plain):
            return key
    return None


def _should_include_in_toc(text: str) -> bool:
    normalized = text.strip().lower()
    if normalized in {
        "table of contents",
        "abstract",
        "keywords",
        "key words",
        "acknowledgments",
        "acknowledgements",
        "references",
        "reference",
    }:
        return False
    return True


def _collect_static_toc_entries(blocks: List[Block]) -> List[Tuple[int, str]]:
    entries: List[Tuple[int, str]] = []
    for block in blocks:
        if block.kind != "heading":
            continue
        text = block.text.strip()
        effective_level = 2 if block.level == 1 and _NUMBERED_SECTION_HEADING_RE.match(text) else block.level
        if effective_level not in {2, 3, 4}:
            continue
        if not text or not _should_include_in_toc(text):
            continue
        entries.append((effective_level, text))
    return entries


def _insert_static_toc(doc: Document, entries: List[Tuple[int, str]]) -> None:
    for level, text in entries:
        p = doc.add_paragraph(style=_S["body"])
        if level == 3:
            p.paragraph_format.left_indent = Inches(0.32)
        elif level >= 4:
            p.paragraph_format.left_indent = Inches(0.58)
        apply_runs(p, parse_inline(text), spec_key="body")


# ---------------------------------------------------------------------------
# Document body clear
# ---------------------------------------------------------------------------

def _clear_body(doc: Document) -> None:
    body = doc.element.body
    sect_pr = body.find(qn("w:sectPr"))
    for child in list(body):
        body.remove(child)
    if sect_pr is not None:
        body.append(sect_pr)


# ---------------------------------------------------------------------------
# Main converter
# ---------------------------------------------------------------------------

def convert(
    md_path: Path,
    out_path: Path,
    template_path: Path,
    author: str = "",
    subject: str = "Scholarly review manuscript",
    keywords: str = "",
) -> None:
    md_text = md_path.read_text(encoding="utf-8")
    if re.search(r"\[@P\d{3}", md_text):
        raise SystemExit("[md2docx] ERROR: unresolved stable citation tokens remain in Markdown")
    if re.search(r"<!--\s*paragraph_id\s*:", md_text, re.I):
        raise SystemExit("[md2docx] ERROR: editor paragraph markers remain in Markdown")
    blocks  = tokenize(md_text)
    toc_entries = _collect_static_toc_entries(blocks)
    doc     = Document(str(template_path))
    _clear_body(doc)
    _configure_academic_document(doc)
    document_title = next(
        (
            block.text.strip()
            for block in blocks
            if block.kind == "heading"
            and block.level == 1
            and not _NUMBERED_SECTION_HEADING_RE.match(block.text.strip())
        ),
        md_path.stem,
    )
    properties = doc.core_properties
    properties.title = document_title
    properties.subject = subject.strip()
    properties.author = author.strip()
    properties.last_modified_by = author.strip()
    properties.keywords = keywords.strip()
    properties.comments = "Generated from the review Markdown manuscript."
    bullet_num_id = _create_numbering_definition(doc, ordered=False)
    ordered_num_id = _create_numbering_definition(doc, ordered=True)
    reference_num_id = _create_numbering_definition(doc, ordered=True, reference=True)

    ctx: str           = "body"
    front_matter: bool = False
    inserted_toc_heading = False
    saw_toc_heading = False
    skipping_source_toc = False
    missing_images: List[str] = []

    def insert_toc_once() -> None:
        nonlocal inserted_toc_heading
        if inserted_toc_heading:
            return
        _para(doc, "body", "h2", "Table of Contents", force_bold=True)
        _insert_static_toc(doc, toc_entries)
        inserted_toc_heading = True

    for block in blocks:

        if block.kind == "heading":
            plain_heading = block.text.strip().lower()
            numbered_h1_section = block.level == 1 and _NUMBERED_SECTION_HEADING_RE.match(block.text.strip())
            if plain_heading == "table of contents":
                saw_toc_heading = True
                skipping_source_toc = True
                insert_toc_once()
                continue
            skipping_source_toc = False
            effective_level = 2 if numbered_h1_section else block.level
            style_key, spec_key = _HEADING_FORMAT.get(effective_level, ("body", "body"))
            new_ctx = _section_ctx(block.text)
            ctx = new_ctx if new_ctx else "body"
            if block.level == 1 and not numbered_h1_section:
                front_matter = True
            elif effective_level >= 2:
                front_matter = False
            _para(doc, style_key, spec_key, block.text)

        elif block.kind == "paragraph":
            text  = block.text.strip()
            plain = _plain_text(text)

            if re.match(r"^\*\*keywords:?\*\*", text, re.I):
                ctx = "keywords"
                _para(doc, "keywords", "keywords", text)
                continue

            # Bold-only section label  e.g. **Abstract**
            new_ctx = _section_ctx(plain)
            if new_ctx:
                skipping_source_toc = False
                if new_ctx in {"abstract", "keywords"} and not inserted_toc_heading and not saw_toc_heading:
                    insert_toc_once()
                ctx = new_ctx
                _para(doc, "body", "body", text, force_bold=True)
                continue
            if skipping_source_toc:
                continue

            # Front matter: author / affiliation
            if front_matter and ctx == "body":
                if _AFFIL_START.match(text):
                    _para(doc, "address", "address", text)
                else:
                    _para(doc, "author", "author", text)
                continue

            if ctx != "body":
                spec = ctx if ctx in _FONT_SPEC else "body"
                _para(doc, ctx, spec, text)
            else:
                cap = _caption_style(text)
                key = cap if cap else "body"
                _para(doc, key, key, text)

        elif block.kind == "indented_block":
            if skipping_source_toc:
                continue
            for raw_line in block.lines:
                text = raw_line.strip()
                if not text:
                    continue
                cap = _caption_style(text)
                key = cap if cap else ("references" if ctx == "references" else "body")
                spec = key if key in _FONT_SPEC else "body"
                _para(doc, key, spec, text)

        elif block.kind == "ref_def":
            if skipping_source_toc:
                continue
            _para(doc, "references", "references", block.text)

        elif block.kind == "list_item":
            if skipping_source_toc:
                continue
            if ctx == "references":
                number = block.list_number or 1
                p = _para(
                    doc,
                    "references",
                    "references",
                    f"{number}. {block.text}",
                )
                p.paragraph_format.left_indent = Inches(0.5)
                p.paragraph_format.first_line_indent = Inches(-0.25)
            else:
                p = _para(doc, "body", "body", block.text)
                _apply_numbering(p, ordered_num_id if block.ordered else bullet_num_id, block.depth)

        elif block.kind == "code_block":
            if skipping_source_toc:
                continue
            p  = doc.add_paragraph(style=_S["body"])
            wr = p.add_run(block.code)
            _set_word_run_font(wr, "Courier New", 9)

        elif block.kind == "math_block":
            if skipping_source_toc:
                continue
            p = doc.add_paragraph(style=_S["body"])
            _apply_math(p, block.latex)

        elif block.kind == "table":
            if skipping_source_toc:
                continue
            _add_table(doc, block.header, block.rows)

        elif block.kind == "image":
            if skipping_source_toc:
                continue
            img_path = Path(block.path)
            if not img_path.is_absolute():
                img_path = md_path.parent / img_path
            if img_path.exists():
                p = doc.add_paragraph(style=_S["body"])
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                p.paragraph_format.keep_with_next = True
                p.paragraph_format.space_before = Pt(6)
                p.paragraph_format.space_after = Pt(2)
                caption_key = _caption_style(block.alt) or "figure"
                max_width, max_height = _figure_bounds_for_caption(
                    caption_key, _usable_page_width_inches(doc)
                )
                figure_width, figure_height = _bounded_figure_size(
                    img_path, max_width, max_height
                )
                picture_kwargs = {"width": Inches(figure_width)}
                if figure_height is not None:
                    picture_kwargs["height"] = Inches(figure_height)
                p.add_run().add_picture(str(img_path), **picture_kwargs)
                if block.alt:
                    _para(doc, caption_key, caption_key, block.alt)
            else:
                missing_images.append(str(img_path))

        elif block.kind == "hr":
            # Horizontal rules in review Markdown are section separators, not
            # desired visual borders in the final DOCX.
            continue

    if missing_images:
        raise SystemExit("[md2docx] ERROR: missing images: " + ", ".join(missing_images))
    _configure_footer(doc)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(out_path))
    print(f"[md2docx] Saved -> {out_path}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

_DEFAULT_TEMPLATE = Path(__file__).resolve().parent.parent / "review_template.docx"


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="md2docx",
        description="Convert Markdown to DOCX using review_template.docx styles.",
    )
    p.add_argument("--input",    required=True, metavar="MD",   help="Input .md file")
    p.add_argument("--output",   required=True, metavar="DOCX", help="Output .docx file")
    p.add_argument("--template", default=str(_DEFAULT_TEMPLATE), metavar="DOCX",
                   help=f"Word template (default: {_DEFAULT_TEMPLATE})")
    p.add_argument("--author", default="", help="Document author metadata; empty removes stale template authors")
    p.add_argument("--subject", default="Scholarly review manuscript", help="Document subject metadata")
    p.add_argument("--keywords", default="", help="Comma- or semicolon-separated document keywords")
    return p


def main() -> None:
    args          = _build_parser().parse_args()
    md_path       = Path(args.input).resolve()
    out_path      = Path(args.output).resolve()
    template_path = Path(args.template).resolve()

    if not md_path.exists():
        raise SystemExit(f"[md2docx] ERROR: Input not found: {md_path}")
    if not template_path.exists():
        raise SystemExit(f"[md2docx] ERROR: Template not found: {template_path}")
    if not _LATEX_OK:
        print("[md2docx] INFO: latex2word unavailable; using built-in deterministic script formatting")

    convert(
        md_path,
        out_path,
        template_path,
        author=args.author,
        subject=args.subject,
        keywords=args.keywords,
    )


if __name__ == "__main__":
    main()
