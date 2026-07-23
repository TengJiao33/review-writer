#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "_shared"))
from review_integrity import (  # noqa: E402
    file_sha256,
    input_artifact_issues,
    metadata_snapshot_issues,
)


REFERENCE_HEADING_RE = re.compile(
    r"^\s*#{1,6}\s*(references|reference list|bibliography|cited literature)\s*$",
    re.I | re.M,
)
NONCANONICAL_BACKMATTER_RE = re.compile(
    r"^\s*\*\*(?:references?|reference list|bibliography|figure descriptions?)\*\*\s*:?.*$",
    re.I | re.M,
)
REFERENCE_CALLOUT_RE = re.compile(r"\[(\d+(?:\s*[-,]\s*\d+)*)\]")
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
    "source_figure_count": 3,
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


def expand_reference_callouts(text: str) -> set[int]:
    refs: set[int] = set()
    for match in REFERENCE_CALLOUT_RE.finditer(text or ""):
        for part in re.split(r"\s*,\s*", match.group(1)):
            if "-" in part:
                left, right = [piece.strip() for piece in part.split("-", 1)]
                if left.isdigit() and right.isdigit() and int(left) <= int(right):
                    refs.update(range(int(left), int(right) + 1))
            elif part.strip().isdigit():
                refs.add(int(part.strip()))
    return refs


def verified_source_figure_count(
    project: Path,
    image_paths: list[str],
    cited_paper_ids: set[str],
) -> int:
    report = read_json(project / "05_final_audit" / "figure_insertion_report.json")
    if not isinstance(report, dict):
        report = read_json(project / "04_first_draft" / "figure_insertion_report.json")
    manifest = read_json(project / "03_figure_redraw" / "redrawn_figure_manifest.json")
    inserted = report.get("inserted") if isinstance(report, dict) else []
    figures = manifest.get("figures") if isinstance(manifest, dict) else []
    by_id = {
        str(row.get("figure_id")): row
        for row in figures or []
        if isinstance(row, dict) and row.get("figure_id")
    }
    count = 0
    counted_ids: set[str] = set()
    counted_paths: set[str] = set()
    for row in inserted or []:
        if not isinstance(row, dict) or row.get("mode") != "source_verified":
            continue
        source = by_id.get(str(row.get("figure_id") or ""))
        rights = source.get("reuse_rights") if isinstance(source, dict) and isinstance(source.get("reuse_rights"), dict) else {}
        figure_id = str(row.get("figure_id") or "")
        inserted_path = str(row.get("inserted_path") or "")
        if (
            isinstance(source, dict)
            and source.get("status") == "source_verified"
            and source.get("verification_status") == "passed"
            and str(source.get("paper_id") or "") in cited_paper_ids
            and str(source.get("source_label") or "").strip()
            and rights.get("status") == "verified"
            and str(rights.get("license_url_or_permission_record") or "").strip()
            and rights.get("third_party_material_checked") is True
            and rights.get("adaptation") == "unchanged"
            and str(rights.get("attribution_text") or "").strip()
            and inserted_path in image_paths
            and figure_id not in counted_ids
            and inserted_path not in counted_paths
        ):
            count += 1
            counted_ids.add(figure_id)
            counted_paths.add(inserted_path)
    return count


