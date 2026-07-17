#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


PLACEHOLDER_RE = re.compile(
    r"\b(TODO|TBD|citation needed|verification needed|check this|fixme)\b",
    re.I,
)
REF_CALLOUT_RE = re.compile(r"\[(\d+(?:\s*[-,]\s*\d+)*)\]")
REF_ITEM_RE = re.compile(r"^\s*(?:\[(\d+)\]|(\d+)[.)])\s+", re.M)
IMAGE_RE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.M)
REFERENCES_HEADING_RE = re.compile(
    r"^\s*#{1,6}\s*(references|reference list|bibliography|cited literature|参考文献)\s*$",
    re.I | re.M,
)
ABSTRACT_HEADING_RE = re.compile(r"^\s*#{1,6}\s*abstract\s*$", re.I | re.M)
KEYWORDS_RE = re.compile(r"(?:^\s*#{1,6}\s*keywords\s*$|^\s*\*\*keywords:?\*\*\s*:?)", re.I | re.M)
INTRODUCTION_HEADING_RE = re.compile(r"^\s*#{1,6}\s*(?:\d+[.)]?\s*)?introduction\s*$", re.I | re.M)
CONCLUSION_HEADING_RE = re.compile(r"^\s*#{1,6}\s*.*(?:conclusion|outlook).*?$", re.I | re.M)
STABLE_CITATION_RE = re.compile(r"\[((?:@P\d{3})(?:\s*[;,]\s*@P\d{3})*)\]")
PAPER_ID_LEAK_RE = re.compile(r"\[P\d{3}\]")
PARAGRAPH_MARKER_RE = re.compile(r"<!--\s*paragraph_id\s*:", re.I)
AUDIT_PLACEHOLDER_RE = re.compile(
    r"representative claim|claim from .{0,80} section|reviewed against evidence",
    re.I,
)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def upstream_release_issues(project: Path) -> list[str]:
    reports = {
        "screening": project / "00_discovery" / "screening_validation.json",
        "matrix": project / "01_matrix_outline" / "matrix_validation.json",
        "blueprint": project / "01_matrix_outline" / "blueprint_validation.json",
        "section_draft": project / "02_section_drafting" / "section_draft_validation.json",
        "merge": project / "04_first_draft" / "merge_validation.json",
    }
    issues: list[str] = []
    for name, path in reports.items():
        if not path.exists():
            issues.append(f"missing_upstream_validation:{name}")
            continue
        try:
            report = read_json(path)
        except Exception:
            issues.append(f"invalid_upstream_validation:{name}")
            continue
        if not isinstance(report, dict):
            issues.append(f"invalid_upstream_validation:{name}")
            continue
        blockers = report.get("blocking_issues") or []
        blocker_count = report.get("blocking_issue_count")
        if blockers or (isinstance(blocker_count, int) and blocker_count > 0):
            issues.append(f"upstream_validation_has_blockers:{name}")

    figures_path = project / "02_section_drafting" / "figure_candidates.json"
    figures: Any = None
    if figures_path.exists():
        try:
            payload = read_json(figures_path)
            figures = payload.get("figures") if isinstance(payload, dict) else payload
        except Exception:
            pass
    if not isinstance(figures, list):
        issues.append("invalid_figure_candidates")
        return issues

    skip_path = project / "03_figure_redraw" / "skip_reason.md"
    skipped = skip_path.exists() and bool(read_text(skip_path).strip())
    if not figures and not skipped:
        issues.append("figure_redraw_skip_reason_missing")
    elif figures and not skipped:
        manifest_path = project / "03_figure_redraw" / "redrawn_figure_manifest.json"
        try:
            manifest = read_json(manifest_path)
        except Exception:
            manifest = None
        prepared = manifest.get("figures") if isinstance(manifest, dict) else None
        if not isinstance(prepared, list):
            prepared = manifest.get("redrawn_figures") if isinstance(manifest, dict) else None
        if not isinstance(prepared, list) or not any(
            isinstance(item, dict)
            and (
                item.get("status") == "redrawn"
                or (
                    item.get("status") == "source_verified"
                    and item.get("verification_status") == "passed"
                )
            )
            for item in prepared
        ):
            issues.append("figure_preparation_incomplete")
    return issues


