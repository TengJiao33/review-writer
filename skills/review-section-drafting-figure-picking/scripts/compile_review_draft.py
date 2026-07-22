#!/usr/bin/env python3
"""Compile a readable Markdown manuscript into the structured draft contract.

The manuscript remains the writing surface.  Small HTML comments carry only the
provenance needed by downstream checks; they are not prose templates.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


H1_RE = re.compile(r"^#\s+(.+?)\s*$")
H2_RE = re.compile(r"^##\s+(.+?)\s*$")
SECTION_ID_RE = re.compile(r"<!--\s*section_id\s*:\s*([^>]+?)\s*-->", re.I)
PROVENANCE_RE = re.compile(r"<!--\s*evidence\s*:\s*(.*?)\s*-->", re.I | re.S)
KEYWORDS_RE = re.compile(r"^\s*(?:\*\*)?keywords(?:\*\*)?\s*:\s*(.+?)\s*$", re.I)
STABLE_RE = re.compile(r"\[((?:@P\d{3})(?:\s*[;,]\s*@P\d{3})*)\]")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def normalized_heading(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def stable_ids(text: str) -> list[str]:
    result: list[str] = []
    for match in STABLE_RE.finditer(text or ""):
        result.extend(re.findall(r"P\d{3}", match.group(1)))
    return list(dict.fromkeys(result))


def split_heading_blocks(text: str) -> tuple[str, list[tuple[str, list[str]]], list[str]]:
    title = ""
    preface: list[str] = []
    blocks: list[tuple[str, list[str]]] = []
    current_title: str | None = None
    current_lines: list[str] = []
    for raw_line in text.splitlines():
        if not title:
            match = H1_RE.match(raw_line)
            if match:
                title = match.group(1).strip()
                continue
        match = H2_RE.match(raw_line)
        if match:
            if current_title is None:
                preface.extend(current_lines)
            else:
                blocks.append((current_title, current_lines))
            current_title = match.group(1).strip()
            current_lines = []
            continue
        current_lines.append(raw_line)
    if current_title is None:
        preface.extend(current_lines)
    else:
        blocks.append((current_title, current_lines))
    return title, blocks, preface


def extract_keywords(lines: list[str]) -> tuple[list[str], list[str]]:
    keywords: list[str] = []
    remaining: list[str] = []
    for line in lines:
        match = KEYWORDS_RE.match(line.replace("**", ""))
        if not match:
            remaining.append(line)
            continue
        raw = match.group(1)
        keywords.extend(
            item.strip()
            for item in re.split(r"[;,]", raw)
            if item.strip()
        )
    return list(dict.fromkeys(keywords)), remaining


def prose_text(lines: list[str]) -> str:
    return " ".join(line.strip() for line in lines if line.strip()).strip()


def paragraph_blocks(lines: list[str]) -> list[str]:
    blocks: list[str] = []
    current: list[str] = []
    in_fence = False
    for line in lines:
        if line.strip().startswith("```"):
            in_fence = not in_fence
        if not line.strip() and not in_fence:
            if current:
                blocks.append("\n".join(current).strip())
                current = []
            continue
        current.append(line)
    if current:
        blocks.append("\n".join(current).strip())
    return [block for block in blocks if block]


def parse_provenance(raw: str) -> tuple[list[str], str | None]:
    parts = [part.strip() for part in raw.split("|") if part.strip()]
    evidence_raw = parts[0] if parts else ""
    paragraph_type: str | None = None
    for part in parts[1:]:
        if part.lower().startswith("type:"):
            paragraph_type = part.split(":", 1)[1].strip() or None
    evidence_ids = [
        item
        for item in re.split(r"[\s,;]+", evidence_raw)
        if re.fullmatch(r"P\d{3}-E\d+", item)
    ]
    return list(dict.fromkeys(evidence_ids)), paragraph_type


def compile_paragraphs(lines: list[str], section_id: str) -> list[dict[str, Any]]:
    paragraphs: list[dict[str, Any]] = []
    pending_evidence: list[str] = []
    pending_type: str | None = None
    for block in paragraph_blocks(lines):
        block = SECTION_ID_RE.sub("", block).strip()
        provenance = PROVENANCE_RE.search(block)
        if provenance:
            evidence_ids, paragraph_type = parse_provenance(provenance.group(1))
            pending_evidence = evidence_ids
            pending_type = paragraph_type
            block = PROVENANCE_RE.sub("", block).strip()
        if not block:
            continue
        cited = stable_ids(block)
        paragraph_type = pending_type or (
            "comparison" if len(cited) > 1 else "evidence" if cited else "transition"
        )
        paragraphs.append(
            {
                "paragraph_id": f"{section_id}-p{len(paragraphs) + 1}",
                "paragraph_type": paragraph_type,
                "markdown": block,
                "cited_paper_ids": cited,
                "evidence_ids": pending_evidence,
            }
        )
        pending_evidence = []
        pending_type = None
    return paragraphs


def compile_manuscript(manuscript_path: Path, blueprint_path: Path) -> dict[str, Any]:
    manuscript = manuscript_path.read_text(encoding="utf-8")
    blueprint = read_json(blueprint_path)
    title, blocks, preface = split_heading_blocks(manuscript)
    plans = [row for row in blueprint.get("sections") or [] if isinstance(row, dict)]
    by_id = {str(row.get("section_id")): row for row in plans if row.get("section_id")}
    by_title = {
        normalized_heading(str(row.get("title") or "")): str(row.get("section_id"))
        for row in plans
        if row.get("section_id") and row.get("title")
    }

    keywords, preface = extract_keywords(preface)
    abstract = ""
    sections: list[dict[str, Any]] = []
    seen: set[str] = set()
    for heading, lines in blocks:
        if normalized_heading(heading) == "abstract":
            block_keywords, remaining = extract_keywords(lines)
            keywords.extend(block_keywords)
            abstract = prose_text(remaining)
            continue
        explicit = None
        for line in lines:
            match = SECTION_ID_RE.search(line)
            if match:
                explicit = match.group(1).strip()
                break
        section_id = explicit or by_title.get(normalized_heading(heading))
        if not section_id:
            raise ValueError(
                f"Heading {heading!r} does not match a blueprint title and has no section_id comment"
            )
        if section_id not in by_id:
            raise ValueError(f"Unknown blueprint section_id under {heading!r}: {section_id}")
        if section_id in seen:
            raise ValueError(f"Duplicate manuscript section: {section_id}")
        seen.add(section_id)
        sections.append(
            {
                "section_id": section_id,
                "title": heading,
                "paragraphs": compile_paragraphs(lines, section_id),
            }
        )

    if not abstract:
        abstract = prose_text(preface)
    return {
        "front_matter": {
            "title": title,
            "abstract": abstract,
            "keywords": list(dict.fromkeys(keywords)),
        },
        "sections": sections,
        "source_manuscript": manuscript_path.name,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compile manuscript.md into section_drafts.json without constraining the prose."
    )
    parser.add_argument("--review-root", default=str(Path(__file__).resolve().parents[3]))
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--input", help="Markdown manuscript path; defaults to the project draft folder")
    parser.add_argument("--output", help="Structured JSON path; defaults to section_drafts.json")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    project = Path(args.review_root).resolve() / "review-projects" / args.project_id
    stage = project / "02_section_drafting"
    manuscript_path = Path(args.input).resolve() if args.input else stage / "manuscript.md"
    output_path = Path(args.output).resolve() if args.output else stage / "section_drafts.json"
    blueprint_path = project / "01_matrix_outline" / "section_blueprint.json"
    for required in (manuscript_path, blueprint_path):
        if not required.exists():
            raise SystemExit(f"Missing required input: {required}")
    try:
        payload = compile_manuscript(manuscript_path, blueprint_path)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Wrote structured draft: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
