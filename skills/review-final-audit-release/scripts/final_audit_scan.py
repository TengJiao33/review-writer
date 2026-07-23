#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "_shared"))
from review_integrity import attach_input_artifacts, input_artifact_issues  # noqa: E402


PLACEHOLDER_RE = re.compile(
    r"\b(TODO|TBD|citation needed|verification needed|check this|fixme)\b",
    re.I,
)
REF_CALLOUT_RE = re.compile(r"\[(\d+(?:\s*[-,]\s*\d+)*)\]")
REF_ITEM_RE = re.compile(r"^\s*(?:\[(\d+)\]|(\d+)[.)])\s+", re.M)
IMAGE_RE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")
TABLE_SEPARATOR_RE = re.compile(
    r"^\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?\s*$",
    re.M,
)
# Mechanical validation only asks whether prose names the asset.  Requiring one
# of a small verb list turns natural writing into a password exercise; whether
# the callout advances the argument remains an editorial reading judgment.
TABLE_REFERENCE_RE = re.compile(r"\btable\s+(\d+)\b", re.I)
FIGURE_REFERENCE_RE = re.compile(r"\b(?:figure|fig\.)\s+(\d+)\b", re.I)
MOJIBAKE_RE = re.compile(r"\ufffd|鍙傝€|鈥\S{0,3}|鈭\??")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.M)
REFERENCES_HEADING_RE = re.compile(
    r"^\s*#{1,6}\s*(references|reference list|bibliography|cited literature|参考文献)\s*$",
    re.I | re.M,
)
NONCANONICAL_BACKMATTER_RE = re.compile(
    r"^\s*\*\*(?:references?|reference list|bibliography|figure descriptions?)\*\*\s*:?.*$",
    re.I | re.M,
)
ABSTRACT_HEADING_RE = re.compile(r"^\s*#{1,6}\s*abstract\s*$", re.I | re.M)
KEYWORDS_RE = re.compile(r"(?:^\s*#{1,6}\s*keywords\s*$|^\s*\*\*keywords:?\*\*\s*:?)", re.I | re.M)
INTRODUCTION_HEADING_RE = re.compile(r"^\s*#{1,6}\s*(?:\d+[.)]?\s*)?introduction\s*$", re.I | re.M)
CONCLUSION_HEADING_RE = re.compile(r"^\s*#{1,6}\s*.*(?:conclusion|outlook).*?$", re.I | re.M)
STABLE_CITATION_RE = re.compile(r"\[((?:@P\d{3})(?:\s*[;,]\s*@P\d{3})*)\]")
PAPER_ID_LEAK_RE = re.compile(r"(?<![@A-Za-z0-9])P\d{3}(?![A-Za-z0-9])")
PARAGRAPH_MARKER_RE = re.compile(r"<!--\s*paragraph_id\s*:", re.I)
RAW_LATEX_COMMAND_RE = re.compile(r"\\(?:mathrm|mathbf|mathsf|ce)\b|_\s*\{|\^\s*\{")
AUDIT_PLACEHOLDER_RE = re.compile(
    r"representative claim|claim from .{0,80} section|reviewed against evidence",
    re.I,
)
DOI_RE = re.compile(r"10\.\d{4,9}/[^\s<>\"']+", re.I)
AUDIT_RATIONALE_STOPWORDS = {
    "against",
    "checked",
    "claim",
    "claims",
    "evidence",
    "paper",
    "papers",
    "source",
    "sources",
    "support",
    "supported",
    "supports",
    "verified",
}

# One low-density product floor prevents a comprehensive review from shrinking
# into a short note after the detailed stage quotas have been removed.  These
# checks apply only at release and do not prescribe section structure or asset
# counts above the minimum viable product.
COMPREHENSIVE_DELIVERY_FLOOR = {
    "word_like_count": 8000,
    "reference_count": 25,
    "table_count": 2,
    "source_figure_count": 3,
}


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def declared_review_profile(project: Path) -> str:
    path = project / "00_discovery" / "topic_contract.json"
    try:
        payload = read_json(path)
    except Exception:
        return ""
    return str(payload.get("review_profile") or "").strip().lower() if isinstance(payload, dict) else ""


def resolved_portfolio_editorial_issues(project: Path) -> list[str]:
    path = project / "01_matrix_outline" / "portfolio_editorial_review.json"
    if not path.exists():
        return ["missing_portfolio_editorial_review"]
    try:
        payload = read_json(path)
    except Exception:
        return ["invalid_portfolio_editorial_review"]
    if not isinstance(payload, dict):
        return ["invalid_portfolio_editorial_review"]
    issues = []
    decisions = payload.get("decisions")
    if not isinstance(decisions, list):
        return ["invalid_portfolio_editorial_review"]
    for row in decisions:
        if not isinstance(row, dict):
            issues.append("invalid_portfolio_editorial_decision")
            continue
        decision_id = str(row.get("decision_id") or "unknown")
        if row.get("status") != "resolved":
            issues.append(f"portfolio_editorial_decision_pending:{decision_id}")
        decision = str(row.get("decision") or "")
        allowed = {str(item) for item in row.get("available_responses") or []}
        if not decision or (allowed and decision not in allowed):
            issues.append(f"portfolio_editorial_decision_invalid:{decision_id}")
        if not str(row.get("rationale") or "").strip():
            issues.append(f"portfolio_editorial_rationale_missing:{decision_id}")
    if payload.get("status") != "resolved" or payload.get("pending_decision_ids"):
        issues.append("portfolio_editorial_review_not_resolved")
    return issues


def resolved_visual_plan_issues(project: Path, manuscript: str) -> list[str]:
    path = project / "02_section_drafting" / "review_visual_plan.json"
    if not path.exists():
        return ["missing_review_visual_plan"]
    try:
        payload = read_json(path)
    except Exception:
        return ["invalid_review_visual_plan"]
    rows = payload.get("visuals") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        return ["invalid_review_visual_plan"]
    issues = []
    allowed = {"selected", "adapted", "combined", "skipped"}
    for row in rows:
        if not isinstance(row, dict):
            issues.append("invalid_review_visual_decision")
            continue
        visual_id = str(row.get("visual_id") or "unknown")
        status = str(row.get("status") or "")
        if status not in allowed:
            issues.append(f"review_visual_decision_pending:{visual_id}")
            continue
        if not str(row.get("decision_rationale") or "").strip():
            issues.append(f"review_visual_rationale_missing:{visual_id}")
        if status in {"selected", "adapted", "combined"} and row.get("kind") == "markdown_comparison_table":
            manifest_path = project / "02_section_drafting" / "method_comparison_table_manifest.json"
            try:
                manifest = read_json(manifest_path) if manifest_path.exists() else None
            except Exception:
                manifest = None
            if not isinstance(manifest, dict) or manifest.get("status") != "verified":
                issues.append(f"comparison_table_not_traceable:{visual_id}")
            if not re.search(r"(?m)^\s*\|.+\|\s*$", manuscript):
                issues.append(f"selected_comparison_table_missing_from_manuscript:{visual_id}")
    if isinstance(payload, dict) and (payload.get("status") != "resolved" or payload.get("pending_visual_ids")):
        issues.append("review_visual_plan_not_resolved")
    return issues


def reader_utility_review_issues(project: Path) -> list[str]:
    path = project / "05_final_audit" / "reader_utility_review.json"
    if not path.exists():
        return ["missing_reader_utility_review"]
    try:
        payload = read_json(path)
    except Exception:
        return ["invalid_reader_utility_review"]
    if not isinstance(payload, dict):
        return ["invalid_reader_utility_review"]
    issues = []
    allowed = {"revise", "accept_as_is", "narrow_scope", "not_applicable"}
    questions = payload.get("questions")
    if not isinstance(questions, list) or not questions:
        return ["invalid_reader_utility_review"]
    for row in questions:
        if not isinstance(row, dict):
            issues.append("invalid_reader_utility_question")
            continue
        question_id = str(row.get("question_id") or "unknown")
        if not str(row.get("finding") or "").strip():
            issues.append(f"reader_utility_finding_missing:{question_id}")
        decision = str(row.get("decision") or "")
        if decision not in allowed:
            issues.append(f"reader_utility_decision_pending:{question_id}")
        if not str(row.get("rationale") or "").strip():
            issues.append(f"reader_utility_rationale_missing:{question_id}")
        actions = row.get("revision_actions")
        if decision == "revise":
            if not isinstance(actions, list) or not actions:
                issues.append(f"reader_utility_revision_action_missing:{question_id}")
            else:
                for index, action in enumerate(actions, start=1):
                    if not isinstance(action, dict) or action.get("status") not in {
                        "completed",
                        "accepted_with_reason",
                        "not_applicable",
                    }:
                        issues.append(f"reader_utility_revision_action_open:{question_id}:{index}")
    if payload.get("status") != "completed" or payload.get("pending_question_ids"):
        issues.append("reader_utility_review_not_completed")
    if not str(payload.get("overall_decision") or "").strip():
        issues.append("reader_utility_overall_decision_missing")
    if not str(payload.get("summary") or "").strip():
        issues.append("reader_utility_summary_missing")
    return issues


