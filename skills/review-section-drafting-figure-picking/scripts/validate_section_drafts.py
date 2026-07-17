#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


STABLE_RE = re.compile(r"\[((?:@P\d{3})(?:\s*[;,]\s*@P\d{3})*)\]")
NUMERIC_RE = re.compile(r"\[\d+(?:\s*[-,]\s*\d+)*\]")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def word_count(text: str) -> int:
    return len(re.findall(r"\b[A-Za-z][A-Za-z'-]*\b", text or ""))


def stable_ids(text: str) -> list[str]:
    result = []
    for match in STABLE_RE.finditer(text or ""):
        result.extend(re.findall(r"P\d{3}", match.group(1)))
    return result


def normalized_paragraph(text: str) -> str:
    without_citations = STABLE_RE.sub(" ", text or "")
    return re.sub(r"\s+", " ", without_citations).strip().lower()


def matrix_ids(payload: Any) -> set[str]:
    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, dict):
        rows = payload.get("papers") or payload.get("rows") or payload.get("literature_matrix") or []
    else:
        rows = []
    return {str(row.get("paper_id")) for row in rows if isinstance(row, dict) and row.get("paper_id")}


def evidence_index(payload: Any) -> dict[str, str]:
    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, dict):
        rows = payload.get("papers") or payload.get("rows") or payload.get("literature_matrix") or []
    else:
        rows = []
    index: dict[str, str] = {}
    for row in rows:
        if not isinstance(row, dict) or not row.get("paper_id"):
            continue
        paper_id = str(row["paper_id"])
        for anchor in row.get("evidence_anchors") or []:
            if isinstance(anchor, dict) and anchor.get("evidence_id"):
                index[str(anchor["evidence_id"])] = paper_id
    return index


def evidence_details(payload: Any) -> dict[str, dict[str, Any]]:
    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, dict):
        rows = payload.get("papers") or payload.get("rows") or payload.get("literature_matrix") or []
    else:
        rows = []
    details: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict) or not row.get("paper_id"):
            continue
        paper_id = str(row["paper_id"])
        for anchor in row.get("evidence_anchors") or []:
            if isinstance(anchor, dict) and anchor.get("evidence_id"):
                details[str(anchor["evidence_id"])] = {**anchor, "paper_id": paper_id}
    return details


