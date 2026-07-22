#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


REFERENCE_HEADING_RE = re.compile(
    r"^\s*#{1,6}\s*(references|reference list|bibliography|cited literature)\s*$",
    re.I | re.M,
)
REFERENCE_ITEM_RE = re.compile(r"^\s*(?:\[(\d+)\]|(\d+)[.)])\s+", re.M)
TABLE_SEPARATOR_RE = re.compile(
    r"^\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?\s*$",
    re.M,
)
IMAGE_RE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")
WORD_RE = re.compile(r"\b[A-Za-z][A-Za-z'-]*\b|[\u4e00-\u9fff]")
COMPREHENSIVE_DELIVERY_FLOOR = {
    "word_like_count": 8000,
    "reference_count": 25,
    "table_count": 2,
    "figure_count": 2,
}


STAGES: list[dict[str, Any]] = [
    {
        "id": "discovery",
        "name": "Topic discovery",
        "dir": "00_discovery",
        "skill": "review-topic-paper-discovery",
        "required": [
            "topic_input.md",
            "topic_contract.json",
            "selected_discovery_results.json",
            "screening_validation.json",
        ],
    },
    {
        "id": "matrix_outline",
        "name": "Literature matrix and outline",
        "dir": "01_matrix_outline",
        "skill": "review-literature-matrix-outline",
        "required": [
            "literature_matrix.json",
            "matrix_validation.json",
            "method_cards.json",
        ],
    },
    {
        "id": "section_blueprint",
        "name": "Section blueprint",
        "dir": "01_matrix_outline",
        "skill": "review-section-blueprint",
        "required": [
            "section_blueprint.json",
            "blueprint_validation.json",
        ],
    },
    {
        "id": "section_drafting",
        "name": "Section drafting and figure picking",
        "dir": "02_section_drafting",
        "skill": "review-section-drafting-figure-picking",
        "required": [
            "section_drafts.json",
            "figure_candidates.json",
            "section_draft_validation.json",
        ],
    },
    {
        "id": "figure_redraw",
        "name": "Figure preparation",
        "dir": "03_figure_redraw",
        "skill": "review-figure-style-redraw",
        "required": [
            "style_config.json",
            "source_figure_manifest.json",
            "redrawn_figure_manifest.json",
            "figure_fidelity_review.json",
        ],
        "skip_anchor": "skip_reason.md",
    },
    {
        "id": "first_draft",
        "name": "First draft merge",
        "dir": "04_first_draft",
        "skill": "review-draft-merge-polish",
        "required": [
            "first_draft.md",
            "citations.json",
            "merge_validation.json",
        ],
    },
    {
        "id": "final_audit",
        "name": "Final content and format audit",
        "dir": "05_final_audit",
        "skill": "review-final-audit-release",
        "required": [
            "format_scan.json",
            "semantic_audit.json",
            "semantic_audit_queue.json",
            "final_draft.md",
        ],
    },
    {
        "id": "docx_export",
        "name": "DOCX and PDF export",
        "dir": "05_final_audit",
        "skill": "review-export-docx",
        "required": [
            "final_draft.docx",
            "final_draft.pdf",
            "docx_audit.json",
            "render_qa_report.json",
        ],
    },
]


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def discover_projects(review_root: Path) -> list[str]:
    root = review_root / "review-projects"
    if not root.exists():
        return []
    return sorted(p.name for p in root.iterdir() if p.is_dir())


def comprehensive_delivery_floor_issues(project: Path) -> list[str]:
    contract = read_json(project / "00_discovery" / "topic_contract.json")
    if not isinstance(contract, dict) or str(contract.get("review_profile") or "").lower() != "comprehensive":
        return []
    draft = project / "05_final_audit" / "final_draft.md"
    if not draft.exists():
        return []
    text = draft.read_text(encoding="utf-8", errors="ignore")
    references = REFERENCE_HEADING_RE.search(text)
    body = text[: references.start()] if references else text
    reference_tail = text[references.end():] if references else ""
    metrics = {
        "word_like_count": len(WORD_RE.findall(body)),
        "reference_count": len(REFERENCE_ITEM_RE.findall(reference_tail)),
        "table_count": len(TABLE_SEPARATOR_RE.findall(body)),
        "figure_count": len(IMAGE_RE.findall(body)),
    }
    return [
        f"comprehensive_delivery_floor:{metric}:{metrics[metric]}/{minimum}"
        for metric, minimum in COMPREHENSIVE_DELIVERY_FLOOR.items()
        if metrics[metric] < minimum
    ]