def referenced_artifact_numbers(pattern: re.Pattern[str], text: str) -> list[int]:
    numbers: set[int] = set()
    for match in pattern.finditer(text):
        for group in match.groups():
            if group and group.isdigit():
                numbers.add(int(group))
    return sorted(numbers)


def figure_inventory_consistency_issues(project: Path) -> list[str]:
    """Cross-check deterministic inventory counts against editorial candidate claims."""
    inventory_path = project / "02_section_drafting" / "paper_figure_inventory.json"
    candidates_path = project / "02_section_drafting" / "paper_figure_candidates.json"
    try:
        inventory = read_json(inventory_path)
    except Exception:
        return ["invalid_paper_figure_inventory"]
    if not isinstance(inventory, dict):
        return ["invalid_paper_figure_inventory"]
    papers = inventory.get("papers")
    if not isinstance(papers, list):
        return ["invalid_paper_figure_inventory"]
    actual_count = sum(
        int(row.get("candidate_count") or 0)
        for row in papers
        if isinstance(row, dict)
    )
    issues: list[str] = []
    declared_inventory_count = inventory.get("candidate_count")
    if isinstance(declared_inventory_count, int) and declared_inventory_count != actual_count:
        issues.append("paper_figure_inventory_count_mismatch")

    try:
        candidates = read_json(candidates_path)
    except Exception:
        return issues + ["invalid_paper_figure_candidates"]
    if isinstance(candidates, list):
        reviewed_rows = candidates
        claimed_count = None
    elif isinstance(candidates, dict):
        reviewed_rows = candidates.get("candidates")
        claimed_count = candidates.get("inventory_candidate_count")
        if claimed_count is None:
            claimed_count = candidates.get("total_inventory_figures")
    else:
        return issues + ["invalid_paper_figure_candidates"]
    if not isinstance(reviewed_rows, list):
        issues.append("invalid_paper_figure_candidates")
        reviewed_rows = []
    if isinstance(claimed_count, int) and claimed_count != actual_count:
        issues.append("paper_figure_candidate_count_mismatch")
    # The inventory is a discovery aid, not a queue that must be dispositioned
    # in full.  Rights and source checks remain mandatory for figures that are
    # actually selected for use.
    return list(dict.fromkeys(issues))


def upstream_release_issues(project: Path) -> list[str]:
    contract = read_json(project / "00_discovery" / "topic_contract.json") if (
        project / "00_discovery" / "topic_contract.json"
    ).exists() else {}
    require_receipts = (
        isinstance(contract, dict)
        and int(contract.get("workflow_contract_version") or 0) >= 2
    )
    reports = {
        "screening": project / "00_discovery" / "screening_validation.json",
        "matrix": project / "01_matrix_outline" / "matrix_validation.json",
        "blueprint": project / "01_matrix_outline" / "blueprint_validation.json",
        "section_draft": project / "02_section_drafting" / "section_draft_validation.json",
        "merge": project / "04_first_draft" / "merge_validation.json",
    }
    required_inputs = {
        "screening": [
            project / "00_discovery" / "topic_contract.json",
            project / "00_discovery" / "selected_discovery_results.json",
        ],
        "matrix": [project / "01_matrix_outline" / "literature_matrix.json"],
        "blueprint": [
            project / "01_matrix_outline" / "section_blueprint.json",
            project / "01_matrix_outline" / "literature_matrix.json",
        ],
        "section_draft": [
            project / "02_section_drafting" / "section_drafts.json",
            project / "02_section_drafting" / "figure_candidates.json",
            project / "01_matrix_outline" / "section_blueprint.json",
            project / "01_matrix_outline" / "literature_matrix.json",
        ],
        "merge": [
            project / "02_section_drafting" / "section_drafts.json",
            project / "01_matrix_outline" / "literature_matrix.json",
        ],
    }
    manuscript = project / "02_section_drafting" / "manuscript.md"
    if manuscript.exists():
        required_inputs["section_draft"].append(manuscript)
        required_inputs["merge"].append(manuscript)
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
        for receipt_issue in input_artifact_issues(
            report, project, required_inputs[name], require_receipts=require_receipts
        ):
            issues.append(f"upstream_validation_{name}:{receipt_issue}")

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
    original_manifest_path = project / "03_figure_redraw" / "review_visual_manifest.json"
    original_visuals: list[dict[str, Any]] = []
    if original_manifest_path.exists():
        try:
            original_manifest = read_json(original_manifest_path)
            raw_visuals = original_manifest.get("visuals") if isinstance(original_manifest, dict) else None
            if isinstance(raw_visuals, list):
                original_visuals = [item for item in raw_visuals if isinstance(item, dict)]
            else:
                issues.append("invalid_review_visual_manifest")
        except Exception:
            issues.append("invalid_review_visual_manifest")

    def original_asset_exists(item: dict[str, Any]) -> bool:
        raw = item.get("original_image")
        if not raw:
            return False
        path = Path(str(raw))
        return path.exists() or (project / path).exists()

    usable_originals = [
        item
        for item in original_visuals
        if item.get("status") == "original_verified"
        and item.get("verification_status") == "passed"
        and original_asset_exists(item)
    ]
    selected_originals = [item for item in original_visuals if item.get("status") not in {"skipped", "suggested"}]
    if selected_originals and not usable_originals:
        issues.append("original_visual_preparation_incomplete")

    selected_figures = [
        item
        for item in figures or []
        if isinstance(item, dict)
        and (
            item.get("manuscript_selected") is True
            or str(item.get("editorial_status") or "").lower() in {"selected", "adapted", "combined"}
        )
    ]
    if selected_figures and not skipped:
        manifest_path = project / "03_figure_redraw" / "redrawn_figure_manifest.json"
        try:
            manifest = read_json(manifest_path)
        except Exception:
            manifest = None
        prepared = manifest.get("figures") if isinstance(manifest, dict) else None
        if not isinstance(prepared, list):
            prepared = manifest.get("redrawn_figures") if isinstance(manifest, dict) else None
        usable_source = False
        if isinstance(prepared, list):
            for item in prepared:
                if not isinstance(item, dict):
                    continue
                accepted = item.get("status") == "redrawn" or (
                    item.get("status") == "source_verified"
                    and item.get("verification_status") == "passed"
                )
                rights = item.get("reuse_rights")
                rights_verified = bool(
                    isinstance(rights, dict)
                    and rights.get("status") == "verified"
                    and str(rights.get("basis") or "").strip()
                    and str(rights.get("license_url_or_permission_record") or "").strip()
                    and str(rights.get("source_locator") or "").strip()
                    and rights.get("third_party_material_checked") is True
                    and str(rights.get("adaptation") or "").strip()
                    and str(rights.get("attribution_text") or "").strip()
                )
                if accepted and not rights_verified:
                    issues.append(
                        "figure_reuse_rights_unverified:"
                        + str(item.get("figure_id") or item.get("source_label") or "unknown")
                    )
                if (
                    accepted
                    and rights_verified
                    and str(item.get("reader_job") or "").strip()
                    and str(item.get("placement_rationale") or "").strip()
                    and str(item.get("reuse_basis") or "").strip()
                ):
                    usable_source = True
        if not usable_source and not usable_originals:
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


def manuscript_body(text: str) -> tuple[str, list[dict[str, Any]]]:
    """Return article prose only, stopping before canonical or disguised back matter."""
    canonical = REFERENCES_HEADING_RE.search(text or "")
    pseudo = list(NONCANONICAL_BACKMATTER_RE.finditer(text or ""))
    boundaries = [match.start() for match in pseudo]
    if canonical:
        boundaries.append(canonical.start())
    end = min(boundaries) if boundaries else len(text or "")
    findings = [
        {
            "line": text[: match.start()].count("\n") + 1,
            "text": match.group(0).strip(),
        }
        for match in pseudo
    ]
    return (text or "")[:end], findings


