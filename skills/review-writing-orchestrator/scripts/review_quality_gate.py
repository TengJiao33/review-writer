#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any


PROFILE_POLICIES: dict[str, dict[str, int]] = {
    "focused": {
        "minimum_included_papers": 15,
        "minimum_primary_papers": 10,
        "minimum_full_text_papers": 12,
        "minimum_primary_full_text_papers": 8,
        "minimum_comparison_ready_method_cards": 6,
        "minimum_comparison_fields_per_card": 4,
        "minimum_papers_per_required_coverage_item": 1,
        "minimum_manuscript_words": 6000,
        "minimum_references": 15,
        "minimum_substantive_sections": 5,
        "minimum_sources_per_substantive_section": 3,
    },
    "comprehensive": {
        "minimum_included_papers": 30,
        "minimum_primary_papers": 20,
        "minimum_full_text_papers": 24,
        "minimum_primary_full_text_papers": 16,
        "minimum_comparison_ready_method_cards": 10,
        "minimum_comparison_fields_per_card": 5,
        "minimum_papers_per_required_coverage_item": 2,
        "minimum_manuscript_words": 9000,
        "minimum_references": 25,
        "minimum_substantive_sections": 6,
        "minimum_sources_per_substantive_section": 4,
    },
}

ALLOWED_STUDY_TYPES = {
    "primary_research",
    "primary_dataset",
    "methods_validation",
    "systematic_review",
    "review",
    "perspective",
    "standard",
    "other",
}
PRIMARY_STUDY_TYPES = {"primary_research", "primary_dataset", "methods_validation"}
IMAGE_RE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")
REFERENCE_HEADING_RE = re.compile(
    r"^\s*#{1,6}\s*(references|reference list|bibliography|cited literature|参考文献)\s*$",
    re.I | re.M,
)
REFERENCE_ITEM_RE = re.compile(r"^\s*(?:\[(\d+)\]|(\d+)[.)])\s+", re.M)
REF_CALLOUT_RE = re.compile(r"\[(\d+(?:\s*[-,]\s*\d+)*)\]")
TABLE_SEPARATOR_RE = re.compile(
    r"^\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?\s*$",
    re.M,
)
WORD_RE = re.compile(r"\b[A-Za-z][A-Za-z'-]*\b|[\u4e00-\u9fff]")


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def file_sha256(path: Path) -> str:
    if not path.exists() or not path.is_file():
        return ""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def matrix_rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, dict):
        rows = payload.get("papers") or payload.get("rows") or payload.get("literature_matrix") or []
    else:
        rows = []
    return [row for row in rows if isinstance(row, dict)]


def method_card_rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, dict):
        rows = payload.get("method_cards") or []
    else:
        rows = []
    return [row for row in rows if isinstance(row, dict)]


def resolve_source_path(review_root: Path, raw: Any) -> Path | None:
    value = str(raw or "").strip()
    if not value:
        return None
    path = Path(value)
    return path if path.is_absolute() else (review_root / path).resolve()


def effective_requirements(contract: dict[str, Any]) -> tuple[str, dict[str, int], list[str]]:
    blockers: list[str] = []
    profile = str(contract.get("review_profile") or "").strip().lower()
    if profile not in PROFILE_POLICIES:
        blockers.append("topic_contract.review_profile must be focused or comprehensive")
        # Diagnose a missing declaration against the safer broad-review
        # expectation instead of suppressing all useful depth signals.
        return profile, dict(PROFILE_POLICIES["comprehensive"]), blockers
    requirements = dict(PROFILE_POLICIES[profile])
    overrides = contract.get("quality_requirements")
    if overrides is not None and not isinstance(overrides, dict):
        blockers.append("topic_contract.quality_requirements must be an object")
        overrides = {}
    for key, floor in list(requirements.items()):
        raw = (overrides or {}).get(key)
        if raw is None:
            continue
        if not isinstance(raw, int) or isinstance(raw, bool) or raw < 0:
            blockers.append(f"quality requirement {key} must be a non-negative integer")
            continue
        # Profiles provide useful defaults.  A topic contract may deliberately
        # narrow one dimension; the resulting depth is reported as a risk, not
        # rejected by a hidden global quota.
        requirements[key] = raw
    return profile, requirements, blockers