def run_record_issues(project: Path, stages: list[dict[str, Any]]) -> list[str]:
    """Diagnose an existing execution log without making logging a release gate."""
    record_path = project / "run_record.md"
    events_path = project / "run_events.jsonl"
    issues: list[str] = []
    if not record_path.exists() and not events_path.exists():
        return issues
    if record_path.exists() and "Generated from `run_events.jsonl`" not in record_path.read_text(encoding="utf-8", errors="ignore"):
        issues.append("project_run_record_not_generated_from_events")
    if not events_path.exists():
        return issues + ["run_record_exists_without_run_events"]
    valid_stages = {stage["id"] for stage in STAGES} | {"status"}
    for line_no, line in enumerate(events_path.read_text(encoding="utf-8", errors="ignore").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except Exception:
            issues.append(f"invalid_run_event_json:{line_no}")
            continue
        if not isinstance(event, dict):
            issues.append(f"invalid_run_event:{line_no}")
            continue
        if str(event.get("project_id") or "") != project.name:
            issues.append(f"run_event_project_mismatch:{line_no}")
        if str(event.get("stage") or "") not in valid_stages:
            issues.append(f"invalid_run_event_stage:{line_no}")
    return list(dict.fromkeys(issues))


def stage_status(project: Path, stage: dict[str, Any]) -> dict[str, Any]:
    stage_dir = project / stage["dir"]
    missing = [name for name in stage["required"] if not (stage_dir / name).exists()]
    semantic_issues: list[str] = []
    confirmation_file = stage.get("confirmation_file")
    confirmed = True
    if confirmation_file:
        confirmation = read_json(stage_dir / confirmation_file)
        confirmed = isinstance(confirmation, dict) and confirmation.get("status") == "confirmed"
        if not confirmed and confirmation_file not in missing:
            semantic_issues.append("candidate_relevance_not_confirmed")
    validation_files = {
        "discovery": "screening_validation.json",
        "matrix_outline": "matrix_validation.json",
        "section_blueprint": "blueprint_validation.json",
        "section_drafting": "section_draft_validation.json",
        "first_draft": "merge_validation.json",
    }
    validation_name = validation_files.get(stage["id"])
    if validation_name and validation_name not in missing:
        validation = read_json(stage_dir / validation_name)
        if not isinstance(validation, dict):
            semantic_issues.append(f"invalid_{validation_name}")
        else:
            blockers = validation.get("blocking_issues")
            blocker_count = validation.get("blocking_issue_count")
            if blockers or (isinstance(blocker_count, int) and blocker_count > 0):
                semantic_issues.append(f"{stage['id']}_validation_has_blockers")
    if stage["id"] == "figure_redraw":
        skip_anchor = stage_dir / stage.get("skip_anchor", "skip_reason.md")
        skip_active = skip_anchor.exists() and bool(skip_anchor.read_text(encoding="utf-8", errors="ignore").strip())
        candidate_payload = read_json(project / "02_section_drafting" / "figure_candidates.json")
        candidate_rows = candidate_payload.get("figures") if isinstance(candidate_payload, dict) else candidate_payload
        source_selected = isinstance(candidate_rows, list) and any(
            isinstance(row, dict)
            and (
                row.get("manuscript_selected") is True
                or str(row.get("editorial_status") or "").lower() in {"selected", "adapted", "combined"}
            )
            for row in candidate_rows
        )
        visual_manifest_path = stage_dir / "review_visual_manifest.json"
        visual_manifest = read_json(visual_manifest_path) if visual_manifest_path.exists() else None
        visual_rows = visual_manifest.get("visuals") if isinstance(visual_manifest, dict) else []
        if visual_manifest_path.exists() and not isinstance(visual_rows, list):
            semantic_issues.append("invalid_review_visual_manifest")
            visual_rows = []
        selected_visuals = [
            visual
            for visual in visual_rows
            if isinstance(visual, dict) and visual.get("status") not in {"suggested", "skipped"}
        ]
        usable_originals = []
        for visual in selected_visuals:
            raw_path = visual.get("original_image")
            image_path = Path(str(raw_path)) if raw_path else None
            asset_exists = bool(
                image_path and (image_path.exists() or (project / image_path).exists())
            )
            if (
                visual.get("status") == "original_verified"
                and visual.get("verification_status") == "passed"
                and asset_exists
            ):
                usable_originals.append(visual)
        if selected_visuals and not usable_originals:
            semantic_issues.append("original_visual_preparation_incomplete")

        if skip_active or (not source_selected and not selected_visuals):
            # Figure count is editorial. No selected asset means there is no
            # preparation sub-workflow to complete.
            missing = []
        elif usable_originals:
            # Original synthesis has its own evidence and rendered-asset check;
            # source-redraw artifacts are not prerequisites for this path.
            missing = []
        else:
            manifest = read_json(stage_dir / "redrawn_figure_manifest.json")
            accepted_figure_ids: set[str] = set()
            if isinstance(manifest, dict):
                if manifest.get("status") == "skipped":
                    semantic_issues.append("figure_redraw_skipped_without_reason")
                figures = manifest.get("figures")
                if not isinstance(figures, list):
                    figures = manifest.get("redrawn_figures")
                if isinstance(figures, list):
                    accepted_figure_ids = {
                        str(f.get("figure_id"))
                        for f in figures
                        if isinstance(f, dict)
                        and f.get("figure_id")
                        and (
                            f.get("status") == "redrawn"
                            or (
                                f.get("status") == "source_verified"
                                and f.get("verification_status") == "passed"
                            )
                        )
                    }
                    if not any(
                        isinstance(f, dict)
                        and (
                            f.get("status") == "redrawn"
                            or (
                                f.get("status") == "source_verified"
                                and f.get("verification_status") == "passed"
                            )
                        )
                        for f in figures
                    ):
                        semantic_issues.append("no_usable_figures")
                elif not missing:
                    semantic_issues.append("invalid_redrawn_figure_manifest")
            elif not missing:
                semantic_issues.append("invalid_redrawn_figure_manifest")
            fidelity = read_json(stage_dir / "figure_fidelity_review.json")
            if isinstance(fidelity, dict):
                fidelity_rows = fidelity.get("figures")
                if isinstance(fidelity_rows, list):
                    passed_figure_ids = {
                        str(row.get("figure_id"))
                        for row in fidelity_rows
                        if isinstance(row, dict)
                        and row.get("figure_id")
                        and row.get("accepted_output")
                        and row.get("verdict") == "passed"
                    }
                    unverified = sorted(accepted_figure_ids - passed_figure_ids)
                    if unverified:
                        semantic_issues.append(
                            "figure_fidelity_not_passed:" + ",".join(unverified)
                        )
                elif "figure_fidelity_review.json" not in missing:
                    semantic_issues.append("invalid_figure_fidelity_review")
            elif "figure_fidelity_review.json" not in missing:
                semantic_issues.append("invalid_figure_fidelity_review")
    if stage["id"] == "matrix_outline":
        matrix = read_json(stage_dir / "literature_matrix.json")
        if isinstance(matrix, list):
            rows = matrix
        elif isinstance(matrix, dict):
            rows = matrix.get("papers") or matrix.get("rows") or matrix.get("literature_matrix") or []
        else:
            rows = []
        missing_excerpts = 0
        for row in rows if isinstance(rows, list) else []:
            if not isinstance(row, dict):
                continue
            role = str(row.get("role_after_reading") or row.get("role") or "core").lower()
            if role not in {"core", "supporting"}:
                continue
            missing_excerpts += sum(
                not str(anchor.get("source_excerpt") or "").strip()
                for anchor in row.get("evidence_anchors") or []
                if isinstance(anchor, dict)
            )
        if missing_excerpts:
            semantic_issues.append(
                f"matrix_evidence_source_excerpts_missing:{missing_excerpts}"
            )
    if stage["id"] == "section_drafting":
        candidates = read_json(stage_dir / "figure_candidates.json")
        if isinstance(candidates, dict):
            figures = candidates.get("figures")
        else:
            figures = candidates
        if not isinstance(figures, list) and "figure_candidates.json" not in missing:
            semantic_issues.append("invalid_figure_candidates")
    if stage["id"] == "docx_export":
        # DOCX is only valid when the final audit passed all blocking checks.
        final_scan = read_json(project / "05_final_audit" / "format_scan.json")
        if isinstance(final_scan, dict) and final_scan.get("blocking_issues"):
            semantic_issues.append("final_audit_has_blocking_issues")
        elif not (project / "05_final_audit" / "final_draft.md").exists():
            semantic_issues.append("final_draft_md_missing")
        docx_audit = read_json(project / "05_final_audit" / "docx_audit.json")
        if not isinstance(docx_audit, dict) and "docx_audit.json" not in missing:
            semantic_issues.append("invalid_docx_audit")
        elif isinstance(docx_audit, dict):
            if docx_audit.get("blocking_issues"):
                semantic_issues.append("docx_audit_has_blocking_issues")
            if docx_audit.get("render_qa") != "passed":
                semantic_issues.append("docx_visual_qa_not_passed")
        render_report = read_json(project / "05_final_audit" / "render_qa_report.json")
        if isinstance(render_report, dict):
            if render_report.get("render_status") != "passed":
                semantic_issues.append("docx_render_not_passed")
            if render_report.get("inspection_status") != "passed":
                semantic_issues.append("docx_page_inspection_not_passed")
            if not render_report.get("renderer"):
                semantic_issues.append("docx_renderer_identity_missing")
            rendered_pdf = Path(str(render_report.get("output_pdf") or ""))
            rendered_docx = Path(str(render_report.get("input_docx") or ""))
            expected_pdf = (project / "05_final_audit" / "final_draft.pdf").resolve()
            expected_docx = (project / "05_final_audit" / "final_draft.docx").resolve()
            if not rendered_pdf.is_absolute():
                rendered_pdf = (project / "05_final_audit" / rendered_pdf).resolve()
            if not rendered_docx.is_absolute():
                rendered_docx = (project / "05_final_audit" / rendered_docx).resolve()
            if rendered_pdf != expected_pdf:
                semantic_issues.append("final_pdf_not_canonical_output")
            if rendered_docx != expected_docx:
                semantic_issues.append("final_docx_not_canonical_render_input")
            if not rendered_pdf.exists():
                semantic_issues.append("rendered_pdf_missing")
            elif expected_docx.exists() and rendered_pdf.stat().st_mtime < expected_docx.stat().st_mtime:
                semantic_issues.append("rendered_pdf_older_than_final_docx")
            if not isinstance(render_report.get("page_count"), int) or render_report.get("page_count", 0) < 1:
                semantic_issues.append("final_pdf_page_count_missing")
            page_images = render_report.get("page_images")
            if not isinstance(page_images, list) or len(page_images) != render_report.get("page_count"):
                semantic_issues.append("rendered_page_image_count_mismatch")
                page_images = []
            missing_page_images = []
            for raw_path in page_images:
                page_path = Path(str(raw_path))
                if not page_path.is_absolute():
                    page_path = (project / "05_final_audit" / page_path).resolve()
                if not page_path.exists() or not page_path.is_file():
                    missing_page_images.append(str(raw_path))
            if missing_page_images:
                semantic_issues.append(
                    f"rendered_page_images_missing:{len(missing_page_images)}"
                )
        elif "render_qa_report.json" not in missing:
            semantic_issues.append("invalid_render_qa_report")
    if stage["id"] in {"first_draft", "final_audit"}:
        draft_path = stage_dir / ("first_draft.md" if stage["id"] == "first_draft" else "final_draft.md")
        if draft_path.exists():
            draft_text = draft_path.read_text(encoding="utf-8", errors="ignore")
            import re as _re
            has_image = bool(_re.search(r"!\[[^\]]*\]\(([^)]+)\)", draft_text))
            has_citation = bool(_re.search(r"\[\d+(?:\s*[-,]\s*\d+)*\]", draft_text))
            has_references = bool(_re.search(
                r"^\s*#{1,6}\s*(references|reference list|bibliography|cited literature|参考文献)\s*$",
                draft_text,
                _re.I | _re.M,
            ))
            skip_reason = project / "03_figure_redraw" / "skip_reason.md"
            figures_skipped_with_reason = skip_reason.exists() and bool(skip_reason.read_text(encoding="utf-8", errors="ignore").strip())
            if not has_citation:
                semantic_issues.append("draft_has_no_citation_callouts")
            if not has_references:
                semantic_issues.append("missing_references_section")
        if stage["id"] == "final_audit":
            for floor_issue in comprehensive_delivery_floor_issues(project):
                if floor_issue not in semantic_issues:
                    semantic_issues.append(floor_issue)
            scan = read_json(stage_dir / "format_scan.json")
            if isinstance(scan, dict):
                blockers = scan.get("blocking_issues") or []
                for issue in blockers:
                    if issue not in semantic_issues:
                        semantic_issues.append(issue)
    skip_path = stage_dir / stage.get("skip_anchor", "") if stage.get("skip_anchor") else None
    skipped_by_user = bool(
        skip_path
        and skip_path.exists()
        and skip_path.read_text(encoding="utf-8", errors="ignore").strip()
    )
    complete = not missing and not semantic_issues
    return {
        "id": stage["id"],
        "name": stage["name"],
        "skill": stage["skill"],
        "directory": str(stage_dir),
        "complete": complete,
        "missing": missing,
        "semantic_issues": semantic_issues,
        "confirmed": confirmed,
        "skipped_by_user": skipped_by_user,
    }


def summarize(review_root: Path, project_id: str) -> dict[str, Any]:
    project = review_root / "review-projects" / project_id
    if not project.exists():
        return {
            "project_id": project_id,
            "exists": False,
            "error": f"Project not found: {project}",
            "available_projects": discover_projects(review_root),
        }

    stages = [stage_status(project, stage) for stage in STAGES]
    completed = [s for s in stages if s["complete"]]
    # Skip stages explicitly opted out by the user (skip_reason.md present).
    next_stage = next((s for s in stages if not s["complete"] and not s.get("skipped_by_user")), None)
    workflow_issues = run_record_issues(project, stages)
    return {
        "project_id": project_id,
        "exists": True,
        "project_dir": str(project),
        "completed_stage_ids": [s["id"] for s in completed],
        "next_stage": next_stage,
        "workflow_issues": workflow_issues,
        "stages": stages,
    }


def print_text(summary: dict[str, Any]) -> None:
    if not summary.get("exists"):
        print(f"Project: {summary['project_id']}")
        print(summary["error"])
        if summary.get("available_projects"):
            print("Available projects:")
            for project in summary["available_projects"]:
                print(f"- {project}")
        return

    print(f"Project: {summary['project_id']}")
    print(f"Completed stages: {', '.join(summary['completed_stage_ids']) or 'none'}")
    next_stage = summary.get("next_stage")
    if next_stage:
        print(f"Next skill: {next_stage['skill']}")
        print(f"Next stage: {next_stage['name']}")
        if next_stage["missing"]:
            print("Missing files:")
            for name in next_stage["missing"]:
                print(f"- {name}")
        if next_stage.get("semantic_issues"):
            print("Stage issues:")
            for issue in next_stage["semantic_issues"]:
                print(f"- {issue}")
    else:
        print("Next skill: none")
        print("Status: final audit outputs exist")
    if summary.get("workflow_issues"):
        print("Workflow issues:")
        for issue in summary["workflow_issues"]:
            print(f"- {issue}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Inspect review project workflow status.")
    parser.add_argument("--review-root", default=str(Path(__file__).resolve().parents[3]))
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    parser.add_argument(
        "--require-complete",
        action="store_true",
        help="Return a non-zero exit code unless every core deliverable is complete.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    summary = summarize(Path(args.review_root).resolve(), args.project_id)
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print_text(summary)
    if args.require_complete and (
        not summary.get("exists")
        or summary.get("next_stage") is not None
    ):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