def reference_numbers(text: str) -> list[int]:
    _, tail = references_tail(text)
    result = []
    for match in REF_ITEM_RE.finditer(tail):
        result.append(int(match.group(1) or match.group(2)))
    return result


def verified_source_figure_usage(
    project: Path,
    manuscript_image_paths: list[str],
    cited_paper_ids: set[str],
    manuscript_text: str = "",
) -> tuple[int, list[str]]:
    """Count only source figures that are verified, licensed, inserted, and present."""
    report_path = next(
        (
            path
            for path in (
                project / "05_final_audit" / "figure_insertion_report.json",
                project / "04_first_draft" / "figure_insertion_report.json",
            )
            if path.exists()
        ),
        None,
    )
    manifest_path = project / "03_figure_redraw" / "redrawn_figure_manifest.json"
    if report_path is None or not manifest_path.exists():
        return 0, []
    try:
        report = read_json(report_path)
        manifest = read_json(manifest_path)
    except Exception:
        return 0, ["invalid_source_figure_provenance"]
    inserted = report.get("inserted") if isinstance(report, dict) else None
    figures = manifest.get("figures") if isinstance(manifest, dict) else None
    if not isinstance(inserted, list) or not isinstance(figures, list):
        return 0, ["invalid_source_figure_provenance"]
    by_id = {
        str(row.get("figure_id")): row
        for row in figures
        if isinstance(row, dict) and row.get("figure_id")
    }
    comprehensive = declared_review_profile(project) == "comprehensive"
    inventory_payload = read_json(
        project / "02_section_drafting" / "paper_figure_inventory.json"
    ) if (project / "02_section_drafting" / "paper_figure_inventory.json").exists() else {}
    inventory_rows = inventory_payload.get("candidates") if isinstance(inventory_payload, dict) else []
    inventory_by_id = {
        str(item.get("inventory_candidate_id")): item
        for item in inventory_rows or []
        if isinstance(item, dict) and item.get("inventory_candidate_id")
    }

    def resolve_asset(raw: Any, stage: str) -> Path:
        path = Path(str(raw or ""))
        if path.is_absolute():
            return path.resolve()
        return (project / stage / path).resolve()
    count = 0
    issues: list[str] = []
    counted_ids: set[str] = set()
    counted_paths: set[str] = set()
    counted_reader_jobs: set[str] = set()
    for row in inserted:
        if not isinstance(row, dict) or row.get("mode") != "source_verified":
            continue
        figure_id = str(row.get("figure_id") or "")
        source = by_id.get(figure_id)
        if not isinstance(source, dict):
            issues.append(f"inserted_source_figure_missing_manifest:{figure_id or 'unknown'}")
            continue
        rights = source.get("reuse_rights") if isinstance(source.get("reuse_rights"), dict) else {}
        inserted_path = str(row.get("inserted_path") or "")
        required = (
            source.get("status") == "source_verified"
            and source.get("verification_status") == "passed"
            and bool(source.get("paper_id"))
            and str(source.get("paper_id")) in cited_paper_ids
            and bool(source.get("source_label"))
            and rights.get("status") == "verified"
            and bool(str(rights.get("license_url_or_permission_record") or "").strip())
            and bool(str(rights.get("basis") or "").strip())
            and bool(str(rights.get("source_locator") or "").strip())
            and rights.get("third_party_material_checked") is True
            and rights.get("adaptation") == "unchanged"
            and bool(str(rights.get("attribution_text") or "").strip())
            and inserted_path in manuscript_image_paths
        )
        if comprehensive:
            candidate_id = str(source.get("inventory_candidate_id") or "")
            candidate = inventory_by_id.get(candidate_id)
            strict_issues: list[str] = []
            source_type = str(source.get("source_type") or "").strip().lower()
            source_label = str(source.get("source_label") or "").strip()
            source_page_index = source.get("source_page_index")
            source_bbox = source.get("source_bbox")
            if source_type not in {"image", "chart"}:
                strict_issues.append("source is not a non-table image/chart candidate")
            if not re.match(r"^(?:fig(?:ure)?|scheme)\s*[A-Za-z0-9]", source_label, re.I):
                strict_issues.append("source label is generic or not a figure/scheme label")
            if not isinstance(source_page_index, int) or source_page_index < 0:
                strict_issues.append("source page index is invalid")
            if not (
                isinstance(source_bbox, list)
                and len(source_bbox) == 4
                and all(isinstance(value, (int, float)) for value in source_bbox)
            ):
                strict_issues.append("source bounding box is invalid")
            if not isinstance(candidate, dict):
                strict_issues.append("unknown inventory candidate")
            else:
                for key in (
                    "paper_id",
                    "source_label",
                    "source_caption_text",
                    "source_pdf_sha256",
                    "source_page_index",
                    "source_bbox",
                ):
                    if source.get(key) != candidate.get(key):
                        strict_issues.append(f"{key} differs from inventory")
            source_pdf = Path(str(source.get("source_pdf") or ""))
            if not source_pdf.is_absolute():
                source_pdf = project.parents[1] / source_pdf
            if not source_pdf.is_file() or file_sha256(source_pdf) != str(
                source.get("source_pdf_sha256") or ""
            ):
                strict_issues.append("source PDF hash is missing or stale")
            accepted_path = Path(str(source.get("verified_image") or source.get("source_image") or ""))
            if not accepted_path.is_absolute():
                accepted_path = project.parents[1] / accepted_path
            accepted_hash = file_sha256(accepted_path)
            inserted_asset = resolve_asset(inserted_path, "05_final_audit")
            inserted_hash = file_sha256(inserted_asset)
            if not accepted_hash or accepted_hash != str(source.get("accepted_image_sha256") or ""):
                strict_issues.append("accepted source image hash is missing or stale")
            if not inserted_hash or inserted_hash != accepted_hash:
                strict_issues.append("inserted image is not the accepted source image")
            if str(source.get("source_completeness") or "").lower() != "complete":
                strict_issues.append("source figure is not recorded as complete")
            if str(source.get("source_page_review_status") or "").lower() not in {"passed", "verified"}:
                strict_issues.append("source page review did not pass")
            reader_job = re.sub(r"\s+", " ", str(source.get("reader_job") or "")).strip().casefold()
            if not reader_job:
                strict_issues.append("reader job is missing")
            elif reader_job in counted_reader_jobs:
                strict_issues.append("reader job duplicates another source figure")
            if not str(source.get("placement_rationale") or "").strip():
                strict_issues.append("placement rationale is missing")
            callout = str(source.get("manuscript_callout") or "").strip()
            if not callout or callout not in manuscript_text:
                strict_issues.append("authored manuscript callout is missing")
            if strict_issues:
                required = False
                issues.append(
                    f"inserted_source_figure_inventory_mismatch:{figure_id or 'unknown'}:"
                    + "; ".join(strict_issues)
                )
            elif reader_job:
                counted_reader_jobs.add(reader_job)
        if required and figure_id not in counted_ids and inserted_path not in counted_paths:
            count += 1
            counted_ids.add(figure_id)
            counted_paths.add(inserted_path)
        elif required:
            issues.append(f"duplicate_inserted_source_figure:{figure_id or 'unknown'}")
        else:
            issues.append(f"inserted_source_figure_provenance_incomplete:{figure_id or 'unknown'}")
    return count, list(dict.fromkeys(issues))


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