def quality_review_issues(
    project: Path,
    phase: str,
    risk_signals: list[dict[str, Any]],
) -> tuple[dict[str, Any] | None, list[str]]:
    name = "evidence_readiness_review.json" if phase == "prewrite" else "release_quality_review.json"
    directory = project / ("01_matrix_outline" if phase == "prewrite" else "05_final_audit")
    path = directory / name
    payload = read_json(path)
    if payload is None:
        return None, []
    if not isinstance(payload, dict):
        return None, [f"optional {name} is invalid"]
    issues: list[str] = []
    if payload.get("status") != "completed":
        issues.append(f"{name} is not completed")
    decision = str(payload.get("decision") or "").strip()
    allowed = (
        {"proceed", "expand_evidence", "narrow_scope"}
        if phase == "prewrite"
        else {"release", "revise", "narrow_scope"}
    )
    if decision not in allowed:
        issues.append(f"{name} has an invalid decision")
    if not str(payload.get("rationale") or "").strip():
        issues.append(f"{name} has no overall rationale")
    dispositions = payload.get("risk_dispositions")
    if dispositions not in (None, []):
        # This file is written inside the same autonomous run that is being
        # judged, so an `approved_by: user` string is not evidence of a user
        # decision. Scope is declared before the run in topic_contract.json.
        issues.append(
            f"{name}.risk_dispositions cannot authorize automated release or scope changes"
        )
    # A model-authored review note may explain a decision, but it cannot clear
    # or create objective risks.  The risks stay visible in the diagnostic and
    # the author chooses whether to expand evidence, narrow scope, or proceed.
    return payload, issues


def screening_inventory(selected: Any) -> tuple[set[str], dict[str, str], list[str]]:
    blockers: list[str] = []
    if not isinstance(selected, dict):
        return set(), {}, ["selected_discovery_results.json is invalid"]
    rows = selected.get("screening_decisions")
    if not isinstance(rows, list):
        return set(), {}, ["screening_decisions is missing"]
    included: set[str] = set()
    study_types: dict[str, str] = {}
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, dict) or str(row.get("decision") or "").lower() != "include":
            continue
        paper_id = str(row.get("paper_id") or "").strip()
        if not paper_id:
            blockers.append(f"included screening decision {index} has no paper_id")
            continue
        included.add(paper_id)
        study_type = str(row.get("study_type") or "").strip().lower()
        if study_type not in ALLOWED_STUDY_TYPES:
            blockers.append(f"{paper_id}: study_type is missing or invalid")
        else:
            study_types[paper_id] = study_type
    return included, study_types, blockers


def full_text_inventory(
    review_root: Path,
    rows: list[dict[str, Any]],
    included: set[str],
) -> tuple[set[str], list[str]]:
    full_text: set[str] = set()
    blockers: list[str] = []
    row_ids = {str(row.get("paper_id") or "") for row in rows}
    missing_rows = sorted(included - row_ids)
    if missing_rows:
        blockers.append("included papers missing from literature matrix: " + ", ".join(missing_rows))
    for row in rows:
        paper_id = str(row.get("paper_id") or "")
        if paper_id not in included:
            continue
        for anchor in row.get("evidence_anchors") or []:
            if not isinstance(anchor, dict) or str(anchor.get("source_level") or "") != "full_text":
                continue
            source = resolve_source_path(review_root, anchor.get("source_path"))
            if source is not None and source.exists() and source.is_file():
                full_text.add(paper_id)
                break
    return full_text, blockers


def comparison_ready_cards(payload: Any, minimum_fields: int) -> tuple[set[str], dict[str, int]]:
    ready: set[str] = set()
    field_counts: dict[str, int] = {}
    for card in method_card_rows(payload):
        paper_id = str(card.get("paper_id") or "").strip()
        populated = [str(item) for item in card.get("populated_fields") or [] if str(item).strip()]
        evidence = card.get("field_evidence") if isinstance(card.get("field_evidence"), dict) else {}
        traced = [field for field in populated if evidence.get(field)]
        field_counts[paper_id] = len(traced)
        if (
            paper_id
            and len(traced) >= minimum_fields
            and card.get("recording_status") == "recorded_with_field_provenance"
        ):
            ready.add(paper_id)
    return ready, field_counts


def required_coverage_rows(blueprint: Any) -> list[dict[str, Any]]:
    contract = blueprint.get("coverage_contract") if isinstance(blueprint, dict) else None
    dimensions = contract.get("dimensions") if isinstance(contract, dict) else None
    rows: list[dict[str, Any]] = []
    for dimension in dimensions or []:
        if not isinstance(dimension, dict):
            continue
        dimension_name = str(dimension.get("name") or "unnamed")
        for item in dimension.get("items") or []:
            if isinstance(item, dict) and item.get("required") is True:
                rows.append({"dimension": dimension_name, **item})
    return rows