def comprehensive_delivery_floor_issues(project: Path) -> list[str]:
    contract = read_json(project / "00_discovery" / "topic_contract.json")
    if not isinstance(contract, dict) or str(contract.get("review_profile") or "").lower() != "comprehensive":
        return []
    draft = project / "05_final_audit" / "final_draft.md"
    if not draft.exists():
        return []
    scan = read_json(project / "05_final_audit" / "format_scan.json")
    scan_metrics = scan.get("delivery_metrics") if isinstance(scan, dict) else None
    if isinstance(scan_metrics, dict) and all(
        isinstance(scan_metrics.get(metric), int) for metric in COMPREHENSIVE_DELIVERY_FLOOR
    ):
        return [
            f"comprehensive_delivery_floor:{metric}:"
            f"{scan_metrics.get('verified_reference_count', scan_metrics[metric]) if metric == 'reference_count' else scan_metrics[metric]}/{minimum}"
            for metric, minimum in COMPREHENSIVE_DELIVERY_FLOOR.items()
            if (
                scan_metrics.get("verified_reference_count", scan_metrics[metric])
                if metric == "reference_count"
                else scan_metrics[metric]
            ) < minimum
        ]
    text = draft.read_text(encoding="utf-8", errors="ignore")
    references = REFERENCE_HEADING_RE.search(text)
    pseudo = NONCANONICAL_BACKMATTER_RE.search(text)
    boundaries = [match.start() for match in (references, pseudo) if match]
    body = text[: min(boundaries)] if boundaries else text
    reference_tail = text[references.end():] if references else ""
    listed = {
        int(match.group(1) or match.group(2))
        for match in REFERENCE_ITEM_RE.finditer(reference_tail)
    }
    called = expand_reference_callouts(body)
    citations = read_json(project / "04_first_draft" / "citations.json")
    cited_paper_ids = {
        str(row.get("paper_id"))
        for row in (citations.get("reference_list") if isinstance(citations, dict) else []) or []
        if isinstance(row, dict)
        and str(row.get("ref_num") or "").isdigit()
        and int(row["ref_num"]) in called
        and row.get("paper_id")
    }
    image_paths = [match.group(1) for match in IMAGE_RE.finditer(body)]
    metrics = {
        "word_like_count": len(WORD_RE.findall(body)),
        "reference_count": len(called & listed),
        "table_count": len(TABLE_SEPARATOR_RE.findall(body)),
        "figure_count": len(image_paths),
        "source_figure_count": verified_source_figure_count(
            project, image_paths, cited_paper_ids
        ),
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
    topic_contract = read_json(project / "00_discovery" / "topic_contract.json")
    comprehensive = (
        isinstance(topic_contract, dict)
        and str(topic_contract.get("review_profile") or "").lower() == "comprehensive"
    )
    current_integrity_contract = (
        isinstance(topic_contract, dict)
        and int(topic_contract.get("workflow_contract_version") or 0) >= 2
    )
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
            validation_inputs = {
                "discovery": [
                    project / "00_discovery" / "topic_contract.json",
                    project / "00_discovery" / "selected_discovery_results.json",
                ],
                "matrix_outline": [
                    project / "01_matrix_outline" / "literature_matrix.json",
                ],
                "section_blueprint": [
                    project / "01_matrix_outline" / "section_blueprint.json",
                    project / "01_matrix_outline" / "literature_matrix.json",
                ],
                "section_drafting": [
                    project / "02_section_drafting" / "section_drafts.json",
                    project / "02_section_drafting" / "figure_candidates.json",
                    project / "01_matrix_outline" / "section_blueprint.json",
                    project / "01_matrix_outline" / "literature_matrix.json",
                ],
                "first_draft": [
                    project / "02_section_drafting" / "section_drafts.json",
                    project / "01_matrix_outline" / "literature_matrix.json",
                ],
            }.get(stage["id"], [])
            manuscript = project / "02_section_drafting" / "manuscript.md"
            if stage["id"] in {"section_drafting", "first_draft"} and manuscript.exists():
                validation_inputs.append(manuscript)
            for issue in input_artifact_issues(
                validation,
                project,
                validation_inputs,
                require_receipts=current_integrity_contract,
            ):
                semantic_issues.append(f"{stage['id']}:{issue}")
    if stage["id"] == "discovery" and current_integrity_contract:
        selected = read_json(project / "00_discovery" / "selected_discovery_results.json")
        rows: list[Any] = []
        if isinstance(selected, list):
            rows = selected
        elif isinstance(selected, dict):
            for key in ("local_papers", "selected_papers", "papers"):
                if isinstance(selected.get(key), list):
                    rows.extend(selected[key])
        paper_ids = [
            str(row.get("paper_id"))
            for row in rows
            if isinstance(row, dict) and row.get("paper_id") and row.get("keep") is not False
        ]
        semantic_issues.extend(metadata_snapshot_issues(project.parents[1], project, paper_ids))
    if stage["id"] == "figure_redraw":
        contract = topic_contract
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

        if comprehensive and skip_active:
            semantic_issues.append("comprehensive_source_figure_portfolio_cannot_be_skipped")
        if not comprehensive and (skip_active or (not source_selected and not selected_visuals)):
            # Figure count is editorial. No selected asset means there is no
            # preparation sub-workflow to complete.
            missing = []
        elif usable_originals and not comprehensive:
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
                    if comprehensive:
                        inventory = read_json(
                            project / "02_section_drafting" / "paper_figure_inventory.json"
                        )
                        inventory_rows = inventory.get("candidates") if isinstance(inventory, dict) else []
                        inventory_by_id = {
                            str(item.get("inventory_candidate_id")): item
                            for item in inventory_rows or []
                            if isinstance(item, dict) and item.get("inventory_candidate_id")
                        }
                        reader_jobs: set[str] = set()
                        for figure in figures:
                            if not isinstance(figure, dict) or figure.get("status") != "source_verified":
                                continue
                            figure_id = str(figure.get("figure_id") or "unknown")
                            candidate_id = str(figure.get("inventory_candidate_id") or "")
                            candidate = inventory_by_id.get(candidate_id)
                            if not isinstance(candidate, dict):
                                semantic_issues.append(
                                    f"source_figure_not_bound_to_inventory:{figure_id}"
                                )
                                continue
                            if any(
                                figure.get(key) != candidate.get(key)
                                for key in (
                                    "paper_id",
                                    "source_label",
                                    "source_caption_text",
                                    "source_pdf_sha256",
                                    "source_page_index",
                                    "source_bbox",
                                )
                            ):
                                semantic_issues.append(
                                    f"source_figure_inventory_mismatch:{figure_id}"
                                )
                            source_type = str(figure.get("source_type") or "").strip().lower()
                            source_label = str(figure.get("source_label") or "").strip()
                            source_page_index = figure.get("source_page_index")
                            source_bbox = figure.get("source_bbox")
                            if (
                                source_type not in {"image", "chart"}
                                or not re.match(
                                    r"^(?:fig(?:ure)?|scheme)\s*[A-Za-z0-9]",
                                    source_label,
                                    re.I,
                                )
                                or not isinstance(source_page_index, int)
                                or source_page_index < 0
                                or not isinstance(source_bbox, list)
                                or len(source_bbox) != 4
                                or not all(
                                    isinstance(value, (int, float)) for value in source_bbox
                                )
                            ):
                                semantic_issues.append(
                                    f"source_figure_not_a_bound_non_table_figure:{figure_id}"
                                )
                            job = re.sub(r"\s+", " ", str(figure.get("reader_job") or "")).casefold().strip()
                            if not job or job in reader_jobs:
                                semantic_issues.append(
                                    f"source_figure_reader_job_missing_or_duplicate:{figure_id}"
                                )
                            reader_jobs.add(job)
                            if not str(figure.get("manuscript_callout") or "").strip():
                                semantic_issues.append(
                                    f"source_figure_manuscript_callout_missing:{figure_id}"
                                )
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
            if expected_docx.exists() and str(render_report.get("input_docx_sha256") or "") != file_sha256(expected_docx):
                semantic_issues.append("render_report_docx_hash_mismatch")
            if rendered_pdf.exists() and str(render_report.get("output_pdf_sha256") or "") != file_sha256(rendered_pdf):
                semantic_issues.append("render_report_pdf_hash_mismatch")
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
            page_artifacts = render_report.get("page_artifacts")
            if not isinstance(page_artifacts, list) or len(page_artifacts) != render_report.get("page_count"):
                semantic_issues.append("rendered_page_hash_receipts_missing")
                page_artifacts = []
            page_hashes: dict[int, str] = {}
            for artifact in page_artifacts:
                if not isinstance(artifact, dict) or not isinstance(artifact.get("page_number"), int):
                    continue
                page_number = int(artifact["page_number"])
                page_path = Path(str(artifact.get("path") or ""))
                if not page_path.is_absolute():
                    page_path = (project / "05_final_audit" / page_path).resolve()
                actual_hash = file_sha256(page_path)
                recorded_hash = str(artifact.get("sha256") or "")
                if not actual_hash or actual_hash != recorded_hash:
                    semantic_issues.append(f"rendered_page_hash_mismatch:{page_number}")
                page_hashes[page_number] = recorded_hash
            inspections = render_report.get("page_inspections")
            if not isinstance(inspections, list) or len(inspections) != render_report.get("page_count"):
                semantic_issues.append("page_specific_inspection_receipts_missing")
                inspections = []
            inspected_numbers: set[int] = set()
            for inspection in inspections:
                if not isinstance(inspection, dict) or not isinstance(inspection.get("page_number"), int):
                    continue
                page_number = int(inspection["page_number"])
                inspected_numbers.add(page_number)
                if str(inspection.get("page_sha256") or "") != page_hashes.get(page_number, ""):
                    semantic_issues.append(f"page_inspection_hash_mismatch:{page_number}")
                observation = str(inspection.get("observation") or "").strip()
                if len(observation) < 30 or len(set(observation.casefold().split())) < 5:
                    semantic_issues.append(f"page_inspection_observation_missing:{page_number}")
                if inspection.get("verdict") != "passed":
                    semantic_issues.append(f"page_inspection_needs_revision:{page_number}")
            expected_pages = set(range(1, int(render_report.get("page_count") or 0) + 1))
            if inspected_numbers != expected_pages:
                semantic_issues.append("page_inspection_coverage_mismatch")
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
                audit_inputs = [
                    project / "05_final_audit" / "final_draft.md",
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
                for issue in input_artifact_issues(
                    scan, project, audit_inputs, require_receipts=current_integrity_contract
                ):
                    semantic_issues.append(f"final_audit:{issue}")
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
