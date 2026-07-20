#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from insert_figures_into_draft import insert_figures


STABLE_CITATION_RE = re.compile(r"\[((?:@P\d{3})(?:\s*[;,]\s*@P\d{3})*)\]")
NUMERIC_CITATION_RE = re.compile(r"\[(?:\d+(?:\s*[-,]\s*\d+)*)\]")
PARAGRAPH_MARKER_RE = re.compile(r"\s*<!--\s*paragraph_id\s*:[^>]+-->\s*", re.I)
ALLOWED_PARAGRAPH_TYPES = {
    "comparison",
    "mechanism",
    "landmark_example",
    "limitation_or_gap",
    "context",
    "synthesis",
    "outlook",
    "prose",
}


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text.rstrip() + "\n", encoding="utf-8")
    tmp.replace(path)


def unwrap(value: Any) -> Any:
    if isinstance(value, dict) and "value" in value:
        return value.get("value")
    return value


def matrix_rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        for key in ("papers", "rows", "literature_matrix"):
            rows = payload.get(key)
            if isinstance(rows, list):
                return [row for row in rows if isinstance(row, dict)]
    return []


def stable_ids(text: str) -> list[str]:
    result: list[str] = []
    for match in STABLE_CITATION_RE.finditer(text or ""):
        result.extend(re.findall(r"@?(P\d{3})", match.group(1)))
    return result


def replace_stable_citations(text: str, order: list[str]) -> str:
    def repl(match: re.Match[str]) -> str:
        paper_ids = re.findall(r"@?(P\d{3})", match.group(1))
        numbers = []
        for paper_id in paper_ids:
            if paper_id not in order:
                order.append(paper_id)
            number = order.index(paper_id) + 1
            if number not in numbers:
                numbers.append(number)
        return "[" + ",".join(str(number) for number in numbers) + "]"

    return STABLE_CITATION_RE.sub(repl, text)


def metadata_for(review_root: Path, paper_id: str) -> dict[str, Any]:
    path = review_root / "review-library" / "metadata" / "papers" / f"{paper_id}.metadata.json"
    if not path.exists():
        return {}
    payload = read_json(path)
    return payload if isinstance(payload, dict) else {}


def author_text(value: Any) -> str:
    authors = unwrap(value)
    if isinstance(authors, str):
        authors = [item.strip() for item in re.split(r";|\band\b", authors) if item.strip()]
    if not isinstance(authors, list) or not authors:
        return "Author information unavailable"
    cleaned = [str(item).strip() for item in authors if str(item).strip()]
    if len(cleaned) > 6:
        return "; ".join(cleaned[:3]) + "; et al."
    return "; ".join(cleaned)


def reference_text(review_root: Path, row: dict[str, Any], number: int) -> tuple[str, list[str]]:
    paper_id = str(row.get("paper_id") or "")
    metadata = metadata_for(review_root, paper_id)
    title = str(unwrap(metadata.get("title")) or row.get("title") or "Untitled").strip().rstrip(".")
    authors = author_text(metadata.get("authors") or row.get("authors"))
    journal = str(unwrap(metadata.get("journal")) or row.get("journal") or "").strip().rstrip(".")
    year = unwrap(metadata.get("year")) or row.get("year")
    year_text = str(year).strip() if year else ""
    # Filename-derived metadata occasionally carries a numeric file prefix,
    # while some journal labels already end with the publication year. Clean
    # those mechanical artifacts once before formatting the reference.
    journal = re.sub(r"^\d{1,3}-\s*(?=[A-Za-z])", "", journal)
    if journal and year_text:
        journal = re.sub(rf"\s+\(?{re.escape(year_text)}\)?$", "", journal).rstrip(" ,.;")
    doi = str(unwrap(metadata.get("doi")) or row.get("doi") or "").strip()
    missing = []
    if not journal:
        missing.append("journal")
    if not year:
        missing.append("year")
    pieces = [f"{number}. {authors}. {title}."]
    if journal:
        pieces.append(f"*{journal}*")
    if year_text:
        pieces.append(year_text + ".")
    if doi:
        pieces.append(f"https://doi.org/{doi.replace('https://doi.org/', '')}")
    return " ".join(pieces).replace("..", "."), missing


def normalize_heading(title: str) -> str:
    return re.sub(r"^#{1,6}\s+", "", str(title or "").strip())


def word_count(text: str) -> int:
    return len(re.findall(r"\b[A-Za-z][A-Za-z'-]*\b", text))