def validate(project: Path) -> dict[str, Any]:
    stage1 = project / "01_matrix_outline"
    stage2 = project / "02_section_drafting"
    payload = read_json(stage2 / "section_drafts.json")
    blueprint = read_json(stage1 / "section_blueprint.json")
    matrix_payload = read_json(stage1 / "literature_matrix.json")
    known_ids = matrix_ids(matrix_payload)
    known_evidence = evidence_index(matrix_payload)
    evidence_by_id = evidence_details(matrix_payload)
    blockers: list[str] = []
    warnings: list[str] = []

    figure_payload = read_json(stage2 / "figure_candidates.json")
    if isinstance(figure_payload, dict):
        figure_rows = figure_payload.get("figures")
    else:
        figure_rows = figure_payload
    if not isinstance(figure_rows, list):
        blockers.append(
            "figure_candidates.json must be a list (legacy objects must contain a figures list)"
        )

    front = payload.get("front_matter") if isinstance(payload, dict) else None
    if not isinstance(front, dict):
        blockers.append("front_matter is missing")
        front = {}
    abstract_words = word_count(str(front.get("abstract") or ""))
    if abstract_words == 0:
        blockers.append("front_matter.abstract is missing")
    elif not 120 <= abstract_words <= 350:
        warnings.append(
            f"abstract has {abstract_words} words; 120-350 is a common review range"
        )
    keywords = front.get("keywords") or []
    keyword_count = len([x for x in keywords if str(x).strip()]) if isinstance(keywords, list) else 0
    if not isinstance(keywords, list) or keyword_count == 0:
        blockers.append("front_matter.keywords is missing or empty")
    elif not 3 <= keyword_count <= 10:
        warnings.append("3-10 keywords is a common review range")
    if not str(front.get("title") or "").strip():
        blockers.append("front_matter.title is missing")

    planned = {
        str(section.get("section_id")): section
        for section in blueprint.get("sections") or []
        if isinstance(section, dict) and section.get("section_id")
    }
    drafted = {
        str(section.get("section_id")): section
        for section in payload.get("sections") or []
        if isinstance(section, dict) and section.get("section_id")
    }
    for sid in sorted(set(planned) - set(drafted)):
        warnings.append(f"planned section is missing or was reorganized: {sid}")
    for sid in sorted(set(drafted) - set(planned)):
        warnings.append(f"unplanned section is present: {sid}")
    if not drafted:
        blockers.append("section_drafts.json contains no drafted sections")

    all_cited: set[str] = set()
    all_evidence: set[str] = set()
    paragraph_ids: set[str] = set()
    normalized_seen: dict[str, str] = {}
    cited_paragraphs_by_paper: dict[str, set[str]] = {}
    used_evidence_by_paper: dict[str, set[str]] = {}
    section_reports = []
    for sid, section in drafted.items():
        plan = planned.get(sid) or {}
        paragraphs = section.get("paragraphs") or []
        if not isinstance(paragraphs, list) or not paragraphs:
            blockers.append(f"{sid}: paragraphs is missing or empty")
            continue
        actual_words = 0
        types = []
        for index, paragraph in enumerate(paragraphs, start=1):
            if not isinstance(paragraph, dict):
                blockers.append(f"{sid}: paragraph {index} is not an object")
                continue
            pid = str(paragraph.get("paragraph_id") or "").strip()
            effective_pid = pid or f"{sid}-p{index}"
            if pid and pid in paragraph_ids:
                blockers.append(f"duplicate paragraph_id: {pid}")
            elif pid:
                paragraph_ids.add(pid)
            paragraph_type = str(paragraph.get("paragraph_type") or "").strip()
            if paragraph_type:
                types.append(paragraph_type)
            markdown = str(paragraph.get("markdown") or paragraph.get("text") or "").strip()
            if not markdown:
                blockers.append(f"{effective_pid}: paragraph markdown is empty")
                continue
            actual_words += word_count(markdown)
            if NUMERIC_RE.search(markdown):
                blockers.append(f"{effective_pid}: numeric citation used before merge")
            cited = stable_ids(markdown)
            declared = [str(item) for item in paragraph.get("cited_paper_ids") or []]
            if declared and set(cited) != set(declared):
                blockers.append(f"{effective_pid}: stable citation IDs do not match cited_paper_ids")
            if paragraph_type == "comparison" and len(set(cited)) < 2:
                warnings.append(f"{effective_pid}: comparison paragraph cites fewer than two papers")
            if not cited and word_count(markdown) >= 40:
                warnings.append(f"{effective_pid}: long paragraph has no stable citations")
            evidence_ids = [str(item) for item in paragraph.get("evidence_ids") or [] if str(item).strip()]
            if cited and not evidence_ids:
                blockers.append(f"{effective_pid}: cited paragraph has no evidence_ids")
            unknown_evidence = sorted(set(evidence_ids) - set(known_evidence))
            if unknown_evidence:
                blockers.append(
                    f"{effective_pid}: unknown evidence IDs {', '.join(unknown_evidence)}"
                )
            evidence_owners = {known_evidence[item] for item in evidence_ids if item in known_evidence}
            owners_without_citation = sorted(evidence_owners - set(cited))
            if owners_without_citation:
                blockers.append(
                    f"{effective_pid}: evidence belongs to uncited papers "
                    + ", ".join(owners_without_citation)
                )
            cited_without_evidence = sorted(set(cited) - evidence_owners)
            if cited_without_evidence:
                blockers.append(
                    f"{effective_pid}: cited papers have no linked evidence "
                    + ", ".join(cited_without_evidence)
                )
            all_evidence.update(evidence_ids)
            for paper_id in cited:
                cited_paragraphs_by_paper.setdefault(paper_id, set()).add(effective_pid)
            for evidence_id in evidence_ids:
                owner = known_evidence.get(evidence_id)
                if owner:
                    used_evidence_by_paper.setdefault(owner, set()).add(evidence_id)
            normalized = normalized_paragraph(markdown)
            if word_count(normalized) >= 40:
                previous = normalized_seen.get(normalized)
                if previous:
                    blockers.append(
                        f"duplicated long paragraph after citation normalization: {previous}, {effective_pid}"
                    )
                else:
                    normalized_seen[normalized] = effective_pid
            for paper_id in cited:
                all_cited.add(paper_id)
                if paper_id not in known_ids:
                    blockers.append(f"{effective_pid}: unknown paper ID {paper_id}")
        target_words = int(plan.get("target_words") or 0)
        ratio = actual_words / target_words if target_words else 0.0
        if target_words and ratio < 0.8:
            warnings.append(f"{sid}: {actual_words} words is below 80% of the planning estimate {target_words}")
        section_reports.append(
            {
                "section_id": sid,
                "target_words": target_words,
                "actual_words": actual_words,
                "target_ratio": round(ratio, 4) if target_words else None,
                "paragraph_types": types,
            }
        )

    contract = blueprint.get("coverage_contract") or {}
    for dimension in contract.get("dimensions") or []:
        if not isinstance(dimension, dict):
            continue
        for item in dimension.get("items") or []:
            if not isinstance(item, dict) or not item.get("required"):
                continue
            candidates = {str(pid) for pid in item.get("covered_by") or []}
            if candidates and not (candidates & all_cited):
                warnings.append(
                    f"planned coverage item is not cited in the draft: "
                    f"{dimension.get('name')}/{item.get('name')}"
                )

    evidence_usage = []
    for paper_id in sorted(all_cited):
        used_ids = sorted(used_evidence_by_paper.get(paper_id, set()))
        available_ids = sorted(
            evidence_id
            for evidence_id, details in evidence_by_id.items()
            if details.get("paper_id") == paper_id
        )
        full_text_used = [
            evidence_id
            for evidence_id in used_ids
            if str(evidence_by_id.get(evidence_id, {}).get("source_level") or "") == "full_text"
        ]
        paragraph_count = len(cited_paragraphs_by_paper.get(paper_id, set()))
        evidence_usage.append(
            {
                "paper_id": paper_id,
                "cited_paragraph_count": paragraph_count,
                "used_evidence_count": len(used_ids),
                "available_evidence_count": len(available_ids),
                "used_evidence_ids": used_ids,
                "full_text_evidence_used_count": len(full_text_used),
                "paragraphs_per_used_anchor": round(paragraph_count / len(used_ids), 3)
                if used_ids
                else None,
            }
        )

    return {
        "project_id": project.name,
        "abstract_words": abstract_words,
        "keyword_count": keyword_count,
        "section_reports": section_reports,
        "cited_paper_ids": sorted(all_cited),
        "evidence_ids": sorted(all_evidence),
        "evidence_usage_by_paper": evidence_usage,
        "blocking_issues": sorted(set(blockers)),
        "warnings": warnings,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate structured review section drafts.")
    parser.add_argument("--review-root", default=str(Path(__file__).resolve().parents[3]))
    parser.add_argument("--project-id", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    project = Path(args.review_root).resolve() / "review-projects" / args.project_id
    for required in (
        project / "02_section_drafting" / "section_drafts.json",
        project / "02_section_drafting" / "figure_candidates.json",
        project / "01_matrix_outline" / "section_blueprint.json",
        project / "01_matrix_outline" / "literature_matrix.json",
    ):
        if not required.exists():
            raise SystemExit(f"Missing required input: {required}")
    report = validate(project)
    out = project / "02_section_drafting" / "section_draft_validation.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote section draft validation to {out}")
    if report["blocking_issues"]:
        print(f"BLOCKING ISSUES: {len(report['blocking_issues'])}")
        for issue in report["blocking_issues"]:
            print(f"- {issue}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