def manuscript_body(text: str) -> str:
    match = REFERENCE_HEADING_RE.search(text)
    pseudo = re.search(
        r"^\s*\*\*(?:references?|reference list|bibliography|figure descriptions?)\*\*\s*:?.*$",
        text,
        re.I | re.M,
    )
    boundaries = [item.start() for item in (match, pseudo) if item]
    return text[: min(boundaries)] if boundaries else text


def expand_callout(raw: str) -> set[int]:
    result: set[int] = set()
    for part in re.split(r"\s*,\s*", raw):
        if "-" in part:
            start, end = (int(item.strip()) for item in part.split("-", 1))
            result.update(range(min(start, end), max(start, end) + 1))
        elif part.strip().isdigit():
            result.add(int(part.strip()))
    return result


def section_source_counts(text: str) -> list[dict[str, Any]]:
    body = manuscript_body(text)
    heading_matches = list(re.finditer(r"^##\s+(.+?)\s*$", body, re.M))
    rows: list[dict[str, Any]] = []
    ignored = {"abstract", "keywords", "references", "bibliography"}
    for index, match in enumerate(heading_matches):
        title = match.group(1).strip()
        if title.lower() in ignored:
            continue
        end = heading_matches[index + 1].start() if index + 1 < len(heading_matches) else len(body)
        segment = body[match.end():end]
        words = len(WORD_RE.findall(segment))
        if words < 250:
            continue
        refs: set[int] = set()
        for callout in REF_CALLOUT_RE.finditer(segment):
            refs.update(expand_callout(callout.group(1)))
        rows.append({"title": title, "word_count": words, "source_count": len(refs)})
    return rows