def build_body(
    section_payload: dict[str, Any],
) -> tuple[str, list[dict[str, Any]], list[str], list[str]]:
    sections = section_payload.get("sections")
    if not isinstance(sections, list) or not sections:
        return "", [], ["section_drafts.json contains no sections"], []
    parts: list[str] = []
    paragraph_records: list[dict[str, Any]] = []
    blockers: list[str] = []
    warnings: list[str] = []
    seen_paragraph_ids: set[str] = set()
    for section in sections:
        if not isinstance(section, dict):
            blockers.append("section entry is not an object")
            continue
        sid = str(section.get("section_id") or "<missing>")
        title = normalize_heading(section.get("title") or "")
        if not title:
            blockers.append(f"{sid}: section title is missing")
            continue
        paragraphs = section.get("paragraphs")
        if not isinstance(paragraphs, list) or not paragraphs:
            blockers.append(f"{sid}: paragraphs is missing or empty")
            continue
        parts.append(f"## {title}")
        for index, paragraph in enumerate(paragraphs, start=1):
            if not isinstance(paragraph, dict):
                blockers.append(f"{sid}: paragraph {index} is not an object")
                continue
            paragraph_id = str(paragraph.get("paragraph_id") or "").strip()
            if not paragraph_id:
                paragraph_id = f"{sid}-p{index}"
            if paragraph_id in seen_paragraph_ids:
                blockers.append(f"duplicate paragraph_id: {paragraph_id}")
            else:
                seen_paragraph_ids.add(paragraph_id)
            paragraph_type = str(paragraph.get("paragraph_type") or "prose").strip()
            if paragraph_type not in ALLOWED_PARAGRAPH_TYPES:
                warnings.append(
                    f"{paragraph_id or sid}: paragraph_type must be one of "
                    + ", ".join(sorted(ALLOWED_PARAGRAPH_TYPES))
                )
            markdown = str(paragraph.get("markdown") or paragraph.get("text") or "").strip()
            markdown = PARAGRAPH_MARKER_RE.sub(" ", markdown).strip()
            if not markdown:
                blockers.append(f"{paragraph_id or sid}: paragraph markdown is empty")
                continue
            if NUMERIC_CITATION_RE.search(markdown):
                blockers.append(
                    f"{paragraph_id or sid}: numeric citations are forbidden before merge; use [@Pxxx]"
                )
            cited = stable_ids(markdown)
            declared = [str(pid) for pid in paragraph.get("cited_paper_ids") or []]
            if declared and set(cited) != set(declared):
                blockers.append(
                    f"{paragraph_id or sid}: inline stable citations {sorted(set(cited))} "
                    f"do not match cited_paper_ids {sorted(set(declared))}"
                )
            if not cited and word_count(markdown) >= 40:
                warnings.append(f"{paragraph_id or sid}: long paragraph has no stable citation")
            parts.append(markdown)
            paragraph_records.append(
                {
                    "paragraph_id": paragraph_id,
                    "section_id": sid,
                    "paragraph_type": paragraph_type,
                    "cited_paper_ids": list(dict.fromkeys(cited)),
                }
            )
    return "\n\n".join(parts).strip(), paragraph_records, blockers, warnings


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Deterministically merge review sections and number citations.")
    parser.add_argument("--review-root", default=str(Path(__file__).resolve().parents[3]))
    parser.add_argument("--project-id", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    review_root = Path(args.review_root).resolve()
    project = review_root / "review-projects" / args.project_id
    stage2 = project / "02_section_drafting"
    stage4 = project / "04_first_draft"
    section_path = stage2 / "section_drafts.json"
    matrix_path = project / "01_matrix_outline" / "literature_matrix.json"
    if not section_path.exists() or not matrix_path.exists():
        raise SystemExit("Missing section_drafts.json or literature_matrix.json")

    section_payload = read_json(section_path)
    matrix = read_json(matrix_path)
    rows = matrix_rows(matrix)
    row_by_id = {str(row.get("paper_id")): row for row in rows if row.get("paper_id")}
    blockers: list[str] = []

    front = section_payload.get("front_matter") if isinstance(section_payload, dict) else None
    if not isinstance(front, dict):
        blockers.append("section_drafts.json.front_matter is missing")
        front = {}
    title = str(front.get("title") or "").strip()
    abstract = str(front.get("abstract") or "").strip()
    keywords = front.get("keywords") or []
    warnings: list[str] = []
    if not title:
        blockers.append("front_matter.title is missing")
    abstract_words = word_count(abstract)
    if abstract_words == 0:
        blockers.append("front_matter.abstract is missing")
    elif not 120 <= abstract_words <= 350:
        warnings.append(
            f"front_matter.abstract has {abstract_words} words; 120-350 is a common review range"
        )
    if re.search(r"!\[[^\]]*\]\([^)]+\)|<img\b", abstract, re.I):
        blockers.append("front_matter.abstract must not contain embedded images")
    keyword_count = len([x for x in keywords if str(x).strip()]) if isinstance(keywords, list) else 0
    if not isinstance(keywords, list) or keyword_count == 0:
        blockers.append("front_matter.keywords is missing or empty")
    elif not 3 <= keyword_count <= 10:
        warnings.append("front_matter.keywords is outside the common 3-10 range")

    body, paragraph_records, body_blockers, body_warnings = build_body(section_payload)
    blockers.extend(body_blockers)
    warnings.extend(body_warnings)
    cited_ids = stable_ids(body)
    for paper_id in cited_ids:
        if paper_id not in row_by_id:
            blockers.append(f"citation references paper absent from literature matrix: {paper_id}")

    validation = {
        "project_id": args.project_id,
        "blocking_issues": sorted(set(blockers)),
        "warnings": sorted(set(warnings)),
        "paragraph_count": len(paragraph_records),
        "stable_citation_ids": list(dict.fromkeys(cited_ids)),
    }
    stage4.mkdir(parents=True, exist_ok=True)
    write_json(stage4 / "merge_validation.json", validation)
    if blockers:
        print(f"BLOCKING ISSUES: {len(set(blockers))}")
        for issue in sorted(set(blockers)):
            print(f"- {issue}")
        return 1

    citation_order: list[str] = []
    numbered_body = replace_stable_citations(body, citation_order)
    reference_lines: list[str] = []
    incomplete_references: list[dict[str, Any]] = []
    for number, paper_id in enumerate(citation_order, start=1):
        text, missing = reference_text(review_root, row_by_id[paper_id], number)
        reference_lines.append(text)
        if missing:
            incomplete_references.append({"paper_id": paper_id, "missing": missing})

    manuscript = "\n\n".join(
        [
            f"# {title}",
            "## Abstract",
            abstract,
            "**Keywords:** " + "; ".join(str(item).strip() for item in keywords if str(item).strip()),
            numbered_body,
            "## References",
            "\n".join(reference_lines),
        ]
    )
    write_text(stage4 / "first_draft.md", manuscript)

    figure_insertion: dict[str, Any] | None = None
    figures_requested = False
    figure_path = stage2 / "figure_candidates.json"
    if figure_path.exists():
        figure_payload = read_json(figure_path)
        figure_rows = figure_payload.get("figures") if isinstance(figure_payload, dict) else figure_payload
        if isinstance(figure_rows, list) and figure_rows:
            figures_requested = True
    visual_manifest_path = project / "03_figure_redraw" / "review_visual_manifest.json"
    if visual_manifest_path.exists():
        visual_payload = read_json(visual_manifest_path)
        visual_rows = visual_payload.get("visuals") if isinstance(visual_payload, dict) else None
        if isinstance(visual_rows, list) and visual_rows:
            figures_requested = True
    if figures_requested:
        try:
            figure_insertion = insert_figures(project)
        except ValueError as exc:
            blockers.append(f"selected figures could not be inserted: {exc}")
        else:
            if int(figure_insertion.get("inserted_count") or 0) == 0:
                blockers.append("selected figures produced no inserted manuscript images")
    validation["blocking_issues"] = sorted(set(blockers))
    validation["figure_insertion"] = figure_insertion
    write_json(stage4 / "merge_validation.json", validation)
    if blockers:
        print(f"BLOCKING ISSUES: {len(set(blockers))}")
        for issue in sorted(set(blockers)):
            print(f"- {issue}")
        return 1

    paper_to_ref = {paper_id: index + 1 for index, paper_id in enumerate(citation_order)}
    citations = {
        "project_id": args.project_id,
        "numbering_rule": "first_appearance",
        "reference_list": [
            {
                "ref_num": number,
                "paper_id": paper_id,
                "title": row_by_id[paper_id].get("title"),
            }
            for number, paper_id in enumerate(citation_order, start=1)
        ],
        "paper_to_ref": paper_to_ref,
        "paragraphs": [
            {
                **record,
                "ref_nums": [paper_to_ref[pid] for pid in record["cited_paper_ids"]],
            }
            for record in paragraph_records
        ],
        "incomplete_reference_metadata": incomplete_references,
    }
    write_json(stage4 / "citations.json", citations)
    report = "\n".join(
        [
            "# Merge Report",
            "",
            f"- Sections merged: {len(section_payload['sections'])}",
            f"- Paragraphs merged: {len(paragraph_records)}",
            f"- References: {len(citation_order)}",
            f"- Figures inserted: {int((figure_insertion or {}).get('inserted_count') or 0)}",
            f"- Draft word count: {word_count(manuscript)}",
            "- Citation numbering: deterministic first appearance from stable paper IDs",
            f"- References with incomplete metadata: {len(incomplete_references)}",
        ]
    )
    write_text(stage4 / "merge_report.md", report)
    issues = ["# Remaining Issues", ""]
    if incomplete_references:
        issues.append("- Some references lack journal or year metadata; see citations.json.")
    else:
        issues.append("None.")
    write_text(stage4 / "remaining_issues.md", "\n".join(issues))
    print(f"Merged {len(paragraph_records)} paragraphs with {len(citation_order)} references")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