def expand_ref_callouts(text: str) -> set[int]:
    refs: set[int] = set()
    for match in REF_CALLOUT_RE.finditer(text or ""):
        for part in re.split(r"\s*,\s*", match.group(1)):
            if "-" in part:
                left, right = [piece.strip() for piece in part.split("-", 1)]
                if left.isdigit() and right.isdigit() and int(left) <= int(right):
                    refs.update(range(int(left), int(right) + 1))
            elif part.strip().isdigit():
                refs.add(int(part.strip()))
    return refs


def references_tail(text: str) -> tuple[re.Match[str] | None, str]:
    match = REFERENCES_HEADING_RE.search(text or "")
    return match, text[match.end() :] if match else ""


def reference_numbers(text: str) -> list[int]:
    _, tail = references_tail(text)
    result = []
    for match in REF_ITEM_RE.finditer(tail):
        result.append(int(match.group(1) or match.group(2)))
    return result


def detect_references_section(text: str) -> dict[str, Any]:
    match, tail = references_tail(text)
    if not match:
        return {"present": False, "start_line": None, "item_count": 0}
    return {
        "present": True,
        "start_line": text[: match.start()].count("\n") + 1,
        "item_count": len(list(REF_ITEM_RE.finditer(tail))),
    }


def matrix_rows_by_id(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    payload = read_json(path)
    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, dict):
        rows = payload.get("papers") or payload.get("rows") or payload.get("literature_matrix") or []
    else:
        rows = []
    return {
        str(row.get("paper_id")): row
        for row in rows
        if isinstance(row, dict) and row.get("paper_id")
    }


def matrix_evidence_owners(rows: dict[str, dict[str, Any]]) -> dict[str, str]:
    owners: dict[str, str] = {}
    for paper_id, row in rows.items():
        for anchor in row.get("evidence_anchors") or []:
            if isinstance(anchor, dict) and anchor.get("evidence_id"):
                owners[str(anchor["evidence_id"])] = paper_id
    return owners