def input_fingerprint(paths: list[Path]) -> str:
    material = [
        {"path": str(path), "sha256": file_sha256(path)}
        for path in paths
    ]
    return hashlib.sha256(
        json.dumps(material, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def evaluate_project_quality(review_root: Path, project_id: str, phase: str) -> dict[str, Any]:
    project = review_root / "review-projects" / project_id
    discovery = project / "00_discovery"
    matrix_stage = project / "01_matrix_outline"
    final_stage = project / "05_final_audit"
    input_paths = [
        discovery / "topic_contract.json",
        discovery / "selected_discovery_results.json",
        matrix_stage / "literature_matrix.json",
        matrix_stage / "method_cards.json",
        matrix_stage / "section_blueprint.json",
    ]
    if phase == "prewrite":
        input_paths.append(matrix_stage / "evidence_readiness_review.json")
    else:
        input_paths.extend(
            [
                project / "04_first_draft" / "citations.json",
                final_stage / "final_draft.md",
                final_stage / "reader_utility_review.json",
                project / "02_section_drafting" / "review_visual_plan.json",
                final_stage / "semantic_audit.json",
                final_stage / "release_quality_review.json",
            ]
        )

    contract = read_json(input_paths[0])
    selected = read_json(input_paths[1])
    matrix_payload = read_json(input_paths[2])
    cards_payload = read_json(input_paths[3])
    blueprint = read_json(input_paths[4])
    blockers: list[str] = []
    warnings: list[str] = []
    risk_signals: list[dict[str, Any]] = []

    if not isinstance(contract, dict):
        contract = {}
        blockers.append("topic_contract.json is invalid")
    profile, requirements, requirement_issues = effective_requirements(contract)
    blockers.extend(requirement_issues)
    included, study_types, screening_issues = screening_inventory(selected)
    blockers.extend(screening_issues)
    rows = matrix_rows(matrix_payload)
    full_text, full_text_issues = full_text_inventory(review_root, rows, included)
    blockers.extend(full_text_issues)
    primary = {paper_id for paper_id, study_type in study_types.items() if study_type in PRIMARY_STUDY_TYPES}
    primary_full_text = primary & full_text

    minimum_fields = requirements.get("minimum_comparison_fields_per_card", 0)
    ready_cards, card_field_counts = comparison_ready_cards(cards_payload, minimum_fields)
    coverage_rows = required_coverage_rows(blueprint)
    coverage_results = []
    coverage_risk_details: list[str] = []
    min_coverage = requirements.get("minimum_papers_per_required_coverage_item", 0)
    for row in coverage_rows:
        paper_ids = {str(item) for item in row.get("covered_by") or [] if str(item).strip()}
        full_text_ids = paper_ids & full_text
        primary_ids = paper_ids & primary_full_text
        status = "passed"
        if len(full_text_ids) < min_coverage:
            status = "failed"
            coverage_risk_details.append(
                f"required coverage is too thin: {row['dimension']}/{row.get('name') or 'unnamed'} "
                f"has {len(full_text_ids)} full-text papers; minimum {min_coverage}"
            )
        elif not primary_ids:
            status = "failed"
            coverage_risk_details.append(
                f"required coverage lacks primary full-text evidence: "
                f"{row['dimension']}/{row.get('name') or 'unnamed'}"
            )
        coverage_results.append(
            {
                "dimension": row["dimension"],
                "name": row.get("name"),
                "full_text_paper_ids": sorted(full_text_ids),
                "primary_full_text_paper_ids": sorted(primary_ids),
                "status": status,
            }
        )

    metrics: dict[str, Any] = {
        "included_paper_count": len(included),
        "primary_paper_count": len(primary),
        "full_text_paper_count": len(full_text),
        "primary_full_text_paper_count": len(primary_full_text),
        "comparison_ready_method_card_count": len(ready_cards),
        "required_coverage_item_count": len(coverage_rows),
        "failed_required_coverage_item_count": sum(row["status"] == "failed" for row in coverage_results),
    }

    evidence_metric_requirements = {
        "included_paper_count": "minimum_included_papers",
        "primary_paper_count": "minimum_primary_papers",
        "full_text_paper_count": "minimum_full_text_papers",
        "primary_full_text_paper_count": "minimum_primary_full_text_papers",
    }
    evidence_depth_details = []
    for metric, requirement in evidence_metric_requirements.items():
        minimum = requirements.get(requirement)
        if minimum is not None and metrics[metric] < minimum:
            evidence_depth_details.append(f"{metric} is {metrics[metric]}; expected minimum {minimum}")
    if evidence_depth_details:
        risk_signals.append(
            {
                "risk_id": "evidence_base_depth",
                "summary": "The retained evidence base is thin for the declared review profile.",
                "details": evidence_depth_details,
            }
        )
    if coverage_risk_details:
        risk_signals.append(
            {
                "risk_id": "coverage_depth",
                "summary": "One or more promised coverage areas lack enough primary full-text support.",
                "details": coverage_risk_details,
            }
        )
    minimum_ready_cards = requirements.get("minimum_comparison_ready_method_cards")
    if minimum_ready_cards is not None and len(ready_cards) < minimum_ready_cards:
        risk_signals.append(
            {
                "risk_id": "comparison_readiness",
                "summary": "Too few evidence-traceable method cards are ready for meaningful comparison.",
                "details": [
                    f"comparison_ready_method_card_count is {len(ready_cards)}; expected minimum {minimum_ready_cards}"
                ],
            }
        )

    blueprint_target = 0
    if isinstance(blueprint, dict):
        blueprint_target = sum(
            int(section.get("target_words") or 0)
            for section in blueprint.get("sections") or []
            if isinstance(section, dict)
        )
    metrics["blueprint_target_words"] = blueprint_target
    minimum_words = requirements.get("minimum_manuscript_words")
    if minimum_words is not None and blueprint_target < minimum_words:
        risk_signals.append(
            {
                "risk_id": "blueprint_depth",
                "summary": "The planned manuscript depth is low for the declared review profile.",
                "details": [f"blueprint_target_words is {blueprint_target}; expected minimum {minimum_words}"],
            }
        )

    section_rows: list[dict[str, Any]] = []
    if phase == "release":
        final_path = final_stage / "final_draft.md"
        text = final_path.read_text(encoding="utf-8", errors="ignore") if final_path.exists() else ""
        body = manuscript_body(text)
        reference_match = REFERENCE_HEADING_RE.search(text)
        reference_tail = text[reference_match.end():] if reference_match else ""
        section_rows = section_source_counts(text)
        metrics.update(
            {
                "manuscript_word_count": len(WORD_RE.findall(body)),
                "reference_count": len(REFERENCE_ITEM_RE.findall(reference_tail)),
                "markdown_table_count": len(TABLE_SEPARATOR_RE.findall(body)),
                "synthesis_figure_count": len(IMAGE_RE.findall(body)),
                "substantive_section_count": len(section_rows),
                "sections_below_source_minimum": sum(
                    row["source_count"] < requirements.get("minimum_sources_per_substantive_section", 0)
                    for row in section_rows
                ),
            }
        )
        scan = read_json(final_stage / "format_scan.json")
        scan_metrics = scan.get("delivery_metrics") if isinstance(scan, dict) else {}
        metrics["verified_source_figure_count"] = int(
            (scan_metrics or {}).get("source_figure_count") or 0
        )
        manuscript_metric_requirements = {
            "manuscript_word_count": "minimum_manuscript_words",
            "reference_count": "minimum_references",
            "substantive_section_count": "minimum_substantive_sections",
        }
        manuscript_depth_details = []
        for metric, requirement in manuscript_metric_requirements.items():
            minimum = requirements.get(requirement)
            if minimum is not None and metrics[metric] < minimum:
                manuscript_depth_details.append(
                    f"{metric} is {metrics[metric]}; expected minimum {minimum}"
                )
        source_minimum = requirements.get("minimum_sources_per_substantive_section", 0)
        for row in section_rows:
            if row["source_count"] < source_minimum:
                manuscript_depth_details.append(
                    f"section_source_count is {row['source_count']} for {row['title']}; expected minimum {source_minimum}"
                )
        if manuscript_depth_details:
            risk_signals.append(
                {
                    "risk_id": "manuscript_depth",
                    "summary": "The delivered manuscript appears underdeveloped for its declared scope.",
                    "details": manuscript_depth_details,
                }
            )
        if profile == "comprehensive" and metrics["verified_source_figure_count"] < 3:
            risk_signals.append(
                {
                    "risk_id": "source_visual_portfolio",
                    "summary": "The comprehensive review does not yet use three lawful, verified figures from cited source papers.",
                    "details": [
                        f"verified_source_figure_count is {metrics['verified_source_figure_count']}; "
                        "retrieve or parse suitable open-reuse sources rather than substituting an automatic diagram"
                    ],
                }
            )

    review_payload, review_issues = quality_review_issues(project, phase, risk_signals)
    warnings.extend(review_issues)

    return {
        "project_id": project_id,
        "phase": phase,
        "profile": profile or None,
        "requirements": requirements,
        "metrics": metrics,
        "included_paper_ids": sorted(included),
        "primary_paper_ids": sorted(primary),
        "full_text_paper_ids": sorted(full_text),
        "primary_full_text_paper_ids": sorted(primary_full_text),
        "comparison_ready_method_card_ids": sorted(ready_cards),
        "method_card_traced_field_counts": card_field_counts,
        "coverage_results": coverage_results,
        "section_source_counts": section_rows,
        "risk_signals": risk_signals,
        "quality_review": review_payload,
        "input_fingerprint": input_fingerprint(input_paths),
        "blocking_issues": list(dict.fromkeys(blockers)),
        "warnings": list(dict.fromkeys(warnings)),
        "passed": not blockers,
    }


def write_report(project: Path, report: dict[str, Any]) -> tuple[Path, Path]:
    if report["phase"] == "prewrite":
        out_dir = project / "01_matrix_outline"
        stem = "quality_gate_prewrite"
    else:
        out_dir = project / "05_final_audit"
        stem = "quality_gate_release"
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / f"{stem}.json"
    md_path = out_dir / f"{stem}.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = [
        "# Review Quality Gate",
        "",
        f"- Phase: `{report['phase']}`",
        f"- Profile: `{report.get('profile') or 'missing'}`",
        f"- Passed: `{str(report['passed']).lower()}`",
        f"- Blocking issues: {len(report['blocking_issues'])}",
        "",
        "## Metrics",
        "",
    ]
    for name, value in report["metrics"].items():
        lines.append(f"- {name}: {value}")
    lines.extend(["", "## Quality risk signals", ""])
    for risk in report.get("risk_signals") or []:
        lines.append(f"- **{risk['risk_id']}**: {risk['summary']}")
        lines.extend(f"  - {detail}" for detail in risk.get("details") or [])
    if not report.get("risk_signals"):
        lines.append("- none")
    lines.extend(["", "## Blocking issues", ""])
    lines.extend(f"- {item}" for item in report["blocking_issues"])
    if not report["blocking_issues"]:
        lines.append("- none")
    md_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return json_path, md_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Report pre-writing and release-level review quality risks."
    )
    parser.add_argument("--review-root", default=str(Path(__file__).resolve().parents[3]))
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--phase", choices=("prewrite", "release"), required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    review_root = Path(args.review_root).resolve()
    project = review_root / "review-projects" / args.project_id
    if not project.exists():
        raise SystemExit(f"Project not found: {project}")
    report = evaluate_project_quality(review_root, args.project_id, args.phase)
    json_path, md_path = write_report(project, report)
    print(f"Wrote {json_path}")
    print(f"Wrote {md_path}")
    if report["blocking_issues"]:
        print(f"BLOCKING ISSUES: {len(report['blocking_issues'])}")
        for issue in report["blocking_issues"]:
            print(f"- {issue}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