def matrix_evidence_records(rows: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    for paper_id, row in rows.items():
        for anchor in row.get("evidence_anchors") or []:
            if not isinstance(anchor, dict) or not anchor.get("evidence_id"):
                continue
            evidence_id = str(anchor["evidence_id"])
            records[evidence_id] = {"paper_id": paper_id, **anchor}
    return records


def source_text_for_audit(path: Path) -> str:
    if path.suffix.lower() == ".pdf":
        try:
            from pypdf import PdfReader

            return "\n".join(page.extract_text() or "" for page in PdfReader(str(path)).pages)
        except Exception:
            return ""
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def audit_content_words(value: Any) -> set[str]:
    return {
        word.lower()
        for word in re.findall(r"\b[A-Za-z][A-Za-z'-]*\b|\b\d+(?:\.\d+)?\b", str(value or ""))
        if len(word) >= 3 and word.lower() not in AUDIT_RATIONALE_STOPWORDS
    }


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
        r"\b(prove|confirm|active species|operative pathway|unified mechanis)\w*\b",
        re.I,
    ),
    "priority_or_absence": re.compile(
        r"\b(first (?:report|example|demonstration|method|synthesis|reaction|application)|"
        r"only (?:known|reported|available|method|example|route|system)|"
        r"unprecedented|unique|no (?:general|reported|known)|"
        r"(?:largely|rarely|not yet) (?:reported|known|available))\b",
        re.I,
    ),
    "field_wide_generalization": re.compile(
        r"\b(universal|consensus|across all|all conventional|most widely|"
        r"common (?:intermediate|mechanism))\w*\b",
        re.I,
    ),
    "maturity_or_superlative": re.compile(
        r"\b(practical maturity|mature platform|single most|most powerful|remarkably broad|"
        r"state of the art|superior platform|highest (?:yield|selectivity|efficiency))\b",
        re.I,
    ),
    "operational_conditions": re.compile(
        r"\b(optimi[sz]ed conditions?|catalyst loading|electrode|electrolyte|solvent|"
        r"temperature|reaction time|troubleshoot|scale[- ]?up|gram[- ]scale)\b",
        re.I,
    ),
    "causal_explanation": re.compile(
        r"\b(due to|arises from|results from|is responsible for|controls?|enables?|"
        r"drives?|determines?)\b",
        re.I,
    ),
    "practical_or_sustainability": re.compile(
        r"\b(practical|robust|scalable|safe(?:ty)?|green(?:er)?|sustainab(?:le|ility)|"
        r"air[- ]tolerant|moisture[- ]tolerant)\b",
        re.I,
    ),
    "scope_generalization": re.compile(
        r"\b(broad scope|wide scope|broadly applicable|tolerates? a wide|"
        r"functional[- ]group tolerance|generally applicable)\b",
        re.I,
    ),
}


def claim_risk_signals(value: str) -> list[str]:
    return [name for name, pattern in CLAIM_RISK_PATTERNS.items() if pattern.search(value or "")]


def file_sha256(path: Path) -> str:
    if not path.exists() or not path.is_file():
        return ""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def paragraph_audit_span(markdown: str) -> str:
    """Return the complete prose span that must be supported for one paragraph."""
    prose_lines = []
    for line in (markdown or "").splitlines():
        stripped = line.strip()
        if stripped.startswith("|") or stripped.startswith("!["):
            continue
        prose_lines.append(line)
    prose = STABLE_CITATION_RE.sub("", " ".join(prose_lines))
    return re.sub(r"\s+", " ", prose).strip()