def drafted_paragraphs(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    try:
        payload = read_json(path)
    except Exception:
        return {}
    records: dict[str, dict[str, Any]] = {}
    for section in payload.get("sections") or []:
        if not isinstance(section, dict):
            continue
        section_id = str(section.get("section_id") or "").strip()
        for index, paragraph in enumerate(section.get("paragraphs") or [], start=1):
            if not isinstance(paragraph, dict):
                continue
            paragraph_id = str(paragraph.get("paragraph_id") or f"{section_id}-p{index}").strip()
            markdown = str(paragraph.get("markdown") or paragraph.get("text") or "").strip()
            cited_ids = [
                paper_id
                for match in STABLE_CITATION_RE.finditer(markdown)
                for paper_id in re.findall(r"P\d{3}", match.group(1))
            ]
            declared = [str(item) for item in paragraph.get("cited_paper_ids") or []]
            records[paragraph_id] = {
                "paragraph_id": paragraph_id,
                "section_id": section_id,
                "paragraph_type": str(paragraph.get("paragraph_type") or "prose"),
                "markdown": markdown,
                "cited_paper_ids": declared or cited_ids,
                "evidence_ids": [str(item) for item in paragraph.get("evidence_ids") or []],
            }
    return records


def normalized_audit_text(value: str) -> str:
    value = STABLE_CITATION_RE.sub(" ", value or "")
    value = REF_CALLOUT_RE.sub(" ", value)
    value = re.sub(r"[`*_#>|]", " ", value)
    value = re.sub(r"\s+", " ", value).strip().lower()
    return re.sub(r"\s+([,.;:!?])", r"\1", value)


CLAIM_RISK_PATTERNS = {
    "mechanistic_certainty": re.compile(
        r"\b(prove|confirm|establish|active species|operative pathway|unified mechanis)\w*\b",
        re.I,
    ),
    "priority_or_absence": re.compile(
        r"\b(first|only|unprecedented|no (?:general|reported|known))\b",
        re.I,
    ),
    "field_wide_generalization": re.compile(
        r"\b(universal|generally|consensus|across all|most widely|converge)\w*\b",
        re.I,
    ),
    "maturity_or_superlative": re.compile(
        r"\b(practical maturity|mature platform|single most|most powerful|remarkably broad)\b",
        re.I,
    ),
}


def claim_risk_signals(value: str) -> list[str]:
    return [name for name, pattern in CLAIM_RISK_PATTERNS.items() if pattern.search(value or "")]


def semantic_queue(project: Path, limit: int = 6) -> dict[str, Any]:
    paragraph_path = project / "02_section_drafting" / "section_drafts.json"
    matrix_path = project / "01_matrix_outline" / "literature_matrix.json"
    paragraphs = drafted_paragraphs(paragraph_path)
    rows = matrix_rows_by_id(matrix_path)
    anchors = {
        str(anchor.get("evidence_id")): {**anchor, "paper_id": paper_id}
        for paper_id, row in rows.items()
        for anchor in row.get("evidence_anchors") or []
        if isinstance(anchor, dict) and anchor.get("evidence_id")
    }
    type_weight = {
        "mechanism": 5,
        "comparison": 4,
        "limitation_or_gap": 4,
        "scope": 3,
        "synthesis": 3,
    }
    high_stakes = re.compile(
        r"\b(first|only|prove|confirm|demonstrat|mechanis|active species|"
        r"enantioselect|regioselect|broad scope|limitation|challenge|suggest|"
        r"universal|generally|common|consensus|elusive|unprecedented)\w*\b|"
        r"\bacross all\b|\bno (?:general|reported|known)\b",
        re.I,
    )
    ranked: list[dict[str, Any]] = []
    for paragraph in paragraphs.values():
        cited_ids = list(dict.fromkeys(paragraph["cited_paper_ids"]))
        evidence_ids = list(dict.fromkeys(paragraph["evidence_ids"]))
        if not cited_ids:
            continue
        markdown = paragraph["markdown"]
        risk_signals = claim_risk_signals(markdown)
        plain = STABLE_CITATION_RE.sub("", markdown)
        sentences = [
            re.sub(r"\s+", " ", raw).strip()
            for raw in re.split(r"(?<=[.!?])\s+", plain)
            if len(re.findall(r"\b[A-Za-z][A-Za-z'-]*\b", raw)) >= 8
        ]
        if not sentences:
            sentences = [re.sub(r"\s+", " ", plain).strip()]
        sentences.sort(
            key=lambda sentence: (
                bool(high_stakes.search(sentence)),
                bool(re.search(r"\b\d+(?:\.\d+)?%?\b", sentence)),
                len(sentence),
            ),
            reverse=True,
        )
        score = type_weight.get(paragraph["paragraph_type"], 1)
        score += min(len(cited_ids), 3)
        score += int(bool(high_stakes.search(markdown))) * 2
        score += min(len(risk_signals), 3)
        score += int(bool(re.search(r"\b\d+(?:\.\d+)?%?\b", markdown)))
        ranked.append(
            {
                "queue_id": f"{paragraph['paragraph_id']}-a1",
                "section_id": paragraph["section_id"],
                "paragraph_id": paragraph["paragraph_id"],
                "paragraph_type": paragraph["paragraph_type"],
                "priority_score": score,
                "claim_risk_signals": risk_signals,
                "queue_status": "source_check_required" if evidence_ids else "missing_paragraph_evidence",
                "text_span": sentences[0],
                # Do not pre-approve every paragraph-level citation for a
                # narrower sentence.  The semantic reviewer must select the
                # minimum supporting subset after opening the linked source.
                "cited_paper_ids": [],
                "evidence_ids": [],
                "paragraph_cited_paper_ids": cited_ids,
                "paragraph_evidence_ids": evidence_ids,
                "evidence_context_candidates": [
                    anchors[evidence_id] for evidence_id in evidence_ids if evidence_id in anchors
                ],
            }
        )
    ranked.sort(
        key=lambda row: (row["priority_score"], len(row["text_span"])),
        reverse=True,
    )
    selected = ranked[: max(1, limit)]
    return {
        "project_id": project.name,
        "selection_rule": "highest-risk cited passages across the manuscript; the reviewer may replace or extend the sample",
        "candidate_count": len(ranked),
        "ready_count": sum(item["queue_status"] == "source_check_required" for item in selected),
        "source_check_required_count": sum(
            item["queue_status"] == "source_check_required" for item in selected
        ),
        "missing_paragraph_evidence_count": sum(
            item["queue_status"] == "missing_paragraph_evidence" for item in selected
        ),
        "items": selected,
    }


def unwrap(value: Any) -> Any:
    if isinstance(value, dict) and "value" in value:
        return value.get("value")
    return value


def actual_incomplete_references(
    review_root: Path,
    paper_ids: list[str],
    rows_by_id: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for paper_id in paper_ids:
        metadata_path = (
            review_root / "review-library" / "metadata" / "papers" / f"{paper_id}.metadata.json"
        )
        metadata: dict[str, Any] = {}
        if metadata_path.exists():
            try:
                payload = read_json(metadata_path)
                if isinstance(payload, dict):
                    metadata = payload
            except Exception:
                pass
        row = rows_by_id.get(paper_id) or {}
        missing = []
        if not str(unwrap(metadata.get("journal")) or row.get("journal") or "").strip():
            missing.append("journal")
        if not (unwrap(metadata.get("year")) or row.get("year")):
            missing.append("year")
        doi = str(unwrap(metadata.get("doi")) or row.get("doi") or "").strip()
        volume = str(unwrap(metadata.get("volume")) or row.get("volume") or "").strip()
        locator = str(
            unwrap(metadata.get("pages"))
            or unwrap(metadata.get("page"))
            or unwrap(metadata.get("article_number"))
            or unwrap(metadata.get("article_no"))
            or row.get("pages")
            or row.get("page")
            or row.get("article_number")
            or row.get("article_no")
            or ""
        ).strip()
        if not doi and not (volume and locator):
            missing.append("doi_or_volume_and_page_locator")
        if missing:
            issues.append({"paper_id": paper_id, "missing": missing})
    return issues


def blueprint_target(path: Path) -> tuple[int | None, list[str]]:
    if not path.exists():
        return None, ["section_blueprint.json is missing"]
    payload = read_json(path)
    sections = payload.get("sections") if isinstance(payload, dict) else []
    target = sum(int(section.get("target_words") or 0) for section in sections or [] if isinstance(section, dict))
    contract = payload.get("coverage_contract") if isinstance(payload, dict) else None
    issues = []
    if not isinstance(contract, dict):
        issues.append("coverage_contract is missing from section_blueprint.json")
    return target or None, issues


def cited_paragraph_stats(text: str) -> dict[str, Any]:
    match, _ = references_tail(text)
    body = text[: match.start()] if match else text
    cited = 0
    multi = 0
    for raw in re.split(r"\n\s*\n", body):
        paragraph = raw.strip()
        if not paragraph or paragraph.startswith("#") or paragraph.startswith("!"):
            continue
        refs = expand_ref_callouts(paragraph)
        if refs:
            cited += 1
            if len(refs) >= 2:
                multi += 1
    return {
        "cited_paragraph_count": cited,
        "multi_source_paragraph_count": multi,
        "multi_source_ratio": round(multi / cited, 4) if cited else 0.0,
    }


def duplicated_long_paragraphs(text: str) -> list[dict[str, Any]]:
    match, _ = references_tail(text)
    body = text[: match.start()] if match else text
    seen: dict[str, int] = {}
    duplicates: list[dict[str, Any]] = []
    for index, raw in enumerate(re.split(r"\n\s*\n", body), start=1):
        paragraph = raw.strip()
        if not paragraph or paragraph.startswith("#") or paragraph.startswith("!"):
            continue
        normalized = REF_CALLOUT_RE.sub(" ", paragraph)
        normalized = re.sub(r"\s+", " ", normalized).strip().lower()
        if len(re.findall(r"\b[A-Za-z][A-Za-z'-]*\b", normalized)) < 40:
            continue
        if normalized in seen:
            duplicates.append({"first_paragraph": seen[normalized], "duplicate_paragraph": index})
        else:
            seen[normalized] = index
    return duplicates


def semantic_audit_status(
    path: Path,
    required: bool,
    known_paper_ids: set[str],
    evidence_owners: dict[str, str],
    paragraphs_by_id: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any], list[str]]:
    if not path.exists():
        return {"present": False}, ["semantic_audit.json is missing"] if required else []
    try:
        payload = read_json(path)
    except Exception as exc:
        return {"present": True, "valid_json": False}, [f"semantic_audit.json is invalid: {exc}"]
    blockers = []
    if not isinstance(payload, dict):
        return {"present": True, "valid_json": True}, ["semantic_audit.json must contain an object"]
    if not str(payload.get("model") or "").strip():
        blockers.append("semantic_audit.model is missing")
    checks = payload.get("checks")
    if not isinstance(checks, list) or not checks:
        blockers.append("semantic_audit.checks is missing or empty")
        checks = []
    allowed = {"supported", "needs_revision", "unsupported", "removed"}
    for index, check in enumerate(checks, start=1):
        if not isinstance(check, dict):
            blockers.append(f"semantic_audit check {index} is not an object")
            continue
        verdict = str(check.get("verdict") or "")
        if verdict not in allowed:
            blockers.append(f"semantic_audit check {index} has an invalid verdict")
        if verdict in {"needs_revision", "unsupported"}:
            blockers.append(f"semantic_audit check {index} has unresolved verdict {verdict}")
        source_checked = check.get("source_checked") is True
        support_scope = str(check.get("support_scope") or "").strip()
        if verdict == "supported" and not source_checked:
            blockers.append(f"semantic_audit check {index} was not checked against the source")
        if verdict != "removed" and support_scope not in {"full", "partial", "none"}:
            blockers.append(f"semantic_audit check {index} has an invalid support_scope")
        if verdict == "supported" and support_scope != "full":
            blockers.append(
                f"semantic_audit check {index} is marked supported without full claim support"
            )
        text_span = str(check.get("text_span") or "").strip()
        if verdict != "removed" and len(text_span) < 20:
            blockers.append(f"semantic_audit check {index} has no substantive text_span")
        elif AUDIT_PLACEHOLDER_RE.search(text_span):
            blockers.append(f"semantic_audit check {index} uses placeholder text_span")
        section_id = str(check.get("section_id") or "").strip()
        if not section_id:
            blockers.append(f"semantic_audit check {index} has no section_id")
        paragraph_id = str(check.get("paragraph_id") or "").strip()
        paragraph = paragraphs_by_id.get(paragraph_id)
        if verdict != "removed" and not paragraph_id:
            blockers.append(f"semantic_audit check {index} has no paragraph_id")
        if verdict != "removed" and paragraph_id and paragraph is None:
            blockers.append(f"semantic_audit check {index} references unknown paragraph {paragraph_id}")
        cited_ids = [str(item) for item in check.get("cited_paper_ids") or []]
        if verdict != "removed" and not cited_ids:
            blockers.append(f"semantic_audit check {index} has no cited_paper_ids")
        unknown_ids = sorted(set(cited_ids) - known_paper_ids) if known_paper_ids else []
        if unknown_ids:
            blockers.append(
                f"semantic_audit check {index} references unknown papers: {', '.join(unknown_ids)}"
            )
        evidence_ids = [str(item) for item in check.get("evidence_ids") or [] if str(item).strip()]
        if verdict != "removed" and not evidence_ids:
            blockers.append(f"semantic_audit check {index} has no evidence_ids")
        unknown_evidence = sorted(set(evidence_ids) - set(evidence_owners))
        if unknown_evidence:
            blockers.append(
                f"semantic_audit check {index} references unknown evidence: "
                + ", ".join(unknown_evidence)
            )
        owners = {evidence_owners[item] for item in evidence_ids if item in evidence_owners}
        if owners - set(cited_ids):
            blockers.append(
                f"semantic_audit check {index} links evidence from uncited papers: "
                + ", ".join(sorted(owners - set(cited_ids)))
            )
        if set(cited_ids) - owners:
            blockers.append(
                f"semantic_audit check {index} has cited papers without linked evidence: "
                + ", ".join(sorted(set(cited_ids) - owners))
            )
        if verdict != "removed" and paragraph is not None:
            if section_id and section_id != paragraph["section_id"]:
                blockers.append(
                    f"semantic_audit check {index} section does not match paragraph {paragraph_id}"
                )
            normalized_span = normalized_audit_text(text_span)
            normalized_paragraph = normalized_audit_text(paragraph["markdown"])
            if normalized_span and normalized_span not in normalized_paragraph:
                blockers.append(
                    f"semantic_audit check {index} text_span is not found in paragraph {paragraph_id}"
                )
            extra_citations = sorted(set(cited_ids) - set(paragraph["cited_paper_ids"]))
            if extra_citations:
                blockers.append(
                    f"semantic_audit check {index} cites papers not linked to paragraph {paragraph_id}: "
                    + ", ".join(extra_citations)
                )
            extra_evidence = sorted(set(evidence_ids) - set(paragraph["evidence_ids"]))
            if extra_evidence:
                blockers.append(
                    f"semantic_audit check {index} uses evidence not linked to paragraph {paragraph_id}: "
                    + ", ".join(extra_evidence)
                )
    unresolved = payload.get("unresolved_blockers")
    if not isinstance(unresolved, list):
        blockers.append("semantic_audit.unresolved_blockers is missing")
    elif unresolved:
        blockers.append("semantic_audit has unresolved blockers")
    return {
        "present": True,
        "valid_json": True,
        "check_count": len(checks),
        "unresolved_blockers": unresolved if isinstance(unresolved, list) else None,
    }, blockers


def scan_draft(project: Path, phase: str) -> dict[str, Any]:
    final_path = project / "05_final_audit" / "final_draft.md"
    first_path = project / "04_first_draft" / "first_draft.md"
    if phase == "preflight":
        draft = first_path
        target = "first_draft"
    else:
        draft = final_path if final_path.exists() else first_path
        target = "final_draft" if draft == final_path and final_path.exists() else "first_draft"
    text = read_text(draft) if draft.exists() else ""
    headings = [{"level": len(m.group(1)), "title": m.group(2).strip()} for m in HEADING_RE.finditer(text)]
    heading_titles = [item["title"] for item in headings]
    duplicate_headings = sorted({title for title in heading_titles if heading_titles.count(title) > 1})
    placeholder_hits = [
        {"line": line_no, "text": line.strip()}
        for line_no, line in enumerate(text.splitlines(), start=1)
        if PLACEHOLDER_RE.search(line)
    ]
    called_refs = sorted(expand_ref_callouts(text))
    listed_sequence = reference_numbers(text)
    listed_refs = sorted(set(listed_sequence))
    missing_listed_refs = sorted(set(called_refs) - set(listed_refs))
    uncalled_listed_refs = sorted(set(listed_refs) - set(called_refs))
    duplicate_reference_numbers = sorted({number for number in listed_sequence if listed_sequence.count(number) > 1})
    expected_sequence = list(range(1, len(listed_sequence) + 1))
    reference_numbering_contiguous = listed_sequence == expected_sequence

    image_paths = [match.group(1) for match in IMAGE_RE.finditer(text)]
    abstract_image_paths: list[str] = []
    abstract_heading = ABSTRACT_HEADING_RE.search(text)
    if abstract_heading:
        keywords_after_abstract = KEYWORDS_RE.search(text, abstract_heading.end())
        next_heading = HEADING_RE.search(text, abstract_heading.end())
        boundaries = [
            match.start()
            for match in (keywords_after_abstract, next_heading)
            if match is not None
        ]
        abstract_end = min(boundaries) if boundaries else len(text)
        abstract_segment = text[abstract_heading.end():abstract_end]
        abstract_image_paths = [
            match.group(1)
            for match in IMAGE_RE.finditer(abstract_segment)
        ]
        if re.search(r"<img\b", abstract_segment, re.I):
            abstract_image_paths.append("<html-img>")
    broken_images = []
    for raw in image_paths:
        if re.match(r"^[a-z]+://", raw):
            continue
        if not (draft.parent / raw).resolve().exists():
            broken_images.append(raw)

    figure_report_paths = [
        project / "05_final_audit" / "figure_insertion_report.json",
        project / "04_first_draft" / "figure_insertion_report.json",
    ]
    figure_report = next((path for path in figure_report_paths if path.exists()), None)
    source_placeholder_mode = False
    if figure_report:
        try:
            source_placeholder_mode = read_json(figure_report).get("mode") == "source_candidates"
        except Exception:
            pass
    skip_reason_path = project / "03_figure_redraw" / "skip_reason.md"
    figures_skipped_with_reason = skip_reason_path.exists() and bool(read_text(skip_reason_path).strip())

    heading_jumps = []
    previous = 0
    for heading in headings:
        if previous and heading["level"] > previous + 1:
            heading_jumps.append({"from": previous, "to": heading["level"], "title": heading["title"]})
        previous = heading["level"]
    references_section = detect_references_section(text)

    citations_path = project / "04_first_draft" / "citations.json"
    citations_payload = None
    if citations_path.exists():
        try:
            citations_payload = read_json(citations_path)
        except Exception:
            pass
    matrix_rows = matrix_rows_by_id(project / "01_matrix_outline" / "literature_matrix.json")
    matrix_ids = set(matrix_rows)
    evidence_owners = matrix_evidence_owners(matrix_rows)
    citation_ref_numbers: list[int] = []
    citation_paper_ids: list[str] = []
    declared_incomplete_reference_metadata = []
    if isinstance(citations_payload, dict):
        entries = citations_payload.get("reference_list") or []
        for entry in entries if isinstance(entries, list) else []:
            if not isinstance(entry, dict):
                continue
            if str(entry.get("ref_num") or "").isdigit():
                citation_ref_numbers.append(int(entry["ref_num"]))
            if entry.get("paper_id"):
                citation_paper_ids.append(str(entry["paper_id"]))
        declared_incomplete_reference_metadata = (
            citations_payload.get("incomplete_reference_metadata") or []
        )
    unknown_cited_papers = sorted(set(citation_paper_ids) - matrix_ids) if matrix_ids else []
    actual_missing_metadata = actual_incomplete_references(
        project.parents[1], citation_paper_ids, matrix_rows
    )
    incomplete_reference_metadata = actual_missing_metadata or declared_incomplete_reference_metadata

    references_match, _ = references_tail(text)
    manuscript_body = text[: references_match.start()] if references_match else text
    word_like_count = len(re.findall(r"\b[A-Za-z][A-Za-z'-]*\b", manuscript_body))
    target_words, blueprint_issues = blueprint_target(project / "01_matrix_outline" / "section_blueprint.json")
    word_target_ratio = round(word_like_count / target_words, 4) if target_words else None
    paragraph_stats = cited_paragraph_stats(text)
    duplicate_paragraphs = duplicated_long_paragraphs(text)
    semantic_status, semantic_blockers = semantic_audit_status(
        project / "05_final_audit" / "semantic_audit.json",
        required=phase == "release",
        known_paper_ids=matrix_ids,
        evidence_owners=evidence_owners,
        paragraphs_by_id=drafted_paragraphs(
            project / "02_section_drafting" / "section_drafts.json"
        ),
    )

    issues: list[str] = []
    blocking: list[str] = []

    def add(issue: str, block: bool = True) -> None:
        if issue not in issues:
            issues.append(issue)
        if block and issue not in blocking:
            blocking.append(issue)

    if not draft.exists():
        add("missing_draft")
    if placeholder_hits:
        add("placeholder_or_verification_notes_present")
    if PARAGRAPH_MARKER_RE.search(text):
        add("editor_paragraph_markers_present")
    if duplicate_paragraphs:
        add("duplicated_long_paragraphs_or_template_padding")
    if STABLE_CITATION_RE.search(text):
        add("unresolved_stable_citation_tokens")
    if PAPER_ID_LEAK_RE.search(text):
        add("internal_paper_ids_leaked_into_manuscript")
    if duplicate_headings:
        add("duplicate_headings", block=False)
    if heading_jumps:
        add("heading_level_jumps", block=False)
    if not ABSTRACT_HEADING_RE.search(text):
        add("missing_abstract")
    if not KEYWORDS_RE.search(text):
        add("missing_keywords")
    if not INTRODUCTION_HEADING_RE.search(text):
        add("missing_introduction")
    if not CONCLUSION_HEADING_RE.search(text):
        add("missing_conclusion_or_outlook")
    if not called_refs:
        add("draft_has_no_citation_callouts")
    if not references_section["present"]:
        add("missing_references_section")
    elif references_section["item_count"] == 0:
        add("empty_references_section")
    if missing_listed_refs:
        add("reference_callouts_missing_from_reference_list")
    if uncalled_listed_refs:
        add("reference_list_contains_uncalled_items")
    if duplicate_reference_numbers:
        add("duplicate_reference_numbers")
    if listed_sequence and not reference_numbering_contiguous:
        add("reference_numbering_not_contiguous")
    if citation_ref_numbers and citation_ref_numbers != listed_sequence:
        add("citations_json_reference_number_mismatch")
    if unknown_cited_papers:
        add("citations_reference_unknown_papers")
    if incomplete_reference_metadata:
        add("incomplete_reference_metadata")
    if abstract_image_paths:
        add("images_embedded_in_abstract")
    if broken_images:
        add("broken_markdown_image_paths")
    if source_placeholder_mode:
        add("unverified_source_figures_need_preparation")
    if not image_paths and not figures_skipped_with_reason:
        add("draft_has_no_figures", block=False)
    if target_words and word_target_ratio is not None and word_target_ratio < 0.8:
        add("manuscript_below_80_percent_of_blueprint_target", block=False)
    for issue in blueprint_issues:
        add(issue.replace(" ", "_"), block=False)
    if paragraph_stats["cited_paragraph_count"] >= 8 and paragraph_stats["multi_source_ratio"] < 0.2:
        add("paper_listing_pattern_too_few_multi_source_paragraphs", block=False)
    for semantic_issue in semantic_blockers:
        add("semantic_audit:" + semantic_issue)
    if phase == "release":
        for upstream_issue in upstream_release_issues(project):
            add(upstream_issue)

    return {
        "project_dir": str(project),
        "phase": phase,
        "draft_path": str(draft),
        "target_draft": target,
        "draft_exists": draft.exists(),
        "word_like_count": word_like_count,
        "blueprint_target_words": target_words,
        "word_target_ratio": word_target_ratio,
        "heading_count": len(headings),
        "headings": headings,
        "duplicate_headings": duplicate_headings,
        "heading_jumps": heading_jumps,
        "placeholder_hits": placeholder_hits,
        "reference_callouts": called_refs,
        "reference_list_items": listed_refs,
        "reference_list_sequence": listed_sequence,
        "missing_listed_refs": missing_listed_refs,
        "uncalled_listed_refs": uncalled_listed_refs,
        "duplicate_reference_numbers": duplicate_reference_numbers,
        "reference_numbering_contiguous": reference_numbering_contiguous,
        "citations_json_reference_numbers": citation_ref_numbers,
        "image_paths": image_paths,
        "abstract_image_paths": abstract_image_paths,
        "broken_images": broken_images,
        "source_placeholder_mode": source_placeholder_mode,
        "references_section": references_section,
        "figures_skipped_with_reason": figures_skipped_with_reason,
        "citations_payload_present": isinstance(citations_payload, dict),
        "unknown_cited_papers": unknown_cited_papers,
        "incomplete_reference_metadata": incomplete_reference_metadata,
        "paragraph_synthesis": paragraph_stats,
        "duplicate_long_paragraphs": duplicate_paragraphs,
        "semantic_audit": semantic_status,
        "issues": issues,
        "blocking_issues": blocking,
        "warnings": [issue for issue in issues if issue not in blocking],
    }


def write_reports(out_dir: Path, scan: dict[str, Any]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "format_scan.json").write_text(
        json.dumps(scan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    lines = [
        "# Format and Release Scan",
        "",
        f"- Phase: {scan['phase']}",
        f"- Draft: {scan['target_draft']}",
        f"- Word count: {scan['word_like_count']}",
        f"- Blueprint target: {scan['blueprint_target_words']}",
        f"- Target ratio: {scan['word_target_ratio']}",
        f"- References: {scan['reference_list_items']}",
        f"- Citation callouts: {scan['reference_callouts']}",
        f"- Multi-source paragraph ratio: {scan['paragraph_synthesis']['multi_source_ratio']}",
        f"- Issues: {', '.join(scan['issues']) if scan['issues'] else 'none'}",
        f"- Blocking issues: {', '.join(scan['blocking_issues']) if scan['blocking_issues'] else 'none'}",
        f"- Warnings: {', '.join(scan['warnings']) if scan['warnings'] else 'none'}",
    ]
    (out_dir / "format_scan.md").write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run deterministic review manuscript audit.")
    parser.add_argument("--review-root", default=str(Path(__file__).resolve().parents[3]))
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--phase", choices=("preflight", "release"), default="release")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    project = Path(args.review_root).resolve() / "review-projects" / args.project_id
    scan = scan_draft(project, args.phase)
    audit_dir = project / "05_final_audit"
    write_reports(audit_dir, scan)
    if args.phase == "preflight":
        (audit_dir / "semantic_audit_queue.json").write_text(
            json.dumps(semantic_queue(project), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    print(f"Wrote {args.phase} audit to {project / '05_final_audit'}")
    if scan["blocking_issues"]:
        print("BLOCKING ISSUES:")
        for issue in scan["blocking_issues"]:
            print(f"- {issue}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
