#!/usr/bin/env python3
"""Summarize the review as three revisitable quality loops.

This is a coordinator, not another release gate.  It turns the many generated
stage reports into one read-only diagnosis of what would most improve the
article next: evidence, manuscript/visual synthesis, or release QA.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "_shared"))
from review_integrity import file_sha256  # noqa: E402


LOOP_ORDER = {"evidence": 0, "manuscript": 1, "release": 2}
EVIDENCE_RISKS = {"evidence_base_depth", "comparison_readiness", "coverage_depth"}
MANUSCRIPT_RISKS = {"manuscript_depth", "section_depth", "source_visual_portfolio"}


def read_json(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def debt(
    debt_id: str,
    loop: str,
    summary: str,
    evidence: list[str],
    action: str,
    severity: str = "blocking",
) -> dict[str, Any]:
    return {
        "debt_id": debt_id,
        "loop": loop,
        "severity": severity,
        "summary": summary,
        "evidence": evidence,
        "recommended_action": action,
    }


def report_issues(path: Path) -> list[str]:
    payload = read_json(path, {})
    if not isinstance(payload, dict):
        return []
    return [str(item) for item in payload.get("blocking_issues") or []]


def render_integrity_issues(project: Path, render: Any) -> list[str]:
    if not isinstance(render, dict):
        return ["render_qa_report.json is missing or invalid"]
    stage = project / "05_final_audit"
    expected_docx = (stage / "final_draft.docx").resolve()
    expected_pdf = (stage / "final_draft.pdf").resolve()

    def resolve(raw: Any) -> Path:
        path = Path(str(raw or ""))
        return path.resolve() if path.is_absolute() else (stage / path).resolve()

    issues: list[str] = []
    input_docx = resolve(render.get("input_docx"))
    output_pdf = resolve(render.get("output_pdf"))
    if input_docx != expected_docx:
        issues.append("render input is not the canonical final DOCX")
    if output_pdf != expected_pdf:
        issues.append("render output is not the canonical final PDF")
    if render.get("render_status") != "passed":
        issues.append("DOCX rendering did not pass")
    if render.get("inspection_status") != "passed":
        issues.append("rendered-page inspection did not pass")
    if expected_docx.is_file() and str(render.get("input_docx_sha256") or "") != file_sha256(expected_docx):
        issues.append("render report is not bound to the current final DOCX")
    if expected_pdf.is_file() and str(render.get("output_pdf_sha256") or "") != file_sha256(expected_pdf):
        issues.append("render report is not bound to the current final PDF")
    page_count = render.get("page_count")
    page_images = render.get("page_images")
    if not isinstance(page_count, int) or page_count < 1:
        issues.append("rendered page count is missing")
    if not isinstance(page_images, list) or len(page_images) != page_count:
        issues.append("rendered page images do not match the reported page count")
        page_images = []
    missing_images = [str(raw) for raw in page_images if not resolve(raw).is_file()]
    if missing_images:
        issues.append(f"{len(missing_images)} rendered page image(s) are missing")
    artifacts = render.get("page_artifacts")
    inspections = render.get("page_inspections")
    if not isinstance(artifacts, list) or len(artifacts) != page_count:
        issues.append("rendered-page hash receipts are missing")
        artifacts = []
    hashes = {
        int(row["page_number"]): str(row.get("sha256") or "")
        for row in artifacts
        if isinstance(row, dict) and isinstance(row.get("page_number"), int)
    }
    for row in artifacts:
        if not isinstance(row, dict) or not isinstance(row.get("page_number"), int):
            continue
        if file_sha256(resolve(row.get("path"))) != str(row.get("sha256") or ""):
            issues.append(f"rendered page {row['page_number']} hash is stale")
    if not isinstance(inspections, list) or len(inspections) != page_count:
        issues.append("page-specific visual inspection receipts are missing")
        inspections = []
    for row in inspections:
        if not isinstance(row, dict) or not isinstance(row.get("page_number"), int):
            continue
        number = int(row["page_number"])
        if str(row.get("page_sha256") or "") != hashes.get(number, ""):
            issues.append(f"page {number} inspection is bound to a different image")
        if row.get("verdict") != "passed" or len(str(row.get("observation") or "").strip()) < 30:
            issues.append(f"page {number} inspection is incomplete or needs revision")
    if expected_docx.is_file() and expected_pdf.is_file():
        if expected_pdf.stat().st_mtime < expected_docx.stat().st_mtime:
            issues.append("final PDF is older than the final DOCX")
    return issues


def risk_debts(project: Path) -> list[dict[str, Any]]:
    reports = [
        project / "01_matrix_outline" / "quality_gate_prewrite.json",
        project / "05_final_audit" / "quality_gate_release.json",
    ]
    latest: dict[str, dict[str, Any]] = {}
    for path in reports:
        payload = read_json(path, {})
        if not isinstance(payload, dict):
            continue
        for risk in payload.get("risk_signals") or []:
            if isinstance(risk, dict) and risk.get("risk_id"):
                latest[str(risk["risk_id"])] = risk
    debts = []
    for risk_id, risk in latest.items():
        loop = "evidence" if risk_id in EVIDENCE_RISKS else "manuscript"
        if risk_id not in EVIDENCE_RISKS | MANUSCRIPT_RISKS:
            loop = "manuscript"
        action = (
            "Reopen discovery and full-text reading for the named coverage and comparison gaps; do not freeze the current corpus."
            if loop == "evidence"
            else "Revise argument units, prose, tables, and figures together around the reader need described by this risk."
        )
        debts.append(
            debt(
                risk_id,
                loop,
                str(risk.get("summary") or risk_id),
                [str(item) for item in risk.get("details") or []],
                action,
                severity="advisory",
            )
        )
    return debts


def blueprint_debts(review_root: Path, project: Path) -> list[dict[str, Any]]:
    path = project / "01_matrix_outline" / "section_blueprint.json"
    blueprint = read_json(path, {})
    if not isinstance(blueprint, dict) or not blueprint:
        return [
            debt(
                "blueprint_missing",
                "manuscript",
                "No shared argument map exists yet.",
                [str(path)],
                "Create a topic-specific argument map from the evidence ledger before drafting prose.",
            )
        ]

    debts: list[dict[str, Any]] = []
    sections = [row for row in blueprint.get("sections") or [] if isinstance(row, dict)]
    generated_prompts = sum(
        1
        for section in sections
        for claim in section.get("review_claims") or []
        if isinstance(claim, dict)
        and str(claim.get("status") or "") == "editorial_prompt_requires_evidence_authoring"
    )
    if generated_prompts:
        debts.append(
            debt(
                "blueprint_not_semantically_authored",
                "manuscript",
                "The blueprint still contains initializer prompts instead of evidence-backed argument units.",
                [f"generated_editorial_prompts={generated_prompts}", f"blueprint_status={blueprint.get('status')!r}"],
                "Read the assigned sources, replace prompts with bounded argument units, then set the blueprint status to ready_for_drafting.",
            )
        )

    topic = str(blueprint.get("review_topic") or "").casefold()
    blueprint_text = json.dumps(blueprint, ensure_ascii=False).casefold()
    manifest_path = review_root / "skills" / "review-section-blueprint" / "references" / "rule_packs.json"
    if not manifest_path.exists():
        manifest_path = Path(__file__).resolve().parents[2] / "review-section-blueprint" / "references" / "rule_packs.json"
    manifest = read_json(manifest_path, {})
    selected_pack = str(blueprint.get("rule_pack") or "general")
    leaked: list[str] = []
    packs = manifest.get("rule_packs") if isinstance(manifest, dict) else {}
    if isinstance(packs, dict):
        for name, config in packs.items():
            if str(name) == selected_pack or not isinstance(config, dict):
                continue
            for signal in config.get("topic_signals") or []:
                signal_text = str(signal).casefold()
                if signal_text and signal_text not in topic and signal_text in blueprint_text:
                    leaked.append(str(signal))
    if leaked:
        debts.append(
            debt(
                "blueprint_domain_leakage",
                "manuscript",
                "The argument map contains terminology from an unrelated domain rule pack.",
                [f"unexpected_terms={', '.join(sorted(set(leaked)))}"],
                "Regenerate the blueprint from the topic contract and evidence; do not repair the contaminated prose downstream.",
            )
        )
    if not str(blueprint.get("review_topic") or "").strip():
        debts.append(
            debt(
                "blueprint_topic_missing",
                "manuscript",
                "The blueprint is not bound to the declared review topic.",
                ["section_blueprint.review_topic is empty"],
                "Regenerate the blueprint using the topic contract as the authoritative topic source.",
            )
        )
    return debts


def artifact_debts(project: Path) -> list[dict[str, Any]]:
    debts: list[dict[str, Any]] = []
    matrix_path = project / "01_matrix_outline" / "literature_matrix.json"
    if not matrix_path.exists():
        debts.append(
            debt(
                "evidence_ledger_missing",
                "evidence",
                "No source-located evidence ledger exists yet.",
                [str(matrix_path)],
                "Screen and deep-read sources, then record source-located evidence and comparison fields in the canonical matrix.",
            )
        )
    matrix_issues = report_issues(project / "01_matrix_outline" / "matrix_validation.json")
    if matrix_issues:
        debts.append(
            debt(
                "evidence_integrity",
                "evidence",
                "The evidence ledger has unresolved provenance or source-depth problems.",
                matrix_issues,
                "Repair or replace the affected evidence anchors by reopening the lawful full text.",
            )
        )

    draft_path = project / "02_section_drafting" / "section_drafts.json"
    if not draft_path.exists():
        debts.append(
            debt(
                "manuscript_missing",
                "manuscript",
                "No evidence-linked section draft exists yet.",
                [str(draft_path)],
                "Author complete argument units from the evidence-backed blueprint, developing prose and visual assets together.",
            )
        )
    draft_report = read_json(project / "02_section_drafting" / "section_draft_validation.json", {})
    if isinstance(draft_report, dict) and draft_report.get("blocking_issues"):
        debts.append(
            debt(
                "draft_not_ready",
                "manuscript",
                "The current prose does not yet realize the planned review.",
                [str(item) for item in draft_report.get("blocking_issues") or []],
                "Expand by answering missing reader questions with new evidence-backed argument units, not filler or a fixed paragraph template.",
            )
        )
    usage = draft_report.get("evidence_usage_by_paper") if isinstance(draft_report, dict) else []
    overloaded = [
        f"{row.get('paper_id')}:{row.get('paragraphs_per_used_anchor')} paragraphs/anchor"
        for row in usage or []
        if isinstance(row, dict) and float(row.get("paragraphs_per_used_anchor") or 0) >= 4
    ]
    if overloaded:
        debts.append(
            debt(
                "evidence_reuse_concentration",
                "evidence",
                "Too much of the manuscript depends on a very small number of evidence anchors.",
                overloaded,
                "Deep-read more passages and add corroborating or conflicting studies before expanding those arguments.",
                severity="advisory",
            )
        )

    inventory = read_json(project / "02_section_drafting" / "paper_figure_inventory.json", {})
    source_candidates_payload = read_json(project / "02_section_drafting" / "figure_candidates.json", [])
    source_candidates = (
        source_candidates_payload.get("figures")
        if isinstance(source_candidates_payload, dict)
        else source_candidates_payload
    )
    source_candidates = [row for row in source_candidates or [] if isinstance(row, dict)]
    source_selected = [
        row
        for row in source_candidates
        if row.get("manuscript_selected") is True
        or str(row.get("editorial_status") or "").lower() in {"selected", "adapted", "combined"}
    ]
    source_manifest = read_json(project / "03_figure_redraw" / "redrawn_figure_manifest.json", {})
    source_prepared = [
        row
        for row in (source_manifest.get("figures") or [])
        if isinstance(row, dict)
        and row.get("status") == "source_verified"
        and row.get("verification_status") == "passed"
        and isinstance(row.get("reuse_rights"), dict)
        and row["reuse_rights"].get("status") == "verified"
        and row["reuse_rights"].get("third_party_material_checked") is True
        and row["reuse_rights"].get("adaptation") == "unchanged"
        and str(row["reuse_rights"].get("license_url_or_permission_record") or "").strip()
        and str(row["reuse_rights"].get("attribution_text") or "").strip()
    ] if isinstance(source_manifest, dict) else []
    candidate_count = int(inventory.get("candidate_count") or 0) if isinstance(inventory, dict) else 0
    contract = read_json(project / "00_discovery" / "topic_contract.json", {})
    if isinstance(contract, dict) and str(contract.get("review_profile") or "").lower() == "comprehensive":
        if len(source_prepared) < 3:
            debts.append(
                debt(
                    "source_visual_portfolio",
                    "manuscript",
                    "The comprehensive article has not yet prepared three lawful source-paper figures for real reader tasks.",
                    [
                        f"inventory_candidates={candidate_count}",
                        f"editorially_selected={len(source_selected)}",
                        f"verified_source_figures={len(source_prepared)}",
                    ],
                    "Select useful source figures before drafting around them; verify licence, full panels, attribution, and placement. If the corpus lacks lawful choices, return to evidence acquisition.",
                )
            )

    table_manifest = read_json(project / "02_section_drafting" / "method_comparison_table_manifest.json", {})
    final_scan = read_json(project / "05_final_audit" / "format_scan.json", {})
    if isinstance(table_manifest, dict) and table_manifest:
        table_count = int(final_scan.get("markdown_table_count") or 0) if isinstance(final_scan, dict) else 0
        if table_count == 0:
            debts.append(
                debt(
                    "generated_table_not_in_manuscript",
                    "manuscript",
                    "A comparison table branch exists but did not reach the manuscript.",
                    [f"table_manifest_status={table_manifest.get('status')!r}", "manuscript_table_count=0"],
                    "Either verify and insert the table where it answers a reader question, or remove the dangling table reference and redesign the comparison.",
                )
            )

    release_issues = report_issues(project / "05_final_audit" / "format_scan.json")
    if release_issues:
        debts.append(
            debt(
                "release_integrity",
                "release",
                "The assembled manuscript has unresolved release-level integrity problems.",
                release_issues,
                "Return each issue to its source artifact, revise there, then rebuild and audit the document.",
            )
        )
    docx = read_json(project / "05_final_audit" / "docx_audit.json", {})
    render = read_json(project / "05_final_audit" / "render_qa_report.json", {})
    final_draft = project / "05_final_audit" / "final_draft.md"
    final_docx = project / "05_final_audit" / "final_draft.docx"
    missing_release = [
        str(path)
        for path in (
            final_draft,
            final_docx,
            project / "05_final_audit" / "final_draft.pdf",
            project / "05_final_audit" / "docx_audit.json",
            project / "05_final_audit" / "render_qa_report.json",
        )
        if not path.exists()
    ]
    if missing_release:
        debts.append(
            debt(
                "release_outputs_missing",
                "release",
                "The audited manuscript and DOCX have not both been produced.",
                missing_release,
                "Assemble, challenge, export, render, and inspect the manuscript after evidence and manuscript debts are resolved.",
            )
        )
    if isinstance(docx, dict) and docx.get("blocking_issues"):
        debts.append(
            debt(
                "docx_integrity",
                "release",
                "The exported DOCX has structural problems.",
                [str(item) for item in docx.get("blocking_issues") or []],
                "Fix export inputs or styles, re-export, and visually inspect the new rendering.",
            )
        )
    if isinstance(render, dict) and render and str(render.get("inspection_status") or "") != "passed":
        debts.append(
            debt(
                "render_not_inspected",
                "release",
                "Rendered pages have not received a completed visual inspection.",
                [f"inspection_status={render.get('inspection_status')!r}"],
                "Inspect every rendered page and record page-specific findings before release.",
            )
        )
    render_issues = render_integrity_issues(project, render)
    if not missing_release and render_issues:
        debts.append(
            debt(
                "render_provenance",
                "release",
                "The PDF or page-inspection record is not tied to the final DOCX.",
                render_issues,
                "Render the canonical final DOCX, rasterize every PDF page, inspect the images, and keep the generated report.",
            )
        )
    return debts


def deduplicate(debts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in debts:
        debt_id = str(item.get("debt_id") or "")
        if debt_id and debt_id not in seen:
            seen.add(debt_id)
            result.append(item)
    return result


def assess(review_root: Path, project_id: str) -> dict[str, Any]:
    project = review_root / "review-projects" / project_id
    if not project.is_dir():
        raise SystemExit(f"Project not found: {project}")
    debts = deduplicate(
        risk_debts(project) + blueprint_debts(review_root, project) + artifact_debts(project)
    )
    blocking = [item for item in debts if item["severity"] == "blocking"]
    # Quality debt guides attention even when it is advisory.  Completion is
    # still determined only by the genuinely blocking subset below.
    candidates = list(debts)
    candidates.sort(key=lambda item: (LOOP_ORDER[item["loop"]], item["debt_id"]))
    active_loop = candidates[0]["loop"] if candidates else "complete"
    next_actions = []
    for item in candidates:
        action = item["recommended_action"]
        if action not in next_actions:
            next_actions.append(action)
        if len(next_actions) == 3:
            break
    return {
        "project_id": project_id,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "operating_model": "evidence_manuscript_release_loops",
        "active_loop": active_loop,
        "release_ready": not blocking,
        "quality_debt_count": len(debts),
        "blocking_debt_count": len(blocking),
        "quality_debts": debts,
        "next_actions": next_actions,
        "note": "Generated diagnosis. It is not an approval record and cannot narrow the topic contract.",
    }


def write_markdown(path: Path, state: dict[str, Any]) -> None:
    lines = [
        "# Review Cycle",
        "",
        f"- Active loop: `{state['active_loop']}`",
        f"- Release ready: `{str(state['release_ready']).lower()}`",
        f"- Blocking debts: {state['blocking_debt_count']}",
        f"- Total debts: {state['quality_debt_count']}",
        "",
        "## Quality debt",
        "",
    ]
    for item in state["quality_debts"]:
        lines.extend(
            [
                f"### {item['debt_id']} ({item['loop']}, {item['severity']})",
                "",
                item["summary"],
                "",
                *[f"- {value}" for value in item["evidence"]],
                "",
                f"Next: {item['recommended_action']}",
                "",
            ]
        )
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Choose the next review action from whole-product quality debt.")
    parser.add_argument("--review-root", default=str(Path(__file__).resolve().parents[3]))
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--write", action="store_true", help="Write review_state.json and review_state.md at project root.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = Path(args.review_root).resolve()
    state = assess(root, args.project_id)
    if args.write:
        project = root / "review-projects" / args.project_id
        write_json(project / "review_state.json", state)
        write_markdown(project / "review_state.md", state)
    print(json.dumps(state, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