def semantic_queue(project: Path, limit: int | None = None) -> dict[str, Any]:
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
    ranked: list[dict[str, Any]] = []
    for paragraph in paragraphs.values():
        cited_ids = list(dict.fromkeys(paragraph["cited_paper_ids"]))
        evidence_ids = list(dict.fromkeys(paragraph["evidence_ids"]))
        markdown = paragraph["markdown"]
        risk_signals = claim_risk_signals(markdown)
        has_number = bool(re.search(r"\b\d+(?:\.\d+)?%?\b", markdown))
        text_span = paragraph_audit_span(markdown)
        if len(re.findall(r"\b[A-Za-z][A-Za-z'-]*\b", text_span)) < 8:
            continue
        score = type_weight.get(paragraph["paragraph_type"], 1)
        score += min(len(cited_ids), 3)
        score += min(len(risk_signals), 3)
        score += int(has_number)
        audit_reasons = [f"claim_risk:{signal}" for signal in risk_signals]
        if has_number:
            audit_reasons.append("numerical_claim")
        if paragraph["paragraph_type"] == "mechanism":
            audit_reasons.append("mechanism_claim")
        if not cited_ids:
            audit_reasons.append("missing_paragraph_citation")
        elif not evidence_ids:
            audit_reasons.append("missing_paragraph_evidence")
        ranked.append(
            {
                "queue_id": f"{paragraph['paragraph_id']}-a1",
                "section_id": paragraph["section_id"],
                "paragraph_id": paragraph["paragraph_id"],
                "paragraph_type": paragraph["paragraph_type"],
                "priority_score": score,
                "claim_risk_signals": risk_signals,
                "audit_reasons": audit_reasons,
                "queue_status": (
                    "missing_paragraph_citation"
                    if not cited_ids
                    else "source_check_required"
                    if evidence_ids
                    else "missing_paragraph_evidence"
                ),
                "text_span": text_span,
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
    high_risk_rows = [row for row in ranked if row["audit_reasons"]]
    critical_signals = {
        "mechanistic_certainty",
        "priority_or_absence",
        "field_wide_generalization",
        "maturity_or_superlative",
    }
    mandatory_rows = [
        row
        for row in high_risk_rows
        if critical_signals.intersection(row["claim_risk_signals"])
    ]
    selected_by_id = {row["queue_id"]: row for row in mandatory_rows}

    # Preserve diversity across risk types instead of turning every yield or
    # condition into a compulsory post-hoc checklist.
    for signal in CLAIM_RISK_PATTERNS:
        signal_rows = sorted(
            [row for row in high_risk_rows if signal in row["claim_risk_signals"]],
            key=lambda row: row["priority_score"],
            reverse=True,
        )
        for row in signal_rows[:2]:
            selected_by_id.setdefault(row["queue_id"], row)

    # Add one evidence-bearing paragraph per section. This samples ordinary
    # synthesis while keeping the audit selective.
    sections = list(dict.fromkeys(row["section_id"] for row in ranked))
    for section_id in sections:
        candidates = [
            row
            for row in ranked
            if row["section_id"] == section_id
            and row["queue_status"] == "source_check_required"
        ]
        if not candidates:
            candidates = [row for row in ranked if row["section_id"] == section_id]
        if candidates:
            sample = max(candidates, key=lambda row: row["priority_score"])
            if sample["queue_id"] not in selected_by_id:
                sample["audit_reasons"].append("section_sample")
                selected_by_id[sample["queue_id"]] = sample
    target_count = min(24, max(15, len(sections) * 2)) if ranked else 0
    for row in sorted(ranked, key=lambda item: item["priority_score"], reverse=True):
        if len(selected_by_id) >= target_count:
            break
        selected_by_id.setdefault(row["queue_id"], row)
    selected = [row for row in ranked if row["queue_id"] in selected_by_id]
    required_ids = [row["queue_id"] for row in selected]
    queue_material = [
        {
            "queue_id": row["queue_id"],
            "section_id": row["section_id"],
            "paragraph_id": row["paragraph_id"],
            "text_span": row["text_span"],
            "paragraph_cited_paper_ids": row["paragraph_cited_paper_ids"],
            "paragraph_evidence_ids": row["paragraph_evidence_ids"],
        }
        for row in selected
    ]
    queue_fingerprint = hashlib.sha256(
        json.dumps(queue_material, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    return {
        "project_id": project.name,
        "queue_version": 4,
        "coverage_mode": "risk_stratified_with_section_sample",
        "selection_rule": "critical scope and certainty claims, stratified samples of other risk types, one section sample, then highest-risk items up to a typical 15-24 passage review",
        "source_draft_sha256": file_sha256(paragraph_path),
        "queue_fingerprint": queue_fingerprint,
        "candidate_count": len(ranked),
        "selected_count": len(selected),
        "requested_limit": limit,
        "limit_policy": "requested limits are advisory; the deterministic stratified sample is preserved",
        "required_queue_ids": required_ids,
        "required_high_risk_queue_ids": [
            row["queue_id"]
            for row in high_risk_rows
            if row["queue_id"] in selected_by_id
        ],
        "ready_count": sum(item["queue_status"] == "source_check_required" for item in selected),
        "source_check_required_count": sum(
            item["queue_status"] == "source_check_required" for item in selected
        ),
        "missing_paragraph_evidence_count": sum(
            item["queue_status"] == "missing_paragraph_evidence" for item in selected
        ),
        "missing_paragraph_citation_count": sum(
            item["queue_status"] == "missing_paragraph_citation" for item in selected
        ),
        "items": selected,
    }


def unwrap(value: Any) -> Any:
    if isinstance(value, dict) and "value" in value:
        return value.get("value")
    return value


UNTRUSTED_METADATA_SOURCE_RE = re.compile(
    r"(?:infer|guess|generat|plausible|synthetic|placeholder|fabricat)", re.I
)


def reference_metadata_provenance_issues(
    review_root: Path,
    paper_ids: list[str],
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    checked_fields = ("authors", "title", "year", "journal", "doi", "volume", "pages", "article_number")
    for paper_id in paper_ids:
        path = review_root / "review-library" / "metadata" / "papers" / f"{paper_id}.metadata.json"
        try:
            payload = read_json(path) if path.exists() else {}
        except Exception:
            payload = {}
        if not isinstance(payload, dict):
            continue
        untrusted = []
        for field in checked_fields:
            record = payload.get(field)
            if not isinstance(record, dict) or not unwrap(record):
                continue
            source = str(record.get("source") or "")
            if UNTRUSTED_METADATA_SOURCE_RE.search(source):
                untrusted.append({"field": field, "source": source})
        if untrusted:
            issues.append({"paper_id": paper_id, "fields": untrusted})
    return issues


def normalize_doi(value: Any) -> str:
    doi = str(value or "").strip().lower()
    doi = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", doi)
    return doi.rstrip(".,;:)]}")


def source_dois(pdf_path: Path) -> set[str]:
    """Return DOI strings visible in the source PDF front matter or document metadata."""
    try:
        from pypdf import PdfReader

        reader = PdfReader(str(pdf_path))
        values = [page.extract_text() or "" for page in reader.pages[:2]]
        metadata = reader.metadata
        if metadata:
            values.extend(str(value or "") for value in metadata.values())
    except Exception:
        return set()
    return {
        normalized
        for match in DOI_RE.findall("\n".join(values))
        if (normalized := normalize_doi(match))
    }


def source_front_matter_text(pdf_path: Path) -> str:
    try:
        from pypdf import PdfReader

        reader = PdfReader(str(pdf_path))
        values = [page.extract_text() or "" for page in reader.pages[:2]]
        if reader.metadata:
            values.extend(str(value or "") for value in reader.metadata.values())
        return re.sub(r"\s+", " ", " ".join(values)).strip()
    except Exception:
        return ""


def bibliographic_tokens(value: Any) -> list[str]:
    return [
        token
        for token in re.findall(r"[a-z0-9]+", str(value or "").casefold())
        if len(token) >= 3 and token not in {"the", "and", "for", "with", "from", "using"}
    ]


def author_surnames(value: Any) -> list[str]:
    if isinstance(value, str):
        rows = [part.strip() for part in re.split(r";|\band\b", value) if part.strip()]
    elif isinstance(value, list):
        rows = value
    else:
        rows = []
    result: list[str] = []
    for row in rows:
        if isinstance(row, dict):
            surname = row.get("family") or row.get("last") or row.get("surname")
        else:
            text = str(row).strip()
            surname = text.split(",", 1)[0] if "," in text else (text.split()[-1] if text else "")
        normalized = "".join(bibliographic_tokens(surname))
        if normalized:
            result.append(normalized)
    return result


def reference_metadata_source_conflicts(
    review_root: Path,
    paper_ids: list[str],
    rows_by_id: dict[str, dict[str, Any]],
    *,
    strict_front_matter: bool = False,
) -> list[dict[str, Any]]:
    """Find bibliographic values that disagree with the linked source PDF."""
    conflicts: list[dict[str, Any]] = []
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
        recorded_doi = normalize_doi(unwrap(metadata.get("doi")) or row.get("doi"))
        source_paths = metadata.get("source_paths")
        raw_pdf = source_paths.get("pdf") if isinstance(source_paths, dict) else None
        if not str(raw_pdf or "").strip():
            if strict_front_matter:
                conflicts.append({"paper_id": paper_id, "issue": "source_pdf_missing"})
            continue
        pdf_path = Path(str(raw_pdf)).expanduser()
        if not pdf_path.is_absolute():
            pdf_path = review_root / pdf_path
        if not pdf_path.exists():
            if strict_front_matter:
                conflicts.append({"paper_id": paper_id, "issue": "source_pdf_missing"})
            continue
        visible_dois = source_dois(pdf_path)
        if recorded_doi and visible_dois and recorded_doi not in visible_dois:
            conflicts.append(
                {
                    "paper_id": paper_id,
                    "recorded_doi": recorded_doi,
                    "source_dois": sorted(visible_dois),
                    "source_pdf": str(pdf_path),
                }
            )
        if not strict_front_matter:
            continue
        front = source_front_matter_text(pdf_path)
        normalized_front = " ".join(bibliographic_tokens(front))
        if not normalized_front:
            conflicts.append(
                {"paper_id": paper_id, "issue": "source_front_matter_unreadable", "source_pdf": str(pdf_path)}
            )
            continue
        recorded_title = unwrap(metadata.get("title")) or row.get("title")
        title_tokens = bibliographic_tokens(recorded_title)
        title_hits = sum(token in normalized_front for token in title_tokens)
        if title_tokens and title_hits / len(title_tokens) < 0.75:
            conflicts.append(
                {
                    "paper_id": paper_id,
                    "issue": "title_not_supported_by_source_front_matter",
                    "recorded_title": recorded_title,
                    "source_pdf": str(pdf_path),
                }
            )
        surnames = author_surnames(unwrap(metadata.get("authors")) or row.get("authors"))
        checked_surnames = surnames[: min(4, len(surnames))]
        surname_hits = sum(surname in normalized_front for surname in checked_surnames)
        if checked_surnames and (
            checked_surnames[0] not in normalized_front
            or surname_hits < max(1, (len(checked_surnames) + 1) // 2)
        ):
            conflicts.append(
                {
                    "paper_id": paper_id,
                    "issue": "authors_not_supported_by_source_front_matter",
                    "recorded_surnames": checked_surnames,
                    "source_pdf": str(pdf_path),
                }
            )
        year = str(unwrap(metadata.get("year")) or row.get("year") or "").strip()
        if year and year not in front:
            conflicts.append(
                {
                    "paper_id": paper_id,
                    "issue": "year_not_supported_by_source_front_matter",
                    "recorded_year": year,
                    "source_pdf": str(pdf_path),
                }
            )
        journal_record = metadata.get("journal")
        journal = unwrap(journal_record) or row.get("journal")
        journal_tokens = bibliographic_tokens(journal)
        journal_verified_elsewhere = bool(
            isinstance(journal_record, dict)
            and journal_record.get("human_checked") is True
            and "official" in str(journal_record.get("source") or "").casefold()
        )
        visible_tokens = bibliographic_tokens(front)
        journal_hits = sum(
            any(
                visible == token or visible.startswith(token[:4]) or token.startswith(visible[:4])
                for visible in visible_tokens
                if len(visible) >= 4
            )
            for token in journal_tokens
        )
        if journal_tokens and not journal_verified_elsewhere and journal_hits < max(
            1, (len(journal_tokens) + 1) // 2
        ):
            conflicts.append(
                {
                    "paper_id": paper_id,
                    "issue": "journal_not_supported_by_source_front_matter",
                    "recorded_journal": journal,
                    "source_pdf": str(pdf_path),
                }
            )
        volume_record = metadata.get("volume")
        volume = str(unwrap(volume_record) or row.get("volume") or "").strip()
        locator_record = metadata.get("pages") or metadata.get("article_number")
        locator = str(
            unwrap(locator_record)
            or row.get("pages")
            or row.get("article_number")
            or ""
        ).strip()
        locator_verified_elsewhere = bool(
            isinstance(locator_record, dict)
            and locator_record.get("human_checked") is True
            and "official" in str(locator_record.get("source") or "").casefold()
        )
        first_locator = re.split(r"[-–—]", locator)[0].strip()
        if (
            volume
            and first_locator
            and not locator_verified_elsewhere
            and not (
                re.search(rf"(?<!\d){re.escape(volume)}(?!\d)", front)
                and re.search(rf"(?<!\d){re.escape(first_locator)}(?!\d)", front)
            )
        ):
            conflicts.append(
                {
                    "paper_id": paper_id,
                    "issue": "volume_or_locator_not_supported_by_source_front_matter",
                    "recorded_volume": volume,
                    "recorded_locator": locator,
                    "source_pdf": str(pdf_path),
                }
            )
    return conflicts


def manuscript_reference_metadata_conflicts(
    text: str,
    review_root: Path,
    paper_ids_by_number: dict[int, str],
    rows_by_id: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Ensure the delivered reference lines still reflect current verified DOI metadata."""
    _, tail = references_tail(text)
    lines_by_number: dict[int, str] = {}
    for line in tail.splitlines():
        match = REF_ITEM_RE.match(line)
        if not match:
            continue
        number = int(match.group(1) or match.group(2))
        lines_by_number[number] = line

    conflicts: list[dict[str, Any]] = []
    for number, paper_id in sorted(paper_ids_by_number.items()):
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
        expected_doi = normalize_doi(unwrap(metadata.get("doi")) or row.get("doi"))
        if not expected_doi:
            continue
        line = lines_by_number.get(number, "")
        delivered_dois = {
            normalized
            for match in DOI_RE.findall(line)
            if (normalized := normalize_doi(match))
        }
        if delivered_dois != {expected_doi}:
            conflicts.append(
                {
                    "ref_num": number,
                    "paper_id": paper_id,
                    "expected_doi": expected_doi,
                    "delivered_dois": sorted(delivered_dois),
                }
            )
    return conflicts


def substantive_audit_comment(value: Any) -> bool:
    comment = str(value or "").strip()
    if len(comment) < 40 or re.search(
        r"(?:verified against \d+ anchors?|source verification confirms|checked against (?:the )?source)",
        comment,
        re.I,
    ):
        return False
    normalized = re.sub(r"\bP\d{3}(?:-E\d+)?\b", " ", comment, flags=re.I)
    words = [
        word.lower()
        for word in re.findall(r"\b[A-Za-z][A-Za-z'-]*\b", normalized)
        if word.lower() not in AUDIT_RATIONALE_STOPWORDS
    ]
    return len(set(words)) >= 6


QUANTITY_RE = re.compile(
    r"(?<![A-Za-z0-9])\d+(?:\.\d+)?\s*(?:%|°\s*C|K\b|h\b|hours?\b|min\b|"
    r"days?\b|mol\s*%|equiv\.?\b|mmol\b|mol\b|mA\b|A\b|V\b|nm\b|"
    r"mg\b|g\b|mL\b|µL\b|uL\b|M\b)",
    re.I,
)


def claim_quantities(value: str) -> list[str]:
    return [re.sub(r"\s+", "", item).casefold() for item in QUANTITY_RE.findall(value or "")]


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
        authors = unwrap(metadata.get("authors")) or row.get("authors")
        if not authors or authors == "Author information unavailable":
            missing.append("authors")
        if not str(unwrap(metadata.get("title")) or row.get("title") or "").strip():
            missing.append("title")
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
    body, _ = manuscript_body(text)
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
    review_root: Path,
    known_paper_ids: set[str],
    evidence_owners: dict[str, str],
    evidence_records: dict[str, dict[str, Any]],
    paragraphs_by_id: dict[str, dict[str, Any]],
    required_queue_ids: set[str],
    queue_items_by_id: dict[str, dict[str, Any]],
    manuscript_sha256: str,
    manuscript_text: str,
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
    recorded_manuscript_sha256 = str(payload.get("manuscript_sha256") or "").strip().lower()
    if not recorded_manuscript_sha256:
        blockers.append("semantic_audit.manuscript_sha256 is missing")
    elif manuscript_sha256 and recorded_manuscript_sha256 != manuscript_sha256:
        blockers.append("semantic_audit was completed against a different manuscript revision")
    checks = payload.get("checks")
    if not isinstance(checks, list) or not checks:
        blockers.append("semantic_audit.checks is missing or empty")
        checks = []
    allowed = {"supported", "needs_revision", "unsupported", "removed"}
    covered_queue_ids: set[str] = set()
    source_text_cache: dict[Path, str] = {}
    source_receipt_failures: list[dict[str, Any]] = []
    for index, check in enumerate(checks, start=1):
        if not isinstance(check, dict):
            blockers.append(f"semantic_audit check {index} is not an object")
            continue
        queue_id = str(check.get("queue_id") or "").strip()
        if queue_id:
            covered_queue_ids.add(queue_id)
            queued = queue_items_by_id.get(queue_id)
            # Authors may audit additional paragraphs beyond the generated
            # risk sample.  Only generated required items affect coverage.
            if queued is not None:
                queued_paragraph = str(queued.get("paragraph_id") or "").strip()
                queued_section = str(queued.get("section_id") or "").strip()
                if queued_paragraph and str(check.get("paragraph_id") or "").strip() != queued_paragraph:
                    blockers.append(
                        f"semantic_audit check {index} paragraph does not match queue item {queue_id}"
                    )
                if queued_section and str(check.get("section_id") or "").strip() != queued_section:
                    blockers.append(
                        f"semantic_audit check {index} section does not match queue item {queue_id}"
                    )
                queued_span = normalized_audit_text(str(queued.get("text_span") or ""))
                checked_span = normalized_audit_text(str(check.get("text_span") or ""))
                if queued_span and checked_span != queued_span:
                    blockers.append(
                        f"semantic_audit check {index} does not cover the complete queued paragraph {queue_id}"
                    )
        if required and required_queue_ids and queue_id not in required_queue_ids:
            # Extra checks remain useful working notes, but they do not expand
            # the deterministic risk sample into a blanket release queue.
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
        if verdict == "supported" and not substantive_audit_comment(check.get("comment")):
            blockers.append(
                f"semantic_audit check {index} has no claim-specific support rationale"
            )
        text_span = str(check.get("text_span") or "").strip()
        if len(text_span) < 20:
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
        normalized_checked_span = normalized_audit_text(text_span)
        if verdict == "removed":
            if normalized_checked_span and normalized_checked_span in normalized_audit_text(manuscript_text):
                blockers.append(
                    f"semantic_audit check {index} is marked removed but the audited span remains in the manuscript"
                )
            if not substantive_audit_comment(
                check.get("comment") or check.get("revision_note")
            ):
                blockers.append(
                    f"semantic_audit check {index} has no claim-specific removal rationale"
                )
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
        if verdict == "supported":
            receipt_errors: list[str] = []
            receipts = check.get("source_receipts")
            if not isinstance(receipts, list):
                receipt_errors.append("source_receipts is missing")
                receipts = []
            receipt_by_evidence = {
                str(receipt.get("evidence_id") or ""): receipt
                for receipt in receipts
                if isinstance(receipt, dict) and receipt.get("evidence_id")
            }
            checked_excerpts: list[str] = []
            for evidence_id in evidence_ids:
                anchor = evidence_records.get(evidence_id)
                receipt = receipt_by_evidence.get(evidence_id)
                if not isinstance(anchor, dict) or not isinstance(receipt, dict):
                    receipt_errors.append(f"no source receipt for {evidence_id}")
                    continue
                paper_id = str(anchor.get("paper_id") or "")
                if str(receipt.get("paper_id") or "") != paper_id:
                    receipt_errors.append(f"source receipt owner mismatch for {evidence_id}")
                if str(anchor.get("source_level") or "") != "full_text":
                    receipt_errors.append(f"non-full-text evidence {evidence_id}")
                anchor_path = Path(str(anchor.get("source_path") or ""))
                if not anchor_path.is_absolute():
                    anchor_path = (review_root / anchor_path).resolve()
                receipt_path = Path(str(receipt.get("source_path") or ""))
                if not receipt_path.is_absolute():
                    receipt_path = (review_root / receipt_path).resolve()
                if receipt_path != anchor_path:
                    receipt_errors.append(f"source receipt path mismatch for {evidence_id}")
                if not anchor_path.exists() or not anchor_path.is_file():
                    receipt_errors.append(f"source receipt file is missing for {evidence_id}")
                    continue
                recorded_sha = str(receipt.get("source_sha256") or "").strip().lower()
                actual_sha = file_sha256(anchor_path)
                if not recorded_sha or recorded_sha != actual_sha:
                    receipt_errors.append(f"source receipt hash mismatch for {evidence_id}")
                locator = str(receipt.get("locator") or "").strip()
                if not locator:
                    receipt_errors.append(f"source receipt locator is missing for {evidence_id}")
                excerpt = str(receipt.get("checked_excerpt") or "").strip()
                checked_excerpts.append(excerpt)
                if len(audit_content_words(excerpt)) < 8:
                    receipt_errors.append(f"checked excerpt is too short for {evidence_id}")
                source_text = source_text_cache.setdefault(
                    anchor_path, source_text_for_audit(anchor_path)
                )
                normalized_excerpt = re.sub(r"\s+", " ", excerpt).strip().lower()
                normalized_source = re.sub(r"\s+", " ", source_text).lower()
                if normalized_excerpt and normalized_excerpt not in normalized_source:
                    receipt_errors.append(
                        f"checked excerpt is not found in {evidence_id} source"
                    )
                anchor_excerpt = re.sub(
                    r"\s+", " ", str(anchor.get("source_excerpt") or "")
                ).strip().lower()
                if anchor_excerpt and not (
                    anchor_excerpt in normalized_excerpt
                    or normalized_excerpt in anchor_excerpt
                ):
                    anchor_terms = set(audit_content_words(anchor_excerpt))
                    receipt_terms = set(audit_content_words(normalized_excerpt))
                    overlap = len(anchor_terms & receipt_terms) / max(1, len(anchor_terms))
                    if overlap < 0.7:
                        receipt_errors.append(
                            f"checked excerpt does not cover the recorded anchor for {evidence_id}"
                        )
            claimed_quantities = set(claim_quantities(text_span))
            checked_quantity_text = " ".join(checked_excerpts)
            checked_quantities = set(claim_quantities(checked_quantity_text))
            missing_quantities = sorted(claimed_quantities - checked_quantities)
            if missing_quantities:
                receipt_errors.append(
                    "claim quantities absent from checked excerpts: "
                    + ", ".join(missing_quantities)
                )
            # The scanner can verify paths, hashes, locators, and verbatim
            # excerpts.  It cannot decide semantic entailment through word
            # overlap; that judgment belongs to the source-reading audit.
            if receipt_errors:
                source_receipt_failures.append(
                    {
                        "check_index": index,
                        "queue_id": queue_id or None,
                        "errors": list(dict.fromkeys(receipt_errors)),
                    }
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
            if verdict == "supported" and normalized_span not in normalized_audit_text(manuscript_text):
                blockers.append(
                    f"semantic_audit check {index} text_span is not found in the audited manuscript revision"
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
    missing_required = sorted(required_queue_ids - covered_queue_ids)
    if required and missing_required:
        blockers.append(
            "semantic_audit does not disposition required queue items: "
            + ", ".join(missing_required)
        )
    if source_receipt_failures:
        blockers.append(
            "semantic_audit source receipt verification failed for "
            f"{len(source_receipt_failures)} supported checks; see structured receipt failures"
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
        "required_queue_ids": sorted(required_queue_ids),
        "covered_queue_ids": sorted(required_queue_ids & covered_queue_ids),
        "manuscript_sha256": recorded_manuscript_sha256 or None,
        "source_receipt_failures": source_receipt_failures,
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
    article_body, noncanonical_backmatter = manuscript_body(text)
    headings = [{"level": len(m.group(1)), "title": m.group(2).strip()} for m in HEADING_RE.finditer(text)]
    heading_titles = [item["title"] for item in headings]
    duplicate_headings = sorted({title for title in heading_titles if heading_titles.count(title) > 1})
    placeholder_hits = [
        {"line": line_no, "text": line.strip()}
        for line_no, line in enumerate(text.splitlines(), start=1)
        if PLACEHOLDER_RE.search(line)
    ]
    raw_latex_captions = [
        {"line": line_no, "text": line.strip()}
        for line_no, line in enumerate(text.splitlines(), start=1)
        if re.search(r"(?:\*\*)?\s*(?:figure|scheme|table|chart)\s*\d+", line, re.I)
        and RAW_LATEX_COMMAND_RE.search(line)
    ]
    called_refs = sorted(expand_ref_callouts(article_body))
    listed_sequence = reference_numbers(text)
    listed_refs = sorted(set(listed_sequence))
    missing_listed_refs = sorted(set(called_refs) - set(listed_refs))
    uncalled_listed_refs = sorted(set(listed_refs) - set(called_refs))
    duplicate_reference_numbers = sorted({number for number in listed_sequence if listed_sequence.count(number) > 1})
    expected_sequence = list(range(1, len(listed_sequence) + 1))
    reference_numbering_contiguous = listed_sequence == expected_sequence

    image_paths = [match.group(1) for match in IMAGE_RE.finditer(article_body)]
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
    evidence_records = matrix_evidence_records(matrix_rows)
    citation_ref_numbers: list[int] = []
    citation_paper_ids: list[str] = []
    citation_paper_by_number: dict[int, str] = {}
    declared_incomplete_reference_metadata = []
    if isinstance(citations_payload, dict):
        entries = citations_payload.get("reference_list") or []
        for entry in entries if isinstance(entries, list) else []:
            if not isinstance(entry, dict):
                continue
            if str(entry.get("ref_num") or "").isdigit():
                ref_num = int(entry["ref_num"])
                citation_ref_numbers.append(ref_num)
                if entry.get("paper_id"):
                    citation_paper_by_number[ref_num] = str(entry["paper_id"])
            if entry.get("paper_id"):
                citation_paper_ids.append(str(entry["paper_id"]))
        declared_incomplete_reference_metadata = (
            citations_payload.get("incomplete_reference_metadata") or []
        )
    actual_citation_paper_ids = [
        citation_paper_by_number[number]
        for number in called_refs
        if number in citation_paper_by_number
    ]
    unknown_cited_papers = sorted(set(actual_citation_paper_ids) - matrix_ids) if matrix_ids else []
    actual_missing_metadata = actual_incomplete_references(
        project.parents[1], actual_citation_paper_ids, matrix_rows
    )
    incomplete_reference_metadata = actual_missing_metadata or declared_incomplete_reference_metadata
    reference_metadata_conflicts = reference_metadata_source_conflicts(
        project.parents[1],
        actual_citation_paper_ids,
        matrix_rows,
        strict_front_matter=declared_review_profile(project) == "comprehensive",
    )
    manuscript_reference_conflicts = manuscript_reference_metadata_conflicts(
        text,
        project.parents[1],
        {
            number: citation_paper_by_number[number]
            for number in called_refs
            if number in citation_paper_by_number
        },
        matrix_rows,
    )
    untrusted_reference_metadata = reference_metadata_provenance_issues(
        project.parents[1], actual_citation_paper_ids
    )

    markdown_table_count = len(TABLE_SEPARATOR_RE.findall(article_body))
    manuscript_table_references = referenced_artifact_numbers(
        TABLE_REFERENCE_RE, article_body
    )
    manuscript_figure_references = referenced_artifact_numbers(
        FIGURE_REFERENCE_RE, article_body
    )
    mojibake_hits = [
        {"line": line_no, "text": line.strip()[:300]}
        for line_no, line in enumerate(text.splitlines(), start=1)
        if MOJIBAKE_RE.search(line)
    ]
    reader_review_path = project / "05_final_audit" / "reader_utility_review.json"
    reader_review_text = read_text(reader_review_path) if reader_review_path.exists() else ""
    reader_review_table_references = referenced_artifact_numbers(
        TABLE_REFERENCE_RE, reader_review_text
    )
    reader_review_figure_references = referenced_artifact_numbers(
        FIGURE_REFERENCE_RE, reader_review_text
    )
    word_like_count = len(re.findall(r"\b[A-Za-z][A-Za-z'-]*\b", article_body))
    source_figure_count, source_figure_issues = verified_source_figure_usage(
        project, image_paths, set(actual_citation_paper_ids), article_body
    )
    review_profile = declared_review_profile(project)
    listed_and_called_reference_count = len(set(called_refs) & set(listed_refs))
    if review_profile == "comprehensive":
        invalid_reference_papers = {
            str(item.get("paper_id"))
            for item in (
                list(actual_missing_metadata)
                + list(reference_metadata_conflicts)
            )
            if isinstance(item, dict) and item.get("paper_id")
        }
        verified_reference_numbers = {
            number
            for number, paper_id in citation_paper_by_number.items()
            if paper_id not in invalid_reference_papers
        }
        verified_reference_count = len(
            set(called_refs) & set(listed_refs) & verified_reference_numbers
        )
    else:
        verified_reference_count = listed_and_called_reference_count
    delivery_metrics = {
        "word_like_count": word_like_count,
        "reference_count": listed_and_called_reference_count,
        "verified_reference_count": verified_reference_count,
        "table_count": markdown_table_count,
        "figure_count": len(image_paths),
        "source_figure_count": source_figure_count,
    }
    delivery_floor = (
        dict(COMPREHENSIVE_DELIVERY_FLOOR)
        if review_profile == "comprehensive"
        else {}
    )
    delivery_floor_issues = [
        f"comprehensive_delivery_floor:{metric}:"
        f"{delivery_metrics['verified_reference_count'] if metric == 'reference_count' else delivery_metrics[metric]}/{minimum}"
        for metric, minimum in delivery_floor.items()
        if (
            delivery_metrics["verified_reference_count"]
            if metric == "reference_count"
            else delivery_metrics[metric]
        ) < minimum
    ]
    target_words, blueprint_issues = blueprint_target(project / "01_matrix_outline" / "section_blueprint.json")
    word_target_ratio = round(word_like_count / target_words, 4) if target_words else None
    paragraph_stats = cited_paragraph_stats(article_body)
    duplicate_paragraphs = duplicated_long_paragraphs(text)
    queue_path = project / "05_final_audit" / "semantic_audit_queue.json"
    queue_payload = read_json(queue_path) if queue_path.exists() else {}
    expected_queue = semantic_queue(project)
    required_queue_ids = {
        str(item)
        for item in expected_queue.get("required_queue_ids") or []
        if str(item).strip()
    }
    queue_items_by_id = {
        str(item.get("queue_id")): item
        for item in expected_queue.get("items") or []
        if isinstance(item, dict) and str(item.get("queue_id") or "").strip()
    }
    semantic_status, semantic_blockers = semantic_audit_status(
        project / "05_final_audit" / "semantic_audit.json",
        required=phase == "release",
        review_root=project.parents[1],
        known_paper_ids=matrix_ids,
        evidence_owners=evidence_owners,
        evidence_records=evidence_records,
        paragraphs_by_id=drafted_paragraphs(
            project / "02_section_drafting" / "section_drafts.json"
        ),
        required_queue_ids=required_queue_ids,
        queue_items_by_id=queue_items_by_id,
        manuscript_sha256=file_sha256(draft),
        manuscript_text=text,
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
    if raw_latex_captions:
        add("raw_latex_commands_present_in_caption")
    if PARAGRAPH_MARKER_RE.search(text):
        add("editor_paragraph_markers_present")
    if duplicate_paragraphs:
        add("duplicated_long_paragraphs_or_template_padding")
    if noncanonical_backmatter:
        add("noncanonical_or_duplicated_backmatter")
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
    if reference_metadata_conflicts:
        add("reference_metadata_conflicts_with_source")
    if manuscript_reference_conflicts:
        add("reference_list_conflicts_with_verified_metadata")
    if untrusted_reference_metadata:
        add(
            "reference_metadata_uses_inferred_or_generated_values",
            block=review_profile != "comprehensive" or bool(reference_metadata_conflicts),
        )
    if abstract_image_paths:
        add("images_embedded_in_abstract")
    if broken_images:
        add("broken_markdown_image_paths")
    if source_placeholder_mode:
        add("unverified_source_figures_need_preparation")
    for source_figure_issue in source_figure_issues:
        add(source_figure_issue)
    if manuscript_table_references and max(manuscript_table_references) > markdown_table_count:
        add("manuscript_references_missing_table")
    if manuscript_figure_references and max(manuscript_figure_references) > len(image_paths):
        add("manuscript_references_missing_figure")
    if markdown_table_count and set(range(1, markdown_table_count + 1)) - set(manuscript_table_references):
        add("tables_not_used_in_manuscript_argument")
    if image_paths and set(range(1, len(image_paths) + 1)) - set(manuscript_figure_references):
        add("figures_not_used_in_manuscript_argument")
    if mojibake_hits:
        add("mojibake_or_replacement_characters_present")
    if not image_paths and not figures_skipped_with_reason:
        add("draft_has_no_figures", block=False)
    if target_words and word_target_ratio is not None and word_target_ratio < 0.8:
        add("manuscript_below_80_percent_of_blueprint_target", block=False)
    for issue in blueprint_issues:
        add(issue.replace(" ", "_"), block=False)
    if paragraph_stats["cited_paragraph_count"] >= 8 and paragraph_stats["multi_source_ratio"] < 0.2:
        add("paper_listing_pattern_too_few_multi_source_paragraphs", block=False)
    for semantic_issue in semantic_blockers:
        # Preflight creates or refreshes the queue before semantic review.
        # A stale audit from an earlier revision is advisory at this phase and
        # becomes blocking only at release.
        add("semantic_audit:" + semantic_issue, block=phase == "release")
    if phase == "release":
        for floor_issue in delivery_floor_issues:
            add(floor_issue)
        if not queue_path.exists():
            add("missing_semantic_audit_queue")
        elif not isinstance(queue_payload, dict):
            add("invalid_semantic_audit_queue")
        else:
            if queue_payload.get("queue_version") != expected_queue.get("queue_version"):
                add("semantic_audit_queue_version_mismatch")
            if queue_payload.get("queue_fingerprint") != expected_queue.get("queue_fingerprint"):
                add("semantic_audit_queue_is_stale")
            if set(queue_payload.get("required_queue_ids") or []) != set(
                expected_queue.get("required_queue_ids") or []
            ):
                add("semantic_audit_queue_coverage_mismatch")
        if reader_review_table_references and max(reader_review_table_references) > markdown_table_count:
            add("reader_utility_review_claims_missing_table")
        if reader_review_figure_references and max(reader_review_figure_references) > len(image_paths):
            add("reader_utility_review_claims_missing_figure")
        for visual_issue in resolved_visual_plan_issues(project, article_body):
            if visual_issue.startswith(
                ("comparison_table_not_traceable:", "selected_comparison_table_missing_from_manuscript:")
            ):
                add(visual_issue)
        for inventory_issue in figure_inventory_consistency_issues(project):
            add(inventory_issue)
        for upstream_issue in upstream_release_issues(project):
            add(upstream_issue)

    return {
        "project_dir": str(project),
        "phase": phase,
        "draft_path": str(draft),
        "target_draft": target,
        "draft_exists": draft.exists(),
        "word_like_count": word_like_count,
        "review_profile": review_profile or None,
        "delivery_metrics": delivery_metrics,
        "delivery_floor": delivery_floor,
        "delivery_floor_issues": delivery_floor_issues,
        "blueprint_target_words": target_words,
        "word_target_ratio": word_target_ratio,
        "heading_count": len(headings),
        "headings": headings,
        "duplicate_headings": duplicate_headings,
        "noncanonical_backmatter": noncanonical_backmatter,
        "heading_jumps": heading_jumps,
        "placeholder_hits": placeholder_hits,
        "raw_latex_captions": raw_latex_captions,
        "reference_callouts": called_refs,
        "reference_list_items": listed_refs,
        "reference_list_sequence": listed_sequence,
        "missing_listed_refs": missing_listed_refs,
        "uncalled_listed_refs": uncalled_listed_refs,
        "duplicate_reference_numbers": duplicate_reference_numbers,
        "reference_numbering_contiguous": reference_numbering_contiguous,
        "citations_json_reference_numbers": citation_ref_numbers,
        "image_paths": image_paths,
        "markdown_table_count": markdown_table_count,
        "manuscript_table_references": manuscript_table_references,
        "manuscript_figure_references": manuscript_figure_references,
        "reader_review_table_references": reader_review_table_references,
        "reader_review_figure_references": reader_review_figure_references,
        "mojibake_hits": mojibake_hits,
        "abstract_image_paths": abstract_image_paths,
        "broken_images": broken_images,
        "source_placeholder_mode": source_placeholder_mode,
        "references_section": references_section,
        "figures_skipped_with_reason": figures_skipped_with_reason,
        "citations_payload_present": isinstance(citations_payload, dict),
        "unknown_cited_papers": unknown_cited_papers,
        "incomplete_reference_metadata": incomplete_reference_metadata,
        "reference_metadata_source_conflicts": reference_metadata_conflicts,
        "manuscript_reference_metadata_conflicts": manuscript_reference_conflicts,
        "untrusted_reference_metadata": untrusted_reference_metadata,
        "source_figure_issues": source_figure_issues,
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
    audit_inputs = [
        Path(scan["draft_path"]),
        project / "01_matrix_outline" / "literature_matrix.json",
        project / "01_matrix_outline" / "section_blueprint.json",
        project / "02_section_drafting" / "section_drafts.json",
        project / "04_first_draft" / "citations.json",
    ]
    for optional in (
        project / "05_final_audit" / "semantic_audit_queue.json",
        project / "05_final_audit" / "semantic_audit.json",
        project / "03_figure_redraw" / "redrawn_figure_manifest.json",
        project / "04_first_draft" / "figure_insertion_report.json",
        project / "05_final_audit" / "figure_insertion_report.json",
    ):
        if optional.exists():
            audit_inputs.append(optional)
    attach_input_artifacts(scan, project, audit_inputs)
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
